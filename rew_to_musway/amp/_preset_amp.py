"""_preset_amp.py - Abstract base class for Musway preset file backends.

``_MuswayPresetAmp`` holds all logic that is common to ``ManualAmp`` and
``MuswayAmp``: buffering DSP changes, building and writing Musway preset
files on ``apply()``, and constructing the user-facing messages for
immediate operations (solo, mute).

Concrete subclasses supply five abstract hooks:

* ``connect()`` — establish a hardware/software connection (or no-op).
* ``_deliver_preset(out_path)`` — hand the written preset to the user or
  to an automation layer after ``apply()`` has written it to disk.
* ``_do_solo_channel(channel, msg)`` — act on a solo-one request.
* ``_do_solo_channels(channels, msg)`` — act on a solo-many request.
* ``_do_master_mute(muted, msg)`` — act on a master-mute toggle.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from musway_preset import FilterType, MuswayPreset, Slope
from rew_to_musway.amp._amp_backend import PresetPhase
from rew_to_musway.prompt import timed_prompt

if TYPE_CHECKING:
    from pathlib import Path

    from aiorew import FilterSetting
    from rew_to_musway.config import ChannelConfig, FilterConfig

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
# Buffered channel state
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
# Abstract base class
# ---------------------------------------------------------------------------


class _MuswayPresetAmp(ABC):
    """Abstract base for backends that flush DSP changes as Musway preset files.

    Subclasses implement five abstract hooks to supply the
    delivery/automation behaviour that differs between backends.
    """

    def __init__(
        self,
        *,
        default_preset_path: Path,
        session_dir: Path,
        channels: list[ChannelConfig],
        action_timeout: float = 10.0,
    ) -> None:
        self._default_preset_path = default_preset_path
        self._session_dir = session_dir
        self._channels = channels
        self._action_timeout = action_timeout

        self._buffer = _Buffer()
        self._levels: dict[int, float] = {}

        # Last written preset (cumulative chain)
        self._last_preset_path: Path | None = None

        self._phase: PresetPhase = PresetPhase.INITIAL
        self._iteration: int = 0

    # ------------------------------------------------------------------
    # Abstract hooks
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection (or no-op for manual mode)."""

    @abstractmethod
    async def _deliver_preset(self, out_path: Path) -> None:
        """Deliver the written preset file to the user or automation layer."""

    @abstractmethod
    async def _do_solo_channel(self, channel: int, msg: str) -> None:
        """Perform the backend-specific solo-one action."""

    @abstractmethod
    async def _do_solo_channels(self, channels: list[int], msg: str) -> None:
        """Perform the backend-specific solo-many action."""

    @abstractmethod
    async def _do_unmute_all_channels(self, msg: str) -> None:
        """Perform the backend-specific unmute-all-channels action."""

    @abstractmethod
    async def _do_master_mute(self, muted: bool, msg: str) -> None:  # noqa: FBT001
        """Perform the backend-specific master-mute action."""

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    def set_phase(self, phase: PresetPhase, iteration: int = 0) -> None:
        logger.debug(
            "Setting phase to %s%s",
            phase,
            f", iteration: {iteration}" if iteration > 0 else "",
        )
        self._phase = phase
        self._iteration = iteration

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
        """Solo a channel — log the action then delegate to subclass hook."""
        ch_cfg = next((c for c in self._channels if c.number == channel), None)
        name = ch_cfg.name if ch_cfg else f"CH{channel}"
        msg = f"Solo channel '{name}': unmute CH{channel}, mute all others"
        logger.info(msg)
        await self._do_solo_channel(channel, msg)

    async def solo_channels(self, channels: list[int]) -> None:
        """Solo multiple channels — log the action then delegate to subclass hook."""
        names: list[str] = []
        for ch_num in channels:
            ch_cfg = next((c for c in self._channels if c.number == ch_num), None)
            names.append(ch_cfg.name if ch_cfg else f"CH{ch_num}")
        ch_list = ", ".join(
            f"CH{n} ({nm})" for n, nm in zip(channels, names, strict=True)
        )
        msg = f"Unmute channels: {ch_list} — mute all others"
        logger.info(msg)
        await self._do_solo_channels(channels, msg)

    async def unmute_all_channels(self) -> None:
        """Prompt user to unmute all channels."""
        msg = "Unmute all channels"
        logger.info(msg)
        await self._do_unmute_all_channels(msg)

    async def set_master_mute(self, muted: bool) -> None:  # noqa: FBT001
        """Mute/unmute master — log the action then delegate to subclass hook."""
        action = "Mute" if muted else "Unmute"
        msg = f"{action} master"
        logger.info(msg)
        await self._do_master_mute(muted, msg)

    # ------------------------------------------------------------------
    # Apply (template method)
    # ------------------------------------------------------------------

    async def apply(self) -> Path | None:
        """Flush buffered changes: write preset file, then deliver it.

        Preset filenames are auto-determined from the current phase.

        Returns
        -------
        Path to the written preset file, or ``None`` if the buffer was empty.

        """
        if self._buffer.is_empty:
            logger.debug("Apply: buffer empty, nothing to do")
            return None

        phase = self._phase
        iteration = self._iteration

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
        logger.info("Wrote preset: %s", out_path)

        self._buffer.clear()

        await self._deliver_preset(out_path)

        return out_path

    # ------------------------------------------------------------------
    # Compound operations
    # ------------------------------------------------------------------

    async def restore_eq(self) -> None:
        """Prompt user to ensure the latest preset with EQ is loaded."""
        if not self._last_preset_path:
            msg = "Ensure correct preset is loaded in Musway software"
            logger.info(msg)
            await timed_prompt(msg, self._action_timeout)
