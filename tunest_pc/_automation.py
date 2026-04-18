"""Low-level UI Automation helpers for Tunest PC.

Wraps comtypes-based UIA, win32api mouse/keyboard, and pywin32 for file
dialogs.  All public functions raise TunestAutomationError on failure.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from typing import TYPE_CHECKING, Any

import comtypes
import comtypes.client
import win32gui

from ._constants import (
    CLICK_SLEEP,
    COMBOBOX_EXPAND_SLEEP,
    DIALOG_DISMISS_SLEEP,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# COM initialisation
# ---------------------------------------------------------------------------
# Generate / cache the UIA type-lib wrapper on first import.
comtypes.client.GetModule("UIAutomationCore.dll")
import comtypes.gen.UIAutomationClient as UIAC  # noqa: E402,N817  (must be after GetModule)

if TYPE_CHECKING:
    from _ctypes import Array


class TunestAutomationError(Exception):
    """Raised when a UI Automation operation fails."""


# ---------------------------------------------------------------------------
# UIA singleton
# ---------------------------------------------------------------------------
_uia: UIAC.IUIAutomation | None = None


def get_uia() -> UIAC.IUIAutomation | Any:
    """Return (or create) the IUIAutomation COM object."""
    global _uia  # noqa: PLW0603
    if _uia is None:
        _uia = comtypes.client.CreateObject(
            UIAC.CUIAutomation._reg_clsid_,
            interface=UIAC.IUIAutomation,
        )
    return _uia


# ---------------------------------------------------------------------------
# Window / element finders
# ---------------------------------------------------------------------------

FILENAME_EDIT_COMBOBOX_WIDTH = 400


def hwnd_from_class(window_class: str, title: str | None = None) -> int | None:
    """Return the HWND of the main top-level window for Tunest PC.

    When *title* is provided, both class AND title must match.
    When only *window_class* is given, class alone must match.
    Always prefers the visible window with the largest area.
    """
    candidates: list[tuple[int, int, int]] = []  # (sort_key, hwnd, visible)

    def _cb(hwnd: int, _: object) -> None:
        cls = win32gui.GetClassName(hwnd)
        wtitle = win32gui.GetWindowText(hwnd)
        if cls != window_class:
            return
        if title is not None and wtitle != title:
            return
        r = win32gui.GetWindowRect(hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]
        vis = 1 if win32gui.IsWindowVisible(hwnd) else 0
        # Sort key: visible first, then by area
        candidates.append((vis * 10_000_000 + w * h, hwnd, vis))

    win32gui.EnumWindows(_cb, None)

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def element_from_hwnd(hwnd: int) -> UIAC.IUIAutomationElement:
    """Return the UIA element for a given HWND."""
    uia = get_uia()
    elem = uia.ElementFromHandle(hwnd)
    if elem is None:
        msg = f"No UIA element for HWND {hwnd:#010x}"
        raise TunestAutomationError(msg)
    return elem


def find_child(
    parent: UIAC.IUIAutomationElement,
    control_type: int,
    name: str | None = None,
    max_wait: float = 5.0,
    poll: float = 0.1,
) -> UIAC.IUIAutomationElement:
    """Search *parent*'s entire subtree for an element with the given *control_type* (UIA_* constant) and optional *name*.

    Polls up to *max_wait* seconds.  Raises TunestAutomationError on timeout.
    """
    uia = get_uia()
    conditions = [
        uia.CreatePropertyCondition(UIAC.UIA_ControlTypePropertyId, control_type)
    ]
    if name is not None:
        conditions.append(uia.CreatePropertyCondition(UIAC.UIA_NamePropertyId, name))

    if len(conditions) == 1:
        condition = conditions[0]
    else:
        condition = uia.CreateAndCondition(conditions[0], conditions[1])

    deadline = time.monotonic() + max_wait
    while True:
        elem = parent.FindFirst(UIAC.TreeScope_Descendants, condition)
        if elem is not None:
            return elem
        if time.monotonic() >= deadline:
            desc = f"ControlType={control_type}"
            if name:
                desc += f" Name={name!r}"
            msg = f"Timed out waiting for element: {desc}"
            raise TunestAutomationError(msg)
        time.sleep(poll)


def find_all_children(
    parent: UIAC.IUIAutomationElement,
    control_type: int,
    name: str | None = None,
) -> list[UIAC.IUIAutomationElement]:
    """Return all matching descendants (no wait)."""
    uia = get_uia()
    conditions = [
        uia.CreatePropertyCondition(UIAC.UIA_ControlTypePropertyId, control_type)
    ]
    if name is not None:
        conditions.append(uia.CreatePropertyCondition(UIAC.UIA_NamePropertyId, name))
    if len(conditions) == 1:
        condition = conditions[0]
    else:
        condition = uia.CreateAndCondition(conditions[0], conditions[1])

    result = parent.FindAll(UIAC.TreeScope_Descendants, condition)
    if result is None:
        return []
    return [result.GetElement(i) for i in range(result.Length)]


# ---------------------------------------------------------------------------
# Bounding rect helpers
# ---------------------------------------------------------------------------


def get_rect(elem: UIAC.IUIAutomationElement) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) screen coords of *elem*."""
    r = elem.CurrentBoundingRectangle
    return r.left, r.top, r.right, r.bottom


