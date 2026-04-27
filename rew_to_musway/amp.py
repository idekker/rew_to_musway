"""amp.py - Amp backend protocol and Tunest PC implementation.

The ``AmpBackend`` protocol defines the interface that calibration code
depends on.  DSP state mutations (levels, EQ filters, crossovers) are
buffered in memory and flushed when ``apply()`` is called.  Immediate
operations (solo, mute, master mute) take effect right away.

``TunestPCAmp`` implements the protocol via COM/win32gui automation
through ``tunest_pc``.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from tunest_pc import FilterSlope, FilterType, TunestPC

from .filters import export_filters_json

if TYPE_CHECKING:
    from aiorew import FilterSetting

    from .config import ChannelConfig, Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Buffered state
# ---------------------------------------------------------------------------


@dataclass
class _CrossoverState:
    filter_type: str  # config enum value, e.g. "linkwitz_riley"
    frequency: int
    slope: int


@dataclass
class _ChannelBuffer:
    """Pending DSP changes for a single channel."""

    level: float | None = None
    eq_filters: list[FilterSetting] | None = None
    eq_reset: bool = False
    highpass: _CrossoverState | None = None
    lowpass: _CrossoverState | None = None


@dataclass
class _AmpBuffer:
    """Pending DSP changes across all channels."""

    channels: dict[int, _ChannelBuffer] = field(default_factory=dict)

    def channel(self, ch: int) -> _ChannelBuffer:
        if ch not in self.channels:
            self.channels[ch] = _ChannelBuffer()
        return self.channels[ch]

    @property
    def is_empty(self) -> bool:
        return not self.channels

    def clear(self) -> None:
        self.channels.clear()


class PresetPhase(Enum):
    """Calibration phase for preset file naming."""

    INITIAL = auto()
    EQ = auto()
    FINETUNE = auto()
    VERIFICATION = auto()


# ---------------------------------------------------------------------------
# AmpBackend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AmpBackend(Protocol):
    """Unified interface for DSP amp control.

    Buffer operations accumulate state; ``apply()`` flushes them.
    Immediate operations take effect right away.
    """

    async def connect(self) -> None: ...

    def set_phase(self, phase: PresetPhase, iteration: int = 0) -> None: ...

    # -- Buffer operations (no side effects until apply) -------------------

    async def set_channel_level(self, channel: int, level_db: float) -> None: ...

    async def set_eq_filters(
        self, channel: int, filters: list[FilterSetting]
    ) -> None: ...

    async def set_crossover(self, channel_cfg: ChannelConfig) -> None: ...

    async def reset_eq(self, channel: int) -> None: ...

    # -- Immediate operations ----------------------------------------------

    async def solo_channel(self, channel: int) -> None: ...

    async def solo_channels(self, channels: list[int]) -> None:
        """Unmute *channels*, mute all others."""
        ...

    async def mute_all(self) -> None: ...

    async def set_master_mute(self, muted: bool) -> None: ...  # noqa: FBT001

    async def apply(self) -> None: ...

    # -- Compound operations -----------------------------------------------

    async def restore_eq(self) -> None: ...


# ---------------------------------------------------------------------------
# Mapping helpers (Tunest PC specific)
# ---------------------------------------------------------------------------

_FILTER_TYPE_MAP = {
    "butterworth": FilterType.BUTTERWORTH,
    "bessel": FilterType.BESSEL,
    "linkwitz_riley": FilterType.LINKWITZ_RILEY,
}

_SLOPE_MAP = {
    12: FilterSlope.DB12,
    24: FilterSlope.DB24,
    36: FilterSlope.DB36,
    48: FilterSlope.DB48,
}

# ---------------------------------------------------------------------------
# TunestPCAmp
# ---------------------------------------------------------------------------

_TUNEST_CALL_TIMEOUT = 30  # seconds — generous for UI automation


class TunestCallError(Exception):
    """Raised when a tunest_pc call fails or times out."""


class TunestPCAmp:
    """AmpBackend implementation via Tunest PC COM automation.

    DSP state changes are buffered and flushed on ``apply()``.
    Immediate operations (solo, mute) go straight to COM.
    """

    def __init__(self, config: Config) -> None:
        if config.tunest_pc is None:
            msg = "TunestPCAmp requires 'tunest_pc' config section"
            raise TypeError(msg)
        self._config = config
        self._tunest_pc_config = config.tunest_pc
        self._tunest = TunestPC()
        self._all_channels = config.channels
        self._buffer = _AmpBuffer()
        self._levels: dict[int, float] = {}

    async def _run(self, func: object, *args: object, **kwargs: object) -> object:
        """Run a sync tunest_pc call in a thread with timeout."""
        func_name = getattr(func, "__name__", str(func))
        logger.debug("tunest_pc call: %s(%s)", func_name, args)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=_TUNEST_CALL_TIMEOUT,
            )
        except TimeoutError:
            logger.critical(
                "tunest_pc call TIMED OUT after %ds: %s(%s) — "
                "the worker thread likely crashed",
                _TUNEST_CALL_TIMEOUT,
                func_name,
                args,
            )
            msg = (
                f"Tunest PC call '{func_name}' did not return within "
                f"{_TUNEST_CALL_TIMEOUT}s — the application may have crashed"
            )
            raise TunestCallError(msg) from None
        except Exception:
            logger.exception("tunest_pc call failed: %s(%s)", func_name, args)
            raise
        else:
            logger.debug("tunest_pc call OK: %s", func_name)
            return result

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Tunest PC (launches if needed)."""
        logger.info(
            "Connecting to Tunest PC: %s (model=%s)",
            self._tunest_pc_config.exe_path,
            self._tunest_pc_config.model,
        )
        await self._run(
            self._tunest.connect,
            exe_path=self._tunest_pc_config.exe_path,
            model=self._tunest_pc_config.model,
            launch_if_needed=True,
            timeout=20.0,
        )
        logger.info("Tunest PC connected.")

    def set_phase(self, phase: PresetPhase, iteration: int = 0) -> None:
        logger.debug(
            "Setting phase to %s%s",
            phase,
            f", iteration: {iteration}" if iteration > 0 else "",
        )

    # ------------------------------------------------------------------
    # Buffer operations
    # ------------------------------------------------------------------

    async def set_channel_level(self, channel: int, level_db: float) -> None:
        logger.debug("Buffer CH%d level: %s dB", channel, level_db)
        self._buffer.channel(channel).level = level_db
        self._levels[channel] = level_db

    async def set_eq_filters(self, channel: int, filters: list[FilterSetting]) -> None:
        logger.debug("Buffer CH%d EQ filters: %d filters", channel, len(filters))
        buf = self._buffer.channel(channel)
        buf.eq_filters = filters
        buf.eq_reset = False

    async def set_crossover(self, channel_cfg: ChannelConfig) -> None:
        ch = channel_cfg.number
        logger.debug("Buffer CH%d crossover", ch)
        buf = self._buffer.channel(ch)
        if channel_cfg.highpass is not None:
            buf.highpass = _CrossoverState(
                filter_type=channel_cfg.highpass.type.value,
                frequency=channel_cfg.highpass.frequency,
                slope=channel_cfg.highpass.slope,
            )
        if channel_cfg.lowpass is not None:
            buf.lowpass = _CrossoverState(
                filter_type=channel_cfg.lowpass.type.value,
                frequency=channel_cfg.lowpass.frequency,
                slope=channel_cfg.lowpass.slope,
            )

    async def reset_eq(self, channel: int) -> None:
        logger.debug("Buffer CH%d reset EQ", channel)
        buf = self._buffer.channel(channel)
        buf.eq_reset = True
        buf.eq_filters = None

    # ------------------------------------------------------------------
    # Immediate operations
    # ------------------------------------------------------------------

    async def set_master_mute(self, muted: bool) -> None:  # noqa: FBT001
        logger.debug("Master mute: %s", muted)
        await self._run(self._tunest.set_master_mute, muted)

    async def solo_channel(self, channel: int) -> None:
        """Unmute *channel*, mute all others."""
        logger.debug("Solo CH%d", channel)
        for ch in self._all_channels:
            await self._run(
                self._tunest.set_channel_mute, ch.number, ch.number != channel
            )

    async def solo_channels(self, channels: list[int]) -> None:
        """Unmute *channels*, mute all others."""
        unmute_set = set(channels)
        logger.debug("Solo channels: %s", channels)
        for ch in self._all_channels:
            await self._run(
                self._tunest.set_channel_mute, ch.number, ch.number not in unmute_set
            )

    async def mute_all(self) -> None:
        """Mute all configured channels."""
        logger.debug("Muting all channels")
        for ch in self._all_channels:
            await self._run(self._tunest.set_channel_mute, ch.number, True)  # noqa: FBT003

    async def unmute_all(self) -> None:
        """Unmute all configured channels."""
        logger.debug("Unmuting all channels")
        for ch in self._all_channels:
            await self._run(self._tunest.set_channel_mute, ch.number, False)  # noqa: FBT003

    async def set_channel_mute(self, channel: int, *, muted: bool) -> None:
        """Mute or unmute a specific channel."""
        logger.debug("CH%d mute: %s", channel, muted)
        await self._run(self._tunest.set_channel_mute, channel, muted)

    # ------------------------------------------------------------------
    # Apply — flush buffer to hardware
    # ------------------------------------------------------------------

    async def apply(self) -> None:
        """Flush all buffered changes to Tunest PC via COM."""
        if self._buffer.is_empty:
            logger.debug("Apply: buffer empty, nothing to do")
            return

        logger.info("Applying buffered changes to Tunest PC")

        for ch_num, buf in self._buffer.channels.items():
            # Levels
            if buf.level is not None:
                logger.debug("Apply CH%d level: %s dB", ch_num, buf.level)
                await self._run(self._tunest.set_channel_level, ch_num, buf.level)

            # EQ reset
            if buf.eq_reset:
                logger.debug("Apply CH%d reset EQ", ch_num)
                await self._run(self._tunest.select_channel, ch_num)
                await self._run(self._tunest.reset_eq, selected_only=True)

            # EQ filters (via JSON export + import)
            if buf.eq_filters is not None:
                logger.debug("Apply CH%d EQ filters", ch_num)
                await self._apply_eq_filters(ch_num, buf.eq_filters)

            # Crossovers
            if buf.highpass is not None:
                await self._apply_highpass(ch_num, buf.highpass)
            if buf.lowpass is not None:
                await self._apply_lowpass(ch_num, buf.lowpass)

        self._buffer.clear()

    async def _apply_eq_filters(
        self, channel: int, filters: list[FilterSetting]
    ) -> None:
        """Export filters to JSON and import via Tunest PC."""
        ch_cfg = next((c for c in self._all_channels if c.number == channel), None)
        ch_name = ch_cfg.name if ch_cfg else f"CH{channel}"

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            tmp_path = tmp.name

        export_filters_json(
            filters,
            Path(tmp_path),
            model=self._config.eq.model,
            channel_name=ch_name,
        )
        await self._run(self._tunest.import_eq, channel, tmp_path)

    async def _apply_highpass(self, channel: int, state: _CrossoverState) -> None:
        ft = _FILTER_TYPE_MAP.get(state.filter_type, FilterType.BUTTERWORTH)
        slope = _SLOPE_MAP.get(state.slope, FilterSlope.DB24)
        await self._run(
            self._tunest.set_highpass, channel, ft, str(state.frequency), slope
        )

    async def _apply_lowpass(self, channel: int, state: _CrossoverState) -> None:
        ft = _FILTER_TYPE_MAP.get(state.filter_type, FilterType.BUTTERWORTH)
        slope = _SLOPE_MAP.get(state.slope, FilterSlope.DB24)
        await self._run(
            self._tunest.set_lowpass, channel, ft, str(state.frequency), slope
        )

    # ------------------------------------------------------------------
    # Legacy compound operations (still used by existing calibration code)
    # ------------------------------------------------------------------

    async def bypass_eq(self) -> None:
        logger.debug("Bypass EQ")
        await self._run(self._tunest.bypass_eq)

    async def restore_eq(self) -> None:
        logger.debug("Restore EQ")
        await self._run(self._tunest.restore_eq)

    async def set_master_volume(self, value: float) -> None:
        """Set master volume (legacy, immediate)."""
        logger.debug("Master volume: %s dB", value)
        await self._run(self._tunest.set_master_volume, value)

    async def get_master_volume(self) -> float:
        """Get master volume (legacy, immediate)."""
        return await self._run(self._tunest.get_master_volume)

    async def configure_filters(self, channel_cfg: ChannelConfig) -> None:
        """Set highpass/lowpass filters for a channel (immediate, legacy)."""
        ch = channel_cfg.number
        logger.debug("Configuring filters for CH%d (%s)", ch, channel_cfg.name)

        if channel_cfg.highpass is not None:
            ft = _FILTER_TYPE_MAP[channel_cfg.highpass.type.value]
            slope = _SLOPE_MAP.get(channel_cfg.highpass.slope, FilterSlope.DB24)
            await self._run(
                self._tunest.set_highpass,
                ch,
                ft,
                str(channel_cfg.highpass.frequency),
                slope,
            )
        else:
            await self._run(
                self._tunest.set_highpass,
                ch,
                FilterType.BUTTERWORTH,
                "20",
                FilterSlope.OFF,
            )

        if channel_cfg.lowpass is not None:
            ft = _FILTER_TYPE_MAP[channel_cfg.lowpass.type.value]
            slope = _SLOPE_MAP.get(channel_cfg.lowpass.slope, FilterSlope.DB24)
            await self._run(
                self._tunest.set_lowpass,
                ch,
                ft,
                str(channel_cfg.lowpass.frequency),
                slope,
            )
        else:
            await self._run(
                self._tunest.set_lowpass,
                ch,
                FilterType.BUTTERWORTH,
                "20000",
                FilterSlope.OFF,
            )

    async def configure_all_filters(self) -> None:
        """Configure filters for all channels from config."""
        for ch_cfg in self._all_channels:
            await self.configure_filters(ch_cfg)

    async def import_eq(self, channel: int, json_path: str) -> None:
        """Import an EQ preset JSON file for *channel* (legacy)."""
        logger.info("Import EQ CH%d from %s", channel, json_path)
        await self._run(self._tunest.import_eq, channel, json_path)

    async def prepare_channel(self, channel_cfg: ChannelConfig) -> None:
        """Prepare a channel for measurement (legacy compound)."""
        ch = channel_cfg.number
        logger.info("Preparing CH%d (%s) for measurement", ch, channel_cfg.name)
        await self._run(self._tunest.select_channel, ch)
        await self._run(self._tunest.reset_eq, selected_only=True)
        await self.configure_filters(channel_cfg)
        await self.solo_channel(ch)

    async def prepare_for_level_measurement(self) -> None:
        """Prepare amp for level measurement phase (legacy compound)."""
        logger.info("Preparing amp for level measurement")
        await self.bypass_eq()
        await self.configure_all_filters()
        for ch in self._all_channels:
            await self._run(self._tunest.set_channel_level, ch.number, 0.0)
        await self.unmute_all()
        await self.set_master_mute(muted=False)


# ---------------------------------------------------------------------------
# Backward compatibility alias
# ---------------------------------------------------------------------------

AmpController = TunestPCAmp
