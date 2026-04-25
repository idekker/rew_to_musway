"""amp.py - Thin wrapper around tunest_pc for calibration operations.

All public methods are async (using asyncio.to_thread for the sync
tunest_pc calls) so they integrate cleanly with the async calibration loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from tunest_pc import FilterSlope, FilterType, TunestPC

if TYPE_CHECKING:
    from .config import ChannelConfig, Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapping helpers
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
# AmpController
# ---------------------------------------------------------------------------


_TUNEST_CALL_TIMEOUT = 30  # seconds — generous for UI automation


class TunestCallError(Exception):
    """Raised when a tunest_pc call fails or times out."""


class AmpController:
    """Calibration-oriented controller for the Musway amp via Tunest PC."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._tunest = TunestPC()
        self._all_channels = config.channels

    async def _run(self, func: object, *args: object, **kwargs: object) -> object:
        """Run a sync tunest_pc call in a thread with timeout.

        Wraps the call with logging and a timeout so that COM/ctypes
        crashes in the worker thread do not hang the program forever.

        Raises
        ------
        TunestCallError
            If the call times out (likely a hard crash in the worker thread).

        """
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
            self._config.tunest_pc.exe_path,
            self._config.tunest_pc.model,
        )
        await self._run(
            self._tunest.connect,
            exe_path=self._config.tunest_pc.exe_path,
            model=self._config.tunest_pc.model,
            launch_if_needed=True,
            timeout=20.0,
        )
        logger.info("Tunest PC connected.")

    # ------------------------------------------------------------------
    # Master controls
    # ------------------------------------------------------------------

    async def set_master_mute(self, muted: bool) -> None:  # noqa: FBT001
        logger.debug("Master mute: %s", muted)
        await self._run(self._tunest.set_master_mute, muted)

    async def get_master_mute(self) -> bool:
        return await self._run(self._tunest.get_master_mute)

    async def set_master_volume(self, value: float) -> None:
        logger.debug("Master volume: %s dB", value)
        await self._run(self._tunest.set_master_volume, value)

    async def get_master_volume(self) -> float:
        return await self._run(self._tunest.get_master_volume)

    # ------------------------------------------------------------------
    # Channel controls
    # ------------------------------------------------------------------

    async def set_channel_mute(self, channel: int, muted: bool) -> None:  # noqa: FBT001
        logger.debug("CH%d mute: %s", channel, muted)
        await self._run(self._tunest.set_channel_mute, channel, muted)

    async def set_channel_level(self, channel: int, level_db: float) -> None:
        logger.debug("CH%d level: %s dB", channel, level_db)
        await self._run(self._tunest.set_channel_level, channel, level_db)

    async def get_channel_level(self, channel: int) -> float:
        return await self._run(self._tunest.get_channel_level, channel)

    # ------------------------------------------------------------------
    # Mute helpers
    # ------------------------------------------------------------------

    async def mute_all(self) -> None:
        """Mute all configured channels."""
        logger.debug("Muting all channels")
        for ch in self._all_channels:
            await self.set_channel_mute(ch.number, muted=True)

    async def unmute_all(self) -> None:
        """Unmute all configured channels."""
        logger.debug("Unmuting all channels")
        for ch in self._all_channels:
            await self.set_channel_mute(ch.number, muted=False)

    async def solo_channel(self, channel: int) -> None:
        """Unmute *channel*, mute all others."""
        logger.debug("Solo CH%d", channel)
        for ch in self._all_channels:
            await self.set_channel_mute(ch.number, muted=(ch.number != channel))

    # ------------------------------------------------------------------
    # Filter configuration
    # ------------------------------------------------------------------

    async def configure_filters(self, channel_cfg: ChannelConfig) -> None:
        """Set highpass/lowpass filters for a channel from config."""
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

    # ------------------------------------------------------------------
    # EQ operations
    # ------------------------------------------------------------------

    async def bypass_eq(self) -> None:
        logger.debug("Bypass EQ")
        await self._run(self._tunest.bypass_eq)

    async def restore_eq(self) -> None:
        logger.debug("Restore EQ")
        await self._run(self._tunest.restore_eq)

    async def reset_eq(self, *, selected_only: bool = True) -> None:
        logger.debug("Reset EQ (selected_only=%s)", selected_only)
        await self._run(self._tunest.reset_eq, selected_only=selected_only)

    async def import_eq(self, channel: int, json_path: str) -> None:
        """Import an EQ preset JSON file for *channel*."""
        logger.info("Import EQ CH%d from %s", channel, json_path)
        await self._run(self._tunest.import_eq, channel, json_path)

    # ------------------------------------------------------------------
    # Compound operations
    # ------------------------------------------------------------------

    async def prepare_channel(self, channel_cfg: ChannelConfig) -> None:
        """Prepare a channel for measurement.

        - Select channel, flatten EQ
        - Configure filters from config
        - Unmute this channel, mute all others
        """
        ch = channel_cfg.number
        logger.info("Preparing CH%d (%s) for measurement", ch, channel_cfg.name)

        # Reset EQ for this channel
        await self._run(self._tunest._select_channel, ch)  # noqa: SLF001
        await self.reset_eq(selected_only=True)

        # Configure filters
        await self.configure_filters(channel_cfg)

        # Solo this channel
        await self.solo_channel(ch)

    async def prepare_for_level_measurement(self) -> None:
        """Prepare amp for level measurement phase.

        - Bypass EQ
        - Configure all filters
        - Set all channel levels to 0 dB
        - Unmute all
        """
        logger.info("Preparing amp for level measurement")
        await self.bypass_eq()
        await self.configure_all_filters()
        for ch in self._all_channels:
            await self.set_channel_level(ch.number, 0.0)
        await self.unmute_all()
        await self.set_master_mute(muted=False)
