"""manual_amp.py - ManualAmp backend for manual mode calibration.

Implements ``AmpBackend`` by buffering DSP state and flushing it to
Musway preset files on ``apply()``.  Immediate operations (solo, mute)
use timed prompts to instruct the user.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

import win32clipboard  # pyright: ignore[reportMissingModuleSource]

from musway_preset import FilterType, MuswayPreset, Slope

from .prompt import timed_prompt

if TYPE_CHECKING:
    from pathlib import Path

    from aiorew import FilterSetting

    from .config import ChannelConfig, FilterConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config -> musway_preset type mapping
# ---------------------------------------------------------------------------

_FILTER_TYPE_MAP: dict[str, FilterType] = {
    "butterworth": FilterType.BUTTERWORTH,
    "bessel": FilterType.BESSEL,
    "linkwitz_riley": FilterType.LINKWITZ_RILEY,
}

_SLOPE_MAP: dict[int, Slope] = {
    6: Slope.DB_6,
    12: Slope.DB_12,
    18: Slope.DB_18,
    24: Slope.DB_24,
    30: Slope.DB_30,
    36: Slope.DB_36,
    42: Slope.DB_42,
    48: Slope.DB_48,
}


def _map_filter_type(cfg_type: FilterConfig) -> FilterType:
    """Convert a config FilterType (str enum) to musway_preset FilterType."""
    return _FILTER_TYPE_MAP[cfg_type.type.value]


def _map_slope(cfg_type: FilterConfig) -> Slope:
    """Convert a config slope (int dB) to musway_preset Slope."""
    return _SLOPE_MAP.get(cfg_type.slope, Slope.OFF)


# ---------------------------------------------------------------------------
# Preset naming
# ---------------------------------------------------------------------------


class PresetPhase(Enum):
    """Calibration phase for preset file naming."""

    INITIAL = auto()
    EQ = auto()
    FINETUNE = auto()
    VERIFICATION = auto()


def preset_filename(phase: PresetPhase, *, iteration: int = 0) -> str:
    """Return the preset filename for *phase*."""
    if phase is PresetPhase.INITIAL:
        return "preset_initial.txt"
    if phase is PresetPhase.EQ:
        return "preset_eq.txt"
    if phase is PresetPhase.FINETUNE:
        return f"preset_finetune_{iteration}.txt"
    # VERIFICATION
    return "preset_verification.txt"


_PHASE_AUTO_ORDER: list[PresetPhase] = [
    PresetPhase.INITIAL,
    PresetPhase.EQ,
]

# ---------------------------------------------------------------------------
# Clipboard helper
# ---------------------------------------------------------------------------

_CF_UNICODETEXT = 13


def _copy_to_clipboard(text: str) -> None:
    """Copy *text* to the Windows clipboard."""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(_CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


# ---------------------------------------------------------------------------
# Buffered channel state (reused from amp.py pattern)
# ---------------------------------------------------------------------------


class _ChannelBuffer:
    """Pending DSP changes for a single channel."""

    def __init__(self) -> None:
        self.level: float | None = None
        self.eq_filters: list[FilterSetting] | None = None
        self.eq_reset: bool = False
        self.crossover_cfg: ChannelConfig | None = None


class _Buffer:
    """Pending DSP changes across all channels."""

    def __init__(self) -> None:
        self._channels: dict[int, _ChannelBuffer] = {}

    def channel(self, ch: int) -> _ChannelBuffer:
        if ch not in self._channels:
            self._channels[ch] = _ChannelBuffer()
        return self._channels[ch]

    @property
    def channels(self) -> dict[int, _ChannelBuffer]:
        return self._channels

    @property
    def is_empty(self) -> bool:
        return not self._channels

    def clear(self) -> None:
        self._channels.clear()


# ---------------------------------------------------------------------------
# ManualAmp
# ---------------------------------------------------------------------------

_CHANNEL_COUNT = 6


class ManualAmp:
    """AmpBackend implementation for manual mode.

    DSP state changes are buffered and flushed as Musway preset files
    on ``apply()``.  Immediate operations instruct the user via timed
    prompts.
    """

    def __init__(
        self,
        *,
        default_preset_path: Path,
        session_dir: Path,
        channels: list[ChannelConfig],
        action_timeout: float = 10.0,
        preset_load_timeout: float = 30.0,
    ) -> None:
        self._default_preset_path = default_preset_path
        self._session_dir = session_dir
        self._channels = channels
        self._action_timeout = action_timeout
        self._preset_load_timeout = preset_load_timeout

        self._buffer = _Buffer()
        self._levels: dict[int, float] = {}

        # Last written preset (cumulative chain)
        self._last_preset_path: Path | None = None

        # Auto-incrementing phase tracking
        self._apply_count: int = 0
        self._finetune_count: int = 0

    # ------------------------------------------------------------------
    # Buffer operations
    # ------------------------------------------------------------------

    async def set_channel_level(self, channel: int, level_db: float) -> None:
        """Buffer a channel level change."""
        logger.debug("Buffer CH%d level: %s dB", channel, level_db)
        self._buffer.channel(channel).level = level_db
        self._levels[channel] = level_db

    async def set_eq_filters(self, channel: int, filters: list[FilterSetting]) -> None:
        """Buffer EQ filters for a channel."""
        logger.debug("Buffer CH%d EQ filters: %d filters", channel, len(filters))
        buf = self._buffer.channel(channel)
        buf.eq_filters = filters
        buf.eq_reset = False

    async def set_crossover(self, channel_cfg: ChannelConfig) -> None:
        """Buffer crossover configuration for a channel."""
        ch = channel_cfg.number
        logger.debug("Buffer CH%d crossover", ch)
        self._buffer.channel(ch).crossover_cfg = channel_cfg

    async def reset_eq(self, channel: int) -> None:
        """Buffer an EQ reset for a channel."""
        logger.debug("Buffer CH%d reset EQ", channel)
        buf = self._buffer.channel(channel)
        buf.eq_reset = True
        buf.eq_filters = None

    # ------------------------------------------------------------------
    # Immediate operations
    # ------------------------------------------------------------------

    async def solo_channel(self, channel: int) -> None:
        """Prompt user to solo a channel."""
        ch_cfg = next((c for c in self._channels if c.number == channel), None)
        name = ch_cfg.name if ch_cfg else f"CH{channel}"
        msg = f"Solo channel '{name}': unmute CH{channel}, mute all others"
        logger.info(msg)
        await timed_prompt(msg, self._action_timeout)

    async def solo_channels(self, channels: list[int]) -> None:
        """Prompt user to unmute multiple channels, mute all others."""
        names: list[str] = []
        for ch_num in channels:
            ch_cfg = next((c for c in self._channels if c.number == ch_num), None)
            names.append(ch_cfg.name if ch_cfg else f"CH{ch_num}")
        ch_list = ", ".join(
            f"CH{n} ({nm})" for n, nm in zip(channels, names, strict=True)
        )
        msg = f"Unmute channels: {ch_list} — mute all others"
        logger.info(msg)
        await timed_prompt(msg, self._action_timeout)

    async def mute_all(self) -> None:
        """Prompt user to mute all channels."""
        msg = "Mute all channels"
        logger.info(msg)
        await timed_prompt(msg, self._action_timeout)

    async def set_master_mute(self, muted: bool) -> None:  # noqa: FBT001
        """Prompt user to mute/unmute master."""
        action = "Mute" if muted else "Unmute"
        msg = f"{action} master"
        logger.info(msg)
        await timed_prompt(msg, self._action_timeout)

    async def apply(self) -> Path | None:
        """Flush buffered changes: write preset, copy path, prompt user.

        Preset filenames are auto-determined from the apply sequence:
        first apply → ``preset_initial.txt``, second → ``preset_eq.txt``,
        subsequent → ``preset_finetune_N.txt``.

        Returns
        -------
        Path to the written preset file, or ``None`` if buffer was empty.

        """
        if self._buffer.is_empty:
            logger.debug("Apply: buffer empty, nothing to do")
            return None

        # Determine phase and filename
        phase, iteration = self._next_phase()

        # Load base preset (cumulative chain)
        base = self._last_preset_path or self._default_preset_path
        preset = MuswayPreset.load(base)

        # Unmute master
        preset.set_master_volume(0)

        # Apply buffered changes
        for ch_num, buf in self._buffer.channels.items():
            if buf.level is not None:
                preset.set_channel_level(ch_num, buf.level)

            if buf.eq_reset:
                preset.reset_eq(ch_num)

            if buf.eq_filters is not None:
                preset.set_eq_filters(ch_num, buf.eq_filters)

            if buf.crossover_cfg is not None:
                cfg = buf.crossover_cfg
                if cfg.highpass is not None:
                    preset.set_highpass(
                        ch_num,
                        _map_filter_type(cfg.highpass),
                        cfg.highpass.frequency,
                        _map_slope(cfg.highpass),
                    )
                else:
                    preset.set_highpass(
                        ch_num,
                        FilterType.BUTTERWORTH,
                        20,
                        Slope.OFF,
                    )
                if cfg.lowpass is not None:
                    preset.set_lowpass(
                        ch_num,
                        _map_filter_type(cfg.lowpass),
                        cfg.lowpass.frequency,
                        _map_slope(cfg.lowpass),
                    )
                else:
                    preset.set_lowpass(
                        ch_num,
                        FilterType.BUTTERWORTH,
                        20000,
                        Slope.OFF,
                    )

        # Write preset
        filename = preset_filename(phase, iteration=iteration)
        out_path = self._session_dir / filename
        self._session_dir.mkdir(parents=True, exist_ok=True)
        preset.write(out_path)
        self._last_preset_path = out_path
        self._apply_count += 1
        logger.info("Wrote preset: %s", out_path)

        self._buffer.clear()

        # Clipboard + prompt
        abs_path = str(out_path.resolve())
        _copy_to_clipboard(abs_path)
        msg = (
            f"Load preset in Musway software (path copied to clipboard):\n{abs_path}"
            "\nAfter loading, mute all channels before continuing."
        )
        await timed_prompt(msg, self._preset_load_timeout)

        return out_path

    def _next_phase(self) -> tuple[PresetPhase, int]:
        """Determine the next preset phase from the apply sequence."""
        if self._apply_count < len(_PHASE_AUTO_ORDER):
            return _PHASE_AUTO_ORDER[self._apply_count], 0
        self._finetune_count += 1
        return PresetPhase.FINETUNE, self._finetune_count

    # ------------------------------------------------------------------
    # Compound operations
    # ------------------------------------------------------------------

    async def restore_eq(self) -> None:
        """Prompt user to ensure the latest preset with EQ is loaded."""
        preset_name = (
            self._last_preset_path.name if self._last_preset_path else "latest preset"
        )
        msg = f"Ensure preset '{preset_name}' is loaded in Musway software"
        logger.info(msg)
        await timed_prompt(msg, self._action_timeout)

    # ------------------------------------------------------------------
    # Connection (no-op for manual mode)
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """No-op — manual mode has no hardware connection."""
