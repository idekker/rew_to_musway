"""prompt.py - Timer-with-cancel user prompts for manual mode.

Provides ``timed_prompt`` which shows a countdown with a progress bar.
The user can press Enter to continue immediately, Backspace to cancel
the timer (then only Enter continues), or let the timer expire to
auto-continue.
"""

from __future__ import annotations

import asyncio
import logging
import msvcrt
from enum import Enum, auto

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.text import Text

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.1  # seconds between keypress checks

_KEY_ENTER = b"\r"
_KEY_BACKSPACE = b"\x08"


class TimedPromptResult(Enum):
    """How the timed prompt was resolved."""

    ENTER = auto()
    TIMER_EXPIRED = auto()
    TIMER_CANCELLED = auto()


def _read_key() -> bytes | None:
    """Read a keypress without blocking, or return ``None``."""
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None


async def _poll_keypress() -> bytes | None:
    """Non-blocking async keypress check."""
    return await asyncio.to_thread(_read_key)


def _build_panel(
    message: str,
    *,
    remaining: float,
    total: float,
    timer_cancelled: bool,
) -> Panel:
    """Build a rich Panel showing the prompt state."""
    bar = ProgressBar(total=total, completed=total - remaining, width=40)
    if timer_cancelled:
        status = Text("Timer cancelled — press Enter to continue", style="yellow")
    else:
        status = Text(f"{remaining:.0f}s remaining", style="cyan")

    content = Group(
        Text(message, style="bold"),
        bar,
        status,
        Text("[Enter] Continue  [Backspace] Cancel timer", style="dim"),
    )
    return Panel(content, expand=False)


async def timed_prompt(
    message: str,
    timeout_seconds: float,
    *,
    console: Console | None = None,
) -> TimedPromptResult:
    """Show a countdown prompt with Enter/Backspace/expiry behaviour.

    Parameters
    ----------
    message:
        The instruction to display (e.g. "Solo channel 'Front Left'").
    timeout_seconds:
        Countdown duration in seconds.  Must be > 0.
    console:
        Optional rich Console for output.

    Returns
    -------
    TimedPromptResult
        How the prompt was resolved.

    """
    if console is None:
        console = Console()

    remaining = float(timeout_seconds)
    timer_cancelled = False

    # Drain stale keypresses
    while msvcrt.kbhit():
        msvcrt.getch()

    with Live(
        _build_panel(
            message, remaining=remaining, total=timeout_seconds, timer_cancelled=False
        ),
        console=console,
        refresh_per_second=10,
        transient=True,
    ) as live:
        while True:
            key = await _poll_keypress()

            if key == _KEY_ENTER:
                logger.debug("Timed prompt: Enter pressed (%.1fs remaining)", remaining)
                return TimedPromptResult.ENTER

            if key == _KEY_BACKSPACE and not timer_cancelled:
                timer_cancelled = True
                logger.debug("Timed prompt: timer cancelled")

            if not timer_cancelled:
                remaining -= _POLL_INTERVAL
                if remaining <= 0:
                    logger.debug("Timed prompt: timer expired")
                    return TimedPromptResult.TIMER_EXPIRED

            live.update(
                _build_panel(
                    message,
                    remaining=max(remaining, 0),
                    total=timeout_seconds,
                    timer_cancelled=timer_cancelled,
                )
            )
            await asyncio.sleep(_POLL_INTERVAL)
