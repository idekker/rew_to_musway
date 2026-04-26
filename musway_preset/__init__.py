"""musway_preset — Musway DSP preset file read/write library.

Supports reading, modifying, and writing Musway preset files (UTF-16LE,
6-channel, 31-band parametric EQ, HP/LP crossovers, channel/master volumes).
"""

from musway_preset._channel import (
    EQ,
    Channel,
    CrossoverFilter,
    FilterType,
    Slope,
)
from musway_preset._encoding import decode_volume, encode_volume
from musway_preset._preset import MuswayPreset

__all__ = [
    "EQ",
    "Channel",
    "CrossoverFilter",
    "FilterType",
    "MuswayPreset",
    "Slope",
    "decode_volume",
    "encode_volume",
]
