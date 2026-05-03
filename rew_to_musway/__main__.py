"""__main__.py - Entry point for python -m rew_to_musway."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import msvcrt
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import keyboard
from keyboard import KeyboardEvent
from prompt_toolkit.input import PipeInput, create_pipe_input
from rich.console import Console

from rew_to_musway.amp import ManualAmp, MuswayAmp, TunestPCAmp

from .calibration import (
    MeasureResult,
    UnifiedContext,
    eligible_finetune_channels,
    run_combined_measurements,
    run_finetune_loop,
    run_measure_loop,
    run_verification_loop,
    save_session,
    select_channels,
)
from .config import Config, PlaybackMode, load_config
from .menu import ask_channel_mode, ask_main_menu, show_status
from .playback import ManualPlayback, PlaybackStrategy, REWGeneratorPlayback
from .rew import REWController

if TYPE_CHECKING:
    import types
    from collections.abc import Awaitable, Callable

    from rew_to_musway.amp import AmpBackend

ENABLE_FAULTHANDLER = False
if ENABLE_FAULTHANDLER:
    import faulthandler

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
        return REWGeneratorPlayback(rew, config.playback, config.levels, config.timer)
    return ManualPlayback(rew, config.levels, config.timer)


def _create_amp_backend(config: Config, session_dir: Path) -> AmpBackend:
    """Create the amp backend based on config."""
    if config.tunest_pc is not None:
        logger.info("Using TunestPC backend (automated mode)")
        return TunestPCAmp(config)

    if config.musway is not None:
        logger.info("Using Musway backend (automated mode)")
        return MuswayAmp(
            config=config.musway,
            timer_config=config.timer,
            channels=config.channels,
            session_dir=session_dir,
        )

    logger.info("Using Manual backend (preset file mode)")
    return ManualAmp(
        config=config.manual,
        timer_config=config.timer,
        channels=config.channels,
        session_dir=session_dir,
    )


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
    amp: AmpBackend,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    state: _SessionState,
    input_pipe: PipeInput,
) -> None:
    """Execute the user's menu choice."""
    ctx = UnifiedContext(
        config=config,
        amp=amp,
        rew=rew,
        playback=playback,
        session_dir=session_dir,
    )
    if choice == "Save measurements (.mdat)":
        await save_session(rew, session_dir)
    else:
        await ctx.playback.start_noise()
        await ctx.amp.set_master_mute(muted=False)
        await ctx.amp.unmute_all_channels()
        try:
            if choice == "Full calibration (phases 1-5)":
                await _run_full_calibration(ctx, state)
            elif choice == "Level balancing + EQ (phases 1-2)":
                mode, ch_num = await ask_channel_mode(config, input_pipe)
                channels = select_channels(
                    config, mode, start_from=ch_num, single=ch_num
                )
                state.measure_result = await run_measure_loop(ctx, channels)
            elif choice == "Finetune EQ":
                if state.measure_result is None:
                    console.print(
                        "[yellow]No measurement data — run phases 1-2 first.[/yellow]"
                    )
                    return
                mode, ch_num = await ask_channel_mode(config, input_pipe)
                channels = select_channels(
                    config, mode, start_from=ch_num, single=ch_num
                )
                state.finetune_iteration += 1
                state.measure_result.predicted_uuids = await run_finetune_loop(
                    ctx,
                    channels,
                    state.measure_result.rta_uuids,
                    state.measure_result.predicted_uuids,
                    iteration=state.finetune_iteration,
                )
            elif choice == "Verification (phases 3-4)":
                await run_verification_loop(ctx)
            elif choice == "Combined measurements (phase 5)":
                await run_combined_measurements(config, amp, rew)
        except Exception:
            await ctx.amp.set_master_mute(muted=True)
            raise
        finally:
            await ctx.playback.stop_noise()


