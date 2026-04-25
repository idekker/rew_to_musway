# AGENTS.md

## Project Overview

This repository contains three Python packages for in-car speaker calibration:

- **`tunest_pc`** — Sync library that automates the Tunest PC DSP application via COM/win32gui UI automation. Windows-only.
- **`aiorew`** — Async client library for the [REW](https://www.roomeqwizard.com/) (Room EQ Wizard) HTTP API. Controls measurements, RTA, SPL meter, signal generator, and EQ filter matching.
- **`rew_to_musway`** — Interactive async CLI that orchestrates both libraries to perform a 4-phase calibration pipeline: level balancing, per-channel EQ calibration, verification measurements, and level verification.

The legacy `MuswayPresetEditor.py` in the repo root is unrelated to the current packages and should be ignored.

## Architecture

```
rew_to_musway/              # CLI application (async, rich + questionary)
├── __main__.py             # Entry point, menu loop, logging, shutdown
├── config.py               # YAML config loader (dataclasses)
├── amp.py                  # AmpController — async wrapper around tunest_pc (uses asyncio.to_thread)
├── rew.py                  # REWController — async wrapper around aiorew
├── filters.py              # Filter export (REW filters -> JSON for tunest_pc)
├── menu.py                 # Interactive menu (questionary + rich)
├── calibration/            # 4-phase calibration logic
│   ├── _eq.py              # Phase 2: per-channel EQ matching
│   ├── _levels.py          # Phases 1 & 4: level balancing and verification
│   └── _verification.py    # Phase 3: post-EQ verification measurements
└── playback/               # Playback strategy pattern
    ├── _base.py            # Abstract PlaybackStrategy (includes shared SPL check loop)
    ├── _manual.py          # Manual playback (USB stick pink noise)
    └── _rew_generator.py   # REW-controlled signal generator playback

aiorew/                     # Async REW HTTP API client
tunest_pc/                  # Sync Tunest PC UI automation (COM/win32gui)
tests/                      # pytest test suite (62 tests, all async)
```

### Key Design Patterns

- **`tunest_pc` is synchronous** — all calls from `rew_to_musway` are wrapped with `asyncio.to_thread()` in `amp.py`.
- **`aiorew` is fully async** — used directly in `rew.py`.
- **Playback strategies** use the strategy pattern with a shared SPL check loop in the abstract base class.
- **Configuration** is loaded from YAML into frozen dataclasses. See `config.example.yaml` for the expected schema.
- **`_eq.py`** uses a `_CalibrationContext` dataclass to bundle calibration state and reduce argument passing across helper functions.
- **Level offsets are always ≤ 0** — within each channel group, the quietest channel is the reference; louder channels are attenuated, never boosted.
- **comtypes `Release()` is suppressed** — `_compointer_base.__del__` is monkey-patched to a no-op in `tunest_pc/_client.py` to prevent heap corruption (0xc0000374) from stale UIA COM pointers. COM references are intentionally leaked; the OS reclaims them on process exit.
- **Windows asyncio SIGINT workaround** — `__main__.py` installs `signal.default_int_handler` and a periodic wakeup task so Ctrl+C works reliably with `ProactorEventLoop`.
- **Console input buffer flush** — `menu.py` drains leftover keypresses via `msvcrt.kbhit()`/`getch()` before every `questionary` prompt to prevent stale Enter keys from auto-selecting menu items.

## Language and Runtime

- **Python 3.10+** (type hints use `X | Y` union syntax, `from __future__ import annotations` where needed)
- **Windows-only** at runtime (`tunest_pc` requires win32gui/COM). Tests can run on any platform since they mock all hardware interaction.
- Virtual environment at `.venv/`

## Code Quality

### Linting — Ruff

Ruff is configured with `select = ["ALL"]` (every rule enabled) with specific ignores. This is strict — pay attention to:

- **No relative imports** in `TYPE_CHECKING` blocks — use absolute imports (TID252)
- **Move runtime imports out** of `TYPE_CHECKING` if used at runtime (TC004)
- **Move type-only imports into** `TYPE_CHECKING` blocks (TC001, TC003)
- **No magic numbers** — extract to module-level constants (PLR2004)
- **No `except Exception`** without `# noqa: BLE001` justification
- **No `try`/`except` in loops** without `# noqa: PERF203` justification
- **Use list comprehensions** over `for` + `append` (PERF401)
- **Use keyword-only arguments** for booleans (FBT001) — use `*` separator
- **Prefer `TypeError`** over `ValueError` for type-checking guards (TRY004)
- **Import sorting** must follow isort conventions (I001) — stdlib, then third-party, then local
- **No `Path.resolve()` in async functions** (ASYNC240) — resolve paths before entering async context

Run lint:

```bash
.venv/Scripts/python.exe -m ruff check . --no-fix
```

Auto-fix what's safe:

```bash
.venv/Scripts/python.exe -m ruff check . --fix
```

### Formatting — Ruff

Ruff format is configured to match Black defaults (double quotes, 88-char line length, spaces).

Check formatting:

```bash
.venv/Scripts/python.exe -m ruff format --check .
```

Apply formatting:

```bash
.venv/Scripts/python.exe -m ruff format .
```

### Testing — pytest

Tests use `pytest` with `pytest-asyncio` in auto mode (all async tests are detected automatically, no need for `@pytest.mark.asyncio` decorators — though they are present for explicitness).

Shared fixtures are in `tests/conftest.py`: `sample_config`, `mock_rew`, `mock_amp`, `mock_playback`, `mock_spl_values`.

All hardware interaction is mocked via `unittest.mock.AsyncMock`. Tests run on any platform.

Run tests:

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

### Per-File Lint Relaxations

Defined in `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]`:

- `tests/*` — `S101` (assert allowed), `PLR2004` (magic values allowed)
- `example_*.py` — `T201` (print allowed)

## Workflow

After making changes, always run in this order:

1. `ruff format .` — format first
2. `ruff check . --no-fix` — lint (fix manually or with `--fix`)
3. `pytest tests/ -q` — ensure all tests pass

All three must be clean (zero errors, zero reformats, zero failures) before considering work complete.

## Configuration

The CLI is configured via a YAML file (see `config.example.yaml`). Key sections:

- `rew` — REW API connection (host, port)
- `tunest_pc` — Tunest PC executable path and amp model
- `playback` — Mode (`manual` or `rew_generator`), generator settings, SPL tolerance
- `levels` — SPL measurement timing (settle/measure duration)
- `paths` — Output directory, house curve path
- `channels` — List of channels with number, name, group, HP/LP filter config

## Dependencies

Runtime: `pywin32`, `comtypes`, `psutil`, `httpx`, `numpy`, `pyyaml`, `rich`, `questionary`

Dev: `ruff`, `pytest`, `pytest-asyncio`

Install: `pip install -e ".[dev]"`
