"""
TunestPC client - public API for Tunest PC (TUNEST_PC_V1) UI Automation.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

import win32gui

from ._constants import (
    BYPASS_EQ_BTN_REL,
    CH_HEADER_OFFSET,
    CH_LEVEL_EDIT_OFFSET,
    CH_MUTE_CB_OFFSET,
    CH_SOLO_CB_OFFSET,
    CHANNEL_STRIP_TOP_Y,
    CHANNEL_X_OFFSETS,
    HP_FREQ_EDIT_REL,
    HP_SLOPE_COMBO_REL,
    HP_TYPE_COMBO_REL,
    IMPORT_EQ_BTN_REL,
    LP_FREQ_EDIT_REL,
    LP_SLOPE_COMBO_REL,
    LP_TYPE_COMBO_REL,
    MASTER_MUTE_REL,
    MASTER_VOL_EDIT_REL,
    RESET_EQ_ALL_CB_REL,
    RESET_EQ_BTN_REL,
    RESET_EQ_DIALOG_CLASS,
    RESET_EQ_OK_BTN_REL,
    RESET_EQ_SELECTED_CB_REL,
)
from ._automation import (
    TunestAutomationError,
    _send_click,
    element_from_hwnd,
    get_rect,
    get_toggle_state,
    get_value,
    invoke_element,
    set_combobox,
    set_file_dialog_path,
    set_toggle,
    set_value,
)
from ._launcher import TunestConnectionError, launch_and_connect

# UIAC is safe to import here: importing _automation above already triggered
# comtypes.client.GetModule("UIAutomationCore.dll") which generates comtypes.gen.
import comtypes.gen.UIAutomationClient as UIAC  # noqa: E402,N814


# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------


class FilterType(Enum):
    BUTTERWORTH = "Butterworth"
    BESSEL = "Bessel"
    LINKWITZ_RILEY = "Linkwitz Riley"


class FilterSlope(Enum):
    OFF = "OFF"
    DB12 = "12dB/Oct"
    DB24 = "24dB/Oct"
    DB36 = "36dB/Oct"
    DB48 = "48dB/Oct"


# ---------------------------------------------------------------------------
# TunestPC
# ---------------------------------------------------------------------------


class TunestPC:
    """
    Programmatic controller for the Tunest PC (TUNEST_PC_V1) DSP application.

    Typical usage::

        t = TunestPC()
        t.connect(r"D:\\Program Files (x86)\\TUNEST PC\\TUNEST_PC_FULL.exe")
        t.set_master_volume("-6dB")
        t.set_channel_level(1, "-3.0dB")
    """

    def __init__(self) -> None:
        self._hwnd: Optional[int] = None
        self._bypass_active: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> int:
        if self._hwnd is None:
            raise TunestConnectionError("Not connected. Call connect() first.")
        if not win32gui.IsWindow(self._hwnd):
            self._hwnd = None
            raise TunestConnectionError(
                "Tunest PC window is no longer valid. Reconnect."
            )
        return self._hwnd

    def _win_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, right, bottom) screen coords of the main window."""
        hwnd = self._require_connected()
        elem = element_from_hwnd(hwnd)
        return get_rect(elem)

    def _abs(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Convert window-relative position to absolute screen coords."""
        l, t, _, _ = self._win_rect()
        return l + rel_x, t + rel_y

    def _click_rel(self, rel_x: int, rel_y: int) -> None:
        sx, sy = self._abs(rel_x, rel_y)
        _send_click(sx, sy)

    def _all_descendants(
        self,
    ) -> list[tuple[int, int, int, int, int, UIAC.IUIAutomationElement]]:
        """
        Return a flat list of (area, left, top, right, bottom, elem) for every
        non-zero-size descendant of the main window.  Re-queried fresh each call.
        """
        hwnd = self._require_connected()
        root = element_from_hwnd(hwnd)
        from ._automation import get_uia

        uia = get_uia()
        tc = uia.CreateTrueCondition()
        all_d = root.FindAll(UIAC.TreeScope_Descendants, tc)
        result = []
        for i in range(all_d.Length if all_d else 0):
            try:
                e = all_d.GetElement(i)
                r = e.CurrentBoundingRectangle
                if r.right <= r.left or r.bottom <= r.top:
                    continue
                area = (r.right - r.left) * (r.bottom - r.top)
                result.append((area, r.left, r.top, r.right, r.bottom, e))
            except Exception:
                pass
        return result

    def _get_elem_at_rel(
        self,
        rel_x: int,
        rel_y: int,
        name: Optional[str] = None,
        max_wait: float = 3.0,
    ) -> UIAC.IUIAutomationElement:
        """
        Find the smallest UIA element whose bounding rect contains the
        window-relative point (*rel_x*, *rel_y*).

        If *name* is provided, the element's CurrentName must match exactly.
        Polls up to *max_wait* seconds.  Raises TunestAutomationError on timeout.

        The Qt app exposes its entire UI as custom control types, so we cannot
        filter by control type.  Instead we find the leaf element by area - the
        smallest element that spatially contains the target point is the leaf.
        """
        l, t, _, _ = self._win_rect()
        sx = l + rel_x
        sy = t + rel_y

        deadline = time.monotonic() + max_wait
        while True:
            candidates = self._all_descendants()
            hits = [
                (area, el, et, er, eb, e)
                for (area, el, et, er, eb, e) in candidates
                if el <= sx <= er and et <= sy <= eb
            ]
            if name is not None:
                named = [h for h in hits if (h[5].CurrentName or "") == name]
                if named:
                    named.sort()
                    return named[0][5]
            elif hits:
                hits.sort()  # smallest area first = leaf element
                return hits[0][5]

            if time.monotonic() >= deadline:
                raise TunestAutomationError(
                    f"No element at rel({rel_x},{rel_y})"
                    + (f" name={name!r}" if name else "")
                )
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------

    def connect(
        self,
        exe_path: str,
        model: str = "M6",
        launch_if_needed: bool = True,
        timeout: float = 15.0,
    ) -> None:
        """
        Connect to a running Tunest PC instance, or launch it.

        Parameters
        ----------
        exe_path:
            Full path to TUNEST_PC_FULL.exe (used only if launch is needed).
        model:
            Model string for the selection dialog, e.g. "M6", "M4+", "D8".
        launch_if_needed:
            If True, start the application when it is not already running.
        timeout:
            Seconds to wait for the main window to appear.
        """
        self._hwnd = launch_and_connect(
            exe_path=exe_path,
            model=model,
            launch_if_needed=launch_if_needed,
            timeout=timeout,
        )
        self._bypass_active = False

    # ------------------------------------------------------------------
    # Master volume
    # ------------------------------------------------------------------

    def get_master_volume(self) -> str:
        """Return the master volume value string, e.g. '0dB'."""
        elem = self._get_elem_at_rel(
            MASTER_VOL_EDIT_REL[0] + 32,
            MASTER_VOL_EDIT_REL[1] + 9,
        )
        return get_value(elem)

    def set_master_volume(self, value: str) -> None:
        """Set master volume.  *value* e.g. '-6dB' or '0dB'."""
        elem = self._get_elem_at_rel(
            MASTER_VOL_EDIT_REL[0] + 32,
            MASTER_VOL_EDIT_REL[1] + 9,
        )
        set_value(elem, value)

    # ------------------------------------------------------------------
    # Master mute
    # ------------------------------------------------------------------

    def get_master_mute(self) -> bool:
        """Return True if master mute is active."""
        elem = self._get_elem_at_rel(
            MASTER_MUTE_REL[0] + 32,
            MASTER_MUTE_REL[1] + 8,
        )
        return get_toggle_state(elem) == 1

    def set_master_mute(self, muted: bool) -> None:
        """Enable or disable master mute."""
        elem = self._get_elem_at_rel(
            MASTER_MUTE_REL[0] + 32,
            MASTER_MUTE_REL[1] + 8,
        )
        set_toggle(elem, muted)

    # ------------------------------------------------------------------
    # Channel level & mute
    # ------------------------------------------------------------------

    @staticmethod
    def _ch_x(channel: int) -> int:
        """Return window-relative X of the left edge of a channel group (1-indexed)."""
        if not (1 <= channel <= 8):
            raise ValueError(f"Channel must be 1–8, got {channel}")
        return CHANNEL_X_OFFSETS[channel - 1]

    def get_channel_level(self, channel: int) -> str:
        """Return the level string for *channel* (1–8), e.g. '0.0dB'."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_LEVEL_EDIT_OFFSET[0] + 38  # centre of the 77px-wide field
        rel_y = CHANNEL_STRIP_TOP_Y + CH_LEVEL_EDIT_OFFSET[1] + 12
        elem = self._get_elem_at_rel(rel_x, rel_y)
        return get_value(elem)

    def set_channel_level(self, channel: int, value: str) -> None:
        """Set *channel* (1–8) level.  *value* e.g. '-3.0dB'."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_LEVEL_EDIT_OFFSET[0] + 38
        rel_y = CHANNEL_STRIP_TOP_Y + CH_LEVEL_EDIT_OFFSET[1] + 12
        elem = self._get_elem_at_rel(rel_x, rel_y)
        set_value(elem, value)

    def get_channel_mute(self, channel: int) -> bool:
        """Return True if *channel* (1–8) is muted."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_MUTE_CB_OFFSET[0] + 14  # centre of 28px-wide button
        rel_y = CHANNEL_STRIP_TOP_Y + CH_MUTE_CB_OFFSET[1] + 11
        elem = self._get_elem_at_rel(rel_x, rel_y)
        return get_toggle_state(elem) == 1

    def set_channel_mute(self, channel: int, muted: bool) -> None:
        """Enable or disable mute on *channel* (1–8)."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_MUTE_CB_OFFSET[0] + 14
        rel_y = CHANNEL_STRIP_TOP_Y + CH_MUTE_CB_OFFSET[1] + 11
        elem = self._get_elem_at_rel(rel_x, rel_y)
        set_toggle(elem, muted)

    def get_channel_solo(self, channel: int) -> bool:
        """Return True if *channel* (1–8) is soloed."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_SOLO_CB_OFFSET[0] + 23  # centre of 47px-wide button
        rel_y = CHANNEL_STRIP_TOP_Y + CH_SOLO_CB_OFFSET[1] + 12
        elem = self._get_elem_at_rel(rel_x, rel_y)
        return get_toggle_state(elem) == 1

    def set_channel_solo(self, channel: int, soloed: bool) -> None:
        """Enable or disable solo on *channel* (1–8)."""
        cx = self._ch_x(channel)
        rel_x = cx + CH_SOLO_CB_OFFSET[0] + 23
        rel_y = CHANNEL_STRIP_TOP_Y + CH_SOLO_CB_OFFSET[1] + 12
        elem = self._get_elem_at_rel(rel_x, rel_y)
        set_toggle(elem, soloed)

    # ------------------------------------------------------------------
    # Channel selection (top checkboxes, required before filter ops)
    # ------------------------------------------------------------------

    def _select_channel(self, channel: int) -> None:
        """
        Select *channel* (1–8) by clicking its header in the bottom channel
        strip (the 160x28 bar at the top of each channel column, Y≈511).
        Clicking the header highlights the section with a coloured border and
        updates the right-panel filter/EQ controls to show that channel.
        Always sends a direct click regardless of current state.
        """
        if not (1 <= channel <= 8):
            raise ValueError(f"Channel must be 1–8, got {channel}")
        cx = self._ch_x(channel)
        rel_x = cx + CH_HEADER_OFFSET[0]  # centre of 160px-wide header = x+80
        rel_y = CHANNEL_STRIP_TOP_Y + CH_HEADER_OFFSET[1]  # 511+14 = 525
        self._click_rel(rel_x, rel_y)
        time.sleep(0.15)

    # ------------------------------------------------------------------
    # Hi/Lo pass filters
    # ------------------------------------------------------------------

    def set_highpass(
        self,
        channel: int,
        filter_type: FilterType,
        freq: str,
        slope: FilterSlope,
    ) -> None:
        """
        Configure the high-pass filter for *channel* (1–8).

        Parameters
        ----------
        channel:    Target channel (1–8).
        filter_type: FilterType enum value.
        freq:       Frequency string, e.g. '80'.
        slope:      FilterSlope enum value.
        """
        self._select_channel(channel)
        time.sleep(0.1)

        # Type combobox - centre of the 115x38 field
        tc = self._get_elem_at_rel(
            HP_TYPE_COMBO_REL[0] + 57,
            HP_TYPE_COMBO_REL[1] + 19,
        )
        set_combobox(tc, filter_type.value)

        # Frequency edit
        fe = self._get_elem_at_rel(
            HP_FREQ_EDIT_REL[0] + 57,
            HP_FREQ_EDIT_REL[1] + 19,
        )
        set_value(fe, freq)

        # Slope combobox
        sc = self._get_elem_at_rel(
            HP_SLOPE_COMBO_REL[0] + 57,
            HP_SLOPE_COMBO_REL[1] + 19,
        )
        set_combobox(sc, slope.value)

    def set_lowpass(
        self,
        channel: int,
        filter_type: FilterType,
        freq: str,
        slope: FilterSlope,
    ) -> None:
        """
        Configure the low-pass filter for *channel* (1–8).

        Parameters
        ----------
        channel:    Target channel (1–8).
        filter_type: FilterType enum value.
        freq:       Frequency string, e.g. '4000'.
        slope:      FilterSlope enum value.
        """
        self._select_channel(channel)
        time.sleep(0.1)

        tc = self._get_elem_at_rel(
            LP_TYPE_COMBO_REL[0] + 57,
            LP_TYPE_COMBO_REL[1] + 19,
        )
        set_combobox(tc, filter_type.value)

        fe = self._get_elem_at_rel(
            LP_FREQ_EDIT_REL[0] + 57,
            LP_FREQ_EDIT_REL[1] + 19,
        )
        set_value(fe, freq)

        sc = self._get_elem_at_rel(
            LP_SLOPE_COMBO_REL[0] + 57,
            LP_SLOPE_COMBO_REL[1] + 19,
        )
        set_combobox(sc, slope.value)

    # ------------------------------------------------------------------
    # Import EQ
    # ------------------------------------------------------------------

    def import_eq(self, channel: int, json_path: str) -> None:
        """
        Import an EQ preset JSON file for *channel* (1–8).

        Selects the channel, clicks "Import EQ", then automates the Windows
        file-open dialog to select *json_path*.
        """
        self._select_channel(channel)
        time.sleep(0.1)

        # Click the Import EQ button (named, centred within the button)
        btn = self._get_elem_at_rel(
            IMPORT_EQ_BTN_REL[0] + 72,
            IMPORT_EQ_BTN_REL[1] + 11,
            name="Import EQ",
        )
        invoke_element(btn)

        # Automate the file dialog
        set_file_dialog_path(json_path)

    # ------------------------------------------------------------------
    # Reset EQ
    # ------------------------------------------------------------------

    def reset_eq(self, selected_only: bool = True) -> None:
        """
        Open the Reset EQ dialog and reset EQ bands.

        Parameters
        ----------
        selected_only:
            If True (default), choose "Reset selected channels".
            If False, choose "Reset all channels".
        """
        # Use direct click - InvokePattern.Invoke() crashes for Qt buttons.
        self._click_rel(RESET_EQ_BTN_REL[0] + 35, RESET_EQ_BTN_REL[1] + 11)

        # Wait for the Reset EQ dialog.
        # The dialog is a Qt5152QWindowToolSaveBits window titled TUNEST_PC_V1,
        # not a CCResetEq HWND class as originally assumed.
        deadline = time.monotonic() + 5.0
        dialog_hwnd = None
        while time.monotonic() < deadline:

            def _find(h: int, _: object) -> bool:
                nonlocal dialog_hwnd
                if win32gui.GetClassName(
                    h
                ) == RESET_EQ_DIALOG_CLASS and win32gui.IsWindowVisible(h):
                    dialog_hwnd = h
                return True

            win32gui.EnumWindows(_find, None)
            if dialog_hwnd:
                break
            time.sleep(0.1)
        if not dialog_hwnd:
            raise TunestAutomationError("Reset EQ dialog did not appear")

        from ._automation import element_from_hwnd as _efh, get_uia, get_rect as _gr

        dialog_elem = _efh(dialog_hwnd)
        time.sleep(0.15)

        # Select the appropriate checkbox by name.
        cb_name = "Reset selected channels" if selected_only else "Reset all channels"
        uia = get_uia()
        nm_cond = uia.CreatePropertyCondition(UIAC.UIA_NamePropertyId, cb_name)
        cb_elem = dialog_elem.FindFirst(UIAC.TreeScope_Descendants, nm_cond)
        if cb_elem is not None:
            set_toggle(cb_elem, True)
        else:
            # Fallback: click by position
            dl, dt, _, _ = _gr(dialog_elem)
            cb_rel = RESET_EQ_SELECTED_CB_REL if selected_only else RESET_EQ_ALL_CB_REL
            _send_click(dl + cb_rel[0] + 8, dt + cb_rel[1] + 12)

        # Click OK by name, using mouse click (InvokePattern may crash).
        ok_cond = uia.CreatePropertyCondition(UIAC.UIA_NamePropertyId, "Ok")
        ok_elem = dialog_elem.FindFirst(UIAC.TreeScope_Descendants, ok_cond)
        if ok_elem is not None:
            from ._automation import centre as _ctr

            _send_click(*_ctr(ok_elem))
        else:
            dl, dt, _, _ = _gr(dialog_elem)
            _send_click(
                dl + RESET_EQ_OK_BTN_REL[0] + 42, dt + RESET_EQ_OK_BTN_REL[1] + 12
            )

    # ------------------------------------------------------------------
    # Bypass / Restore EQ
    # ------------------------------------------------------------------

    def bypass_eq(self) -> None:
        """
        Bypass EQ on all channels (click the Bypass EQ toggle button).
        No-op if bypass is already active (tracked internally).
        """
        if self._bypass_active:
            return
        # InvokePattern.Invoke() crashes for this button - use a direct mouse
        # click on the button centre instead.
        self._click_rel(BYPASS_EQ_BTN_REL[0] + 35, BYPASS_EQ_BTN_REL[1] + 11)
        self._bypass_active = True

    def restore_eq(self) -> None:
        """
        Remove EQ bypass (click RestoreEQ toggle to restore).
        No-op if bypass is not active.
        """
        if not self._bypass_active:
            return
        # Same: use direct mouse click, not InvokePattern.
        self._click_rel(BYPASS_EQ_BTN_REL[0] + 35, BYPASS_EQ_BTN_REL[1] + 11)
        self._bypass_active = False
