"""filters.py - Match range computation and filter JSON export."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from aiorew import FilterSetting

    from .config import ChannelConfig


# ---------------------------------------------------------------------------
# Match range
# ---------------------------------------------------------------------------

MIN_FREQ = 20.0
MAX_FREQ = 20000.0


def compute_match_range(
    channel: ChannelConfig, margin_octaves: int = 1
) -> tuple[float, float]:
    """Compute the EQ match frequency range for a channel.

    Uses the channel's highpass/lowpass filter frequencies with a margin
    (in octaves) and clamps to [20, 20000] Hz.

    Parameters
    ----------
    channel:
        Channel configuration with optional highpass/lowpass filters.
    margin_octaves:
        Number of octaves to extend beyond the filter cutoff.

    Returns
    -------
    (start_hz, end_hz) tuple.

    """
    if channel.match_range is not None:
        return channel.match_range

    if channel.highpass is not None:
        start = max(MIN_FREQ, channel.highpass.frequency / (2**margin_octaves))
    else:
        start = MIN_FREQ

    if channel.lowpass is not None:
        end = min(MAX_FREQ, channel.lowpass.frequency * (2**margin_octaves))
    else:
        end = MAX_FREQ

    return (start, end)


# ---------------------------------------------------------------------------
# Filter JSON export
# ---------------------------------------------------------------------------


def export_filters_json(
    filters: list[FilterSetting],
    path: Path,
    *,
    model: str,
    channel_name: str,
) -> None:
    """Write REW filters to a JSON file in tunest_pc import format.

    Parameters
    ----------
    filters:
        List of FilterSetting objects from aiorew.
    path:
        Output file path.
    model:
        EQ model string (e.g. "31 bands (Output)").
    channel_name:
        Channel name for the "location" field.

    """
    active = [f for f in filters if f.type != "None"]
    eq_list = [
        {
            "number": f.index,
            "type": f.type,
            "freq": round(f.frequency, 1) if f.frequency is not None else 0.0,
            "gain": round(f.gaindB, 1) if f.gaindB is not None else 0.0,
            "q": round(f.q, 2) if f.q is not None else 1.0,
        }
        for f in active
    ]

    doc = {
        "model": model,
        "location": channel_name,
        "fileMagic": "autoIIR",
        "eq": eq_list,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(doc, fh, indent=2)
