"""example_eq_filters.py - EQ filter workflow using aiorew.

Workflow
--------
 1. Delete all existing measurements.
 2. Load test_files/measurement_for_eq.mdat.
 3. Set the equaliser to Musway, model "M DSP 31 Band".
 4. Set EQ target settings: Full range shape, house curve from
    test_files/house_curve.txt, target level calculated from response.
 5. Set match-target settings: 40-20000 Hz range, 6 dB individual and
    overall max boost, 1 dB flatness target, low/high shelf -6 to +6 dB,
    allow narrow filters below 200 Hz, vary max Q above 200 Hz.
 6. Match response to target (polls until complete).
 7. Save filter settings to test_files/<title>.txt.
 8. Generate predicted measurement from EQ.
 9. Save all measurements to test_files/after_eq.mdat.

Run with:
    python example_eq_filters.py
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

from aiorew import (
    ArithmeticFunction,
    Equaliser,
    FilterSetting,
    MatchTargetSettings,
    REWClient,
    Smoothing,
    TargetShape,
)

# Force UTF-8 output on cp1252 consoles (Windows), with line buffering so
# logger.warning() output appears immediately rather than at process exit.
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REW_HOST = "localhost"
REW_PORT = 4735

# Script directory - paths are resolved relative to it
SCRIPT_DIR = Path(__file__).parent
TEST_FILES = SCRIPT_DIR / "test_files"

MDAT_INPUT = TEST_FILES / "measurement_for_eq.mdat"
HOUSE_CURVE = TEST_FILES / "house_curve.txt"
FILTER_OUTPUT = TEST_FILES / "filter.json"
MDAT_OUTPUT = TEST_FILES / "after_eq.mdat"

EQ_MANUFACTURER = "Musway"
EQ_MODEL = "31 bands (Output)"

# Match-target limits
MATCH_START_HZ = 40.0
MATCH_END_HZ = 20_000.0
MATCH_INDIVIDUAL_BOOST = 6.0  # dB
MATCH_OVERALL_BOOST = 6.0  # dB
MATCH_FLATNESS = 1.0  # dB
SHELF_MIN = -6.0  # dB
SHELF_MAX = 6.0  # dB

logger = logging.getLogger(__name__)


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
        # 2. Load measurement file
        # ------------------------------------------------------------------ #
        mdat_path = str(MDAT_INPUT).replace("\\", "/")
        logger.warning("Loading '%s'...", MDAT_INPUT.name)
        await rew.measurements.load(mdat_path)
        # Give REW a moment to finish loading before listing
        await asyncio.sleep(1.0)

        measurements = await rew.measurements.list()
        if not measurements:
            msg = (
                f"No measurements found after loading '{mdat_path}'. "
                "Check the file path and that REW has finished loading."
            )
            raise RuntimeError(msg)
        m = measurements[0]
        uuid = m.uuid
        logger.warning("  Loaded: '%s'  UUID: %s", m.title, uuid)

        logger.warning("Apply 1/6th smoothing...")
        await rew.measurements.apply_smoothing(uuid, Smoothing.S6)

        # ------------------------------------------------------------------ #
        # 3. Set equaliser to Musway M DSP 31 Band
        # ------------------------------------------------------------------ #
        logger.warning("Setting equaliser to %s / %s...", EQ_MANUFACTURER, EQ_MODEL)
        await rew.measurements.set_equaliser(
            uuid,
            Equaliser(
                manufacturer=EQ_MANUFACTURER,
                model=EQ_MODEL,
            ),
        )
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # 4. EQ target settings
        #    - Shape: Full range
        #    - House curve: test_files/house_curve.txt
        #    - Target level: calculated from response (via EQ command below)
        # ------------------------------------------------------------------ #

        # 4a. Read current target settings so we only change the shape field
        logger.warning("Reading current target settings...")
        target = await rew.measurements.get_target_settings(uuid)
        logger.warning("  Current shape: %s", target.shape)

        if target.shape != TargetShape.FULL_RANGE:
            logger.warning("Setting target shape to 'Full range'...")
            target.shape = TargetShape.FULL_RANGE
            await rew.measurements.set_target_settings(uuid, target)
            logger.warning("  Done.")

        # 4b. Set the house curve file (global EQ default, applies to all measurements)
        house_curve_path = str(HOUSE_CURVE).replace("\\", "/")
        logger.warning("Setting house curve to '%s'...", HOUSE_CURVE.name)
        await rew.eq.set_house_curve(house_curve_path, log_interpolation=True)
        logger.warning("  Done.")

        # 4c. Calculate target level from the measurement response
        logger.warning("Calculating target level from response...")
        await rew.measurements.calculate_target_level(uuid)
        target_level = await rew.measurements.get_target_level(uuid)
        logger.warning("  Target level: %.1f", target_level)

        # ------------------------------------------------------------------ #
        # 5. Set match-target settings
        # ------------------------------------------------------------------ #
        logger.warning("Configuring match-target settings...")
        await rew.eq.set_match_target_settings(
            MatchTargetSettings(
                startFrequency=MATCH_START_HZ,
                endFrequency=MATCH_END_HZ,
                individualMaxBoostdB=MATCH_INDIVIDUAL_BOOST,
                overallMaxBoostdB=MATCH_OVERALL_BOOST,
                flatnessTargetdB=MATCH_FLATNESS,
                allowNarrowFiltersBelow200Hz=True,
                varyQAbove200Hz=True,
                allowLowShelf=True,
                lowShelfMin=SHELF_MIN,
                lowShelfMax=SHELF_MAX,
                allowHighShelf=True,
                highShelfMin=SHELF_MIN,
                highShelfMax=SHELF_MAX,
            )
        )
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # 6. Match response to target
        # ------------------------------------------------------------------ #
        logger.warning("Matching response to target (this may take a moment)...")
        await rew.measurements.match_target(uuid)

        # ------------------------------------------------------------------ #
        # 7. Save filter settings to test_files/<title>.txt
        # ------------------------------------------------------------------ #
        logger.warning("Saving filters to '%s'...", FILTER_OUTPUT)
        # Read back filters for a quick report
        filters = await rew.measurements.get_filters(uuid)
        active_filters = [f for f in filters if f.type != "None"]
        _write_filter_json(FILTER_OUTPUT, active_filters, EQ_MODEL, "All channels")

        # ------------------------------------------------------------------ #
        # 8. Generate predicted measurement from EQ
        # ------------------------------------------------------------------ #
        logger.warning("Generating predicted measurement...")
        results = await rew.measurements.generate_predicted_measurement(uuid)
        logger.warning("  Result: %r", results)

        results = await rew.measurements.arithmetic(
            [uuid, UUID(results["2"]["UUID"])], ArithmeticFunction.A_MIN_B
        )
        logger.warning("  Result: %r", results)

        # ------------------------------------------------------------------ #
        # 9. Save all measurements to test_files/after_eq.mdat
        # ------------------------------------------------------------------ #
        mdat_out_str = str(MDAT_OUTPUT).replace("\\", "/")
        logger.warning("Saving all measurements to '%s'...", MDAT_OUTPUT.name)
        await rew.measurements.save_all(mdat_out_str)
        logger.warning("  Done.")

        # ------------------------------------------------------------------ #
        # Summary
        # ------------------------------------------------------------------ #

        logger.warning("\n" + "=" * 60)  # noqa: G003
        logger.warning("EQ filter workflow complete.")
        logger.warning("  Measurement:    %s", m.title)
        logger.warning("  UUID:           %s", uuid)
        logger.warning("  Equaliser:      %s / %s", EQ_MANUFACTURER, EQ_MODEL)
        logger.warning("  House curve:    %s", HOUSE_CURVE.name)
        logger.warning("  Match range:    %.0f - %.0f Hz", MATCH_START_HZ, MATCH_END_HZ)
        logger.warning("  Active filters: %d / %d", len(active_filters), len(filters))
        logger.warning("  Filters saved:  %s", FILTER_OUTPUT.name)
        logger.warning("  Output .mdat:   %s", MDAT_OUTPUT.name)
        logger.warning("  Filters:")
        for f in active_filters:
            logger.warning(
                "  [%d]: %s, %.1fHz, %.1fdB, %.2f",
                f.index,
                f.type,
                f.frequency,
                f.gaindB,
                f.q,
            )

        logger.warning("=" * 60)


def _write_filter_json(
    path: Path, filters: list[FilterSetting], model: str, channel: str
) -> None:
    with path.open("w") as file:
        eqs = []
        for f in filters:
            eq = {
                "number": f.index,
                "type": f.type,
                "freq": round(f.frequency, 1),
                "gain": round(f.gaindB, 1),
                "q": round(f.q, 2),
            }
            eqs.append(eq)

        doc = {
            "model": model,
            "location": channel,
            "fileMagic": "autoIIR",
            "eq": eqs,
        }

        json.dump(doc, file, indent=2)


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.WARNING)
    asyncio.run(main())
