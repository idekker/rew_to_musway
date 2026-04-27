"""_unified.py - Combined calibration flow for manual and automated modes.

Combines measurement phases to minimise user interactions (fewer solo
cycles and preset loads).  The flow is:

1. **Measure loop (Phase 1+2):** For each channel (one solo each):
   measure SPL + RTA.  Then batch-compute level offsets and EQ.
   Single ``apply()``.

2. **Finetune loop:** Per iteration: solo each eligible channel → RTA.
   Then batch-compute corrections.  Single ``apply()``.

3. **Verification loop (Phase 3+4):** For each channel: RTA + SPL
   in one solo pass.  Compute level adjustments.  Conditional ``apply()``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console

from rew_to_musway.amp import PresetPhase
from rew_to_musway.filters import compute_match_range

from ._levels import ChannelLevel, LevelOffsets, _compute_two_stage_offsets

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from rew_to_musway.amp import AmpBackend
    from rew_to_musway.config import ChannelConfig, Config
    from rew_to_musway.playback._base import PlaybackStrategy
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

COUNTDOWN_SECONDS = 3


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@dataclass
class _ChannelMeasurements:
    """Measurements collected for a single channel during phase 1+2."""

    channel: ChannelConfig
    spl_db: float = 0.0
    rta_uuid: UUID | None = None


@dataclass
class _UnifiedContext:
    """Bundle of dependencies for the unified calibration flow."""

    config: Config
    amp: AmpBackend
    rew: REWController
    playback: PlaybackStrategy
    session_dir: Path


async def _countdown(seconds: int = COUNTDOWN_SECONDS) -> None:
    """Display a countdown before measurement."""
    for sec in range(seconds, 0, -1):
        console.print(f"    {sec}...")
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Phase 1+2: Combined measure loop
# ---------------------------------------------------------------------------


@dataclass
class MeasureResult:
    """Results from the combined measure loop."""

    rta_uuids: dict[int, UUID] = field(default_factory=dict)
    predicted_uuids: dict[int, UUID] = field(default_factory=dict)


async def run_measure_loop(
    ctx: _UnifiedContext,
    channels: list[ChannelConfig] | None = None,
) -> MeasureResult:
    """Phase 1+2: Measure SPL + RTA for each channel in a single solo pass.

    After all channels are measured, batch-compute level offsets and EQ
    filters, then buffer everything into the amp backend for a single
    ``apply()`` call by the caller.

    Parameters
    ----------
    ctx:
        Unified calibration context.
    channels:
        Channels to measure.  Defaults to all config channels.

    Returns
    -------
    MeasureResult with level offsets, RTA UUIDs, and predicted UUIDs.

    """
    if channels is None:
        channels = ctx.config.channels

    console.print("\n[bold]Phase 1+2: Combined SPL + RTA Measurement[/bold]\n")

    # Prepare: bypass EQ, configure filters, levels to 0
    for ch_cfg in channels:
        await ctx.amp.reset_eq(ch_cfg.number)
        await ctx.amp.set_channel_level(ch_cfg.number, -60.0)
        await ctx.amp.set_crossover(ch_cfg)
    ctx.amp.set_phase(PresetPhase.INITIAL)
    await ctx.amp.apply()

    measurements: list[_ChannelMeasurements] = []

    for i, ch_cfg in enumerate(channels):
        console.print(
            f"\n  [{i + 1}/{len(channels)}] CH{ch_cfg.number} ({ch_cfg.name})"
        )

        # Solo channel
        await ctx.amp.solo_channel(ch_cfg.number)

        # Measure SPL
        console.print("    Measuring SPL...")
        spl = await ctx.rew.measure_spl()
        console.print(f"    SPL: {spl.spl:.1f} dB")

        # Countdown + RTA
        console.print(f"    Starting RTA in {COUNTDOWN_SECONDS}s...")
        await _countdown()
        console.print("    Running RTA...")
        rta_uuid = await ctx.rew.run_rta()

        name = f"{ch_cfg.name}_flat"
        await ctx.rew.rename_measurement(rta_uuid, name)

        measurements.append(
            _ChannelMeasurements(channel=ch_cfg, spl_db=spl.spl, rta_uuid=rta_uuid)
        )

    # Batch compute EQ
    rta_uuids: dict[int, UUID] = {}
    predicted_uuids: dict[int, UUID] = {}
    for m in measurements:
        ch_cfg = m.channel
        assert m.rta_uuid is not None  # noqa: S101
        rta_uuids[ch_cfg.number] = m.rta_uuid

        console.print(f"\n  Computing EQ for CH{ch_cfg.number} ({ch_cfg.name})...")
        predicted = await _run_eq_pipeline(ctx, m.rta_uuid, ch_cfg)
        predicted_uuids[ch_cfg.number] = predicted

        # Buffer EQ filters
        filters = await ctx.rew.get_filters(m.rta_uuid)
        await ctx.amp.set_eq_filters(ch_cfg.number, filters)

    ctx.amp.set_phase(PresetPhase.EQ)
    await ctx.amp.apply()

    console.print(
        f"\n[green]Measurement complete for {len(channels)} channels.[/green]"
    )

    return MeasureResult(
        rta_uuids=rta_uuids,
        predicted_uuids=predicted_uuids,
    )


# ---------------------------------------------------------------------------
# Finetune loop
# ---------------------------------------------------------------------------


def _eligible_finetune_channels(
    channels: list[ChannelConfig],
    iteration: int,
) -> list[ChannelConfig]:
    """Return channels whose ``finetune_loops`` >= *iteration*."""
    return [ch for ch in channels if ch.finetune_loops >= iteration]


async def run_finetune_loop(
    ctx: _UnifiedContext,
    channels: list[ChannelConfig],
    rta_uuids: dict[int, UUID],
    predicted_uuids: dict[int, UUID],
    *,
    iteration: int = 1,
) -> dict[int, UUID]:
    """Run one batched finetune iteration across eligible channels.

    Only channels with ``finetune_loops >= iteration`` are measured and
    re-EQ'd.  Others retain their previous EQ filters.

    Solos each channel once for RTA, then batch-computes corrections
    and buffers updated EQ filters.  Caller should ``apply()`` after.

    Parameters
    ----------
    ctx:
        Unified calibration context.
    channels:
        All calibrated channels (filtering by finetune_loops is done internally).
    rta_uuids:
        Per-channel flat/basis RTA UUIDs (updated in place).
    predicted_uuids:
        Per-channel predicted UUIDs from previous iteration.
    iteration:
        1-based iteration number.

    Returns
    -------
    Updated predicted_uuids dict.

    """
    eligible = _eligible_finetune_channels(channels, iteration)

    if not eligible:
        console.print(
            f"\n[yellow]Finetune iteration {iteration}: "
            f"no channels have finetune_loops >= {iteration} — skipping.[/yellow]"
        )
        return predicted_uuids

    skipped = [ch for ch in channels if ch not in eligible]
    console.print(
        f"\n[bold]Finetune Iteration {iteration}[/bold] "
        f"({len(eligible)} channels"
        f"{f', skipping {len(skipped)}' if skipped else ''})\n"
    )

    measured_uuids: dict[int, UUID] = {}

    for i, ch_cfg in enumerate(eligible):
        ch = ch_cfg.number
        console.print(f"\n  [{i + 1}/{len(eligible)}] CH{ch} ({ch_cfg.name})")
        await ctx.amp.solo_channel(ch)

        console.print(f"    Starting RTA in {COUNTDOWN_SECONDS}s...")
        await _countdown()
        console.print("    Running RTA...")
        measured = await ctx.rew.run_rta()
        await ctx.rew.rename_measurement(
            measured, f"{ch_cfg.name}_finetune_{iteration}_measured"
        )
        measured_uuids[ch] = measured

    # Batch compute corrections
    new_predicted = dict(predicted_uuids)  # preserve non-eligible entries
    for ch_cfg in eligible:
        ch = ch_cfg.number
        name = ch_cfg.name
        prev_predicted = predicted_uuids[ch]
        measured = measured_uuids[ch]
        basis = rta_uuids[ch]

        console.print(f"\n  Computing correction for CH{ch} ({name})...")

        # Correction: measured / predicted (error curve)
        correction = await ctx.rew.divide_measurements(measured, prev_predicted)
        await ctx.rew.rename_measurement(
            correction, f"{name}_finetune_{iteration}_correction"
        )

        # Adjusted: basis * correction (accumulated target)
        adjusted = await ctx.rew.multiply_measurements(basis, correction)
        await ctx.rew.rename_measurement(
            adjusted, f"{name}_finetune_{iteration}_adjusted"
        )

        # Re-run EQ pipeline
        predicted = await _run_eq_pipeline(ctx, adjusted, ch_cfg)
        new_predicted[ch] = predicted

        # Buffer updated EQ
        filters = await ctx.rew.get_filters(adjusted)
        await ctx.amp.set_eq_filters(ch, filters)

        # Update basis for next iteration
        rta_uuids[ch] = adjusted

    ctx.amp.set_phase(PresetPhase.FINETUNE, iteration)
    await ctx.amp.apply()

    console.print(f"\n[green]Finetune iteration {iteration} complete.[/green]")
    return new_predicted


# ---------------------------------------------------------------------------
# Phase 3+4: Combined verification loop
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Results from the combined verification loop."""

    level_offsets: LevelOffsets
    adjustments: dict[int, float] = field(default_factory=dict)


