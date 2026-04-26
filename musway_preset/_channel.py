"""Channel, EQ, and crossover filter models for Musway preset files."""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from musway_preset._encoding import (
    decode_gain,
    decode_volume,
    encode_gain,
    encode_volume,
)

if TYPE_CHECKING:
    from aiorew import FilterSetting

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_EQ_BANDS: int = 31
CHANNEL_BLOCK_SIZE: int = 99
"""Lines per channel: 31 freqs + 31 gains + 31 Qs + 3 HP + 3 LP."""

FREQ_OFFSET: int = 0
GAIN_OFFSET: int = 31
Q_OFFSET: int = 62
HP_OFFSET: int = 93
LP_OFFSET: int = 96

HEADER_LINES: int = 7
CHANNEL_VOLUME_OFFSET: int = 7
NUM_CHANNELS: int = 6
MASTER_VOLUME_LINE: int = 13
CHANNEL_DATA_START: int = 14

MIN_GAIN: float = -15.0
MAX_GAIN: float = 15.0
MIN_Q: float = 1.0
MAX_Q: float = 10.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FilterType(IntEnum):
    """Crossover filter type."""

    BUTTERWORTH = 0
    BESSEL = 1
    LINKWITZ_RILEY = 2


class Slope(IntEnum):
    """Crossover filter slope."""

    DB_6 = 0
    DB_12 = 1
    DB_18 = 2
    DB_24 = 3
    DB_30 = 4
    DB_36 = 5
    DB_42 = 6
    DB_48 = 7
    OFF = 8


# ---------------------------------------------------------------------------
# CrossoverFilter
# ---------------------------------------------------------------------------


class CrossoverFilter:
    """Highpass or lowpass crossover filter."""

    __slots__ = ("filter_type", "frequency", "slope")

    def __init__(
        self,
        filter_type: FilterType,
        frequency: int,
        slope: Slope,
    ) -> None:
        self.filter_type = filter_type
        self.frequency = frequency
        self.slope = slope

    @classmethod
    def from_preset_lines(cls, lines: list[str]) -> CrossoverFilter:
        """Parse from 3 consecutive preset lines."""
        return cls(
            filter_type=FilterType(int(lines[0])),
            frequency=int(lines[1]),
            slope=Slope(int(lines[2])),
        )

    def to_preset_lines(self) -> list[str]:
        """Serialize to 3 preset lines."""
        return [
            str(self.filter_type.value),
            str(self.frequency),
            str(self.slope.value),
        ]


# ---------------------------------------------------------------------------
# EQ
# ---------------------------------------------------------------------------


class EQ:
    """31-band parametric equalizer."""

    __slots__ = ("frequencies", "gains", "q_factors")

    def __init__(
        self,
        frequencies: list[int],
        gains: list[float],
        q_factors: list[float],
    ) -> None:
        self.frequencies = frequencies
        self.gains = gains
        self.q_factors = q_factors

    @classmethod
    def from_preset_lines(cls, lines: list[str]) -> EQ:
        """Parse from 93 consecutive preset lines (31 freq + 31 gain + 31 Q).

        Band order is preserved as-is from the preset file.
        """
        return cls(
            frequencies=[
                int(x) for x in lines[FREQ_OFFSET : FREQ_OFFSET + NUM_EQ_BANDS]
            ],
            gains=[
                decode_gain(int(x))
                for x in lines[GAIN_OFFSET : GAIN_OFFSET + NUM_EQ_BANDS]
            ],
            q_factors=[float(x) for x in lines[Q_OFFSET : Q_OFFSET + NUM_EQ_BANDS]],
        )

    def to_preset_lines(self) -> list[str]:
        """Serialize to 93 preset lines."""
        lines: list[str] = []
        lines.extend(str(f) for f in self.frequencies)
        lines.extend(str(encode_gain(g)) for g in self.gains)
        lines.extend(f"{q:>1.6f}" for q in self.q_factors)
        return lines

    def reset(self) -> None:
        """Reset all gains to 0.0 dB, preserving frequencies and Q factors."""
        self.gains = [0.0] * NUM_EQ_BANDS

    def from_filter_settings(self, filters: list[FilterSetting]) -> None:
        """Apply aiorew FilterSetting objects to this EQ.

        Resets all gains to 0.0 dB first, then applies active Peak filters.
        Gains are clamped to [-15.0, +15.0] dB. Q values are clamped to
        [1.0, 10.0].

        Parameters
        ----------
        filters:
            List of FilterSetting objects from aiorew.

        """
        self.reset()
        for f in filters:
            if f.type == "None" or not f.enabled:
                continue
            idx = f.index - 1
            if idx < 0 or idx >= NUM_EQ_BANDS:
                continue
            if f.frequency is not None:
                self.frequencies[idx] = round(f.frequency)
            if f.gaindB is not None:
                self.gains[idx] = max(MIN_GAIN, min(MAX_GAIN, f.gaindB))
            if f.q is not None:
                self.q_factors[idx] = max(MIN_Q, min(MAX_Q, f.q))


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


class Channel:
    """A single DSP channel with volume, EQ, and crossover filters."""

    __slots__ = ("channel_id", "eq", "highpass", "lowpass", "volume")

    def __init__(
        self,
        channel_id: int,
        volume: float,
        eq: EQ,
        highpass: CrossoverFilter,
        lowpass: CrossoverFilter,
    ) -> None:
        self.channel_id = channel_id
        self.volume = volume
        self.eq = eq
        self.highpass = highpass
        self.lowpass = lowpass

    @classmethod
    def from_preset_content(
        cls,
        channel_id: int,
        content: list[str],
    ) -> Channel:
        """Parse a channel from full preset content lines."""
        volume = decode_volume(int(content[CHANNEL_VOLUME_OFFSET + (channel_id - 1)]))
        block_start = CHANNEL_DATA_START + (channel_id - 1) * CHANNEL_BLOCK_SIZE
        block = content[block_start : block_start + CHANNEL_BLOCK_SIZE]
        return cls(
            channel_id=channel_id,
            volume=volume,
            eq=EQ.from_preset_lines(block),
            highpass=CrossoverFilter.from_preset_lines(block[HP_OFFSET:]),
            lowpass=CrossoverFilter.from_preset_lines(block[LP_OFFSET:]),
        )

    def write_to_content(self, content: list[str]) -> None:
        """Write this channel's data back into preset content lines.

        Modifies *content* in place.
        """
        # Volume
        content[CHANNEL_VOLUME_OFFSET + (self.channel_id - 1)] = str(
            encode_volume(self.volume)
        )
        # EQ + crossover block
        block_start = CHANNEL_DATA_START + (self.channel_id - 1) * CHANNEL_BLOCK_SIZE
        eq_lines = self.eq.to_preset_lines()
        content[block_start : block_start + NUM_EQ_BANDS * 3] = eq_lines
        hp_lines = self.highpass.to_preset_lines()
        content[block_start + HP_OFFSET : block_start + HP_OFFSET + 3] = hp_lines
        lp_lines = self.lowpass.to_preset_lines()
        content[block_start + LP_OFFSET : block_start + LP_OFFSET + 3] = lp_lines
