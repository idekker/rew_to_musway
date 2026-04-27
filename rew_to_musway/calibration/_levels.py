"""_levels.py - Phase 1 (level balancing) and Phase 4 (level verification)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

OFFSET_THRESHOLD_DB = 0.5


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ChannelLevel:
    channel_number: int
    channel_name: str
    group: str
    spl_db: float


@dataclass
class LevelOffsets:
    """Stores per-channel SPL measurements and computed offsets."""

    readings: list[ChannelLevel] = field(default_factory=list)
    offsets: dict[int, float] = field(
        default_factory=dict
    )  # channel_number -> offset_db


# ---------------------------------------------------------------------------
# Offset calculation
# ---------------------------------------------------------------------------


def compute_two_stage_offsets(readings: list[ChannelLevel]) -> dict[int, float]:
    """Compute per-channel level offsets in two stages.

    **Stage 1 — between-group offsets:** Compute the average SPL for each
    group, then attenuate all members of louder groups so that their group
    average matches the quietest group's average.

    **Stage 2 — within-group (L/R) offsets:** Within each group, attenuate
    louder channels to match the quietest member.

    The final offset for each channel is ``group_offset + lr_offset`` and is
    always ≤ 0 (attenuation only).

    Returns a dict of ``{channel_number: offset_db}``.
    """
    # Group channels
    groups: dict[str, list[ChannelLevel]] = {}
    for r in readings:
        groups.setdefault(r.group, []).append(r)

    # Stage 1: between-group offsets
    group_avgs: dict[str, float] = {}
    for group_name, members in groups.items():
        group_avgs[group_name] = sum(m.spl_db for m in members) / len(members)

    quietest_group_avg = min(group_avgs.values())

    group_offsets: dict[str, float] = {
        name: round(quietest_group_avg - avg, 1) for name, avg in group_avgs.items()
    }

    logger.debug(
        "Between-group: averages=%s, quietest=%.1f, offsets=%s",
        {k: round(v, 1) for k, v in group_avgs.items()},
        quietest_group_avg,
        group_offsets,
    )

    # Stage 2: within-group (L/R) offsets
    offsets: dict[int, float] = {}
    for group_name, members in groups.items():
        grp_offset = group_offsets[group_name]

        if len(members) == 1:
            offsets[members[0].channel_number] = grp_offset
            continue

        ref = min(m.spl_db for m in members)
        for m in members:
            lr_offset = round(ref - m.spl_db, 1)
            offsets[m.channel_number] = round(grp_offset + lr_offset, 1)

        logger.debug(
            "Group '%s': grp_offset=%.1f, lr ref=%.1f, combined=%s",
            group_name,
            grp_offset,
            ref,
            {m.channel_name: offsets[m.channel_number] for m in members},
        )

    return offsets