_OFFSET_THRESHOLD_DB = 0.5


async def run_verification_loop(
    ctx: _UnifiedContext,
    channels: list[ChannelConfig] | None = None,
) -> VerificationResult:
    """Phase 3+4: SPL + RTA verification in one solo pass per channel.

    Measurement order matches the measure loop: SPL first, then RTA.
    Buffers level adjustments only if offsets exceed the threshold.

    Parameters
    ----------
    ctx:
        Unified calibration context.
    channels:
        Channels to verify.  Defaults to all config channels.

    Returns
    -------
    VerificationResult with level offsets and proposed adjustments.

    """
    if channels is None:
        channels = ctx.config.channels

    console.print("\n[bold]Phase 3+4: Combined Verification[/bold]\n")

    readings: list[ChannelLevel] = []

    for i, ch_cfg in enumerate(channels):
        ch = ch_cfg.number
        console.print(f"\n  [{i + 1}/{len(channels)}] CH{ch} ({ch_cfg.name})")
        await ctx.amp.solo_channel(ch)

        # SPL first (same order as measure loop)
        console.print("    Measuring SPL...")
        spl = await ctx.rew.measure_spl()
        console.print(f"    SPL: {spl.spl:.1f} dB")

        # Then RTA
        console.print(f"    Starting RTA in {COUNTDOWN_SECONDS}s...")
        await _countdown()
        console.print("    Running RTA...")
        uuid = await ctx.rew.run_rta()
        await ctx.rew.rename_measurement(uuid, f"{ch_cfg.name}_after_eq")

        readings.append(
            ChannelLevel(
                channel_number=ch,
                channel_name=ch_cfg.name,
                group=ch_cfg.group,
                spl_db=spl.spl,
            )
        )

    # Compute two-stage offsets (between-group + within-group L/R)
    offsets = _compute_two_stage_offsets(readings)
    level_offsets = LevelOffsets(readings=readings, offsets=offsets)

    adjustments = {
        ch_num: offset
        for ch_num, offset in offsets.items()
        if abs(offset) > _OFFSET_THRESHOLD_DB
    }

    if adjustments:
        console.print(
            f"\n[yellow]{len(adjustments)} channel(s) exceed "
            f"{_OFFSET_THRESHOLD_DB} dB threshold — buffering adjustments.[/yellow]"
        )
        # ruff: disable[ERA001]
        # for ch_num, adj in adjustments.items():
        #     await ctx.amp.set_channel_level(ch_num, 0.0 + adj)
        #
        # ctx.amp.set_phase(PresetPhase.VERIFICATION)
        # await ctx.amp.apply()
        # ruff: enable[ERA001]
    else:
        console.print(
            "\n[green]All channels within threshold — no adjustments needed.[/green]"
        )

    return VerificationResult(level_offsets=level_offsets, adjustments=adjustments)


# ---------------------------------------------------------------------------
# EQ pipeline helper
# ---------------------------------------------------------------------------


async def _run_eq_pipeline(
    ctx: _UnifiedContext,
    uuid: UUID,
    ch_cfg: ChannelConfig,
) -> UUID:
    """Apply smoothing, configure equaliser/target, match, predict.

    Returns the UUID of the predicted measurement.
    """
    await ctx.rew.apply_smoothing(uuid)
    await ctx.rew.configure_equaliser(uuid)
    await ctx.rew.configure_target(
        uuid, target_cfg=ch_cfg.target, target_offset=ch_cfg.target.offset
    )

    match_start, match_end = compute_match_range(
        ch_cfg, ctx.config.eq.match_range_margin
    )
    console.print(f"    Match range: {match_start:.0f} - {match_end:.0f} Hz")
    await ctx.rew.configure_match_settings(match_start, match_end)
    await ctx.rew.match_target(uuid)

    return await ctx.rew.generate_predicted(uuid)
