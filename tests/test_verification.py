"""Tests for verification measurement flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from rew_to_musway.calibration._verification import run_verification, save_session

if TYPE_CHECKING:
    from pathlib import Path

    from rew_to_musway.config import Config


class TestRunVerification:
    @pytest.mark.asyncio
    async def test_verifies_all_channels(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        with patch("rew_to_musway.calibration._verification.asyncio.sleep"):
            await run_verification(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
            )

        num_channels = 6
        assert mock_rew.run_rta.call_count == num_channels
        assert mock_amp.solo_channel.call_count == num_channels
        assert mock_rew.rename_measurement.call_count == num_channels
        mock_amp.restore_eq.assert_called_once()
        assert mock_playback.start_noise.call_count == 1
        assert mock_playback.stop_noise.call_count == 1

    @pytest.mark.asyncio
    async def test_verifies_subset(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        with patch("rew_to_musway.calibration._verification.asyncio.sleep"):
            await run_verification(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
                channels=[1, 3],
            )

        expected_count = 2
        assert mock_rew.run_rta.call_count == expected_count

    @pytest.mark.asyncio
    async def test_measurement_naming(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
    ) -> None:
        with patch("rew_to_musway.calibration._verification.asyncio.sleep"):
            await run_verification(
                sample_config,
                mock_amp,
                mock_rew,
                mock_playback,
                channels=[1],
            )

        name = mock_rew.rename_measurement.call_args.args[1]
        assert name == "LF_after_eq"


class TestSaveSession:
    @pytest.mark.asyncio
    async def test_saves_mdat(self, mock_rew: AsyncMock, tmp_path: Path) -> None:
        path = await save_session(mock_rew, tmp_path)
        assert path == tmp_path / "calibration.mdat"
        mock_rew.save_all_measurements.assert_called_once_with(
            str(tmp_path / "calibration.mdat")
        )
