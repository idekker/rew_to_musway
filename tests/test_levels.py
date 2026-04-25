"""Tests for level balancing offset computation and measurement flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from rew_to_musway.calibration._levels import (
    ChannelLevel,
    _compute_offsets,
    measure_levels,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from rew_to_musway.config import Config


# ---------------------------------------------------------------------------
# Offset computation (pure logic, no mocks needed)
# ---------------------------------------------------------------------------


class TestComputeOffsets:
    def test_balanced_pair(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 75.0),
            ChannelLevel(2, "RF", "front", 75.0),
        ]
        offsets = _compute_offsets(readings)
        assert offsets[1] == 0.0
        assert offsets[2] == 0.0

    def test_unbalanced_pair(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 77.0),
            ChannelLevel(2, "RF", "front", 73.0),
        ]
        offsets = _compute_offsets(readings)
        # ref = 73.0 (quietest); LF = 73-77 = -4.0; RF = 73-73 = 0.0
        assert offsets[1] == -4.0
        assert offsets[2] == 0.0

    def test_single_channel_group(self) -> None:
        readings = [
            ChannelLevel(3, "C", "centre", 72.0),
        ]
        offsets = _compute_offsets(readings)
        assert offsets[3] == 0.0

    def test_multiple_groups(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 76.0),
            ChannelLevel(2, "RF", "front", 74.0),
            ChannelLevel(3, "C", "centre", 80.0),
            ChannelLevel(4, "LR", "rear", 70.0),
            ChannelLevel(5, "RR", "rear", 72.0),
            ChannelLevel(6, "Sub", "sub", 85.0),
        ]
        offsets = _compute_offsets(readings)

        # Front: ref=74 (quietest), LF=74-76=-2, RF=0
        assert offsets[1] == -2.0
        assert offsets[2] == 0.0

        # Centre: single, no offset
        assert offsets[3] == 0.0

        # Rear: ref=70 (quietest), LR=0, RR=70-72=-2
        assert offsets[4] == 0.0
        assert offsets[5] == -2.0

        # Sub: single, no offset
        assert offsets[6] == 0.0

    def test_rounding(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 75.3),
            ChannelLevel(2, "RF", "front", 74.8),
        ]
        offsets = _compute_offsets(readings)
        # ref = 74.8 (quietest); LF = 74.8 - 75.3 = -0.5
        # RF = 74.8 - 74.8 = 0.0
        assert offsets[1] == -0.5
        assert offsets[2] == 0.0


# ---------------------------------------------------------------------------
# Measurement flow (mocked)
# ---------------------------------------------------------------------------


class TestMeasureLevels:
    @pytest.mark.asyncio
    async def test_measures_all_channels(
        self,
        sample_config: Config,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        mock_playback: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """Verify measure_levels measures each channel and returns offsets."""
        spl_values = [76.0, 74.0, 72.0, 71.0, 73.0, 85.0]
        mock_rew.measure_spl = AsyncMock(
            side_effect=[mock_spl_values(v) for v in spl_values]
        )

        result = await measure_levels(sample_config, mock_amp, mock_rew, mock_playback)

        num_channels = 6
        assert len(result.readings) == num_channels
        assert mock_rew.measure_spl.call_count == num_channels

        mock_amp.prepare_for_level_measurement.assert_called_once()
        assert mock_amp.solo_channel.call_count == num_channels

        mock_playback.start_noise.assert_called_once()
        mock_playback.stop_noise.assert_called_once()

        assert len(result.offsets) == num_channels
        # Front pair: ref=74 (quietest), LF=74-76=-2, RF=0
        assert result.offsets[1] == -2.0
        assert result.offsets[2] == 0.0
