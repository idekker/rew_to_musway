"""Tests for the musway_preset package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from musway_preset import (
    CrossoverFilter,
    FilterType,
    MuswayPreset,
    Slope,
    decode_gain,
    decode_volume,
    encode_gain,
    encode_volume,
)

PRESET_PATH = Path("test_files/default_preset.txt")


# ---------------------------------------------------------------------------
# Helpers — minimal FilterSetting stub
# ---------------------------------------------------------------------------


@dataclass
class _FakeFilterSetting:
    index: int
    type: str
    enabled: bool
    isAuto: bool = False  # noqa: N815
    frequency: float | None = None
    gaindB: float | None = None  # noqa: N815
    q: float | None = None


# ---------------------------------------------------------------------------
# Volume encoding/decoding
# ---------------------------------------------------------------------------


class TestVolumeEncoding:
    def test_decode_zero(self) -> None:
        assert decode_volume(0) == -0.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (5, -0.5),
            (10, -1.0),
            (35, -3.5),
            (100, -10.0),
            (120, -12.0),
        ],
    )
    def test_decode_known_values(self, raw: int, expected: float) -> None:
        assert decode_volume(raw) == expected

    def test_encode_zero(self) -> None:
        assert encode_volume(0.0) == 0

    def test_round_trip_representable_values(self) -> None:
        """Exact representable values round-trip correctly."""
        test_values = [0.0, -0.5, -1.0, -3.5, -10.0, -12.0, -12.7]
        for db in test_values:
            assert decode_volume(encode_volume(db)) == db

    def test_encode_snaps_to_nearest(self) -> None:
        """Non-representable values snap to nearest representable."""
        encoded = encode_volume(-15.0)
        result = decode_volume(encoded)
        assert abs(result - (-15.0)) <= 1.0

    def test_encode_negative_values(self) -> None:
        encoded = encode_volume(-20.0)
        result = decode_volume(encoded)
        assert abs(result - (-20.0)) <= 1.0


# ---------------------------------------------------------------------------
# Gain encoding/decoding
# ---------------------------------------------------------------------------


class TestGainEncoding:
    def test_decode_zero_gain(self) -> None:
        assert decode_gain(150) == 0.0

    def test_decode_positive_gain(self) -> None:
        assert decode_gain(100) == 5.0

    def test_decode_negative_gain(self) -> None:
        assert decode_gain(200) == -5.0

    def test_encode_zero_gain(self) -> None:
        assert encode_gain(0.0) == 150

    def test_encode_positive_gain(self) -> None:
        assert encode_gain(5.0) == 100

    def test_encode_negative_gain(self) -> None:
        assert encode_gain(-5.0) == 200

    def test_round_trip(self) -> None:
        for db in [-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0]:
            assert decode_gain(encode_gain(db)) == db

    def test_clamp_above_max(self) -> None:
        assert encode_gain(18.0) == encode_gain(15.0)

    def test_clamp_below_min(self) -> None:
        assert encode_gain(-18.0) == encode_gain(-15.0)


# ---------------------------------------------------------------------------
# Preset round-trip
# ---------------------------------------------------------------------------


class TestPresetRoundTrip:
    def test_byte_identical_round_trip(self, tmp_path: Path) -> None:
        """Loading and writing an unmodified preset produces identical bytes."""
        preset = MuswayPreset.load(PRESET_PATH)
        out = tmp_path / "round_trip.txt"
        preset.write(out)
        assert PRESET_PATH.read_bytes() == out.read_bytes()


# ---------------------------------------------------------------------------
# Channel level
# ---------------------------------------------------------------------------


class TestChannelLevel:
    def test_get_default_level(self) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        for ch in range(1, 7):
            assert preset.get_channel_level(ch) == -60.0

    def test_set_and_get_level(self) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_channel_level(1, -3.5)
        assert preset.get_channel_level(1) == -3.5

    def test_invalid_channel_raises(self) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        with pytest.raises(ValueError, match="Channel must be 1-6"):
            preset.get_channel_level(7)
        with pytest.raises(ValueError, match="Channel must be 1-6"):
            preset.get_channel_level(0)

    def test_set_level_persists_through_write(self, tmp_path: Path) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_channel_level(2, -3.5)
        out = tmp_path / "level.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        assert reloaded.get_channel_level(2) == -3.5
        assert reloaded.get_channel_level(1) == -60.0


# ---------------------------------------------------------------------------
# Master volume
# ---------------------------------------------------------------------------


class TestMasterVolume:
    def test_get_default_master(self) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        assert preset.get_master_volume() == -60

    def test_set_master(self, tmp_path: Path) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_master_volume(-5)
        out = tmp_path / "master.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        assert reloaded.get_master_volume() == -5


# ---------------------------------------------------------------------------
# EQ filters
# ---------------------------------------------------------------------------


class TestEQFilters:
    def test_reset_eq(self, tmp_path: Path) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.reset_eq(1)
        out = tmp_path / "reset.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        for gain in reloaded.channel(1).eq.gains:
            assert gain == 0.0

    def test_from_filter_settings(self) -> None:
        filters = [
            _FakeFilterSetting(
                index=1,
                type="PK",
                enabled=True,
                frequency=100.0,
                gaindB=-3.5,
                q=2.0,
            ),
            _FakeFilterSetting(
                index=5,
                type="PK",
                enabled=True,
                frequency=1000.0,
                gaindB=6.0,
                q=4.5,
            ),
            _FakeFilterSetting(
                index=10,
                type="None",
                enabled=False,
            ),
        ]
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_eq_filters(1, filters)
        ch = preset.channel(1)
        assert ch.eq.frequencies[0] == 100
        assert ch.eq.gains[0] == -3.5
        assert ch.eq.q_factors[0] == 2.0
        assert ch.eq.frequencies[4] == 1000
        assert ch.eq.gains[4] == 6.0
        assert ch.eq.gains[2] == 0.0

    def test_gain_clamping(self) -> None:
        filters = [
            _FakeFilterSetting(
                index=1,
                type="PK",
                enabled=True,
                frequency=100.0,
                gaindB=18.0,
                q=2.0,
            ),
        ]
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_eq_filters(1, filters)
        assert preset.channel(1).eq.gains[0] == 15.0

    def test_q_clamping(self) -> None:
        filters = [
            _FakeFilterSetting(
                index=1,
                type="PK",
                enabled=True,
                frequency=100.0,
                gaindB=0.0,
                q=0.5,
            ),
        ]
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_eq_filters(1, filters)
        assert preset.channel(1).eq.q_factors[0] == 1.0

    def test_eq_persists_through_write(self, tmp_path: Path) -> None:
        filters = [
            _FakeFilterSetting(
                index=1,
                type="PK",
                enabled=True,
                frequency=200.0,
                gaindB=-2.0,
                q=3.0,
            ),
        ]
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_eq_filters(3, filters)
        out = tmp_path / "eq.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        ch3 = reloaded.channel(3)
        assert ch3.eq.frequencies[0] == 200
        assert ch3.eq.gains[0] == -2.0
        assert ch3.eq.q_factors[0] == 3.0


# ---------------------------------------------------------------------------
# Crossover filters
# ---------------------------------------------------------------------------


class TestCrossover:
    def test_set_highpass(self, tmp_path: Path) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_highpass(1, FilterType.LINKWITZ_RILEY, 50, Slope.DB_24)
        out = tmp_path / "hp.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        hp = reloaded.channel(1).highpass
        assert hp.filter_type == FilterType.LINKWITZ_RILEY
        assert hp.frequency == 50
        assert hp.slope == Slope.DB_24

    def test_set_lowpass_off(self, tmp_path: Path) -> None:
        preset = MuswayPreset.load(PRESET_PATH)
        preset.set_lowpass(1, FilterType.BUTTERWORTH, 0, Slope.OFF)
        out = tmp_path / "lp.txt"
        preset.write(out)
        reloaded = MuswayPreset.load(out)
        lp = reloaded.channel(1).lowpass
        assert lp.slope == Slope.OFF

    def test_crossover_from_preset_lines(self) -> None:
        xover = CrossoverFilter.from_preset_lines(["2", "50", "3"])
        assert xover.filter_type == FilterType.LINKWITZ_RILEY
        assert xover.frequency == 50
        assert xover.slope == Slope.DB_24

    def test_crossover_to_preset_lines(self) -> None:
        xover = CrossoverFilter(FilterType.BESSEL, 1000, Slope.DB_12)
        assert xover.to_preset_lines() == ["1", "1000", "1"]
