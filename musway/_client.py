import contextlib
from enum import Enum, auto
from pathlib import Path

import win32gui
from PIL import ImageGrab
from pywinauto import Application, WindowSpecification
from pywinauto.application import ProcessNotFoundError

from musway._constants import (
    CHANNEL_DISTANCE,
    CHANNEL_MUTE_COLOR_MUTED,
    CHANNEL_MUTE_COLOR_UNMUTED,
    CHANNEL_MUTE_COORDS,
    CHANNEL_SELECTION_COLOR_SELECTED,
    CHANNEL_SELECTION_COLOR_UNSELECTED,
    CHANNEL_SELECTION_COORDS,
    MASTER_MUTE_COLOR_MUTED,
    MASTER_MUTE_COLOR_UNMUTED,
    MASTER_MUTE_COORDS,
    MODEL_SELECTION_ENTER_COORDS,
    MODEL_SELECTION_M6_COORDS,
    PRESET_LOAD_SINGLE_PRESET_FROM_PC_COORDS,
    PRESET_MANAGER_COORDS,
)


class MuswayUnknownWindowStateError(Exception):
    """Raised when the app is in an unexpected state."""


class MuswayBadStateError(Exception):
    """Raised when the app is in an unexpected state."""


class _State(Enum):
    NOT_CONNECTED = auto()
    MODEL_SELECTION = auto()
    MAIN_WINDOW = auto()
    PRESET_MANAGER = auto()
    OPEN_PRESET = auto()
    SAVE_PRESET = auto()


