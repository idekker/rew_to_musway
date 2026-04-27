"""_combined.py - Phase 5: Combined channel measurements."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from rew_to_musway.amp import AmpBackend
    from rew_to_musway.config import Config
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

COUNTDOWN_SECONDS = 3


async def run_combined_measurements(
    config: Config, amp: AmpBackend, rew: REWController
) -> None:
    """Phase 5: Measure channel combinations defined in config.

    For each combined measurement group: unmute the specified channels
    (mute all others), run RTA, and save the measurement with the
    configured name.

    Parameters
    ----------
    config:
        Application config (must have ``combined_measurements`` populated).
    amp:
        Amp controller.
    rew:
        REW controller.

    """
    groups = config.combined_measurements
    if not groups:
        console.print(
            "[yellow]No combined measurements configured — skipping.[/yellow]"
        )
        return

    channel_numbers = {ch.number for ch in config.channels}

    console.print("\n[bold]Phase 5: Combined Channel Measurements[/bold]\n")
    console.print(f"Groups: {len(groups)}")

    # EQ should be active
    await amp.restore_eq()

    for i, group in enumerate(groups):
        group_channels = [n for n in group.channels if n in channel_numbers]
        ch_names = _resolve_channel_names(config, group_channels)

        console.print(
            f"\n  [{i + 1}/{len(groups)}] {group.name} ({', '.join(ch_names)})..."
        )

        # Unmute only the channels in this group, mute all others
        await amp.solo_channels(group_channels)

        # Countdown
        console.print(f"    Starting RTA in {COUNTDOWN_SECONDS} seconds...")
        for sec in range(COUNTDOWN_SECONDS, 0, -1):
            console.print(f"      {sec}...")
            await asyncio.sleep(1)

        # Run RTA
        console.print("    Running RTA measurement...")
        uuid = await rew.run_rta()

        # Rename measurement
        await rew.rename_measurement(uuid, group.name)
        console.print(f"    Saved as '{group.name}'")

    console.print(
        f"\n[green]Combined measurements complete for {len(groups)} groups.[/green]"
    )


def _resolve_channel_names(config: Config, channel_numbers: list[int]) -> list[str]:
    """Return human-readable names for a list of channel numbers."""
    name_map = {ch.number: f"CH{ch.number} {ch.name}" for ch in config.channels}
    return [name_map[n] for n in channel_numbers if n in name_map]
