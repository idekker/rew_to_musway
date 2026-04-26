"""Volume and gain encoding/decoding for Musway preset files."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Volume encoding
# ---------------------------------------------------------------------------
#
# The preset file stores channel volumes as integers with a bit-field layout
# where bit 7 is a dead (always-zero) bit.  To decode, remove bit 7 and
# scale by -0.1.  To encode, compute the logical value (dB * -10), then
# insert a zero bit at position 7.
#
# The encoding is lossless at 0.1 dB resolution — every 0.1 dB step from
# 0.0 downward is representable.

_DEAD_BIT: int = 7
_LOW_MASK: int = (1 << _DEAD_BIT) - 1  # 0x7F — bits 0-6


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
    logical = ((val >> 1) & ~_LOW_MASK) | (val & _LOW_MASK)
    return round(-0.1 * logical, 1)


def encode_volume(db: float) -> int:
    """Encode a dB volume to the preset integer format.

    Parameters
    ----------
    db:
        Volume in dB (should be <= 0).

    Returns
    -------
    Encoded integer for the preset file.

    """
    logical = round(-db * 10)
    return ((logical & ~_LOW_MASK) << 1) | (logical & _LOW_MASK)


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
