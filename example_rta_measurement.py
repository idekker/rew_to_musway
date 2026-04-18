"""example_rta_measurement.py - RTA measurement workflow using aiorew.

Workflow
--------
 1. Delete all existing measurements.
 2. Start the input-levels monitor.
 3. Configure and start the signal generator (periodic pink noise).
 4. Wait 3 seconds for levels to stabilise, then snapshot input levels.
 5. Configure the RTA for 100 averages and start it; wait until it stops.
 6. Save the RTA data as a new measurement via REWClient.save_rta().
 7. Rename the measurement to the current date/time.
 8. Add a note with the active output device and channel configuration.
 9. Snapshot input levels again (post-measurement).
10. Open the SPL meter, take one reading, and close it.
11. Stop the signal generator and tear down.
12. Save all measurements to file

Run with:
    python example_rta_measurement.py
"""

from __future__ import annotations

import asyncio
import datetime
import io
import logging
import sys
from pathlib import Path

from aiorew import GeneratorSignal, InputLevels, REWClient, RTAConfiguration

# Force UTF-8 output on cp1252 consoles (Windows), with line buffering so
# logger.warning() output appears immediately rather than at process exit.
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

# ---------------------------------------------------------------------------
# Configuration - adjust as needed
# ---------------------------------------------------------------------------

REW_HOST = "localhost"
REW_PORT = 4735

GENERATOR_SIGNAL = (
    GeneratorSignal.PINK_PERIODIC
)  # periodic pink noise - as returned by generator.get_signals()
GENERATOR_LEVEL = -12.0  # dBFS

