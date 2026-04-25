"""__main__.py - Entry point for python -m rew_to_musway."""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rich.console import Console

from .amp import AmpController
from .calibration import (
    LevelOffsets,
    calibrate_channels,
    measure_levels,
    run_combined_measurements,
    run_verification,
    save_session,
    select_channels,
    verify_levels,
)
from .config import Config, PlaybackMode, load_config
from .menu import ask_channel_mode, ask_main_menu, show_status
from .playback import ManualPlayback, REWGeneratorPlayback
from .rew import REWController

if TYPE_CHECKING:
    import types
    from collections.abc import Awaitable, Callable

    from .playback._base import PlaybackStrategy

from pathlib import Path

console = Console()
logger = logging.getLogger("rew_to_musway")


# ---------------------------------------------------------------------------
# Global exception hooks — ensure every crash is logged
# ---------------------------------------------------------------------------


def _excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: types.TracebackType | None,
) -> None:
    """Log unhandled exceptions before the process terminates."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    console.print(f"\n[red]Fatal error:[/red] {exc_value}")


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    """Log unhandled exceptions in background threads (e.g. COM workers)."""
    if args.exc_type is SystemExit:
        return
    logger.critical(
        "Unhandled exception in thread %s",
        args.thread.name if args.thread else "<unknown>",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _unraisablehook(unraisable: sys.UnraisableHookArgs) -> None:
    """Log exceptions that cannot be raised (e.g. during __del__)."""
    logger.critical(
        "Unraisable exception in %s: %s",
        unraisable.object,
        unraisable.exc_value,
        exc_info=(
            type(unraisable.exc_value),
            unraisable.exc_value,
            unraisable.exc_traceback,
        ),
    )


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(log_path: Path) -> None:
    """Configure logging: DEBUG to file, WARNING to console (suppressed)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("rew_to_musway")
    root.setLevel(logging.DEBUG)

    # File handler — debug level, flush after every record so that a
    # crash does not lose buffered log entries.
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    _orig_emit = fh.emit

    def _flushing_emit(record: logging.LogRecord) -> None:
        _orig_emit(record)
        fh.flush()

    fh.emit = _flushing_emit  # type: ignore[method-assign]
    root.addHandler(fh)

    # Suppress console logging (rich handles user output)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(ch)


# ---------------------------------------------------------------------------
# Playback factory
# ---------------------------------------------------------------------------


def _create_playback(config: Config, rew: REWController) -> PlaybackStrategy:
    """Create the playback strategy based on config."""
    if config.playback.mode == PlaybackMode.REW_GENERATOR:
        return REWGeneratorPlayback(rew, config.playback, config.levels)
    return ManualPlayback(rew, config.levels)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

_RETRY_DELAY = 3


async def _connect_with_retry(
    name: str,
    connect_fn: Callable[[], Awaitable[None]],
    max_retries: int = 3,
) -> bool:
    """Attempt to connect, retrying on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            await connect_fn()
        except Exception as exc:  # noqa: PERF203
            logger.exception("%s connection attempt %d failed", name, attempt)
            console.print(
                f"[red]{name} connection failed[/red] "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )
            if attempt < max_retries:
                console.print(f"Retrying in {_RETRY_DELAY} seconds...")
                await asyncio.sleep(_RETRY_DELAY)
        else:
            return True
    return False


# ---------------------------------------------------------------------------
# Menu dispatch
# ---------------------------------------------------------------------------


async def _dispatch_menu(  # noqa: PLR0913
    choice: str,
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    state: _SessionState,
) -> None:
    """Execute the user's menu choice."""
    if choice == "Full calibration (phases 1-5)":
        await _run_full_calibration(config, amp, rew, playback, session_dir, state)
    elif choice == "Level balancing (phase 1)":
        state.level_offsets = await measure_levels(config, amp, rew, playback)
    elif choice == "Calibrate channels (phase 2)":
        mode, ch_num = await ask_channel_mode(config)
        channels = select_channels(config, mode, start_from=ch_num, single=ch_num)
        state.calibrated_channels = await calibrate_channels(
            config, amp, rew, playback, session_dir, channels
        )
    elif choice == "Verification measurements (phase 3)":
        await run_verification(
            config,
            amp,
            rew,
            playback,
            channels=state.calibrated_channels,
        )
    elif choice == "Level verification (phase 4)":
        if state.level_offsets is None:
            console.print(
                "[yellow]No baseline levels — run phase 1 first,[/yellow] "
                "or proceeding with empty baseline."
            )
            state.level_offsets = LevelOffsets()
        await verify_levels(config, amp, rew, playback)
    elif choice == "Combined measurements (phase 5)":
        await run_combined_measurements(config, amp, rew, playback)
    elif choice == "Save measurements (.mdat)":
        await save_session(rew, session_dir)


