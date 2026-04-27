"""_verification.py - Phase 3: Post-EQ verification measurements."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

COUNTDOWN_SECONDS = 3


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
