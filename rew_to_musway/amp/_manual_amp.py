"""_manual_amp.py - ManualAmp backend for manual mode calibration.

Implements ``AmpBackend`` by buffering DSP state and flushing it to
Musway preset files on ``apply()``.  Immediate operations (solo, mute)
use timed prompts to instruct the user.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import win32clipboard  # pyright: ignore[reportMissingModuleSource]

from rew_to_musway.amp._preset_amp import _MuswayPresetAmp
from rew_to_musway.prompt import timed_prompt

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig, ManualConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clipboard helper
# ---------------------------------------------------------------------------

_CF_UNICODETEXT = 13


def _copy_to_clipboard(text: str) -> None:
    """Copy *text* to the Windows clipboard."""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(_CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


# ---------------------------------------------------------------------------
# ManualAmp
# ---------------------------------------------------------------------------


class ManualAmp(_MuswayPresetAmp):
    """AmpBackend implementation for manual mode.

    DSP state changes are buffered and flushed as Musway preset files
    on ``apply()``.  Immediate operations instruct the user via timed
    prompts.
    """

    def __init__(
        self,
        *,
        config: ManualConfig,
        channels: list[ChannelConfig],
        session_dir: Path,
    ) -> None:
        super().__init__(
            default_preset_path=Path(config.default_preset_path),
            session_dir=session_dir,
            channels=channels,
            action_timeout=config.timers.action_timeout,
        )
        self._preset_load_timeout = config.timers.preset_load_timeout

    # ------------------------------------------------------------------
    # Abstract hook implementations
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """No-op — manual mode has no hardware connection."""

    async def _deliver_preset(self, out_path: Path) -> None:
        """Copy preset path to clipboard and prompt user to load it."""
        abs_path = str(out_path.resolve())  # noqa: ASYNC240
        _copy_to_clipboard(abs_path)
        msg = (
            f"Load preset in Musway software (path copied to clipboard):\n{abs_path}"
            "\nAfter loading, mute all channels before continuing."
        )
        await timed_prompt(msg, self._preset_load_timeout)

    async def _do_solo_channel(self, channel: int, msg: str) -> None:  # noqa: ARG002
        """Prompt the user to solo the given channel."""
        await timed_prompt(msg, self._action_timeout)

    async def _do_solo_channels(self, channels: list[int], msg: str) -> None:  # noqa: ARG002
        """Prompt the user to unmute the given channels."""
        await timed_prompt(msg, self._action_timeout)

    async def _do_master_mute(self, muted: bool, msg: str) -> None:  # noqa: ARG002, FBT001
        """Prompt the user to mute/unmute master."""
        await timed_prompt(msg, self._action_timeout)
