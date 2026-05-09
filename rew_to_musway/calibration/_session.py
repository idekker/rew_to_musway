"""_session.py - Phase 3: Post-EQ verification measurements."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from rew_to_musway.config import ChannelConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()


async def load_session(
    rew: REWController, mdat_input_file: Path, channels: list[ChannelConfig]
) -> (dict[int, UUID], dict[int, UUID]):
    """Save all REW measurements to an .mdat file in the session directory.

    Returns the path to the saved file.
    """
    console.print(f"\nLoading measurements from {mdat_input_file}...")
    await rew.load_measurements(str(mdat_input_file))
    console.print(f"[green]Loaded: {mdat_input_file}[/green]")

    await asyncio.sleep(2)

    measurements = await rew.get_measurements()

    rta_uuids = {}
    eq_predictions = {}

    for m in measurements:
        title = m.title
        elems = title.split("_")
        is_eq = elems[0].startswith("EQ ")
        channel_name = elems[0].removeprefix("EQ ")
        for c in channels:
            if c.name == channel_name:
                channel_number = c.number

                if elems[1] == "flat":
                    if is_eq:
                        console.print(
                            rf"Loaded EQ prediction for channel {channel_number}: {channel_name}"
                        )
                        eq_predictions[channel_number] = m.uuid
                    else:
                        console.print(
                            rf"Loaded RTA measurement for channel {channel_number}: {channel_name}"
                        )
                        rta_uuids[channel_number] = m.uuid
                break

    return rta_uuids, eq_predictions


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