async def _run_full_calibration(  # noqa: PLR0913
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    state: _SessionState,
) -> None:
    """Execute the complete 5-phase calibration pipeline."""
    state.level_offsets = await measure_levels(config, amp, rew, playback)

    channels = select_channels(config, "all")
    state.calibrated_channels = await calibrate_channels(
        config, amp, rew, playback, session_dir, channels
    )

    await run_verification(
        config,
        amp,
        rew,
        playback,
        channels=state.calibrated_channels,
    )

    if state.level_offsets is not None:
        await verify_levels(config, amp, rew, playback)

    await run_combined_measurements(config, amp, rew, playback)

    await save_session(rew, session_dir)
    console.print("\n[bold green]Full calibration complete![/bold green]")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class _SessionState:
    """Mutable session state shared across menu iterations."""

    def __init__(self) -> None:
        self.level_offsets: LevelOffsets | None = None
        self.calibrated_channels: list[int] | None = None


# ---------------------------------------------------------------------------
# Main application loop
# ---------------------------------------------------------------------------


async def _run(config: Config, session_dir: Path) -> None:
    """Run the interactive calibration session."""
    # On Windows, the ProactorEventLoop does not wake up on SIGINT reliably.
    # Install a signal handler that raises KeyboardInterrupt and schedule a
    # periodic no-op so the event loop checks for pending signals.
    signal.signal(signal.SIGINT, signal.default_int_handler)

    async def _wakeup() -> None:
        """Periodic no-op that lets the event loop process pending signals."""
        stop = asyncio.Event()
        while not stop.is_set():  # noqa: ASYNC110 — intentional periodic wakeup for signal handling
            await asyncio.sleep(0.5)

    wakeup_task = asyncio.create_task(_wakeup())

    rew = REWController(config)
    amp = AmpController(config)
    playback = _create_playback(config, rew)
    state = _SessionState()

    # --- Connect ---
    console.print("\n[bold]Connecting...[/bold]")

    if not await _connect_with_retry("REW", rew.connect):
        console.print("[red]Cannot proceed without REW connection.[/red]")
        return

    await rew.delete_all_measurements()
    logger.info("Cleared existing REW measurements.")

    if not await _connect_with_retry("Tunest PC", amp.connect):
        console.print("[red]Cannot proceed without Tunest PC connection.[/red]")
        await rew.close()
        return

    try:
        await _menu_loop(config, amp, rew, playback, session_dir, state)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        logger.warning("Interrupted by user (KeyboardInterrupt)")
    except SystemExit as exc:
        logger.warning("SystemExit(%s) caught — shutting down gracefully", exc.code)
    except BaseException:
        logger.exception("Fatal error in main loop")
        console.print("\n[red]A fatal error occurred.[/red]")
        console.print("Check the log file for details.")
        raise
    finally:
        wakeup_task.cancel()
        await _shutdown(config, amp, rew)


async def _menu_loop(  # noqa: PLR0913
    config: Config,
    amp: AmpController,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    state: _SessionState,
) -> None:
    """Run the interactive menu loop until the user quits."""
    while True:
        console.print()
        show_status(config, rew_connected=True, amp_connected=True)

        choice = await ask_main_menu()
        logger.info("Menu selection: %s", choice)

        if choice == "Quit":
            break

        try:
            await _dispatch_menu(choice, config, amp, rew, playback, session_dir, state)
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("Error during '%s'", choice)
            console.print(
                f"\n[red]Error during '{choice}'.[/red] Check the log file for details."
            )
            console.print("[dim]Returning to main menu...[/dim]")


async def _shutdown(config: Config, amp: AmpController, rew: REWController) -> None:
    """Perform graceful shutdown: mute, stop generator, close connections."""
    console.print("\n[dim]Cleaning up...[/dim]")
    logger.info("Shutting down...")

    try:
        await amp.mute_all()
        await amp.set_master_mute(muted=True)
        logger.info("All channels muted.")
    except Exception:
        logger.exception("Error muting channels during shutdown")

    try:
        if config.playback.mode == PlaybackMode.REW_GENERATOR:
            await rew.generator_stop()
            logger.info("Generator stopped.")
    except Exception:
        logger.exception("Error stopping generator during shutdown")

    try:
        await rew.close()
        logger.info("REW connection closed.")
    except Exception:
        logger.exception("Error closing REW connection")

    console.print("[dim]Done.[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and launch the calibration session."""
    parser = argparse.ArgumentParser(
        prog="rew_to_musway",
        description="In-car speaker calibration using REW and Tunest PC.",
    )
    parser.add_argument(
        "--config",
        "-c",
        required=True,
        help="Path to YAML configuration file.",
    )
    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        sys.exit(1)

    # Create session directory
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_dir = (Path(config.paths.output_dir) / timestamp).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    log_path = session_dir / "calibration.log"
    _setup_logging(log_path)
    logger.info("Session started: %s", session_dir)
    logger.info("Config: %s", args.config)

    # Enable faulthandler so that segfaults (e.g. COM/ctypes crashes)
    # dump a traceback to the log file before the process dies.
    _fault_file = log_path.open("a", encoding="utf-8")
    faulthandler.enable(file=_fault_file)

    # Install global exception hooks (must be after logging setup)
    sys.excepthook = _excepthook
    threading.excepthook = _threading_excepthook
    sys.unraisablehook = _unraisablehook

    console.print(f"\n[bold]rew_to_musway[/bold] — session: {session_dir}")
    console.print(f"Log: {log_path}\n")

    # Run
    try:
        asyncio.run(_run(config, session_dir))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
