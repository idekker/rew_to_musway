"""_eq.py - Phase 2: Per-channel EQ calibration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console

from rew_to_musway.filters import compute_match_range, export_filters_json

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


async def calibrate_channels(  # noqa: PLR0913
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    channels: list[ChannelConfig] | None = None,
) -> list[int]:
    """Phase 2: Calibrate EQ for each selected channel.

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
    session_dir:
        Session output directory for filter JSON files.
    channels:
        Channels to calibrate. If None, calibrates all channels.

    Returns
    -------
    List of channel numbers that were successfully calibrated.

    """
    if channels is None:
        channels = config.channels

    console.print("\n[bold]Phase 2: Per-Channel EQ Calibration[/bold]\n")
    console.print(
        f"Channels to calibrate: "
        f"{', '.join(f'CH{ch.number} {ch.name}' for ch in channels)}"
    )

    ctx = _CalibrationContext(
        config=config,
        amp=amp,
        rew=rew,
        playback=playback,
        session_dir=session_dir,
    )
    calibrated: list[int] = []

    # Start noise once for the entire calibration run
    await playback.start_noise()

    try:
        for i, ch_cfg in enumerate(channels):
            console.print(
                f"\n{'=' * 50}\n"
                f"[bold]Channel {i + 1}/{len(channels)}: "
                f"CH{ch_cfg.number} {ch_cfg.name}[/bold]\n"
                f"{'=' * 50}"
            )

            await _calibrate_single_channel(ctx, ch_cfg)
            calibrated.append(ch_cfg.number)
    finally:
        # Stop noise and mute when done (or on error)
        await playback.stop_noise()
        await amp.mute_all()
        await amp.set_master_mute(muted=True)

    console.print(
        f"\n[green]Calibration complete for {len(calibrated)} channels.[/green]"
    )
    return calibrated


async def _calibrate_single_channel(
    ctx: _CalibrationContext,
    ch_cfg: ChannelConfig,
) -> None:
    """Calibrate a single channel (noise is already playing)."""
    ch = ch_cfg.number
    name = ch_cfg.name

    # 1. Prepare amp — solo this channel
    console.print(f"Preparing CH{ch} ({name})...")
    await ctx.amp.prepare_channel(ch_cfg)
    await ctx.amp.set_master_mute(muted=False)

    # 2. Countdown
    console.print(f"\n  Starting RTA in {COUNTDOWN_SECONDS} seconds...")
    for sec in range(COUNTDOWN_SECONDS, 0, -1):
        console.print(f"    {sec}...")
        await asyncio.sleep(1)

    # 3. Run RTA
    console.print("  Running RTA measurement...")
    flat_uuid = await ctx.rew.run_rta()

    # 4. Mute while processing
    await ctx.amp.mute_all()
    await ctx.amp.set_master_mute(muted=True)

    # 5. Save and rename
    measurement_name = f"{name}_flat"
    await ctx.rew.rename_measurement(flat_uuid, measurement_name)
    console.print(f"  Measurement saved as '{measurement_name}'")

    # 6. EQ pipeline
    predicted_uuid = await _run_eq_pipeline(ctx, flat_uuid, ch_cfg)

    # 7. Export filters to JSON and import into amp
    await _export_and_import(ctx, flat_uuid, ch_cfg)

    # 8. Finetuning loops (if configured)
    if ch_cfg.finetune_loops > 0:
        await _run_finetune_loops(ctx, ch_cfg, flat_uuid, predicted_uuid)

    console.print(f"  [green]CH{ch} ({name}) calibration complete.[/green]")


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
        uuid, target_cfg=ch_cfg.target, target_offset=ch_cfg.target_offset
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


async def _run_finetune_loops(
    ctx: _CalibrationContext,
    ch_cfg: ChannelConfig,
    flat_uuid: object,
    predicted_uuid: object,
) -> None:
    """Run iterative finetuning loops for a channel.

    Each loop:
    1. Measure the actual response (RTA) with EQ applied.
    2. Compute correction = predicted / measured (the error curve).
    3. Compute adjusted = previous_basis * correction — where the basis
       starts as the flat measurement and accumulates corrections.
    4. Re-run the EQ pipeline on the adjusted measurement.
    5. Export and import the new filters.

    Parameters
    ----------
    ctx:
        Calibration context.
    ch_cfg:
        Channel configuration.
    flat_uuid:
        UUID of the original flat (no-EQ) measurement from phase 2.
    predicted_uuid:
        UUID of the predicted measurement from the previous EQ pipeline.

    """
    ch = ch_cfg.number
    name = ch_cfg.name
    loops = ch_cfg.finetune_loops

    console.print(f"\n  [bold]Finetuning CH{ch} ({name}): {loops} loop(s)[/bold]")

    prev_predicted = predicted_uuid
    basis_uuid = flat_uuid

    for loop in range(1, loops + 1):
        console.print(f"\n  --- Finetune loop {loop}/{loops} ---")

        # 1. Unmute and measure actual response with current EQ
        console.print("  Restoring EQ and unmuting...")
        await ctx.amp.restore_eq()
        await ctx.amp.solo_channel(ch)
        await ctx.amp.set_master_mute(muted=False)

        console.print(f"  Starting RTA in {COUNTDOWN_SECONDS} seconds...")
        for sec in range(COUNTDOWN_SECONDS, 0, -1):
            console.print(f"    {sec}...")
            await asyncio.sleep(1)

        console.print("  Running RTA measurement...")
        measured_uuid = await ctx.rew.run_rta()

        # Mute while processing
        await ctx.amp.mute_all()
        await ctx.amp.set_master_mute(muted=True)

        measured_name = f"{name}_finetune_{loop}_measured"
        await ctx.rew.rename_measurement(measured_uuid, measured_name)
        console.print(f"  Saved as '{measured_name}'")

        # 2. correction = predicted / measured (error curve)
        console.print("  Computing correction (predicted / measured)...")
        correction_uuid = await ctx.rew.divide_measurements(
            prev_predicted, measured_uuid
        )
        correction_name = f"{name}_finetune_{loop}_correction"
        await ctx.rew.rename_measurement(correction_uuid, correction_name)

        # 3. adjusted = basis * correction
        console.print("  Computing adjusted measurement (basis * correction)...")
        adjusted_uuid = await ctx.rew.multiply_measurements(basis_uuid, correction_uuid)
        adjusted_name = f"{name}_finetune_{loop}_adjusted"
        await ctx.rew.rename_measurement(adjusted_uuid, adjusted_name)
        console.print(f"  Saved as '{adjusted_name}'")

        # 4. Run EQ pipeline on the adjusted measurement
        prev_predicted = await _run_eq_pipeline(ctx, adjusted_uuid, ch_cfg)

        # 5. Export and import new filters
        await _export_and_import(ctx, adjusted_uuid, ch_cfg)

        # Update basis for next iteration
        basis_uuid = adjusted_uuid

        console.print(f"  [green]Finetune loop {loop} complete.[/green]")


async def _export_and_import(
    ctx: _CalibrationContext,
    uuid: object,
    ch_cfg: ChannelConfig,
) -> None:
    """Export filters to JSON and import EQ into the amp."""
    filters = await ctx.rew.get_filters(uuid)
    active_filters = [f for f in filters if f.type != "None"]
    console.print(f"  Generated {len(active_filters)} active filters")

    json_path = ctx.session_dir / f"{ch_cfg.name}.json"
    export_filters_json(
        filters,
        json_path,
        model=ctx.config.eq.model,
        channel_name=ch_cfg.name,
    )
    console.print(f"  Filters saved to {json_path}")

    console.print(f"  Importing EQ into CH{ch_cfg.number}...")
    await ctx.amp.import_eq(ch_cfg.number, str(json_path.resolve()))
