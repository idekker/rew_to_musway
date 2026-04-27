"""_verification.py - Phase 3: Post-EQ verification measurements."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

    from rew_to_musway.amp import AmpBackend
    from rew_to_musway.config import Config
    from rew_to_musway.playback._base import PlaybackStrategy
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

COUNTDOWN_SECONDS = 3


async def run_verification(
    config: Config,
    amp: AmpBackend,
    rew: REWController,
    playback: PlaybackStrategy,
    *,
    channels: list[int] | None = None,
) -> None:
    """Phase 3: Run verification measurements for each calibrated channel.

    Starts noise once, then for each channel: solo channel, run RTA,
    save as ``<channel_name>_after_eq``.  Stops noise after all channels.

    Parameters
    ----------
    config:
        Application config.
    amp:
        Amp controller.
    rew:
        REW controller.
    playback:
        Playback strategy.
    channels:
        Channel numbers to verify. If None, verifies all channels.

    """
    all_channels = config.channels
    if channels is not None:
        channel_set = set(channels)
        target_channels = [ch for ch in all_channels if ch.number in channel_set]
    else:
        target_channels = list(all_channels)

    console.print("\n[bold]Phase 3: Verification Measurements[/bold]\n")
    console.print(
        f"Channels: {', '.join(f'CH{ch.number} {ch.name}' for ch in target_channels)}"
    )

    # EQ should be active — restore from bypass if needed
    await amp.restore_eq()
    await amp.set_master_mute(muted=False)

    # Start noise once for the entire verification run
    await playback.start_noise()

    try:
        for i, ch_cfg in enumerate(target_channels):
            console.print(
                f"\n  [{i + 1}/{len(target_channels)}] "
                f"CH{ch_cfg.number} ({ch_cfg.name})..."
            )

            # Solo channel
            await amp.solo_channel(ch_cfg.number)

            # Countdown
            console.print(f"    Starting RTA in {COUNTDOWN_SECONDS} seconds...")
            for sec in range(COUNTDOWN_SECONDS, 0, -1):
                console.print(f"      {sec}...")
                await asyncio.sleep(1)

            # Run RTA
            console.print("    Running RTA measurement...")
            uuid = await rew.run_rta()

            # Rename measurement
            measurement_name = f"{ch_cfg.name}_after_eq"
            await rew.rename_measurement(uuid, measurement_name)
            console.print(f"    Saved as '{measurement_name}'")
    finally:
        # Stop noise and mute when done (or on error)
        await playback.stop_noise()
        await amp.mute_all()
        await amp.set_master_mute(muted=True)

    console.print(
        f"\n[green]Verification complete for {len(target_channels)} channels.[/green]"
    )


async def save_session(
    rew: REWController,
    session_dir: Path,
) -> Path:
    """Save all REW measurements to an .mdat file in the session directory.

    Returns the path to the saved file.
    """
    mdat_path = session_dir / "calibration.mdat"
    console.print(f"\nSaving all measurements to {mdat_path}...")
    await rew.save_all_measurements(str(mdat_path))
    console.print(f"[green]Saved: {mdat_path}[/green]")
    return mdat_path
