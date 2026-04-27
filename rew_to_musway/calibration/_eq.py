"""_eq.py - Phase 2: Per-channel EQ calibration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig, Config

logger = logging.getLogger(__name__)
console = Console()

COUNTDOWN_SECONDS = 3


# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------


def select_channels(
    config: Config,
    mode: str,
    start_from: int | None = None,
    single: int | None = None,
) -> list[ChannelConfig]:
    """Select channels to calibrate based on mode.

    Parameters
    ----------
    config:
        Application config.
    mode:
        "all", "start_from", or "single".
    start_from:
        Channel number to start from (used when mode="start_from").
    single:
        Channel number to calibrate (used when mode="single").

    Returns
    -------
    List of ChannelConfig objects to calibrate, in order.

    """
    all_channels = config.channels

    if mode == "single" and single is not None:
        return [ch for ch in all_channels if ch.number == single]

    if mode == "start_from" and start_from is not None:
        idx = next(
            (i for i, ch in enumerate(all_channels) if ch.number == start_from),
            0,
        )
        return all_channels[idx:]

    return list(all_channels)
