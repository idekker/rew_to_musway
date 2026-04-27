"""Tests for EQ calibration channel selection and flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rew_to_musway.calibration import select_channels

if TYPE_CHECKING:
    from rew_to_musway.config import Config


# ---------------------------------------------------------------------------
# Channel selection (pure logic)
# ---------------------------------------------------------------------------


class TestSelectChannels:
    def test_all(self, sample_config: Config) -> None:
        channels = select_channels(sample_config, "all")
        assert len(channels) == 6

    def test_single(self, sample_config: Config) -> None:
        channels = select_channels(sample_config, "single", single=3)
        assert len(channels) == 1
        assert channels[0].number == 3
        assert channels[0].name == "C"

    def test_start_from(self, sample_config: Config) -> None:
        channels = select_channels(sample_config, "start_from", start_from=4)
        expected_count = 3
        assert len(channels) == expected_count
        assert channels[0].number == 4
        assert channels[-1].number == 6

    def test_start_from_first(self, sample_config: Config) -> None:
        channels = select_channels(sample_config, "start_from", start_from=1)
        assert len(channels) == 6

    def test_single_nonexistent(self, sample_config: Config) -> None:
        channels = select_channels(sample_config, "single", single=99)
        assert len(channels) == 0