async def _run_full_calibration(
    ctx: UnifiedContext,
    state: _SessionState,
) -> None:
    """Execute the complete calibration pipeline using the unified flow."""
    # Phase 1+2: measure + EQ
    state.measure_result = await run_measure_loop(ctx)

    # Finetune loops — auto-determine max iterations from config
    max_finetune = max((ch.finetune_loops for ch in ctx.config.channels), default=0)
    for iteration in range(1, max_finetune + 1):
        eligible = eligible_finetune_channels(ctx.config.channels, iteration)
        if not eligible:
            break
        console.print(
            f"\n[dim]Finetune iteration {iteration}/{max_finetune} "
            f"({len(eligible)} channels eligible)[/dim]"
        )
        state.measure_result.predicted_uuids = await run_finetune_loop(
            ctx,
            ctx.config.channels,
            state.measure_result.rta_uuids,
            state.measure_result.predicted_uuids,
            iteration=iteration,
        )

    # Phase 3+4: verification
    await run_verification_loop(ctx)

    # Phase 5: combined
    await run_combined_measurements(ctx.config, ctx.amp, ctx.rew)

    # Save
    await save_session(ctx.rew, ctx.session_dir)
    console.print("\n[bold green]Full calibration complete![/bold green]")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class _SessionState:
    """Mutable session state shared across menu iterations."""

    def __init__(self) -> None:
        self.measure_result: MeasureResult | None = None
        self.finetune_iteration: int = 0


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
    amp = _create_amp_backend(config, session_dir)
    playback = _create_playback(config, rew)
    state = _SessionState()

    # --- Connect ---
    console.print("\n[bold]Connecting...[/bold]")

    if not await _connect_with_retry("REW", rew.connect):
        console.print("[red]Cannot proceed without REW connection.[/red]")
        return

    await rew.delete_all_measurements()
    logger.info("Cleared existing REW measurements.")

    # Connect amp backend (TunestPCAmp needs COM, ManualAmp is no-op)
    if not await _connect_with_retry("Amp backend", amp.connect):
        console.print("[red]Cannot proceed without amp connection.[/red]")
        await rew.close()
        return

    with create_pipe_input() as input_pipe:
        key_task = asyncio.create_task(_listen_globally(input_pipe))

        try:
            await _menu_loop(config, amp, rew, playback, session_dir, state, input_pipe)
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
            input_pipe.flush()
            wakeup_task.cancel()
            key_task.cancel()
            await _shutdown(config, rew)


async def _menu_loop(  # noqa: PLR0913
    config: Config,
    amp: AmpBackend,
    rew: REWController,
    playback: PlaybackStrategy,
    session_dir: Path,
    state: _SessionState,
    input_pipe: PipeInput,
) -> None:
    """Run the interactive menu loop until the user quits."""
    while True:
        console.print()
        show_status(config, rew_connected=True, amp_connected=True)

        choice = await ask_main_menu(input_pipe)
        logger.info("Menu selection: %s", choice)

        if choice == "Quit":
            break

        try:
            await _dispatch_menu(
                choice, config, amp, rew, playback, session_dir, state, input_pipe
            )
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("Error during '%s'", choice)
            console.print(
                f"\n[red]Error during '{choice}'.[/red] Check the log file for details."
            )
            console.print("[dim]Returning to main menu...[/dim]")


async def _listen_globally(input_pipe: PipeInput) -> None:
    def _clear_stdin_buffer_and_insert_character(ch: bytes) -> None:
        if msvcrt.kbhit():
            msvcrt.getch()
        msvcrt.ungetch(ch)

    def on_key(event: KeyboardEvent) -> None:
        with contextlib.suppress(Exception):
            if event.name == "enter":
                input_pipe.send_bytes(b"\r")
                _clear_stdin_buffer_and_insert_character(b"\r")
            elif event.name in {"j", "down"}:
                input_pipe.send_bytes(b"j")
                _clear_stdin_buffer_and_insert_character(b"j")
            elif event.name in {"k", "up"}:
                input_pipe.send_bytes(b"k")
                _clear_stdin_buffer_and_insert_character(b"k")
            elif event.name == "esc":
                input_pipe.send_bytes(b"\x1b")
                _clear_stdin_buffer_and_insert_character(b"\x1b")

    async def _do_wait() -> None:
        stop = asyncio.Event()
        while not stop.is_set():  # noqa: ASYNC110 — intentional periodic wakeup for signal handling
            await asyncio.sleep(0.5)

    keyboard.on_press(on_key)
    await _do_wait()


async def _shutdown(config: Config, rew: REWController) -> None:
    """Perform graceful shutdown: mute, stop generator, close connections."""
    console.print("\n[dim]Cleaning up...[/dim]")
    logger.info("Shutting down...")

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

    if ENABLE_FAULTHANDLER:
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
