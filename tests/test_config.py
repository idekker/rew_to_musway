"""Tests for config loading and match range computation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rew_to_musway.config import (
    ChannelConfig,
    FilterConfig,
    FilterType,
    PlaybackMode,
    load_config,
)
from rew_to_musway.filters import compute_match_range

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# compute_match_range
# ---------------------------------------------------------------------------


class TestComputeMatchRange:
    def test_no_filters(self) -> None:
        ch = ChannelConfig(number=1, name="LF", group="front")
        assert compute_match_range(ch) == (20.0, 20000.0)

    def test_highpass_only(self) -> None:
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            highpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=50, slope=24
            ),
        )
        start, end = compute_match_range(ch, margin_octaves=1)
        assert start == 25.0  # 50 / 2^1
        assert end == 20000.0

    def test_lowpass_only(self) -> None:
        ch = ChannelConfig(
            number=6,
            name="Sub",
            group="sub",
            lowpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=80, slope=24
            ),
        )
        start, end = compute_match_range(ch, margin_octaves=1)
        assert start == 20.0
        assert end == 160.0  # 80 * 2^1

    def test_both_filters(self) -> None:
        ch = ChannelConfig(
            number=3,
            name="C",
            group="centre",
            highpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=300, slope=24
            ),
            lowpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=3500, slope=24
            ),
        )
        start, end = compute_match_range(ch, margin_octaves=1)
        assert start == 150.0  # 300 / 2
        assert end == 7000.0  # 3500 * 2

    def test_clamp_to_min(self) -> None:
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            highpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=10, slope=24
            ),
        )
        start, _end = compute_match_range(ch, margin_octaves=1)
        assert start == 20.0  # clamped

    def test_clamp_to_max(self) -> None:
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            lowpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=15000, slope=24
            ),
        )
        _start, end = compute_match_range(ch, margin_octaves=1)
        assert end == 20000.0  # clamped

    def test_manual_override(self) -> None:
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            highpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=50, slope=24
            ),
            match_range=(100.0, 5000.0),
        )
        assert compute_match_range(ch) == (100.0, 5000.0)

    def test_margin_two_octaves(self) -> None:
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            highpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=200, slope=24
            ),
        )
        start, end = compute_match_range(ch, margin_octaves=2)
        assert start == 50.0  # 200 / 4
        assert end == 20000.0


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_example_config(self) -> None:
        config = load_config("test_files/config.example.yaml")
        assert len(config.channels) == 6
        assert config.rew.host == "localhost"
        assert config.playback.mode == PlaybackMode.MANUAL

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_no_channels(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("rew:\n  host: localhost\n")
        with pytest.raises(ValueError, match="at least one channel"):
            load_config(str(cfg))

    def test_duplicate_channels(self, tmp_path: Path) -> None:
        cfg = tmp_path / "dup.yaml"
        cfg.write_text(
            "channels:\n  - number: 1\n    name: LF\n  - number: 1\n    name: RF\n"
        )
        with pytest.raises(ValueError, match="unique"):
            load_config(str(cfg))

    def test_minimal_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "min.yaml"
        cfg.write_text("channels:\n  - number: 1\n    name: LF\n    group: front\n")
        config = load_config(str(cfg))
        assert len(config.channels) == 1
        assert config.channels[0].name == "LF"
        # Defaults applied
        assert config.rew.port == 4735
        assert config.levels.target_spl == 75.0
