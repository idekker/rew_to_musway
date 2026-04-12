"""
Layout constants for Tunest PC (TUNEST_PC_V1) UI Automation.

All positions are window-relative (pixels from top-left of M6Window).
Reference window size: W=1366, H=792.
Coordinates are used as hints only; actual element bounds are always
re-read from BoundingRectangle at call time.
"""

# ---------------------------------------------------------------------------
# Process / window identifiers
# ---------------------------------------------------------------------------
PROCESS_NAMES = ["TUNEST_PC_FULL.exe", "TUNEST_PC_V1"]  # searched in order
MAIN_WINDOW_CLASS = "Qt5152QWindowIcon"  # Qt5 wrapper; was "M6Window" on older builds
MAIN_WINDOW_TITLE = "TUNEST_PC_V1"  # fallback: find by title if class search fails
MODEL_DIALOG_CLASS = "ModelSelectionPanel"
RESET_EQ_DIALOG_CLASS = "Qt5152QWindowToolSaveBits"

# ---------------------------------------------------------------------------
# Timing (seconds)
# ---------------------------------------------------------------------------
LAUNCH_POLL_INTERVAL = 0.5
DEFAULT_LAUNCH_TIMEOUT = 15.0
CLICK_SLEEP = 0.05  # brief pause after every synthetic click
DIALOG_DISMISS_SLEEP = 0.5  # wait after file-dialog OK
COMBOBOX_EXPAND_SLEEP = 0.15

# ---------------------------------------------------------------------------
# Model selection dialog
# ---------------------------------------------------------------------------
# Each model button is an unnamed Group element.
# Grid origin (window-relative): X=40, Y=269; col-step=89px, row-step=40px
MODEL_GRID_ORIGIN = (40, 269)
MODEL_GRID_COL_STEP = 89
MODEL_GRID_ROW_STEP = 40
# Row 0 (Y=269)
MODEL_POSITIONS = {
    "M4": (0, 0),
    "M4+": (1, 0),
    "M6": (2, 0),
    "D8": (3, 0),
    "DSP68": (4, 0),
    "TUNE12": (5, 0),
    # Row 1 (Y=309)
    "M6PRO": (0, 1),
    "M12": (1, 1),
    "M5": (2, 1),
    "M10": (3, 1),
    "M8": (4, 1),
    "M4nano": (5, 1),
}
MODEL_ENTER_BUTTON_REL = (40, 347)  # "Enter" button inside ModelSelectionPanel

# ---------------------------------------------------------------------------
# Top-panel controls (window-relative)
# ---------------------------------------------------------------------------
# Master volume
MASTER_VOL_EDIT_REL = (1292, 68)
MASTER_MUTE_REL = (1292, 229)

# EQ section buttons
RESET_EQ_BTN_REL = (1130, 83)
BYPASS_EQ_BTN_REL = (1204, 83)
IMPORT_EQ_BTN_REL = (1130, 111)
PARAM_EQ_BTN_REL = (1130, 55)

# Channel selector checkboxes (CH1=index 0 .. CH8=index 7)
# Named '1' through '8' in UIA
CH_SELECTOR_BASE_REL = (888, 54)  # centre of CH1 checkbox
CH_SELECTOR_STEP_X = 26  # pixels between consecutive checkboxes

# ---------------------------------------------------------------------------
# Hi/Lo pass filter controls (window-relative)
# These apply to the currently-selected channel.
# ---------------------------------------------------------------------------
HP_TYPE_COMBO_REL = (1129, 308)
LP_TYPE_COMBO_REL = (1244, 308)
HP_FREQ_EDIT_REL = (1129, 370)
LP_FREQ_EDIT_REL = (1244, 370)
HP_SLOPE_COMBO_REL = (1129, 432)
LP_SLOPE_COMBO_REL = (1244, 432)

# ---------------------------------------------------------------------------
# Channel strip (bottom section, Y starts ~481 from window top)
# ---------------------------------------------------------------------------
# X offset (from window left) for the left edge of each channel group (1-indexed)
CHANNEL_X_OFFSETS = [8, 178, 348, 518, 688, 858, 1028, 1198]
CHANNEL_STRIP_TOP_Y = 511  # window-relative Y of the top of each channel group

# Offsets relative to (channel_left_x, CHANNEL_STRIP_TOP_Y):
CH_HEADER_OFFSET = (80, 14)  # click target inside channel header (centre)
CH_LEVEL_EDIT_OFFSET = (8, 33)
CH_MUTE_CB_OFFSET = (57, 61)  # narrow 28x22 button - Mute
CH_SOLO_CB_OFFSET = (8, 61)  # wide 47x24 button - Solo
CH_PHASE_CB_OFFSET = (57, 61)
CH_ZERO_DEG_CB_OFFSET = (8, 88)
CH_LINK_CB_OFFSET = (48, 88)
CH_DELAY_EDIT_OFFSET = (8, 116)

# BTL checkboxes (one per stereo pair, at window-relative X positions):
BTL_X_OFFSETS = [133, 473, 813, 1153]  # pairs 1+2, 3+4, 5+6, 7+8
BTL_Y_REL = 486  # window-relative Y

# ---------------------------------------------------------------------------
# EQ band table
# ---------------------------------------------------------------------------
# 31 bands; band N (1-based) label is a Text element named str(N).
# The label X ≈ column X.  Data fields are below the label:
#   Type combobox : label_y + 20
#   Freq edit     : label_y + 41
#   Q edit        : label_y + 62
#   Gain edit     : label_y + 83
#   Bypass cb     : label_y + 179
EQ_SECTION_TOP_Y = 282
EQ_BAND_LABEL_DY = 20  # label is ~20px below section top
EQ_FIELD_DY_TYPE = 20
EQ_FIELD_DY_FREQ = 41
EQ_FIELD_DY_Q = 62
EQ_FIELD_DY_GAIN = 83
EQ_FIELD_DY_BYPASS = 179

# ---------------------------------------------------------------------------
# Reset EQ dialog (CCResetEq), window-relative
# ---------------------------------------------------------------------------
RESET_EQ_SELECTED_CB_REL = (63, 73)  # "Reset selected channels"
RESET_EQ_ALL_CB_REL = (63, 123)  # "Reset all channels"
RESET_EQ_OK_BTN_REL = (86, 200)
RESET_EQ_CANCEL_BTN_REL = (230, 200)

# ---------------------------------------------------------------------------
# Windows messages (for file dialog automation)
# ---------------------------------------------------------------------------
WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
