"""_musway.py - MuswayAmp backend for Musway app calibration.

Implements ``AmpBackend`` by buffering DSP state and flushing it to
Musway preset files on ``apply()``.  Immediate operations (solo, mute)
use UI automation to control Musway app, others use timed prompts to
instruct the user.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from musway import Musway
from rew_to_musway.amp._preset_amp import _MuswayPresetAmp

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig, MuswayConfig

logger = logging.getLogger(__name__)

_MUSWAY_CALL_TIMEOUT = 30  # seconds


class MuswayCallError(Exception):
    """Raised when a musway call fails or times out."""


class MuswayAmp(_MuswayPresetAmp):
    """AmpBackend implementation for Musway.

    DSP state changes are buffered and flushed as Musway preset files
    on ``apply()``. Some immediate operations directly control Musway app,
    others instruct the user via timed prompts.
    """

    def __init__(
        self,
        *,
        config: MuswayConfig,
        channels: list[ChannelConfig],
        session_dir: Path,
    ) -> None:
        super().__init__(
            default_preset_path=Path(config.default_preset_path),
            session_dir=session_dir,
            channels=channels,
            action_timeout=config.timers.action_timeout,
        )
        self._musway = Musway()
        self._musway_path = Path(config.exe_path)

    async def _run(self, func: object, *args: object, **kwargs: object) -> object:
        """Run a sync musway call in a thread with timeout."""
        func_name = getattr(func, "__name__", str(func))
        logger.debug("musway call: %s(%s)", func_name, args)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=_MUSWAY_CALL_TIMEOUT,
            )
        except TimeoutError:
            logger.critical(
                "musway call TIMED OUT after %ds: %s(%s) — "
                "the worker thread likely crashed",
                _MUSWAY_CALL_TIMEOUT,
                func_name,
                args,
            )
            msg = (
                f"Musway call '{func_name}' did not return within "
                f"{_MUSWAY_CALL_TIMEOUT}s — the application may have crashed"
            )
            raise MuswayCallError(msg) from None
        except Exception:
            logger.exception("musway call failed: %s(%s)", func_name, args)
            raise
        else:
            logger.debug("musway call OK: %s", func_name)
            return result

    # ------------------------------------------------------------------
    # Abstract hook implementations
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Musway (launches if needed)."""
        logger.info("Connecting to Musway: %s", self._musway_path)
        await self._run(self._musway.connect, path=self._musway_path)
        logger.info("Musway connected.")

    async def _deliver_preset(self, out_path: Path) -> None:
        """Load the written preset into the Musway app."""
        abs_path = out_path.resolve()  # noqa: ASYNC240
        await self._run(self._musway.load_preset, path=abs_path)

    async def _do_solo_channel(self, channel: int, msg: str) -> None:  # noqa: ARG002
        """Solo a channel via Musway UI automation."""
        for c in self._channels:
            if c.number == channel:
                await self._run(
                    self._musway.set_channel_mute, channel=c.number, mute=False
                )
            else:
                await self._run(
                    self._musway.set_channel_mute, channel=c.number, mute=True
                )

    async def _do_solo_channels(self, channels: list[int], msg: str) -> None:  # noqa: ARG002
        """Solo multiple channels via Musway UI automation."""
        for c in self._channels:
            if c.number in channels:
                await self._run(
                    self._musway.set_channel_mute, channel=c.number, mute=False
                )
            else:
                await self._run(
                    self._musway.set_channel_mute, channel=c.number, mute=True
                )

    async def _do_unmute_all_channels(self, msg: str) -> None:  # noqa: ARG002
        """Unmute all channels via Musway UI automation."""
        for c in self._channels:
            await self._run(self._musway.set_channel_mute, channel=c.number, mute=False)

    async def _do_master_mute(self, muted: bool, msg: str) -> None:  # noqa: ARG002, FBT001
        """Mute/unmute master via Musway UI automation."""
        await self._run(self._musway.set_master_mute, mute=muted)
