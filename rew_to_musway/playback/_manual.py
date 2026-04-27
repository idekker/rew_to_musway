"""_manual.py - Manual playback strategy (user controls noise externally)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.console import Console

from rew_to_musway.prompt import timed_prompt

from ._base import check_spl_level, wait_for_enter

if TYPE_CHECKING:
    from rew_to_musway.config import LevelsConfig, PlaybackConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()


class ManualPlayback:
    """Playback strategy where the user manages noise playback manually.

    The program prompts the user to start/stop noise (e.g. via USB stick
    on the in-car infotainment system) and verifies the SPL level.
    """

    def __init__(
        self,
        rew: REWController,
        levels_config: LevelsConfig,
        playback_config: PlaybackConfig,
    ) -> None:
        self._rew = rew
        self._levels_config = levels_config
        self._start_noise_timeout = playback_config.start_noise_timeout
        self._spl_check_timeout = playback_config.spl_check_timeout

    async def start_noise(self) -> None:
        """Prompt user to start noise, then verify SPL level."""
        await timed_prompt(
            "Please start playing pink noise on the infotainment system",
            self._start_noise_timeout,
        )
        logger.info("User confirmed noise is playing (manual mode)")

        await check_spl_level(self._rew, self._levels_config, self._spl_check_timeout)

    async def stop_noise(self) -> None:
        """Prompt user to stop noise."""
        console.print("\n[bold]Please stop playing pink noise.[/bold]")
        console.print("Press [bold]Enter[/bold] when stopped...")
        await wait_for_enter()
        logger.info("User confirmed noise is stopped (manual mode)")
