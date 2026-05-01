import io
import sys
from pathlib import Path

from musway import Musway, MuswayUnknownWindowStateError

# Force UTF-8 output so arrow / ellipsis characters don't crash on cp1252 consoles.
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

# Adjust this path to your Tunest PC installation.
EXE_PATH = r"D:\Program Files (x86)\TUNEST PC\Musway Software-240813.exe"

# Path to an EQ preset JSON file to import (edit as needed).
PRESET_PATH = r"F:\Personal\Ino\SynologyDrive\Hobby\MuswayPresetEditor\test_files\default_preset.txt"


def main() -> None:
    m = Musway()

    # ------------------------------------------------------------------ #
    # 1. Connect
    # ------------------------------------------------------------------ #
    print("Connecting to Tunest PC...")
    try:
        m.connect(EXE_PATH)
    except MuswayUnknownWindowStateError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}")
        sys.exit(1)
    print("Connected.")

    # ------------------------------------------------------------------ #
    # 2. Read master mute
    # ------------------------------------------------------------------ #
    mute = m.get_master_mute()
    print(f"Current master mute: {mute}")

    # ------------------------------------------------------------------ #
    # 3. Mute channel 3
    # ------------------------------------------------------------------ #
    print("Muting CH3...")
    m.set_channel_mute(3, mute=True)
    print(f"  CH3 muted: {m.get_channel_mute(3)}")

    # ------------------------------------------------------------------ #
    # 4. Load preset
    #    (skip if the file doesn't exist - just a demo)
    # ------------------------------------------------------------------ #

    preset = Path(PRESET_PATH)
    if preset.is_file():
        print(f"Load preset from {PRESET_PATH}...")
        m.load_preset(preset)
        print("  Done.")
    else:
        print(f"(Skipping load_preset - file not found: {PRESET_PATH})")

    # ------------------------------------------------------------------ #
    # 5. Select CH2
    # ------------------------------------------------------------------ #
    print("Select channel 2...")
    m.select_channel(2)
    print(f"  -> {m.is_channel_selected(2)}")

    # ------------------------------------------------------------------ #
    # 6. Unmute master
    # ------------------------------------------------------------------ #
    print("Unmute master...")
    m.set_master_mute(mute=False)
    print(f"  -> {m.get_master_mute()}")

    print("\nDone.")


if __name__ == "__main__":
    main()