def centre(elem: UIAC.IUIAutomationElement) -> tuple[int, int]:
    """Return screen (x, y) of element centre."""
    l, t, r, b = get_rect(elem)  # noqa: E741
    return (l + r) // 2, (t + b) // 2


# ---------------------------------------------------------------------------
# Mouse / keyboard primitives
# ---------------------------------------------------------------------------

_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):  # noqa: N801
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("_", _INPUT_UNION)]


_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_ABSOLUTE = 0x8000
_KEYEVENTF_KEYUP = 0x0002

_VK_RETURN = 0x0D

_SM_CXSCREEN = 0
_SM_CYSCREEN = 1


def _screen_to_absolute(x: int, y: int) -> tuple[int, int]:
    sw = ctypes.windll.user32.GetSystemMetrics(_SM_CXSCREEN)
    sh = ctypes.windll.user32.GetSystemMetrics(_SM_CYSCREEN)
    return (x * 65535) // sw, (y * 65535) // sh


def _send_click(screen_x: int, screen_y: int) -> None:
    """Move mouse to absolute screen position and left-click."""
    ax, ay = _screen_to_absolute(screen_x, screen_y)

    inputs = (_INPUT * 3)(
        _INPUT(
            type=_INPUT_MOUSE,
            _=_INPUT_UNION(
                mi=_MOUSEINPUT(
                    dx=ax,
                    dy=ay,
                    mouseData=0,
                    dwFlags=_MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        ),
        _INPUT(
            type=_INPUT_MOUSE,
            _=_INPUT_UNION(
                mi=_MOUSEINPUT(
                    dx=ax,
                    dy=ay,
                    mouseData=0,
                    dwFlags=_MOUSEEVENTF_LEFTDOWN | _MOUSEEVENTF_ABSOLUTE,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        ),
        _INPUT(
            type=_INPUT_MOUSE,
            _=_INPUT_UNION(
                mi=_MOUSEINPUT(
                    dx=ax,
                    dy=ay,
                    mouseData=0,
                    dwFlags=_MOUSEEVENTF_LEFTUP | _MOUSEEVENTF_ABSOLUTE,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        ),
    )
    ctypes.windll.user32.SendInput(3, inputs, ctypes.sizeof(_INPUT))
    time.sleep(CLICK_SLEEP)


def _send_key(vk: int) -> None:
    """Send a key-down + key-up for virtual key *vk*."""
    inputs = (_INPUT * 2)(
        _INPUT(
            type=_INPUT_KEYBOARD,
            _=_INPUT_UNION(
                ki=_KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
            ),
        ),
        _INPUT(
            type=_INPUT_KEYBOARD,
            _=_INPUT_UNION(
                ki=_KEYBDINPUT(
                    wVk=vk, wScan=0, dwFlags=_KEYEVENTF_KEYUP, time=0, dwExtraInfo=None
                )
            ),
        ),
    )
    ctypes.windll.user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))
    time.sleep(CLICK_SLEEP)


# ---------------------------------------------------------------------------
# Higher-level UIA interactions
# ---------------------------------------------------------------------------


def _get_pattern(
    elem: UIAC.IUIAutomationElement,
    pattern_id: int,
    iface_type: type,
) -> object | None:
    """Safely retrieve a UIA pattern interface from *elem*.

    comtypes returns an IUnknown-level POINTER from GetCurrentPattern(); we
    must use comtypes.cast to get the correctly typed interface pointer.
    Returns None if the pattern is not supported (null pointer).
    """
    raw = elem.GetCurrentPattern(pattern_id)
    if raw is None:
        return None
    try:
        ptr = comtypes.cast(raw, comtypes.POINTER(iface_type))
        if ptr:
            return ptr
    except Exception as exc:  # noqa: BLE001
        msg = f"Error casting pattern {pattern_id} to {iface_type}: {exc}"
        logger.fatal(msg)
        return None
    else:
        return None


def click_element(elem: UIAC.IUIAutomationElement) -> None:
    """Click the centre of a UIA element."""
    sx, sy = centre(elem)
    _send_click(sx, sy)


def click_at_rel(window_hwnd: int, rel_x: int, rel_y: int) -> None:
    """Click at a position relative to *window_hwnd*'s client area top-left.

    Converts to screen coords using GetWindowRect (includes title bar/border).
    We use the window element bounding rect to stay consistent with UIA coords.
    """
    elem = element_from_hwnd(window_hwnd)
    l, t, _, _ = get_rect(elem)  # noqa: E741
    _send_click(l + rel_x, t + rel_y)


def get_value(elem: UIAC.IUIAutomationElement) -> str:
    """Read the ValuePattern value from an element."""
    vp = _get_pattern(elem, UIAC.UIA_ValuePatternId, UIAC.IUIAutomationValuePattern)
    if vp is None:
        msg = "Element does not support ValuePattern"
        raise TunestAutomationError(msg)
    return vp.CurrentValue


def set_value(elem: UIAC.IUIAutomationElement, value: str) -> None:
    """Set an edit field via ValuePattern.SetValue, then confirm with Enter."""
    vp = _get_pattern(elem, UIAC.UIA_ValuePatternId, UIAC.IUIAutomationValuePattern)
    if vp is None:
        msg = "Element does not support ValuePattern"
        raise TunestAutomationError(msg)
    vp.SetValue(value)
    time.sleep(CLICK_SLEEP)
    _send_key(_VK_RETURN)


def get_toggle_state(elem: UIAC.IUIAutomationElement) -> int:
    """Return TogglePattern.CurrentToggleState (0=off, 1=on, 2=indeterminate)."""
    tp = _get_pattern(elem, UIAC.UIA_TogglePatternId, UIAC.IUIAutomationTogglePattern)
    if tp is None:
        msg = "Element does not support TogglePattern"
        raise TunestAutomationError(msg)
    return tp.CurrentToggleState


def set_toggle(elem: UIAC.IUIAutomationElement, desired: bool) -> None:  # noqa: FBT001
    """Set a checkbox to the desired state (True=checked / on)."""
    current = get_toggle_state(elem)
    # ToggleState_On == 1  # noqa: ERA001
    if bool(current == 1) != desired:
        click_element(elem)
        time.sleep(CLICK_SLEEP)


def invoke_element(elem: UIAC.IUIAutomationElement) -> None:
    """Invoke (click) a button via InvokePattern, falling back to mouse click."""
    ip = _get_pattern(elem, UIAC.UIA_InvokePatternId, UIAC.IUIAutomationInvokePattern)
    if ip is None:
        click_element(elem)
        return
    ip.Invoke()
    time.sleep(CLICK_SLEEP)


# ---------------------------------------------------------------------------
# ComboBox helper
# ---------------------------------------------------------------------------


def set_combobox(
    combo_elem: UIAC.IUIAutomationElement,
    target_value: str,
) -> None:
    """Expand a combobox, find the list item named *target_value*, and select it.

    Falls back to ValuePattern.SetValue if ExpandCollapse is not supported.
    """
    # Try ExpandCollapsePattern
    ecp = _get_pattern(
        combo_elem,
        UIAC.UIA_ExpandCollapsePatternId,
        UIAC.IUIAutomationExpandCollapsePattern,
    )
    if ecp is not None:
        ecp.Expand()
        time.sleep(COMBOBOX_EXPAND_SLEEP)

        # Find the list item
        uia = get_uia()
        name_cond = uia.CreatePropertyCondition(UIAC.UIA_NamePropertyId, target_value)
        item = combo_elem.FindFirst(UIAC.TreeScope_Subtree, name_cond)
        if item is None:
            ecp.Collapse()
            msg = f"ComboBox item {target_value!r} not found"
            raise TunestAutomationError(msg)
        click_element(item)
        return

    # Fallback: ValuePattern  # noqa: ERA001
    vp = _get_pattern(
        combo_elem, UIAC.UIA_ValuePatternId, UIAC.IUIAutomationValuePattern
    )
    if vp is not None:
        vp.SetValue(target_value)
        return

    msg = "ComboBox supports neither ExpandCollapsePattern nor ValuePattern"
    raise TunestAutomationError(msg)


def get_combobox_value(combo_elem: UIAC.IUIAutomationElement) -> str:
    """Return the current value of a combobox (via ValuePattern)."""
    return get_value(combo_elem)


# ---------------------------------------------------------------------------
# File dialog automation
# ---------------------------------------------------------------------------


def set_file_dialog_path(file_path: str, timeout: float = 5.0) -> None:  # noqa: C901
    """Find the Windows common file-open dialog (#32770), set the filename edit field to *file_path*, and click the Open/OK button.

    Uses Win32 EnumChildWindows to locate the native Edit control inside
    the ComboBoxEx32 filename field, sends WM_SETTEXT, then BM_CLICK on
    the Open button.  This avoids UIA control-type queries which return
    no results for Qt-hosted dialogs.
    """
    # Poll for the dialog to appear.
    # FindWindow("#32770", None) may return an unrelated dialog (e.g. PuTTY error,
    # update notifications) because multiple #32770 windows can be open at once.
    # Enumerate all top-level windows and pick the visible #32770 titled "Open File"
    # or "Open" that was most recently activated (foreground first, then by creation).
    dialog_hwnd: int | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dialog_hwnd = _find_open_file_dialog()
        if dialog_hwnd:
            break
        time.sleep(0.1)
    if not dialog_hwnd:
        msg = "File open dialog (#32770) did not appear within timeout"
        raise TunestAutomationError(msg)

    # Give the dialog a moment to fully render
    time.sleep(0.3)

    # Enumerate all child windows to find:
    #   - The Edit control inside the ComboBoxEx32 filename field
    #   - The Open / OK button
    edit_hwnds: list[int] = []

    def _enum_cb(hwnd: int, _param: object) -> bool:
        cls = win32gui.GetClassName(hwnd)
        if cls == "Edit":
            edit_hwnds.append(hwnd)
        return True  # continue enumeration

    win32gui.EnumChildWindows(dialog_hwnd, _enum_cb, None)

    # The filename Edit is the one whose parent is a ComboBox (inside ComboBoxEx32).
    # When multiple Edit controls are found, pick the one that is a child of a
    # ComboBox class (the filename combo), not a plain Edit (the address bar Edit
    # has parent class ComboBox too, but is narrower; the filename one is wider).
    fn_hwnd: int | None = None
    if edit_hwnds:
        # Prefer the Edit whose Win32 parent class is 'ComboBox' and whose
        # screen width is >= 400px (filename box is ~514px wide).
        for eh in edit_hwnds:
            parent_cls = win32gui.GetClassName(win32gui.GetParent(eh))
            rect = win32gui.GetWindowRect(eh)
            width = rect[2] - rect[0]
            if parent_cls == "ComboBox" and width >= FILENAME_EDIT_COMBOBOX_WIDTH:
                fn_hwnd = eh
                break
        if fn_hwnd is None:
            # Fallback: widest Edit
            fn_hwnd = max(
                edit_hwnds,
                key=lambda h: (
                    win32gui.GetWindowRect(h)[2] - win32gui.GetWindowRect(h)[0]
                ),
            )

    if fn_hwnd is None:
        msg = "Could not find filename edit in file dialog"
        raise TunestAutomationError(msg)

    # Bring the dialog to the foreground so SendInput goes to it.
    ctypes.windll.user32.SetForegroundWindow(dialog_hwnd)
    time.sleep(0.15)

    # Click the filename edit field to give it focus.
    fn_rect = win32gui.GetWindowRect(fn_hwnd)
    fn_cx = (fn_rect[0] + fn_rect[2]) // 2
    fn_cy = (fn_rect[1] + fn_rect[3]) // 2
    _send_click(fn_cx, fn_cy)
    time.sleep(0.1)

    # Select all existing text with Ctrl+A, then delete it.
    _VK_CONTROL = 0x11  # noqa: N806
    _VK_A = 0x41  # noqa: N806

    ctrl_a = (_INPUT * 4)(
        _key_down(_VK_CONTROL), _key_down(_VK_A), _key_up(_VK_A), _key_up(_VK_CONTROL)
    )
    ctypes.windll.user32.SendInput(4, ctrl_a, ctypes.sizeof(_INPUT))
    time.sleep(0.05)

    # Type the file path using Unicode SendInput (KEYEVENTF_UNICODE).
    # This is the most reliable way to insert arbitrary text into a focused
    # edit control across process boundaries.
    chars = list(file_path)
    n = len(chars)
    char_inputs = _generate_char_inputs(chars, n)
    ctypes.windll.user32.SendInput(n * 2, char_inputs, ctypes.sizeof(_INPUT))
    time.sleep(0.15)

    # Press Enter to confirm the filename and close the dialog.
    _send_key(_VK_RETURN)
    time.sleep(DIALOG_DISMISS_SLEEP)


def _find_open_file_dialog() -> int | None:
    candidates: list[int] = []

    def _cb(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.GetClassName(hwnd) != "#32770":
            return True
        title = win32gui.GetWindowText(hwnd).lower()
        if "open" in title or "import" in title:
            candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    return candidates[-1] if candidates else None


def _key_down(vk: int) -> _INPUT:
    return _INPUT(
        type=_INPUT_KEYBOARD,
        _=_INPUT_UNION(
            ki=_KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
        ),
    )


def _key_up(vk: int) -> _INPUT:
    return _INPUT(
        type=_INPUT_KEYBOARD,
        _=_INPUT_UNION(
            ki=_KEYBDINPUT(
                wVk=vk, wScan=0, dwFlags=_KEYEVENTF_KEYUP, time=0, dwExtraInfo=None
            )
        ),
    )


def _generate_char_inputs(chars: list[str], n: int) -> Array[_INPUT]:
    _KEYEVENTF_UNICODE = 0x0004  # noqa: N806
    char_inputs = (_INPUT * (n * 2))()
    for i, ch in enumerate(chars):
        char_inputs[i * 2] = _INPUT(
            type=_INPUT_KEYBOARD,
            _=_INPUT_UNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=ord(ch),
                    dwFlags=_KEYEVENTF_UNICODE,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        )
        char_inputs[i * 2 + 1] = _INPUT(
            type=_INPUT_KEYBOARD,
            _=_INPUT_UNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=ord(ch),
                    dwFlags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        )
    return char_inputs
