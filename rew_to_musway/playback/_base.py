"""_base.py - PlaybackStrategy protocol and shared SPL check loop."""

from __future__ import annotations

import asyncio
import logging
import math
import msvcrt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console, Group
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rew_to_musway.config import LevelsConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

SPL_POLL_INTERVAL = 0.5

# Key codes
_KEY_ENTER = b"\r"
_KEY_ESC = b"\x1b"

_KEYPRESS_POLL_INTERVAL = 0.1


@runtime_checkable
class PlaybackStrategy(Protocol):
    """Protocol for noise playback strategies."""

    async def start_noise(self) -> None:
        """Start playing pink noise and verify SPL is within tolerance."""
        ...

    async def stop_noise(self) -> None:
        """Stop playing pink noise."""
        ...


@dataclass
class _SPLDisplayState:
    """Bundle of values for the SPL + countdown display."""

    current: float
    target: float
    tolerance: float
    in_range: bool
    remaining: float
    total: float
    timer_cancelled: bool


def _build_spl_display(state: _SPLDisplayState) -> Group:
    """Build a rich Group showing live SPL status with countdown."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()

    if math.isnan(state.current):
        table.add_row("SPL:", "[dim]waiting for reading...[/dim]")
    elif state.in_range:
        table.add_row(
            "SPL:",
            f"[green]{state.current:.1f} dB[/green]  [green]OK[/green]",
        )
    else:
        diff = state.current - state.target
        direction = "increase" if diff < 0 else "decrease"
        table.add_row(
            "SPL:",
            f"[yellow]{state.current:.1f} dB[/yellow]  "
            f"({diff:+.1f} dB) — please [bold]{direction}[/bold] volume",
        )

    table.add_row(
        "Target:",
        f"{state.target:.0f} ± {state.tolerance:.0f} dB",
    )

    bar = ProgressBar(
        total=state.total, completed=state.total - state.remaining, width=40
    )
    if state.timer_cancelled:
        timer_text = Text("Timer cancelled — press Enter to continue", style="yellow")
    else:
        timer_text = Text(f"{state.remaining:.0f}s remaining", style="cyan")

    hint = Text("[Enter] Continue  [Esc] Cancel timer", style="dim")
    return Group(table, bar, timer_text, hint)


async def _poll_keypress() -> bytes | None:
    """Non-blocking check for a keypress (Windows msvcrt)."""
    return await asyncio.to_thread(_read_key)


def _read_key() -> bytes | None:
    """Read a keypress without blocking, or return None."""
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None


async def wait_for_enter() -> None:
    """Block asynchronously until the user presses Enter.

    Uses msvcrt (non-blocking key polling in a thread) instead of
    ``input()`` / ``ReadConsoleW`` which can become unresponsive when
    the console input mode has been altered by prompt_toolkit or COM
    automation running in other threads.
    """
    while True:
        key = await _poll_keypress()
        if key == _KEY_ENTER:
            return
        await asyncio.sleep(_KEYPRESS_POLL_INTERVAL)


async def check_spl_level(
    rew: REWController,
    levels_config: LevelsConfig,
    timeout_seconds: float,
) -> float:
    """Show live SPL with a countdown timer.

    The SPL meter is polled continuously and displayed via rich Live
    alongside a countdown progress bar.

    - **Enter** continues immediately.
    - **Esc** cancels the timer (wait indefinitely for Enter).
    - **Timer expiry** auto-continues with the current SPL reading.

    Returns
    -------
    The final SPL reading in dB.

    """
    target = levels_config.target_spl
    tolerance = levels_config.tolerance
    low = target - tolerance
    high = target + tolerance

    await rew.spl_open()

    # Brief warmup before first read
    await asyncio.sleep(1.0)

    current = float("nan")
    remaining = float(timeout_seconds)
    timer_cancelled = False

    state = _SPLDisplayState(
        current=current,
        target=target,
        tolerance=tolerance,
        in_range=False,
        remaining=remaining,
        total=timeout_seconds,
        timer_cancelled=False,
    )

    # Drain stale keypresses
    while msvcrt.kbhit():
        msvcrt.getch()

    try:
        with Live(
            _build_spl_display(state),
            console=console,
            refresh_per_second=4,
        ) as live:
            while True:
                # Read SPL
                spl = await rew.spl_read()
                current = spl.spl
                in_range = not math.isnan(current) and low <= current <= high

                # Check for keypress
                key = await _poll_keypress()
                if key == _KEY_ENTER:
                    break
                if key == _KEY_ESC and not timer_cancelled:
                    timer_cancelled = True
                    logger.debug("SPL check: timer cancelled")

                # Countdown
                if not timer_cancelled:
                    remaining -= SPL_POLL_INTERVAL
                    if remaining <= 0:
                        logger.debug("SPL check: timer expired")
                        break

                state = _SPLDisplayState(
                    current=current,
                    target=target,
                    tolerance=tolerance,
                    in_range=in_range,
                    remaining=max(remaining, 0),
                    total=timeout_seconds,
                    timer_cancelled=timer_cancelled,
                )
                live.update(_build_spl_display(state))

                await asyncio.sleep(SPL_POLL_INTERVAL)
    finally:
        await rew.spl_close()

    logger.info("SPL check confirmed at %.1f dB", current)
    return current