class Musway:
    def __init__(
        self,
        validate_state_every_request: bool = False,  # noqa: FBT001, FBT002
        update_coordinates_every_request: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self._main_window: WindowSpecification = None
        self._main_pane: WindowSpecification = None
        self._main_pane_child: WindowSpecification = None
        self._preset_manager_pane: WindowSpecification = None
        self._open_window: WindowSpecification = None
        self._save_window: WindowSpecification = None
        self._state = _State.NOT_CONNECTED
        self._validate_state_every_request: bool = validate_state_every_request
        self._update_coordinates_every_request: bool = update_coordinates_every_request
        self._main_pain_coords = (0, 0)

    def connect(self, path: str) -> None:
        try:
            app = Application(backend="uia").connect(path=path, timeout=2)
        except ProcessNotFoundError:
            app = Application(backend="uia").start(path)

        self._main_window = app.window(title="MUSWAY", control_type="Window")
        self._main_pane = self._main_window.child_window(
            title="DuiFrameWnd", control_type="Pane"
        )
        self._main_pane_child = self._main_pane.child_window(
            auto_id="8001", control_type="Text"
        )
        self._preset_manager_pane = self._main_window.child_window(
            title="FileWnd", control_type="Pane"
        )
        self._open_window = self._main_window.child_window(
            title="Open", control_type="Window"
        )
        self._save_window = self._main_window.child_window(
            title="Save", control_type="Window"
        )

        self._update_state()
        if self._state == _State.MODEL_SELECTION:
            self._main_pane.click_input(coords=MODEL_SELECTION_M6_COORDS)
            self._main_pane.click_input(coords=MODEL_SELECTION_ENTER_COORDS)

        self._update_and_check_state(_State.MAIN_WINDOW)
        window_coords = self._main_pane.rectangle()
        self._main_pain_coords = window_coords.left, window_coords.top

    def get_master_mute(self) -> bool:
        self._update_and_check_state(_State.MAIN_WINDOW)
        return self._get_state_from_color_at_coordinate(
            self._main_pane,
            MASTER_MUTE_COORDS,
            MASTER_MUTE_COLOR_MUTED,
            MASTER_MUTE_COLOR_UNMUTED,
        )

    def set_master_mute(self, mute: bool) -> None:  # noqa: FBT001
        self._update_and_check_state(_State.MAIN_WINDOW)
        if (
            self._get_state_from_color_at_coordinate(
                self._main_pane,
                MASTER_MUTE_COORDS,
                MASTER_MUTE_COLOR_MUTED,
                MASTER_MUTE_COLOR_UNMUTED,
            )
            != mute
        ):
            self._main_pane.click_input(coords=MASTER_MUTE_COORDS)
            if (
                self._get_state_from_color_at_coordinate(
                    self._main_pane,
                    MASTER_MUTE_COORDS,
                    MASTER_MUTE_COLOR_MUTED,
                    MASTER_MUTE_COLOR_UNMUTED,
                )
                != mute
            ):
                exception = f"Failed to set master mute to {mute}"
                raise MuswayBadStateError(exception)

    def select_channel(self, channel: int) -> None:
        self._update_and_check_state(_State.MAIN_WINDOW)
        if channel < 1 or channel > 8:  # noqa: PLR2004
            exception = f"Invalid channel: {channel}"
            raise ValueError(exception)
        coords = (
            CHANNEL_SELECTION_COORDS[0] + (channel - 1) * CHANNEL_DISTANCE,
            CHANNEL_SELECTION_COORDS[1],
        )
        if not self._get_state_from_color_at_coordinate(
            self._main_pane,
            coords,
            CHANNEL_SELECTION_COLOR_SELECTED,
            CHANNEL_SELECTION_COLOR_UNSELECTED,
        ):
            self._main_pane.click_input(coords=coords)
            if not self._get_state_from_color_at_coordinate(
                self._main_pane,
                coords,
                CHANNEL_SELECTION_COLOR_SELECTED,
                CHANNEL_SELECTION_COLOR_UNSELECTED,
            ):
                exception = f"Failed to select channel {channel}"
                raise MuswayBadStateError(exception)

    def is_channel_selected(self, channel: int) -> bool:
        self._update_and_check_state(_State.MAIN_WINDOW)
        coords = (
            CHANNEL_SELECTION_COORDS[0] + (channel - 1) * CHANNEL_DISTANCE,
            CHANNEL_SELECTION_COORDS[1],
        )
        return self._get_state_from_color_at_coordinate(
            self._main_pane,
            coords,
            CHANNEL_SELECTION_COLOR_SELECTED,
            CHANNEL_SELECTION_COLOR_UNSELECTED,
        )

    def get_channel_mute(self, channel: int) -> bool:
        self._update_and_check_state(_State.MAIN_WINDOW)
        coords = (
            CHANNEL_MUTE_COORDS[0] + (channel - 1) * CHANNEL_DISTANCE,
            CHANNEL_MUTE_COORDS[1],
        )
        return self._get_state_from_color_at_coordinate(
            self._main_pane,
            coords,
            CHANNEL_MUTE_COLOR_MUTED,
            CHANNEL_MUTE_COLOR_UNMUTED,
        )

    def set_channel_mute(self, channel: int, mute: bool) -> None:  # noqa: FBT001
        self._update_and_check_state(_State.MAIN_WINDOW)
        coords = (
            CHANNEL_MUTE_COORDS[0] + (channel - 1) * CHANNEL_DISTANCE,
            CHANNEL_MUTE_COORDS[1],
        )
        if (
            self._get_state_from_color_at_coordinate(
                self._main_pane,
                coords,
                CHANNEL_MUTE_COLOR_MUTED,
                CHANNEL_MUTE_COLOR_UNMUTED,
            )
            != mute
        ):
            self._main_pane.click_input(coords=coords)
            if (
                self._get_state_from_color_at_coordinate(
                    self._main_pane,
                    coords,
                    CHANNEL_MUTE_COLOR_MUTED,
                    CHANNEL_MUTE_COLOR_UNMUTED,
                )
                != mute
            ):
                exception = f"Failed to set master mute to {mute}"
                raise MuswayBadStateError(exception)

    def load_preset(self, path: Path) -> None:
        self._update_state()
        if self._state == _State.MAIN_WINDOW:
            self._main_pane.click_input(coords=PRESET_MANAGER_COORDS)
            self._update_state()

        if self._state == _State.PRESET_MANAGER:
            self._preset_manager_pane.click_input(
                coords=PRESET_LOAD_SINGLE_PRESET_FROM_PC_COORDS
            )
            self._update_state()

        if self._state != _State.OPEN_PRESET:
            exception = f"Cannot load preset: expected state {_State.OPEN_PRESET}, actual state {self._state}"
            raise MuswayBadStateError(exception)

        self._open_window.child_window(
            title="File name:", control_type="Edit"
        ).set_text(path)
        self._open_window.child_window(
            title="Open", auto_id="1", control_type="Button"
        ).click()

    def _update_state(self) -> None:
        if self._save_window.exists():
            self._state = _State.SAVE_PRESET
        elif self._open_window.exists():
            self._state = _State.OPEN_PRESET
        elif self._preset_manager_pane.exists():
            self._state = _State.PRESET_MANAGER
        elif self._main_pane_child.exists():
            self._state = _State.MAIN_WINDOW
        elif self._main_pane.exists():
            self._state = _State.MODEL_SELECTION
        else:
            exception = "MUSWAY is in an unknown state: no known windows detected"
            raise MuswayUnknownWindowStateError(exception)

    def _update_and_check_state(self, excepted_state: _State) -> None:
        self._main_window.restore()
        with contextlib.suppress(Exception):
            win32gui.SetForegroundWindow(self._main_window.wrapper_object().handle)

        if self._validate_state_every_request:
            self._update_state()
            if self._state != excepted_state:
                exception = f"Cannot perform action: expected state {excepted_state}, actual state {self._state}"
                raise MuswayBadStateError(exception)

    def _check_color(
        self, window: WindowSpecification, coords: tuple[int, int]
    ) -> tuple[int, int, int]:
        if self._update_coordinates_every_request:
            window_coords = window.rectangle()
            self._main_pain_coords = window_coords.left, window_coords.right
        x = self._main_pain_coords[0] + coords[0]
        y = self._main_pain_coords[1] + coords[1]
        bbox = (x, y, x + 1, y + 1)
        im = ImageGrab.grab(bbox=bbox, all_screens=True)
        rgb = im.convert("RGB")
        r, g, b = rgb.getpixel((0, 0))
        return r, g, b

    def _get_state_from_color_at_coordinate(
        self,
        window: WindowSpecification,
        coords: tuple[int, int],
        true_color: tuple[int, int, int],
        false_color: tuple[int, int, int],
    ) -> bool:
        color = self._check_color(window, coords)
        if color == true_color:
            return True
        if color == false_color:
            return False

        exception = f"Unexpected color: {color}"
        raise MuswayBadStateError(exception)
