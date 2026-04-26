"""Volume and gain encoding/decoding for Musway preset files."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Volume encoding
# ---------------------------------------------------------------------------
#
# The preset file stores channel volumes as integers with a bit-field layout.
# Bit 7 is a dead bit (ignored by decode).  Not all 0.1 dB values are
# representable — there are periodic 0.9 dB gaps every ~3.2 dB caused by
# bit 4 double-contributing.  For encoding we build a lookup table from
# decoded values to the smallest encoded int, then snap to the nearest
# representable value.

_MAX_ENCODED: int = 4096

_DECODE_TABLE: dict[float, int] = {}
# Pairs sorted by dB descending (0.0 first) for nearest-value search.
_ENCODE_SORTED: list[tuple[float, int]] = []


def _decode_raw(val: int) -> float:
    return round(-0.1 * (((val & 0xFF10) >> 1) | (val & 0x7F)), 1)


def _build_tables() -> None:
    if _DECODE_TABLE:
        return
    for v in range(_MAX_ENCODED):
        db = _decode_raw(v)
        if db not in _DECODE_TABLE:
            _DECODE_TABLE[db] = v
    _ENCODE_SORTED.extend(
        sorted(_DECODE_TABLE.items(), key=lambda x: x[0], reverse=True)
    )


def decode_volume(val: int) -> float:
    """Decode a preset volume integer to dB.

    Parameters
    ----------
    val:
        Raw integer from the preset file.

    Returns
    -------
    Volume in dB (always <= 0).

    """
    return _decode_raw(val)


def encode_volume(db: float) -> int:
    """Encode a dB volume to the preset integer format.

    Snaps to the nearest representable value (0.1 dB resolution with
    periodic gaps).

    Parameters
    ----------
    db:
        Volume in dB (should be <= 0).

    Returns
    -------
    Encoded integer for the preset file.

    """
    _build_tables()
    if db in _DECODE_TABLE:
        return _DECODE_TABLE[db]
    # Snap to nearest representable value
    best_val = 0
    best_diff = float("inf")
    for entry_db, entry_val in _ENCODE_SORTED:
        diff = abs(db - entry_db)
        if diff < best_diff:
            best_diff = diff
            best_val = entry_val
        elif entry_db < db - 1.0:
            break
    return best_val


# ---------------------------------------------------------------------------
# Gain encoding
# ---------------------------------------------------------------------------

_GAIN_ZERO_OFFSET: float = 15.0
_GAIN_SCALE: int = 10


def decode_gain(val: int) -> float:
    """Decode a preset EQ gain integer to dB.

    Parameters
    ----------
    val:
        Raw integer from preset (e.g. 150 = 0.0 dB).

    Returns
    -------
    Gain in dB, range [-15.0, +15.0].

    """
    return _GAIN_ZERO_OFFSET - val / _GAIN_SCALE


def encode_gain(db: float) -> int:
    """Encode a dB gain to the preset integer format.

    Parameters
    ----------
    db:
        Gain in dB, will be clamped to [-15.0, +15.0].

    Returns
    -------
    Encoded integer for the preset file.

    """
    clamped = max(-_GAIN_ZERO_OFFSET, min(_GAIN_ZERO_OFFSET, db))
    return int((_GAIN_ZERO_OFFSET - clamped) * _GAIN_SCALE)
