"""_eq.py - Phase 2: Per-channel EQ calibration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console

from rew_to_musway.filters import compute_match_range

if TYPE_CHECKING:
    from pathlib import Path

    from rew_to_musway.amp import AmpController
    from rew_to_musway.config import ChannelConfig, Config
    from rew_to_musway.playback._base import PlaybackStrategy
    from rew_to_musway.rew import REWController

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


# ---------------------------------------------------------------------------
# Phase 2: Per-channel calibration
# ---------------------------------------------------------------------------


@dataclass
class _CalibrationContext:
    """Bundle of dependencies for the calibration loop."""

    config: Config
    amp: AmpController
    rew: REWController
    playback: PlaybackStrategy
    session_dir: Path


async def _run_eq_pipeline(
    ctx: _CalibrationContext,
    uuid: object,
    ch_cfg: ChannelConfig,
) -> object:
    """Apply smoothing, configure equaliser/target, match, and predict.

    Returns the UUID of the generated predicted measurement.
    """
    await ctx.rew.apply_smoothing(uuid)
    await ctx.rew.configure_equaliser(uuid)
    await ctx.rew.configure_target(
        uuid, target_cfg=ch_cfg.target, target_offset=ch_cfg.target.offset
    )

    match_start, match_end = compute_match_range(
        ch_cfg, ctx.config.eq.match_range_margin
    )
    console.print(f"  Match range: {match_start:.0f} - {match_end:.0f} Hz")
    await ctx.rew.configure_match_settings(match_start, match_end)

    console.print("  Matching response to target...")
    await ctx.rew.match_target(uuid)

    console.print("  Generating predicted measurement...")
    return await ctx.rew.generate_predicted(uuid)
