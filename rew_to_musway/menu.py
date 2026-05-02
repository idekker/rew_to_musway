"""menu.py - Interactive menu for rew_to_musway using rich + questionary."""

from __future__ import annotations

import logging
import msvcrt
from typing import TYPE_CHECKING

import questionary
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Menu choices
# ---------------------------------------------------------------------------

MAIN_CHOICES = [
    "Full calibration (phases 1-5)",
    "Level balancing + EQ (phases 1-2)",
    "Finetune EQ",
    "Verification (phases 3-4)",
    "Combined measurements (phase 5)",
    "Save measurements (.mdat)",
    "Quit",
]

CHANNEL_MODE_CHOICES = [
    "All channels",
    "Start from channel...",
    "Single channel",
]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def show_status(
    config: Config,
    *,
    rew_connected: bool,
    amp_connected: bool,
) -> None:
    """Display connection status panel."""
    rew_status = (
        "[green]Connected[/green]" if rew_connected else "[red]Not connected[/red]"
    )
    amp_status = (
        "[green]Connected[/green]" if amp_connected else "[red]Not connected[/red]"
    )

    amp_mode = "Manual"
    if config.tunest_pc:
        amp_mode = f"Tunest PC: {config.tunest_pc.model}"
    elif config.musway:
        amp_mode = "Musway"

    status_text = (
        f"REW:       {rew_status}  ({config.rew.host}:{config.rew.port})\n"
        f"Amp:       {amp_status}  ({amp_mode})\n"
        f"Playback:  {config.playback.mode.value}\n"
        f"Channels:  {len(config.channels)}"
    )
    console.print(Panel(status_text, title="rew_to_musway", border_style="blue"))


# ---------------------------------------------------------------------------
# Menu prompts
# ---------------------------------------------------------------------------


def _flush_input() -> None:
    """Drain any leftover keypresses from the console input buffer.

    ``msvcrt``-based helpers (``wait_for_enter``, SPL check loop) consume
    keys at the low-level console API layer.  Unread keys left in the
    buffer cause ``prompt_toolkit`` (used by questionary) to see a stale
    Enter and immediately select the first menu item.
    """
    while msvcrt.kbhit():
        msvcrt.getch()


async def ask_main_menu() -> str:
    """Show main menu and return selected action."""
    _flush_input()
    result = await questionary.select(
        "What would you like to do?",
        choices=MAIN_CHOICES,
    ).ask_async()
    if result is None:
        return "Quit"
    return result


async def ask_channel_mode(config: Config) -> tuple[str, int | None]:
    """Ask user for channel selection mode.

    Returns
    -------
    (mode, channel_number) where mode is "all", "start_from", or "single"
    and channel_number is set for start_from/single modes.

    """
    _flush_input()
    mode_result = await questionary.select(
        "Channel selection:",
        choices=CHANNEL_MODE_CHOICES,
    ).ask_async()

    if mode_result is None or mode_result == "All channels":
        return ("all", None)

    # Build channel choices
    ch_choices = [f"CH{ch.number} {ch.name}" for ch in config.channels]

    ch_result = await questionary.select(
        "Select channel:",
        choices=ch_choices,
    ).ask_async()

    if ch_result is None:
        return ("all", None)

    # Parse channel number from "CH<n> <name>"
    ch_num = int(ch_result.split()[0].replace("CH", ""))

    if mode_result == "Start from channel...":
        return ("start_from", ch_num)
    return ("single", ch_num)


async def ask_confirm(message: str, default: bool = True) -> bool:  # noqa: FBT001,FBT002
    """Ask a yes/no confirmation."""
    _flush_input()
    result = await questionary.confirm(message, default=default).ask_async()
    return result if result is not None else False
