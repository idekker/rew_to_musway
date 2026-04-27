# AGENTS.md

## Project Overview

This repository contains four Python packages for in-car speaker calibration:

- **`tunest_pc`** — Sync library that automates the Tunest PC DSP application via COM/win32gui UI automation. Windows-only.
- **`aiorew`** — Async client library for the [REW](https://www.roomeqwizard.com/) (Room EQ Wizard) HTTP API. Controls measurements, RTA, SPL meter, signal generator, and EQ filter matching.
- **`musway_preset`** — Musway DSP preset file read/write library. Supports reading, modifying (levels, EQ, crossovers), and writing Musway preset files (UTF-16LE, 6-channel, 31-band parametric EQ). Independent of `rew_to_musway`.
- **`rew_to_musway`** — Interactive async CLI that orchestrates the above libraries to perform calibration. Supports two modes: **automated** (via Tunest PC COM automation) and **manual** (via Musway preset files + user prompts).

The legacy `MuswayPresetEditor.py` in the repo root is unrelated to the current packages and should be ignored.

## Architecture

```
rew_to_musway/              # CLI application (async, rich + questionary)
├── __main__.py             # Entry point, menu loop, logging, shutdown, backend selection
├── config.py               # YAML config loader (dataclasses), optional tunest_pc
├── amp.py                  # AmpBackend protocol + TunestPCAmp (COM automation)
├── manual_amp.py           # ManualAmp backend (preset files + user prompts)
├── prompt.py               # Timer-with-cancel user prompts (msvcrt keypress polling)
├── sanity.py               # SPL sanity check before measurements
├── rew.py                  # REWController — async wrapper around aiorew
├── filters.py              # Filter export (REW filters -> JSON for tunest_pc)
├── menu.py                 # Interactive menu (questionary + rich)
├── calibration/            # Calibration logic
│   ├── _eq.py              # Phase 2: per-channel EQ matching (individual)
│   ├── _levels.py          # Phases 1 & 4: level balancing and verification (individual)
│   ├── _verification.py    # Phase 3: post-EQ verification measurements (individual)
│   ├── _unified.py         # Combined calibration flow (phases 1+2, finetune, 3+4)
│   └── _combined.py        # Phase 5: multi-channel combined measurements
└── playback/               # Playback strategy pattern
    ├── _base.py            # Abstract PlaybackStrategy (includes shared SPL check loop)
    ├── _manual.py          # Manual playback (USB stick pink noise)
    └── _rew_generator.py   # REW-controlled signal generator playback

musway_preset/              # Musway preset file library
├── __init__.py             # Public API re-exports
├── _preset.py              # MuswayPreset: load, write, channel access
├── _channel.py             # Channel, EQ (31-band), CrossoverFilter
└── _encoding.py            # Volume encode/decode (dead-bit-7 bit-field), gain encode/decode

aiorew/                     # Async REW HTTP API client
tunest_pc/                  # Sync Tunest PC UI automation (COM/win32gui)
tests/                      # pytest test suite (154 tests, all async)
```

### Key Design Patterns

- **AmpBackend protocol with buffer/apply** — All DSP state mutations (levels, EQ filters, crossovers) are buffered in memory. `apply()` flushes the buffer: `TunestPCAmp` via COM calls, `ManualAmp` by writing a preset file + copying path to clipboard + prompting the user. This minimises user interactions in manual mode and COM round-trips in automated mode.
- **Backend selection** — Presence of `tunest_pc` config section selects `TunestPCAmp`; absence selects `ManualAmp`. Both implement `AmpBackend`. Calibration code is backend-agnostic.
- **Combined calibration flow** (`_unified.py`) — Merges measurement phases to reduce solo/mute cycles: Phase 1+2 (SPL+RTA per channel, then batch EQ), finetune (batch iterations), Phase 3+4 (RTA+SPL verification). Original individual phases in `_eq.py`/`_levels.py`/`_verification.py` are preserved for automated mode.
- **Timer-with-cancel prompts** — `prompt.py` shows countdown with Enter (continue), Backspace (cancel timer → wait for Enter), or timer expiry (auto-continue). Uses `msvcrt` keypress polling.
- **SPL sanity check** — Quick SPL read before measurements; warns if too low (configurable threshold), offers retry/proceed.
- **Cumulative preset chain** — `ManualAmp` writes versioned presets (`preset_initial.txt`, `preset_eq.txt`, `preset_finetune_{n}.txt`, `preset_verification.txt`), each built by loading the previous and applying new changes.
- **Volume encoding has a dead bit** — `musway_preset` encodes volumes via a bit-field where bit 7 is always zero (dead). To decode: remove bit 7, scale by -0.1. To encode: compute `round(-dB * 10)`, insert a zero bit at position 7. Encoding is lossless at 0.1 dB resolution.
- **`tunest_pc` is synchronous** — all calls from `rew_to_musway` are wrapped with `asyncio.to_thread()` in `amp.py`.
- **`aiorew` is fully async** — used directly in `rew.py`.
- **Playback strategies** use the strategy pattern with a shared SPL check loop in the abstract base class.
- **Configuration** is loaded from YAML into dataclasses. See `config.example.yaml` for the expected schema.
- **Level offsets are always ≤ 0** — within each channel group, the quietest channel is the reference; louder channels are attenuated, never boosted.
- **comtypes `Release()` is suppressed** — `_compointer_base.__del__` is monkey-patched to a no-op in `tunest_pc/_client.py` to prevent heap corruption (0xc0000374) from stale UIA COM pointers. COM references are intentionally leaked; the OS reclaims them on process exit.
- **Windows asyncio SIGINT workaround** — `__main__.py` installs `signal.default_int_handler` and a periodic wakeup task so Ctrl+C works reliably with `ProactorEventLoop`.
- **Console input buffer flush** — `menu.py` drains leftover keypresses via `msvcrt.kbhit()`/`getch()` before every `questionary` prompt to prevent stale Enter keys from auto-selecting menu items.

## Language and Runtime

- **Python 3.10+** (type hints use `X | Y` union syntax, `from __future__ import annotations` where needed)
- **Windows-only** at runtime (`tunest_pc` requires win32gui/COM, `manual_amp` uses `win32clipboard`, `prompt.py` uses `msvcrt`). Tests can run on any platform since they mock all hardware interaction.
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
- **No top-level imports that are only used in annotations** (TC003) — move to `TYPE_CHECKING` block
- **No imports inside functions** (PLC0415) — move to module level or `TYPE_CHECKING`

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

Shared fixtures are in `tests/conftest.py`: `sample_config`, `sample_channels`, `mock_rew`, `mock_amp`, `mock_playback`, `mock_spl_values`.

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
- `tunest_pc` — *(optional)* Tunest PC executable path and amp model. Presence activates automated mode.
- `manual` — Manual mode config. Used when `tunest_pc` is absent.
  - `default_preset_path` — Path to the base Musway preset file (required in manual mode)
  - `spl_sanity_threshold` — dB below target SPL to trigger warning (default: `-10.0`)
  - `timers.action_timeout` — Seconds for mute/solo prompts (default: `10`)
  - `timers.preset_load_timeout` — Seconds for preset load prompts (default: `30`)
- `playback` — Mode (`manual` or `rew_generator`), generator settings, SPL tolerance
- `levels` — SPL measurement timing (settle/measure duration)
- `paths` — Output directory, house curve path
- `channels` — List of channels with number, name, group, HP/LP filter config

### Mode Selection

- **Automated mode:** Include `tunest_pc` section in config. `TunestPCAmp` controls DSP via COM automation.
- **Manual mode:** Omit `tunest_pc` section entirely. `ManualAmp` writes preset files and prompts the user to load them in Musway software. Requires `manual.default_preset_path` to be set.

Both modes may coexist in config (manual settings as fallback), but at runtime exactly one backend is active based on presence of `tunest_pc`.

## musway_preset Package

Independent library for Musway preset files. Key details:

- **Preset file format:** UTF-16LE, no BOM, `\r\n` line endings, 1992 lines, 6 channels x 99-line blocks starting at line 14
- **Volume encoding:** Lossless bit-field at 0.1 dB resolution. Bit 7 is a dead (always-zero) bit. To decode: remove bit 7, scale by -0.1. To encode: compute `round(-dB * 10)`, insert a zero bit at position 7. Round-trip `decode(encode(x))` is exact for all 0.1 dB values.
- **Gain encoding:** Lossless. `encode_gain(dB) = int((15.0 - gain) * 10)`, range [-15, +15].
- **Write fidelity:** Uses raw bytes (`Path.write_bytes()`) not `Path.write_text()` to avoid extra bytes. Round-trip read/write is byte-identical for unmodified presets.
- **Fixed 6 channels** — no support for other amp models.
- **Accepts `aiorew.FilterSetting`** objects directly for EQ (no intermediate format).

## Dependencies

Runtime: `pywin32`, `comtypes`, `psutil`, `httpx`, `numpy`, `pyyaml`, `rich`, `questionary`

Dev: `ruff`, `pytest`, `pytest-asyncio`

Install: `pip install -e ".[dev]"`
