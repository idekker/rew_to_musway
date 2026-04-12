"""
example_rta_measurement.py — RTA measurement workflow using aiorew.

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
import sys
import io
import os
from datetime import datetime

# Force UTF-8 output on cp1252 consoles (Windows), with line buffering so
# print() output appears immediately rather than at process exit.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from aiorew import REWClient, RTAConfiguration, GeneratorSignal

# ---------------------------------------------------------------------------
# Configuration — adjust as needed
# ---------------------------------------------------------------------------

REW_HOST = "localhost"
REW_PORT = 4735

GENERATOR_SIGNAL = GeneratorSignal.PINK_PERIODIC  # periodic pink noise — as returned by generator.get_signals()
GENERATOR_LEVEL = -12.0  # dBFS

RTA_MAX_AVERAGES = 100
GENERATOR_WARMUP = 3.0  # seconds to let the generator stabilise before reading levels
SPL_WARMUP = 1.5  # pause after starting SPL meter before reading


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_levels(levels) -> str:
    rms_str = ", ".join(f"{v:.1f}" for v in levels.rms)
    peak_str = ", ".join(f"{v:.1f}" for v in levels.peak)
    return f"RMS=[{rms_str}] Peak=[{peak_str}] {levels.unit}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    async with REWClient(host=REW_HOST, port=REW_PORT) as rew:

        # ------------------------------------------------------------------ #
        # 1. Delete all existing measurements
        # ------------------------------------------------------------------ #
        print("Deleting all existing measurements…")
        await rew.measurements.delete_all()
        print("  Done.")

        # ------------------------------------------------------------------ #
        # 2. Start input-levels monitor
        # ------------------------------------------------------------------ #
        print("Starting input-levels monitor…")
        await rew.input_levels.start_monitoring()
        print("  Done.")

        # ------------------------------------------------------------------ #
        # 3. Configure and start the signal generator
        # ------------------------------------------------------------------ #
        print(f"Setting signal to '{GENERATOR_SIGNAL}' at {GENERATOR_LEVEL} dBFS…")
        await rew.generator.set_signal(GENERATOR_SIGNAL)
        await rew.generator.set_level(GENERATOR_LEVEL)
        await rew.generator.play()
        print(f"  Generator playing.")

        # Wait for the generator output to stabilise before any level readings.
        print(f"Waiting {GENERATOR_WARMUP:.0f}s for generator to stabilise…")
        await asyncio.sleep(GENERATOR_WARMUP)

        # ------------------------------------------------------------------ #
        # 4. Snapshot pre-measurement input levels
        # ------------------------------------------------------------------ #
        pre_levels = await rew.input_levels.get_last_levels()
        print(f"  Pre-measurement input levels: {_fmt_levels(pre_levels)}")

        # ------------------------------------------------------------------ #
        # 5. Configure RTA for 100 averages and start
        # ------------------------------------------------------------------ #
        print(f"Configuring RTA: stopAt=True, stopAtValue={RTA_MAX_AVERAGES}…")
        await rew.rta.set_configuration(RTAConfiguration(
            stopAt=True,
            stopAtValue=RTA_MAX_AVERAGES,
            stopGeneratorWithRTA=False,  # we stop the generator ourselves below
        ))

        print("Starting RTA…")
        await rew.rta.start()
        print(f"  Waiting for {RTA_MAX_AVERAGES} averages to complete…")
        await rew.rta.wait_until_stopped()
        print("  RTA stopped.")

        # ------------------------------------------------------------------ #
        # 6. Save the RTA data as a new measurement and retrieve its UUID
        # ------------------------------------------------------------------ #
        print("Saving RTA data as measurement…")
        uuid = await rew.save_rta()
        print(f"  Saved - UUID: {uuid}")

        # ------------------------------------------------------------------ #
        # 7. Rename measurement to current date/time
        # ------------------------------------------------------------------ #
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = f"RTA {timestamp}"
        print(f"Renaming measurement to '{title}'…")
        await rew.measurements.set_title(uuid, title)

        # ------------------------------------------------------------------ #
        # 8. Add a note with output device and channel configuration
        # ------------------------------------------------------------------ #
        print("Reading output device and channel configuration…")
        try:
            output_device = await rew.audio.get_java_output_device()
        except Exception as exc:
            output_device = f"(unavailable: {exc})"

        try:
            output_channel = await rew.audio.get_java_output_channel()
        except Exception as exc:
            output_channel = f"(unavailable: {exc})"

        note = (
            f"Recorded: {timestamp}\n"
            f"Output device:  {output_device}\n"
            f"Output channel: {output_channel}\n"
            f"Signal: {GENERATOR_SIGNAL} @ {GENERATOR_LEVEL} dBFS\n"
            f"RTA averages: {RTA_MAX_AVERAGES}\n"
            f"Pre-measurement input levels: {_fmt_levels(pre_levels)}"
        )
        print("Setting measurement note…")
        await rew.measurements.set_notes(uuid, note)
        print(f"  Note:\n{note}")

        # ------------------------------------------------------------------ #
        # 9. Post-measurement input level snapshot
        # ------------------------------------------------------------------ #
        post_levels = await rew.input_levels.get_last_levels()
        print(f"Post-measurement input levels: {_fmt_levels(post_levels)}")

        # Stop the input-levels monitor — we no longer need it.
        await rew.input_levels.stop_monitoring()

        # ------------------------------------------------------------------ #
        # 10. SPL meter: open, start, read, close
        # ------------------------------------------------------------------ #
        print("Opening SPL meter 1…")
        await rew.spl_meter.open(meter_id=1)
        await rew.spl_meter.start(meter_id=1)
        print(f"  Waiting {SPL_WARMUP:.1f}s for a stable SPL reading…")
        await asyncio.sleep(SPL_WARMUP)

        spl = await rew.spl_meter.get_levels(meter_id=1)
        print(
            f"  SPL meter reading: "
            f"SPL={spl.spl:.1f} dB  "
            f"Leq={spl.leq:.1f} dB  "
            f"(weighting={spl.weighting}, filter={spl.filter})"
        )

        await rew.spl_meter.stop(meter_id=1)
        await rew.spl_meter.close(meter_id=1)

        # ------------------------------------------------------------------ #
        # 11. Stop the signal generator
        # ------------------------------------------------------------------ #
        print("Stopping signal generator…")
        await rew.generator.stop()

        # ------------------------------------------------------------------ #
        # 12. Save measurements
        # ------------------------------------------------------------------ #
        print("Saving measurements…")
        cwd = os.getcwd()
        await rew.measurements.save_all(fr"{cwd}\test_files\rta.mdat", timestamp)
        print("  Done.")

        # ------------------------------------------------------------------ #
        # Summary
        # ------------------------------------------------------------------ #
        print("\n" + "=" * 60)
        print("Measurement complete.")
        print(f"  Title:          {title}")
        print(f"  UUID:           {uuid}")
        print(f"  Output device:  {output_device}")
        print(f"  Output channel: {output_channel}")
        print(f"  Signal:         {GENERATOR_SIGNAL} @ {GENERATOR_LEVEL} dBFS")
        print(f"  RTA averages:   {RTA_MAX_AVERAGES}")
        print(f"  Pre-levels:     {_fmt_levels(pre_levels)}")
        print(f"  Post-levels:    {_fmt_levels(post_levels)}")
        print(f"  SPL:            {spl.spl:.1f} dB ({spl.weighting}-weighted, {spl.filter})")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
