"""_manual.py - Manual playback strategy (user controls noise externally)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.console import Console

from ._base import SPLCheckSkippedError, check_spl_level, wait_for_enter

if TYPE_CHECKING:
    from rew_to_musway.config import LevelsConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()


class ManualPlayback:
    """Playback strategy where the user manages noise playback manually.

    The program prompts the user to start/stop noise (e.g. via USB stick
    on the in-car infotainment system) and verifies the SPL level.
    """

    def __init__(self, rew: REWController, levels_config: LevelsConfig) -> None:
        self._rew = rew
        self._levels_config = levels_config

    async def start_noise(self) -> None:
        """Prompt user to start noise, then verify SPL level."""
        console.print(
            "\n[bold]Please start playing pink noise[/bold] on the infotainment system."
        )
        console.print("Press [bold]Enter[/bold] when noise is playing...")
        await wait_for_enter()
        logger.info("User confirmed noise is playing (manual mode)")

        try:
            await check_spl_level(self._rew, self._levels_config)
        except SPLCheckSkippedError:
            console.print("[yellow]SPL check skipped.[/yellow]")

    async def stop_noise(self) -> None:
        """Prompt user to stop noise."""
        console.print("\n[bold]Please stop playing pink noise.[/bold]")
        console.print("Press [bold]Enter[/bold] when stopped...")
        await wait_for_enter()
        logger.info("User confirmed noise is stopped (manual mode)")
