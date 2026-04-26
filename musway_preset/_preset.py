"""Musway preset file read/write."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - used at runtime
from typing import TYPE_CHECKING

from musway_preset._channel import (
    MASTER_VOLUME_LINE,
    NUM_CHANNELS,
    Channel,
    CrossoverFilter,
    FilterType,
    Slope,
)

if TYPE_CHECKING:
    from aiorew import FilterSetting

_ENCODING = "utf-16le"
_LINE_ENDING = "\r\n"


class MuswayPreset:
    """Musway DSP preset file reader/writer.

    Supports 6 channels with 31-band parametric EQ, HP/LP crossovers,
    and channel/master volumes.
    """

    __slots__ = ("_channels", "_content")

    def __init__(self, content: list[str], channels: list[Channel]) -> None:
        self._content = content
        self._channels = channels

    @classmethod
    def load(cls, path: Path) -> MuswayPreset:
        """Load a preset file from disk.

        Parameters
        ----------
        path:
            Path to the preset file (UTF-16LE encoded).

        Returns
        -------
        Parsed MuswayPreset instance.

        """
        text = path.read_text(encoding=_ENCODING)
        lines = [line.strip() for line in text.splitlines()]
        channels = [
            Channel.from_preset_content(i, lines) for i in range(1, NUM_CHANNELS + 1)
        ]
        return cls(content=lines, channels=channels)

    def write(self, path: Path) -> None:
        """Write the preset to disk.

        All channel modifications are flushed to the internal content
        before writing.

        Parameters
        ----------
        path:
            Output file path.

        """
        for ch in self._channels:
            ch.write_to_content(self._content)
        # Master volume
        self._content[MASTER_VOLUME_LINE] = str(-1 * self.get_master_volume())
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = _LINE_ENDING.join(self._content).encode(_ENCODING)
        path.write_bytes(raw)

    # -- Channel access ------------------------------------------------------

    def _channel(self, channel: int) -> Channel:
        return self.channel(channel)

    def channel(self, channel: int) -> Channel:
        """Get a channel by number (1-indexed)."""
        if channel < 1 or channel > NUM_CHANNELS:
            msg = f"Channel must be 1-{NUM_CHANNELS}, got {channel}"
            raise ValueError(msg)
        return self._channels[channel - 1]

    # -- Volume --------------------------------------------------------------

    def get_channel_level(self, channel: int) -> float:
        """Get channel volume in dB."""
        return self._channel(channel).volume

    def set_channel_level(self, channel: int, db: float) -> None:
        """Set channel volume in dB."""
        self._channel(channel).volume = db

    def get_master_volume(self) -> int:
        """Get master volume in dB."""
        return -1 * int(self._content[MASTER_VOLUME_LINE])

    def set_master_volume(self, db: int) -> None:
        """Set master volume in dB."""
        self._content[MASTER_VOLUME_LINE] = str(-1 * db)

    # -- EQ ------------------------------------------------------------------

    def set_eq_filters(self, channel: int, filters: list[FilterSetting]) -> None:
        """Apply aiorew FilterSetting objects to a channel's EQ."""
        self._channel(channel).eq.from_filter_settings(filters)

    def reset_eq(self, channel: int) -> None:
        """Reset a channel's EQ to flat (all gains 0.0 dB)."""
        self._channel(channel).eq.reset()

    # -- Crossover -----------------------------------------------------------

    def set_highpass(
        self,
        channel: int,
        filter_type: FilterType,
        frequency: int,
        slope: Slope,
    ) -> None:
        """Set highpass crossover filter for a channel."""
        self._channel(channel).highpass = CrossoverFilter(
            filter_type=filter_type,
            frequency=frequency,
            slope=slope,
        )

    def set_lowpass(
        self,
        channel: int,
        filter_type: FilterType,
        frequency: int,
        slope: Slope,
    ) -> None:
        """Set lowpass crossover filter for a channel."""
        self._channel(channel).lowpass = CrossoverFilter(
            filter_type=filter_type,
            frequency=frequency,
            slope=slope,
        )