RTA_MAX_AVERAGES = 100
GENERATOR_WARMUP = 3.0  # seconds to let the generator stabilise before reading levels
SPL_WARMUP = 1.5  # pause after starting SPL meter before reading

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_levels(levels: InputLevels) -> str:
    rms_str = ", ".join(f"{v:.1f}" for v in levels.rms)
    peak_str = ", ".join(f"{v:.1f}" for v in levels.peak)
    return f"RMS=[{rms_str}] Peak=[{peak_str}] {levels.unit}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:  # noqa: PLR0915
    async with REWClient(host=REW_HOST, port=REW_PORT) as rew:
        # ------------------------------------------------------------------ #
        # 1. Delete all existing measurements
        # ------------------------------------------------------------------ #
        logger.warning("Deleting all existing measurements...")
        await rew.measurements.delete_all()
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # 2. Start input-levels monitor
        # ------------------------------------------------------------------ #
        logger.warning("Starting input-levels monitor...")
        await rew.input_levels.start_monitoring()
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # 3. Configure and start the signal generator
        # ------------------------------------------------------------------ #
        logger.warning(
            "Setting signal to '%s' at %.1f dBFS...", GENERATOR_SIGNAL, GENERATOR_LEVEL
        )
        await rew.generator.set_signal(GENERATOR_SIGNAL)
        await rew.generator.set_level(GENERATOR_LEVEL)
        await rew.generator.play()
        logger.warning("  Generator playing.")

        # Wait for the generator output to stabilise before any level readings.
        logger.warning("Waiting %.0fs for generator to stabilise...", GENERATOR_WARMUP)
        await asyncio.sleep(GENERATOR_WARMUP)

        # ------------------------------------------------------------------ #
        # 4. Snapshot pre-measurement input levels
        # ------------------------------------------------------------------ #
        pre_levels = await rew.input_levels.get_last_levels()
        logger.warning("  Pre-measurement input levels: %s", _fmt_levels(pre_levels))

        # ------------------------------------------------------------------ #
        # 5. Configure RTA for 100 averages and start
        # ------------------------------------------------------------------ #
        logger.warning(
            "Configuring RTA: stopAt=True, stopAtValue=%d...", RTA_MAX_AVERAGES
        )
        await rew.rta.set_configuration(
            RTAConfiguration(
                stopAt=True,
                stopAtValue=RTA_MAX_AVERAGES,
                stopGeneratorWithRTA=False,  # we stop the generator ourselves below
            )
        )

        logger.warning("Starting RTA...")
        await rew.rta.start()
        logger.warning("  Waiting for %d averages to complete...", RTA_MAX_AVERAGES)
        await rew.rta.wait_until_stopped()
        logger.warning("  RTA stopped.")

        # ------------------------------------------------------------------ #
        # 6. Save the RTA data as a new measurement and retrieve its UUID
        # ------------------------------------------------------------------ #
        logger.warning("Saving RTA data as measurement...")
        uuid = await rew.save_rta()
        logger.warning("  Saved - UUID: %s", uuid)

        # ------------------------------------------------------------------ #
        # 7. Rename measurement to current date/time
        # ------------------------------------------------------------------ #
        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        title = f"RTA {timestamp}"
        logger.warning("Renaming measurement to '%s'...", title)
        await rew.measurements.set_title(uuid, title)

        # ------------------------------------------------------------------ #
        # 8. Add a note with output device and channel configuration
        # ------------------------------------------------------------------ #
        logger.warning("Reading output device and channel configuration...")
        try:
            output_device = await rew.audio.get_java_output_device()
        except KeyError as exc:
            output_device = f"(unavailable: {exc})"

        try:
            output_channel = await rew.audio.get_java_output_channel()
        except KeyError as exc:
            output_channel = f"(unavailable: {exc})"

        note = (
            f"Recorded: {timestamp}\n"
            f"Output device:  {output_device}\n"
            f"Output channel: {output_channel}\n"
            f"Signal: {GENERATOR_SIGNAL} @ {GENERATOR_LEVEL} dBFS\n"
            f"RTA averages: {RTA_MAX_AVERAGES}\n"
            f"Pre-measurement input levels: {_fmt_levels(pre_levels)}"
        )
        logger.warning("Setting measurement note...")
        await rew.measurements.set_notes(uuid, note)
        logger.warning("  Note:\n%s", note)

        # ------------------------------------------------------------------ #
        # 9. Post-measurement input level snapshot
        # ------------------------------------------------------------------ #
        post_levels = await rew.input_levels.get_last_levels()
        logger.warning("Post-measurement input levels: %s", _fmt_levels(post_levels))

        # Stop the input-levels monitor - we no longer need it.
        await rew.input_levels.stop_monitoring()

        # ------------------------------------------------------------------ #
        # 10. SPL meter: open, start, read, close
        # ------------------------------------------------------------------ #
        logger.warning("Opening SPL meter 1...")
        await rew.spl_meter.open(meter_id=1)
        await rew.spl_meter.start(meter_id=1)
        logger.warning("  Waiting %.1fs for a stable SPL reading...", SPL_WARMUP)
        await asyncio.sleep(SPL_WARMUP)

        spl = await rew.spl_meter.get_levels(meter_id=1)
        logger.warning(
            "  SPL meter reading: SPL=%.1f dB  Leq=%.1f dB  (weighting=%s, filter=%s)",
            spl.spl,
            spl.leq,
            spl.weighting,
            spl.filter,
        )

        await rew.spl_meter.stop(meter_id=1)
        await rew.spl_meter.close(meter_id=1)

        # ------------------------------------------------------------------ #
        # 11. Stop the signal generator
        # ------------------------------------------------------------------ #
        logger.warning("Stopping signal generator...")
        await rew.generator.stop()

        # ------------------------------------------------------------------ #
        # 12. Save measurements
        # ------------------------------------------------------------------ #
        logger.warning("Saving measurements...")
        cwd = Path.cwd()
        await rew.measurements.save_all(rf"{cwd}\test_files\rta.mdat", timestamp)
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # Summary
        # ------------------------------------------------------------------ #
        logger.warning("\n" + "=" * 60)  # noqa: G003
        logger.warning("Measurement complete.")
        logger.warning("  Title:          %s", title)
        logger.warning("  UUID:           %s", uuid)
        logger.warning("  Output device:  %s", output_device)
        logger.warning("  Output channel: %s", output_channel)
        logger.warning(
            "  Signal:         %s @ %.1f dBFS", GENERATOR_SIGNAL, GENERATOR_LEVEL
        )
        logger.warning("  RTA averages:   %d", RTA_MAX_AVERAGES)
        logger.warning("  Pre-levels:     %s", _fmt_levels(pre_levels))
        logger.warning("  Post-levels:    %s", _fmt_levels(post_levels))
        logger.warning(
            "  SPL:            %.1f dB (%s-weighted, %s)",
            spl.spl,
            spl.weighting,
            spl.filter,
        )
        logger.warning("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.WARNING)
    asyncio.run(main())
