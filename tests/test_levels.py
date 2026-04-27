"""Tests for level balancing offset computation and measurement flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from rew_to_musway.calibration._levels import (
    ChannelLevel,
    _compute_offsets,
    _compute_two_stage_offsets,
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
# Two-stage offset computation (between-group + within-group)
# ---------------------------------------------------------------------------


class TestComputeTwoStageOffsets:
    def test_single_group_balanced(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 75.0),
            ChannelLevel(2, "RF", "front", 75.0),
        ]
        offsets = _compute_two_stage_offsets(readings)
        assert offsets[1] == 0.0
        assert offsets[2] == 0.0

    def test_single_group_unbalanced(self) -> None:
        """Within-group L/R balancing only (single group)."""
        readings = [
            ChannelLevel(1, "LF", "front", 78.0),
            ChannelLevel(2, "RF", "front", 75.0),
        ]
        offsets = _compute_two_stage_offsets(readings)
        # Group avg = 76.5, quietest group = 76.5 → group offset = 0
        # Within-group: ref=75, LF=75-78=-3, RF=0
        assert offsets[1] == -3.0
        assert offsets[2] == 0.0

    def test_two_groups_equal_avg(self) -> None:
        """Two groups with equal average SPL → only L/R offsets."""
        readings = [
            ChannelLevel(1, "LF", "front", 76.0),
            ChannelLevel(2, "RF", "front", 74.0),  # avg=75
            ChannelLevel(4, "LR", "rear", 77.0),
            ChannelLevel(5, "RR", "rear", 73.0),  # avg=75
        ]
        offsets = _compute_two_stage_offsets(readings)
        # Group offsets = 0 for both (equal avg)
        # Front L/R: ref=74, LF=74-76=-2, RF=0
        assert offsets[1] == -2.0
        assert offsets[2] == 0.0
        # Rear L/R: ref=73, LR=73-77=-4, RR=0
        assert offsets[4] == -4.0
        assert offsets[5] == 0.0

    def test_between_group_offsets(self) -> None:
        """Louder group is attenuated to match quietest group."""
        readings = [
            ChannelLevel(1, "LF", "front", 80.0),
            ChannelLevel(2, "RF", "front", 80.0),  # avg=80
            ChannelLevel(4, "LR", "rear", 75.0),
            ChannelLevel(5, "RR", "rear", 75.0),  # avg=75
        ]
        offsets = _compute_two_stage_offsets(readings)
        # Quietest group avg = 75 (rear)
        # Front group offset = 75 - 80 = -5
        # Within each group: balanced (0 L/R offset)
        assert offsets[1] == -5.0
        assert offsets[2] == -5.0
        assert offsets[4] == 0.0
        assert offsets[5] == 0.0

    def test_combined_group_and_lr(self) -> None:
        """Both group offset and L/R offset combine."""
        readings = [
            ChannelLevel(1, "LF", "front", 82.0),
            ChannelLevel(2, "RF", "front", 78.0),  # avg=80
            ChannelLevel(4, "LR", "rear", 75.0),
            ChannelLevel(5, "RR", "rear", 75.0),  # avg=75
        ]
        offsets = _compute_two_stage_offsets(readings)
        # Quietest group avg = 75 (rear)
        # Front group offset = 75 - 80 = -5
        # Front L/R: ref=78, LF=78-82=-4, RF=0
        # Combined: LF = -5 + -4 = -9, RF = -5 + 0 = -5
        assert offsets[1] == -9.0
        assert offsets[2] == -5.0
        assert offsets[4] == 0.0
        assert offsets[5] == 0.0

    def test_single_channel_group(self) -> None:
        """Single-channel group gets only group offset."""
        readings = [
            ChannelLevel(1, "LF", "front", 80.0),
            ChannelLevel(2, "RF", "front", 80.0),  # avg=80
            ChannelLevel(3, "C", "centre", 75.0),  # avg=75
        ]
        offsets = _compute_two_stage_offsets(readings)
        # Quietest group avg = 75 (centre)
        # Front group offset = 75 - 80 = -5
        assert offsets[1] == -5.0
        assert offsets[2] == -5.0
        assert offsets[3] == 0.0

    def test_all_offsets_le_zero(self) -> None:
        """All offsets must be ≤ 0 (attenuation only)."""
        readings = [
            ChannelLevel(1, "LF", "front", 76.0),
            ChannelLevel(2, "RF", "front", 74.0),
            ChannelLevel(3, "C", "centre", 80.0),
            ChannelLevel(4, "LR", "rear", 70.0),
            ChannelLevel(5, "RR", "rear", 72.0),
            ChannelLevel(6, "Sub", "sub", 85.0),
        ]
        offsets = _compute_two_stage_offsets(readings)
        for ch_num, offset in offsets.items():
            assert offset <= 0.0, f"CH{ch_num} offset {offset} should be ≤ 0"

    def test_full_six_channel(self) -> None:
        """Full 6-channel scenario with all groups."""
        readings = [
            ChannelLevel(1, "LF", "front", 76.0),
            ChannelLevel(2, "RF", "front", 74.0),  # avg=75
            ChannelLevel(3, "C", "centre", 80.0),  # avg=80
            ChannelLevel(4, "LR", "rear", 70.0),
            ChannelLevel(5, "RR", "rear", 72.0),  # avg=71
            ChannelLevel(6, "Sub", "sub", 85.0),  # avg=85
        ]
        offsets = _compute_two_stage_offsets(readings)

        # Quietest group = rear (avg=71)
        # Group offsets: front=71-75=-4, centre=71-80=-9, rear=0, sub=71-85=-14
        # Front L/R: ref=74, LF=74-76=-2, RF=0 → LF=-4+-2=-6, RF=-4+0=-4
        # Centre: single → -9
        # Rear L/R: ref=70, LR=0, RR=70-72=-2 → LR=0, RR=-2
        # Sub: single → -14
        assert offsets[1] == -6.0
        assert offsets[2] == -4.0
        assert offsets[3] == -9.0
        assert offsets[4] == 0.0
        assert offsets[5] == -2.0
        assert offsets[6] == -14.0


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
