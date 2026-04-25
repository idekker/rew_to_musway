"""Tests for combined channel measurement flow (phase 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rew_to_musway.calibration._combined import run_combined_measurements
from rew_to_musway.config import CombinedMeasurement, Config


class TestRunCombinedMeasurements:
    @pytest.mark.asyncio
    async def test_skips_when_no_groups(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        """No combined_measurements configured — should skip gracefully."""
        with patch("rew_to_musway.calibration._combined.asyncio.sleep"):
            await run_combined_measurements(
                sample_config, mock_amp, mock_rew, mock_playback
            )

        mock_rew.run_rta.assert_not_called()
        mock_playback.start_noise.assert_not_called()

    @pytest.mark.asyncio
    async def test_measures_all_groups(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        """Runs RTA once per combined measurement group."""
        config = _with_combined(sample_config)

        with patch("rew_to_musway.calibration._combined.asyncio.sleep"):
            await run_combined_measurements(config, mock_amp, mock_rew, mock_playback)

        num_groups = 2
        assert mock_rew.run_rta.call_count == num_groups
        assert mock_rew.rename_measurement.call_count == num_groups
        assert mock_playback.start_noise.call_count == 1
        assert mock_playback.stop_noise.call_count == 1
        mock_amp.restore_eq.assert_called_once()

    @pytest.mark.asyncio
    async def test_measurement_naming(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        """Measurements are renamed to the group name from config."""
        config = _with_combined(sample_config)

        with patch("rew_to_musway.calibration._combined.asyncio.sleep"):
            await run_combined_measurements(config, mock_amp, mock_rew, mock_playback)

        names = [call.args[1] for call in mock_rew.rename_measurement.call_args_list]
        assert names == ["LF+Sub", "LF+RF"]

    @pytest.mark.asyncio
    async def test_unmutes_correct_channels(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        """Only channels in the group are unmuted; others are muted."""
        config = _with_combined(
            sample_config,
            groups=[CombinedMeasurement(name="LF+Sub", channels=[1, 6])],
        )

        with patch("rew_to_musway.calibration._combined.asyncio.sleep"):
            await run_combined_measurements(config, mock_amp, mock_rew, mock_playback)

        # The first 6 set_channel_mute calls are from _unmute_group
        # (one per configured channel); subsequent calls are from mute_all in finally.
        num_channels = 6
        group_calls = mock_amp.set_channel_mute.call_args_list[:num_channels]
        mute_state = {call.args[0]: call.kwargs["muted"] for call in group_calls}
        assert mute_state[1] is False  # LF unmuted
        assert mute_state[6] is False  # Sub unmuted
        assert mute_state[2] is True  # RF muted
        assert mute_state[3] is True  # C muted

    @pytest.mark.asyncio
    async def test_stops_noise_on_error(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        """Noise is stopped even when RTA fails."""
        config = _with_combined(sample_config)
        mock_rew.run_rta.side_effect = RuntimeError("RTA failed")

        with (
            patch("rew_to_musway.calibration._combined.asyncio.sleep"),
            pytest.raises(RuntimeError, match="RTA failed"),
        ):
            await run_combined_measurements(config, mock_amp, mock_rew, mock_playback)

        mock_playback.stop_noise.assert_called_once()


def _with_combined(
    config: Config,
    groups: list[CombinedMeasurement] | None = None,
) -> Config:
    """Return a copy of *config* with combined measurements added."""
    if groups is None:
        groups = [
            CombinedMeasurement(name="LF+Sub", channels=[1, 6]),
            CombinedMeasurement(name="LF+RF", channels=[1, 2]),
        ]
    return Config(
        rew=config.rew,
        tunest_pc=config.tunest_pc,
        paths=config.paths,
        playback=config.playback,
        measurement=config.measurement,
        eq=config.eq,
        levels=config.levels,
        channels=config.channels,
        combined_measurements=groups,
    )
