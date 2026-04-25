"""Tests for EQ calibration channel selection and flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from rew_to_musway.calibration._eq import calibrate_channels, select_channels
from rew_to_musway.config import ChannelConfig

if TYPE_CHECKING:
    from pathlib import Path

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


# ---------------------------------------------------------------------------
# Calibration flow (mocked)
# ---------------------------------------------------------------------------


class TestCalibrateChannels:
    @pytest.mark.asyncio
    async def test_calibrates_selected_channels(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test that calibrate_channels processes each channel."""
        channels = select_channels(sample_config, "single", single=1)

        with patch("rew_to_musway.calibration._eq.asyncio.sleep"):
            result = await calibrate_channels(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
                tmp_path,
                channels,
            )

        assert result == [1]

        mock_amp.prepare_channel.assert_called_once()
        mock_playback.start_noise.assert_called_once()
        mock_playback.stop_noise.assert_called_once()
        mock_rew.run_rta.assert_called_once()
        mock_rew.apply_smoothing.assert_called_once()
        mock_rew.configure_equaliser.assert_called_once()
        mock_rew.configure_target.assert_called_once()
        # Verify target_offset from channel config is passed through
        call_kwargs = mock_rew.configure_target.call_args
        assert call_kwargs.kwargs.get("target_offset", 0.0) == 0.0
        mock_rew.configure_match_settings.assert_called_once()
        mock_rew.match_target.assert_called_once()
        mock_rew.generate_predicted.assert_called_once()
        mock_rew.get_filters.assert_called_once()
        mock_amp.import_eq.assert_called_once()

    @pytest.mark.asyncio
    async def test_calibrates_all_channels(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Test full calibration of all 6 channels."""
        with patch("rew_to_musway.calibration._eq.asyncio.sleep"):
            result = await calibrate_channels(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
                tmp_path,
            )

        num_channels = 6
        assert len(result) == num_channels
        assert mock_rew.run_rta.call_count == num_channels
        assert mock_amp.import_eq.call_count == num_channels

    @pytest.mark.asyncio
    async def test_target_offset_passed_to_configure_target(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Verify that a non-zero target_offset is forwarded to configure_target."""
        offset_db = -3.0
        ch = sample_config.channels[0]
        modified = ChannelConfig(
            number=ch.number,
            name=ch.name,
            group=ch.group,
            highpass=ch.highpass,
            lowpass=ch.lowpass,
            target_offset=offset_db,
        )

        with patch("rew_to_musway.calibration._eq.asyncio.sleep"):
            await calibrate_channels(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
                tmp_path,
                [modified],
            )

        call_kwargs = mock_rew.configure_target.call_args
        assert call_kwargs.kwargs["target_offset"] == offset_db
