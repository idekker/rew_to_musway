"""example_tunest_pc.py - demonstration of the tunest_pc automation library.

Scenario:
  1. Connect to Tunest PC (launches it if not already running).
  2. Read and logger.warning the master volume.
  3. Set master volume to -6dB.
  4. Configure channel 1 as a subwoofer (low-pass at 80 Hz, 24 dB/oct LR).
  5. Configure channel 2 as a tweeter (high-pass at 4000 Hz, 24 dB/oct LR).
  6. Mute channel 3.
  7. Import an EQ preset JSON file to channel 1.
  8. Bypass EQ briefly, then restore it.
  9. Reset EQ on selected channels.
 10. Restore master volume to 0dB.
 11. Set master mute to True.
 12. Set channel 6 volume to -3dB.

Run with:
    python example_tunest_pc.py
"""

import io
import logging
import sys
import time
from pathlib import Path

from tunest_pc import FilterSlope, FilterType, TunestConnectionError, TunestPC

# Force UTF-8 output so arrow / ellipsis characters don't crash on cp1252 consoles.
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

# Adjust this path to your Tunest PC installation.
EXE_PATH = r"D:\Program Files (x86)\TUNEST PC\TUNEST_PC_FULL.exe"

# Path to an EQ preset JSON file to import (edit as needed).
EQ_PRESET_PATH = r"F:\Personal\Ino\SynologyDrive\Hobby\DSP\Ioniq 5\20260411\lf.json"

logger = logging.getLogger(__name__)


def main() -> None:  # noqa: PLR0915
    t = TunestPC()

    # ------------------------------------------------------------------ #
    # 1. Connect
    # ------------------------------------------------------------------ #
    logger.warning("Connecting to Tunest PC...")
    try:
        t.connect(EXE_PATH, model="M6", launch_if_needed=True, timeout=20.0)
    except TunestConnectionError as e:
        logger.warning("ERROR: %s", e)
        sys.exit(1)
    logger.warning("Connected.")

    # ------------------------------------------------------------------ #
    # 2. Read master volume
    # ------------------------------------------------------------------ #
    vol = t.get_master_volume()
    logger.warning("Current master volume: %.1f dB", vol)

    # ------------------------------------------------------------------ #
    # 3. Set master volume to -6 dB
    # ------------------------------------------------------------------ #
    logger.warning("Setting master volume to -6dB...")
    t.set_master_volume(-6)
    time.sleep(0.5)
    logger.warning("  -> %.1f", t.get_master_volume())

    # ------------------------------------------------------------------ #
    # 4. CH1: subwoofer - low-pass 80 Hz, 24 dB/oct Linkwitz-Riley
    # ------------------------------------------------------------------ #
    logger.warning("CH1: setting low-pass filter (80 Hz, LR 24 dB/oct)...")
    t.set_lowpass(
        channel=1,
        filter_type=FilterType.LINKWITZ_RILEY,
        freq="80",
        slope=FilterSlope.DB24,
    )

    # ------------------------------------------------------------------ #
    # 5. CH2: tweeter - high-pass 4 kHz, 24 dB/oct Linkwitz-Riley
    # ------------------------------------------------------------------ #
    logger.warning("CH2: setting high-pass filter (4000 Hz, LR 24 dB/oct)...")
    t.set_highpass(
        channel=2,
        filter_type=FilterType.LINKWITZ_RILEY,
        freq="4000",
        slope=FilterSlope.DB24,
    )

    # ------------------------------------------------------------------ #
    # 6. Mute channel 3
    # ------------------------------------------------------------------ #
    logger.warning("Muting CH3...")
    t.set_channel_mute(3, muted=True)
    time.sleep(0.3)
    logger.warning("  CH3 muted: %s", t.get_channel_mute(3))

    # ------------------------------------------------------------------ #
    # 7. Import EQ preset to channel 1
    #    (skip if the file doesn't exist - just a demo)
    # ------------------------------------------------------------------ #

    if Path(EQ_PRESET_PATH).is_file():
        logger.warning("Importing EQ preset to CH1 from %s...", EQ_PRESET_PATH)
        t.import_eq(channel=1, json_path=EQ_PRESET_PATH)
        logger.warning("  Done.")
    else:
        logger.warning("(Skipping import_eq - file not found: %s)", EQ_PRESET_PATH)

    # ------------------------------------------------------------------ #
    # 8. Bypass EQ briefly, then restore
    # ------------------------------------------------------------------ #
    logger.warning("Bypassing EQ...")
    t.bypass_eq()
    time.sleep(1.0)
    logger.warning("Restoring EQ...")
    t.restore_eq()
    time.sleep(0.3)

    # ------------------------------------------------------------------ #
    # 9. Reset EQ (selected channels only)
    # ------------------------------------------------------------------ #
    logger.warning("Resetting EQ (selected channels)...")
    t.reset_eq(selected_only=True)
    time.sleep(0.3)

    # ------------------------------------------------------------------ #
    # 10. Restore master volume to 0 dB
    # ------------------------------------------------------------------ #
    logger.warning("Restoring master volume to 0dB...")
    t.set_master_volume(0)
    time.sleep(0.3)
    logger.warning("  -> %.1f", t.get_master_volume())

    # Unmute channel 3
    t.set_channel_mute(3, muted=False)

    # ------------------------------------------------------------------ #
    # 11. Set master mute
    # ------------------------------------------------------------------ #
    logger.warning("Set master mute...")
    t.set_master_mute(True)
    time.sleep(0.3)
    logger.warning("  -> %s", t.get_master_mute())

    # ------------------------------------------------------------------ #
    # 12. Set volume on channel 6
    # ------------------------------------------------------------------ #
    logger.warning("Set volume channel 6...")
    t.set_channel_level(6, -3)
    time.sleep(0.3)
    logger.warning("  -> %.1f", t.get_channel_level(6))

    logger.warning("\nDone.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
