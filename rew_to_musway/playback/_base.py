"""_base.py - PlaybackStrategy protocol and shared SPL check loop."""

from __future__ import annotations

import asyncio
import logging
import math
import msvcrt
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console
from rich.live import Live
from rich.table import Table

if TYPE_CHECKING:
    from rew_to_musway.config import LevelsConfig
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)
console = Console()

SPL_POLL_INTERVAL = 0.5

# Key codes
_KEY_ENTER = b"\r"
_KEY_ESC = b"\x1b"


class SPLCheckSkippedError(Exception):
    """Raised when the user presses Esc to skip the SPL check."""


@runtime_checkable
class PlaybackStrategy(Protocol):
    """Protocol for noise playback strategies."""

    async def start_noise(self) -> None:
        """Start playing pink noise and verify SPL is within tolerance."""
        ...

    async def stop_noise(self) -> None:
        """Stop playing pink noise."""
        ...


def _build_spl_display(
    current: float,
    target: float,
    tolerance: float,
    *,
    in_range: bool,
) -> Table:
    """Build a rich Table showing live SPL status."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()

    if math.isnan(current):
        table.add_row("SPL:", "[dim]waiting for reading...[/dim]")
    elif in_range:
        table.add_row(
            "SPL:",
            f"[green]{current:.1f} dB[/green]  "
            f"[green]OK[/green] — press [bold]Enter[/bold] to continue",
        )
    else:
        diff = current - target
        direction = "increase" if diff < 0 else "decrease"
        table.add_row(
            "SPL:",
            f"[yellow]{current:.1f} dB[/yellow]  "
            f"({diff:+.1f} dB) — please [bold]{direction}[/bold] volume",
        )

    table.add_row(
        "Target:",
        f"{target:.0f} ± {tolerance:.0f} dB",
    )
    table.add_row("", "[dim]Enter = continue  |  Esc = skip[/dim]")
    return table


async def _poll_keypress() -> bytes | None:
    """Non-blocking check for a keypress (Windows msvcrt)."""
    return await asyncio.to_thread(_read_key)


def _read_key() -> bytes | None:
    """Read a keypress without blocking, or return None."""
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None


_KEYPRESS_POLL_INTERVAL = 0.1


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
) -> float:
    """Show live SPL and let the user adjust volume interactively.

    The SPL meter is polled continuously and displayed via rich Live.
    The user presses **Enter** when the level is acceptable, or **Esc**
    to skip the check.

    Returns
    -------
    The final SPL reading in dB.

    Raises
    ------
    SPLCheckSkipped
        If the user pressed Esc.

    """
    target = levels_config.target_spl
    tolerance = levels_config.tolerance
    low = target - tolerance
    high = target + tolerance

    await rew.spl_open()

    # Brief warmup before first read
    await asyncio.sleep(1.0)

    current = float("nan")
    try:
        with Live(
            _build_spl_display(current, target, tolerance, in_range=False),
            console=console,
            refresh_per_second=4,
        ) as live:
            while True:
                # Read SPL
                spl = await rew.spl_read()
                current = spl.spl
                in_range = not math.isnan(current) and low <= current <= high

                live.update(
                    _build_spl_display(current, target, tolerance, in_range=in_range)
                )

                # Check for keypress
                key = await _poll_keypress()
                if key == _KEY_ENTER:
                    break
                if key == _KEY_ESC:
                    logger.info("SPL check skipped by user")
                    raise SPLCheckSkippedError

                await asyncio.sleep(SPL_POLL_INTERVAL)
    finally:
        await rew.spl_close()

    logger.info("SPL check confirmed at %.1f dB", current)
    return current
