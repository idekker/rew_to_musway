"""Shared test fixtures for rew_to_musway tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from rew_to_musway.config import (
    ChannelConfig,
    Config,
    EQConfig,
    FilterConfig,
    FilterType,
    LevelsConfig,
    MatchTargetConfig,
    MeasurementConfig,
    PathsConfig,
    PlaybackConfig,
    PlaybackMode,
    REWConfig,
    TunestPCConfig,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_UUID = UUID("12345678-1234-1234-1234-123456789abc")

# Distinct UUIDs for predicted/arithmetic results
_PREDICTED_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DIVIDE_UUID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_MULTIPLY_UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _make_channel(
    number: int,
    name: str,
    group: str,
    hp_freq: int | None = None,
    lp_freq: int | None = None,
) -> ChannelConfig:
    return ChannelConfig(
        number=number,
        name=name,
        group=group,
        highpass=FilterConfig(
            type=FilterType.LINKWITZ_RILEY, frequency=hp_freq, slope=24
        )
        if hp_freq
        else None,
        lowpass=FilterConfig(
            type=FilterType.LINKWITZ_RILEY, frequency=lp_freq, slope=24
        )
        if lp_freq
        else None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_channels() -> list[ChannelConfig]:
    """Return a 6-channel Ioniq 5 layout."""
    return [
        _make_channel(1, "LF", "front", hp_freq=50),
        _make_channel(2, "RF", "front", hp_freq=50),
        _make_channel(3, "C", "centre", hp_freq=300, lp_freq=3500),
        _make_channel(4, "LR", "rear", hp_freq=300, lp_freq=3500),
        _make_channel(5, "RR", "rear", hp_freq=300, lp_freq=3500),
        _make_channel(6, "Sub", "sub", hp_freq=30, lp_freq=80),
    ]


@pytest.fixture
def sample_config(sample_channels: list[ChannelConfig], tmp_path: Path) -> Config:
    """Build a complete Config using *sample_channels*."""
    return Config(
        rew=REWConfig(host="localhost", port=4735),
        tunest_pc=TunestPCConfig(exe_path="C:\\tunest.exe", model="M6"),
        paths=PathsConfig(output_dir=str(tmp_path / "output")),
        playback=PlaybackConfig(mode=PlaybackMode.MANUAL),
        measurement=MeasurementConfig(rta_averages=100, smoothing="1/6"),
        eq=EQConfig(
            manufacturer="Musway",
            model="31 bands (Output)",
            match_range_margin=1,
            match_target=MatchTargetConfig(),
        ),
        levels=LevelsConfig(target_spl=75.0, tolerance=1.0),
        channels=sample_channels,
    )


@pytest.fixture
def mock_spl_values() -> Callable[..., MagicMock]:
    """Create a mock SPLValues with a given *spl* value."""

    def _make(spl: float = 75.0) -> MagicMock:
        mock = MagicMock()
        mock.spl = spl
        return mock

    return _make


@pytest.fixture
def mock_rew(mock_spl_values: Callable[..., MagicMock]) -> AsyncMock:
    """Mock REWController with all async methods."""
    rew = AsyncMock()
    rew.connect = AsyncMock()
    rew.close = AsyncMock()
    rew.run_rta = AsyncMock(return_value=SAMPLE_UUID)
    rew.measure_spl = AsyncMock(return_value=mock_spl_values(75.0))
    rew.rename_measurement = AsyncMock()
    rew.apply_smoothing = AsyncMock()
    rew.configure_equaliser = AsyncMock()
    rew.configure_target = AsyncMock()
    rew.configure_match_settings = AsyncMock()
    rew.match_target = AsyncMock()
    rew.generate_predicted = AsyncMock(return_value=_PREDICTED_UUID)
    rew.get_filters = AsyncMock(return_value=[])
    rew.divide_measurements = AsyncMock(return_value=_DIVIDE_UUID)
    rew.multiply_measurements = AsyncMock(return_value=_MULTIPLY_UUID)
    rew.save_all_measurements = AsyncMock()
    rew.generator_play = AsyncMock()
    rew.generator_stop = AsyncMock()
    rew.set_output_device = AsyncMock()
    rew.set_output_device_name = AsyncMock()
    rew.set_output_channel = AsyncMock()
    rew.get_output_devices = AsyncMock(return_value=["Device A", "Device B"])
    rew.get_output_channels = AsyncMock(return_value=["1", "2", "L+R"])
    return rew


@pytest.fixture
def mock_amp() -> AsyncMock:
    """Mock AmpController with all async methods."""
    amp = AsyncMock()
    amp.connect = AsyncMock()
    amp.prepare_for_level_measurement = AsyncMock()
    amp.prepare_channel = AsyncMock()
    amp.solo_channel = AsyncMock()
    amp.solo_channels = AsyncMock()
    amp.mute_all = AsyncMock()
    amp.unmute_all = AsyncMock()
    amp.set_master_mute = AsyncMock()
    amp.set_channel_mute = AsyncMock()
    amp.set_channel_level = AsyncMock()
    amp.configure_filters = AsyncMock()
    amp.configure_all_filters = AsyncMock()
    amp.bypass_eq = AsyncMock()
    amp.restore_eq = AsyncMock()
    amp.reset_eq = AsyncMock()
    amp.import_eq = AsyncMock()
    return amp


@pytest.fixture
def mock_playback() -> AsyncMock:
    """Mock PlaybackStrategy."""
    pb = AsyncMock()
    pb.start_noise = AsyncMock()
    pb.stop_noise = AsyncMock()
    return pb
