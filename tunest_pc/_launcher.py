"""Process discovery, launch, and main-window wait loop for Tunest PC."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import time

import psutil

from ._automation import (
    TunestAutomationError,
    _send_click,
    element_from_hwnd,
    get_rect,
    hwnd_from_class,
)
from ._constants import (
    CLICK_SLEEP,
    DEFAULT_LAUNCH_TIMEOUT,
    LAUNCH_POLL_INTERVAL,
    MAIN_WINDOW_CLASS,
    MAIN_WINDOW_TITLE,
    MODEL_ENTER_BUTTON_REL,
    MODEL_GRID_COL_STEP,
    MODEL_GRID_ORIGIN,
    MODEL_GRID_ROW_STEP,
    MODEL_POSITIONS,
    PROCESS_NAMES,
)

MAIN_WINDOW_WIDTH = 1300

logger = logging.getLogger(__name__)


class TunestConnectionError(Exception):
    """Raised when the app cannot be connected to within the timeout."""


# ---------------------------------------------------------------------------
# Process lookup
# ---------------------------------------------------------------------------


def _find_process_pid() -> int | None:
    """Return the PID of a running Tunest PC process, or None."""
    for proc in psutil.process_iter(["pid", "name"]):
        name = proc.info.get("name") or ""
        for target in PROCESS_NAMES:
            if name.lower().startswith(target.lower().removesuffix(".exe").rstrip("*")):
                return proc.info["pid"]
    return None


# ---------------------------------------------------------------------------
# Model selection helper
# ---------------------------------------------------------------------------


def _click_model_button(dialog_hwnd: int, model: str) -> None:
    """Click the model button for *model* inside the model-selection window.

    The model selection UI is rendered inside the main Qt5152QWindowIcon window
    while it is in its 600x400 startup state - there is no separate HWND.
    """
    if model not in MODEL_POSITIONS:
        exception = f"Unknown model {model!r}. Known: {list(MODEL_POSITIONS)}"
        raise TunestAutomationError(exception)
    col, row = MODEL_POSITIONS[model]
    origin_x, origin_y = MODEL_GRID_ORIGIN
    # Click centre of the model cell
    rel_x = origin_x + col * MODEL_GRID_COL_STEP + MODEL_GRID_COL_STEP // 2
    rel_y = origin_y + row * MODEL_GRID_ROW_STEP + MODEL_GRID_ROW_STEP // 2

    elem = element_from_hwnd(dialog_hwnd)
    l, t, _, _ = get_rect(elem)  # noqa: E741

    # Bring window to foreground so SendInput is delivered to it.
    ctypes.windll.user32.SetForegroundWindow(dialog_hwnd)
    time.sleep(0.4)

    _send_click(l + rel_x, t + rel_y)
    time.sleep(0.3)

    # Click the Enter button - use centre of its full width (40..562 -> cx=301)
    enter_x = (MODEL_ENTER_BUTTON_REL[0] + 562) // 2  # ≈ 301
    enter_y = MODEL_ENTER_BUTTON_REL[1] + 14  # centre vertically (H=28)
    _send_click(l + enter_x, t + enter_y)
    time.sleep(CLICK_SLEEP * 3)


# ---------------------------------------------------------------------------
# Launch & connect
# ---------------------------------------------------------------------------


def launch_and_connect(
    exe_path: str,
    model: str = "M6",
    launch_if_needed: bool = True,  # noqa: FBT001,FBT002
    timeout: float = DEFAULT_LAUNCH_TIMEOUT,
) -> int:
    """Ensure Tunest PC is running and return the HWND of the main window.

    Flow:
    1. If the main window already exists, return it immediately.
    2. If no process is running and launch_if_needed, start it.
    3. Poll until the main window appears (or timeout).
       - If ModelSelectionPanel appears first, click the correct model + Enter.

    Returns:
        int: HWND of the main window.

    Raises:
        TunestConnectionError: if the window doesn't appear within *timeout*.
        FileNotFoundError: if *exe_path* doesn't exist when launch is needed.

    """
    # Fast path: main window already up and fully loaded
    hwnd = _find_main_hwnd()
    if hwnd and _is_main_ready(hwnd):
        return hwnd

    pid = _find_process_pid()
    if pid is None:
        if not launch_if_needed:
            exception = "Tunest PC is not running and launch_if_needed=False"
            raise TunestConnectionError(exception)
        subprocess.Popen([exe_path])  # noqa: S603

    _model_clicked = False
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        hwnd = _find_main_hwnd()
        if hwnd:
            if _is_main_ready(hwnd):
                # Window is fully loaded - done.
                return hwnd

            # Window exists but is still small: this IS the model-selection
            # screen (renders inside the same Qt window at 600x400 before
            # growing to 1366x792 once a model is confirmed).
            if not _model_clicked:
                try:
                    _click_model_button(hwnd, model)
                    _model_clicked = True
                except TunestAutomationError:
                    pass  # still loading, retry next iteration

        time.sleep(LAUNCH_POLL_INTERVAL)

    exception = f"Tunest PC main window (class={MAIN_WINDOW_CLASS!r}, title={MAIN_WINDOW_TITLE!r}) did not appear within {timeout:.1f}s"
    raise TunestConnectionError(exception)


def _find_main_hwnd() -> int | None:
    return hwnd_from_class(MAIN_WINDOW_CLASS, title=MAIN_WINDOW_TITLE)


def _is_main_ready(hwnd: int) -> bool:
    """Return True once the main window has reached its full size (≥1300 px wide)."""
    try:
        elem = element_from_hwnd(hwnd)
        l, _, r, _ = get_rect(elem)  # noqa: E741
        return (r - l) >= MAIN_WINDOW_WIDTH
    except Exception as exc:  # noqa: BLE001
        msg = f"Error checking main window size: {exc}"
        logger.fatal(msg)
        return False
