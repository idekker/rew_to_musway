"""Tests for level balancing offset computation and measurement flow."""

from __future__ import annotations

from rew_to_musway.calibration import (
    ChannelLevel,
    compute_two_stage_offsets,
)

# ---------------------------------------------------------------------------
# Two-stage offset computation (between-group + within-group)
# ---------------------------------------------------------------------------


class TestComputeTwoStageOffsets:
    def test_single_group_balanced(self) -> None:
        readings = [
            ChannelLevel(1, "LF", "front", 75.0),
            ChannelLevel(2, "RF", "front", 75.0),
        ]
        offsets = compute_two_stage_offsets(readings)
        assert offsets[1] == 0.0
        assert offsets[2] == 0.0

    def test_single_group_unbalanced(self) -> None:
        """Within-group L/R balancing only (single group)."""
        readings = [
            ChannelLevel(1, "LF", "front", 78.0),
            ChannelLevel(2, "RF", "front", 75.0),
        ]
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)
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
        offsets = compute_two_stage_offsets(readings)

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
