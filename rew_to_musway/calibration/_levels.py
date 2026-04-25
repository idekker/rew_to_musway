"""_levels.py - Phase 1 (level balancing) and Phase 4 (level verification)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import questionary
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from rew_to_musway.amp import AmpController
    from rew_to_musway.config import Config
    from rew_to_musway.playback._base import PlaybackStrategy
    from rew_to_musway.rew import REWController

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


def _compute_offsets(readings: list[ChannelLevel]) -> dict[int, float]:
    """Compute per-channel level offsets within groups.

    Within each group, channels are balanced relative to the *quietest*
    member (the lowest SPL).  This guarantees all offsets are ≤ 0 — louder
    channels are attenuated, no channel is ever boosted.

    Returns a dict of {channel_number: offset_db}.
    """
    # Group channels
    groups: dict[str, list[ChannelLevel]] = {}
    for r in readings:
        groups.setdefault(r.group, []).append(r)

    offsets: dict[int, float] = {}
    for group_name, members in groups.items():
        if len(members) == 1:
            # Single-channel group — no balancing needed
            offsets[members[0].channel_number] = 0.0
            continue

        ref = min(m.spl_db for m in members)
        for m in members:
            # offset = ref - measured:  always ≤ 0  (louder → more negative)
            offsets[m.channel_number] = round(ref - m.spl_db, 1)

        logger.debug(
            "Group '%s': ref=%.1f dB (quietest), offsets=%s",
            group_name,
            ref,
            {m.channel_name: offsets[m.channel_number] for m in members},
        )

    return offsets


# ---------------------------------------------------------------------------
# Phase 1: Level balancing
# ---------------------------------------------------------------------------


async def measure_levels(
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
) -> LevelOffsets:
    """Phase 1: Measure SPL per channel, compute offsets within groups.

    Parameters
    ----------
    config:
        Application config.
    amp:
        Amp controller.
    rew:
        REW controller.
    playback:
        Playback strategy (manual or REW generator).

    Returns
    -------
    LevelOffsets with per-channel readings and computed offsets.

    """
    console.print("\n[bold]Phase 1: Level Balancing[/bold]\n")

    # Prepare amp
    console.print("Preparing amp: bypass EQ, configure filters, levels to 0 dB...")
    await amp.prepare_for_level_measurement()

    # Start noise
    await playback.start_noise()

    # Measure each channel
    readings: list[ChannelLevel] = []
    for ch_cfg in config.channels:
        console.print(f"\n  Measuring CH{ch_cfg.number} ({ch_cfg.name})...")
        await amp.solo_channel(ch_cfg.number)

        spl = await rew.measure_spl()
        reading = ChannelLevel(
            channel_number=ch_cfg.number,
            channel_name=ch_cfg.name,
            group=ch_cfg.group,
            spl_db=spl.spl,
        )
        readings.append(reading)
        console.print(f"    SPL: {spl.spl:.1f} dB")

    # Stop noise and mute
    await playback.stop_noise()
    await amp.mute_all()
    await amp.set_master_mute(muted=True)

    # Compute offsets
    offsets = _compute_offsets(readings)
    result = LevelOffsets(readings=readings, offsets=offsets)

    # Display results
    _display_level_results(readings, offsets)

    return result


def _display_level_results(
    readings: list[ChannelLevel],
    offsets: dict[int, float],
) -> None:
    """Display level measurements and offsets in a rich table."""
    table = Table(title="Level Measurements")
    table.add_column("Channel", style="bold")
    table.add_column("Group")
    table.add_column("SPL (dB)", justify="right")
    table.add_column("Offset (dB)", justify="right")

    for r in readings:
        offset = offsets.get(r.channel_number, 0.0)
        offset_str = f"{offset:+.1f}" if offset != 0.0 else "0.0"
        offset_style = "yellow" if abs(offset) > OFFSET_THRESHOLD_DB else "green"
        table.add_row(
            f"CH{r.channel_number} {r.channel_name}",
            r.group,
            f"{r.spl_db:.1f}",
            f"[{offset_style}]{offset_str}[/{offset_style}]",
        )

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Phase 4: Level verification
# ---------------------------------------------------------------------------


async def verify_levels(
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
) -> None:
    """Phase 4: Re-measure SPL with EQ active, apply offsets.

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

    """
    console.print("\n[bold]Phase 4: Level Verification[/bold]\n")

    # Start noise (EQ should be active from Phase 2)
    await amp.set_master_mute(muted=False)
    await playback.start_noise()

    # Measure each channel
    new_readings: list[ChannelLevel] = []
    for ch_cfg in config.channels:
        console.print(f"\n  Measuring CH{ch_cfg.number} ({ch_cfg.name})...")
        await amp.solo_channel(ch_cfg.number)

        spl = await rew.measure_spl()
        reading = ChannelLevel(
            channel_number=ch_cfg.number,
            channel_name=ch_cfg.name,
            group=ch_cfg.group,
            spl_db=spl.spl,
        )
        new_readings.append(reading)
        console.print(f"    SPL: {spl.spl:.1f} dB")

    # Stop noise
    await playback.stop_noise()
    await amp.mute_all()

    # Compute new offsets and show comparison
    new_offsets = _compute_offsets(new_readings)

    # Build proposed adjustments (combine baseline offsets with new measurement)
    adjustments = _compute_adjustments(new_offsets)

    # Display proposed adjustments
    _display_adjustments(new_readings, new_offsets, adjustments)

    # Ask for confirmation
    if not adjustments:
        console.print("\n[green]No level adjustments needed.[/green]")
        return

    confirmed = await questionary.confirm(
        "Apply these level adjustments?",
        default=True,
    ).ask_async()

    if confirmed:
        for ch_num, adj_db in adjustments.items():
            current_level = await amp.get_channel_level(ch_num)
            new_level = current_level + adj_db
            console.print(
                f"  CH{ch_num}: {current_level:.1f} dB -> {new_level:.1f} dB "
                f"({adj_db:+.1f} dB)"
            )
            await amp.set_channel_level(ch_num, new_level)
        console.print("[green]Level adjustments applied.[/green]")
    else:
        console.print("Level adjustments skipped.")


def _compute_adjustments(
    new_offsets: dict[int, float],
) -> dict[int, float]:
    """Compute level adjustments to apply.

    Uses the new offset measurements to determine what adjustments
    are needed to balance channels within their groups.

    Returns dict of {channel_number: adjustment_db}.
    Only includes channels that need adjustment (> OFFSET_THRESHOLD_DB).
    """
    return {
        ch_num: offset
        for ch_num, offset in new_offsets.items()
        if abs(offset) > OFFSET_THRESHOLD_DB
    }


def _display_adjustments(
    readings: list[ChannelLevel],
    offsets: dict[int, float],
    adjustments: dict[int, float],
) -> None:
    """Display proposed level adjustments."""
    table = Table(title="Level Verification - Proposed Adjustments")
    table.add_column("Channel", style="bold")
    table.add_column("Group")
    table.add_column("SPL (dB)", justify="right")
    table.add_column("Offset (dB)", justify="right")
    table.add_column("Adjustment", justify="right")

    for r in readings:
        offset = offsets.get(r.channel_number, 0.0)
        adj = adjustments.get(r.channel_number)
        adj_str = f"{adj:+.1f} dB" if adj is not None else "-"
        adj_style = "yellow" if adj is not None else "green"
        table.add_row(
            f"CH{r.channel_number} {r.channel_name}",
            r.group,
            f"{r.spl_db:.1f}",
            f"{offset:+.1f}",
            f"[{adj_style}]{adj_str}[/{adj_style}]",
        )

    console.print()
    console.print(table)
