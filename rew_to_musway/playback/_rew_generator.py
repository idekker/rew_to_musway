"""_rew_generator.py - REW generator playback strategy."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import questionary
from rich.console import Console

from ._base import check_spl_level

if TYPE_CHECKING:
    from rew_to_musway.config import LevelsConfig, PlaybackConfig, TimerConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

GENERATOR_WARMUP = 3.0  # seconds to let generator stabilise


class REWGeneratorPlayback:
    """Playback strategy using REW's signal generator.

    Controls the generator via aiorew (signal selection, level, play/stop)
    and configures the output device/channel — either from the config or
    interactively when not specified.
    """

    def __init__(
        self,
        rew: REWController,
        playback_config: PlaybackConfig,
        levels_config: LevelsConfig,
        timer_config: TimerConfig,
    ) -> None:
        self._rew = rew
        self._playback_config = playback_config
        self._levels_config = levels_config
        self._device_configured = False
        self._spl_check_timeout = timer_config.spl_check_timeout

    async def _configure_output(self) -> None:
        """Select output device and channel, prompting if not configured."""
        device = self._playback_config.output_device
        channel = self._playback_config.output_channel

        # --- Device ---
        if device is None:
            devices = await self._rew.get_output_devices()
            device = await questionary.select(
                "Select REW output device:",
                choices=devices,
            ).ask_async()
            if device is None:
                msg = "No output device selected"
                raise RuntimeError(msg)

        await self._rew.set_output_device_name(device)
        console.print(f"  Output device: [bold]{device}[/bold]")

        # --- Channel ---
        if channel is None:
            channels = await self._rew.get_output_channels()
            channel = await questionary.select(
                "Select output channel:",
                choices=channels,
            ).ask_async()
            if channel is None:
                msg = "No output channel selected"
                raise RuntimeError(msg)

        await self._rew.set_output_channel(channel)
        console.print(f"  Output channel: [bold]{channel}[/bold]")

    async def start_noise(self) -> None:
        """Configure output device, start generator, verify SPL level."""
        if not self._device_configured:
            await self._configure_output()
            self._device_configured = True

        console.print(
            f"\nStarting REW generator "
            f"({self._playback_config.generator_signal}, "
            f"{self._playback_config.generator_level} dBFS)..."
        )
        await self._rew.generator_play()

        # Wait for generator to stabilise
        console.print(
            f"  Waiting {GENERATOR_WARMUP:.0f}s for generator to stabilise..."
        )
        await asyncio.sleep(GENERATOR_WARMUP)

        await check_spl_level(self._rew, self._levels_config, self._spl_check_timeout)

    async def stop_noise(self) -> None:
        """Stop the REW signal generator."""
        console.print("Stopping generator...")
        await self._rew.generator_stop()
        logger.info("Generator stopped")
