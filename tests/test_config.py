"""Tests for config loading and match range computation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rew_to_musway.config import (
    ChannelConfig,
    FilterConfig,
    FilterType,
    PlaybackMode,
    TargetShape,
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
        assert len(config.combined_measurements) == 4
        assert config.combined_measurements[0].name == "LF+Sub"
        assert config.combined_measurements[0].channels == [1, 6]

        # Target shape parsing
        lf = config.channels[0]
        assert lf.target.shape == TargetShape.BASS_LIMITED
        assert lf.target.cutoff_hz == 55.0
        assert lf.target.slope_db_per_octave == 24
        sub = config.channels[5]
        assert sub.target.shape == TargetShape.SUBWOOFER
        assert sub.target.cutoff_hz == 55.0

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_no_channels(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text(
            "tunest_pc:\n  exe_path: C:\\tunest.exe\nrew:\n  host: localhost\n"
        )
        with pytest.raises(ValueError, match="at least one channel"):
            load_config(str(cfg))

    def test_duplicate_channels(self, tmp_path: Path) -> None:
        cfg = tmp_path / "dup.yaml"
        cfg.write_text(
            "tunest_pc:\n  exe_path: C:\\tunest.exe\n"
            "channels:\n  - number: 1\n    name: LF\n  - number: 1\n    name: RF\n"
        )
        with pytest.raises(ValueError, match="unique"):
            load_config(str(cfg))

    def test_minimal_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "min.yaml"
        cfg.write_text(
            "tunest_pc:\n  exe_path: C:\\tunest.exe\n"
            "channels:\n  - number: 1\n    name: LF\n    group: front\n"
        )
        config = load_config(str(cfg))
        assert len(config.channels) == 1
        assert config.channels[0].name == "LF"
        # Defaults applied
        assert config.rew.port == 4735
        assert config.levels.target_spl == 75.0
        # Target defaults to full_range when omitted
        assert config.channels[0].target.shape == TargetShape.FULL_RANGE

    def test_target_shape_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "target.yaml"
        cfg.write_text(
            "tunest_pc:\n  exe_path: C:\\tunest.exe\n"
            "channels:\n"
            "  - number: 1\n    name: LF\n    group: front\n"
            "    target:\n"
            "      shape: bass_limited\n"
            "      cutoff_hz: 55\n"
            "      slope_db_per_octave: 24\n"
            "  - number: 6\n    name: Sub\n    group: sub\n"
            "    target:\n"
            "      shape: subwoofer\n"
            "      cutoff_hz: 80\n"
            "      slope_db_per_octave: 12\n"
        )
        config = load_config(str(cfg))
        assert config.channels[0].target.shape == TargetShape.BASS_LIMITED
        assert config.channels[0].target.cutoff_hz == 55.0
        assert config.channels[0].target.slope_db_per_octave == 24
        assert config.channels[1].target.shape == TargetShape.SUBWOOFER
        assert config.channels[1].target.cutoff_hz == 80.0
        assert config.channels[1].target.slope_db_per_octave == 12

    def test_target_speaker_driver_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "driver.yaml"
        cfg.write_text(
            "tunest_pc:\n  exe_path: C:\\tunest.exe\n"
            "channels:\n"
            "  - number: 3\n    name: C\n    group: centre\n"
            "    target:\n"
            "      shape: speaker_driver\n"
            "      highpass_hz: 300\n"
            "      highpass_type: L-R4\n"
            "      lowpass_hz: 3500\n"
            "      lowpass_type: BU3\n"
        )
        config = load_config(str(cfg))
        t = config.channels[0].target
        assert t.shape == TargetShape.SPEAKER_DRIVER
        assert t.highpass_hz == 300.0
        assert t.highpass_type == "L-R4"
        assert t.lowpass_hz == 3500.0
        assert t.lowpass_type == "BU3"

    def test_manual_mode_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "manual.yaml"
        cfg.write_text(
            "manual:\n"
            "  default_preset_path: ./preset.txt\n"
            "  spl_sanity_threshold: -15.0\n"
            "  timers:\n"
            "    action_timeout: 5\n"
            "    preset_load_timeout: 20\n"
            "channels:\n  - number: 1\n    name: LF\n    group: front\n"
        )
        config = load_config(str(cfg))
        assert config.tunest_pc is None
        assert config.manual.default_preset_path == "./preset.txt"
        assert config.manual.spl_sanity_threshold == -15.0
        assert config.manual.timers.action_timeout == 5
        assert config.manual.timers.preset_load_timeout == 20

    def test_manual_mode_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "manual_defaults.yaml"
        cfg.write_text(
            "manual:\n"
            "  default_preset_path: ./preset.txt\n"
            "channels:\n  - number: 1\n    name: LF\n    group: front\n"
        )
        config = load_config(str(cfg))
        assert config.manual.spl_sanity_threshold == -10.0
        assert config.manual.timers.action_timeout == 10
        assert config.manual.timers.preset_load_timeout == 30

    def test_no_tunest_no_manual_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "neither.yaml"
        cfg.write_text("channels:\n  - number: 1\n    name: LF\n    group: front\n")
        with pytest.raises(ValueError, match=r"tunest_pc.*manual"):
            load_config(str(cfg))
