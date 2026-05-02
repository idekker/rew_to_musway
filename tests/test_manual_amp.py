"""Tests for ManualAmp backend."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from rew_to_musway.amp._manual_amp import ManualAmp
from rew_to_musway.amp._preset_amp import PresetPhase
from rew_to_musway.config import ManualConfig, TimerConfig

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig

# Path to the reference preset file
_TEST_PRESET = Path(__file__).parent.parent / "test_files" / "default_preset.txt"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    return tmp_path / "session"


@pytest.fixture
def default_preset(tmp_path: Path) -> Path:
    """Copy test preset to tmp for isolation."""
    dest = tmp_path / "default_preset.txt"
    shutil.copy2(_TEST_PRESET, dest)
    return dest


@pytest.fixture
def config(default_preset: Path) -> ManualConfig:
    return ManualConfig(
        default_preset_path=str(default_preset),
        timers=TimerConfig(
            action_timeout=1.0,
            preset_load_timeout=1.0,
        ),
    )


@pytest.fixture
def manual_amp(
    config: ManualConfig,
    session_dir: Path,
    sample_channels: list[ChannelConfig],
) -> ManualAmp:
    return ManualAmp(
        config=config,
        session_dir=session_dir,
        channels=sample_channels,
    )


# ---------------------------------------------------------------------------
# Buffer / Apply
# ---------------------------------------------------------------------------


class TestManualAmpBuffer:
    @pytest.mark.asyncio
    async def test_empty_apply_returns_none(self, manual_amp: ManualAmp) -> None:
        result = await manual_amp.apply()
        assert result is None

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_apply_writes_preset(
        self,
        mock_prompt: AsyncMock,  # noqa: ARG002
        mock_clipboard: AsyncMock,  # noqa: ARG002
        manual_amp: ManualAmp,
        session_dir: Path,
    ) -> None:
        await manual_amp.set_channel_level(1, -3.0)
        result = await manual_amp.apply()
        assert result is not None
        assert result == session_dir / "preset_initial.txt"
        assert result.exists()

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_apply_clears_buffer(
        self,
        mock_prompt: AsyncMock,  # noqa: ARG002
        mock_clipboard: AsyncMock,  # noqa: ARG002
        manual_amp: ManualAmp,
    ) -> None:
        await manual_amp.set_channel_level(1, -3.0)
        await manual_amp.apply()
        # Second apply should be no-op (buffer cleared)
        result = await manual_amp.apply()
        assert result is None

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_cumulative_preset_chain(
        self,
        mock_prompt: AsyncMock,  # noqa: ARG002
        mock_clipboard: AsyncMock,  # noqa: ARG002
        manual_amp: ManualAmp,
        session_dir: Path,
    ) -> None:
        # Initial phase → preset_initial.txt
        await manual_amp.set_channel_level(1, -3.0)
        manual_amp.set_phase(PresetPhase.INITIAL)
        path1 = await manual_amp.apply()
        assert path1 is not None
        assert path1 == session_dir / "preset_initial.txt"

        # EQ phase → preset_eq.txt (loads from preset_initial.txt)
        await manual_amp.reset_eq(1)
        manual_amp.set_phase(PresetPhase.EQ)
        path2 = await manual_amp.apply()
        assert path2 is not None
        assert path2 == session_dir / "preset_eq.txt"

        # First finetuning phase → preset_finetune_1.txt
        await manual_amp.set_channel_level(2, -1.0)
        manual_amp.set_phase(PresetPhase.FINETUNE, iteration=1)
        path3 = await manual_amp.apply()
        assert path3 is not None
        assert path3 == session_dir / "preset_finetune_1.txt"

        # Second finetuning phase → preset_finetune_2.txt
        await manual_amp.set_channel_level(2, -1.0)
        manual_amp.set_phase(PresetPhase.FINETUNE, iteration=2)
        path4 = await manual_amp.apply()
        assert path4 is not None
        assert path4 == session_dir / "preset_finetune_2.txt"

        # Verification phase → preset_verification.txt
        await manual_amp.set_channel_level(2, -1.0)
        manual_amp.set_phase(PresetPhase.VERIFICATION)
        path5 = await manual_amp.apply()
        assert path5 is not None
        assert path5 == session_dir / "preset_verification.txt"

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_clipboard_called_with_path(
        self,
        mock_prompt: AsyncMock,  # noqa: ARG002
        mock_clipboard: AsyncMock,
        manual_amp: ManualAmp,
        session_dir: Path,
    ) -> None:
        await manual_amp.set_channel_level(1, -1.0)
        await manual_amp.apply()
        expected = str((session_dir / "preset_initial.txt").resolve())
        mock_clipboard.assert_called_once_with(expected)


# ---------------------------------------------------------------------------
# Immediate operations
# ---------------------------------------------------------------------------


class TestManualAmpImmediate:
    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_solo_channel_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.solo_channel(1)
        mock_prompt.assert_called_once()
        msg = mock_prompt.call_args[0][0]
        assert "LF" in msg
        assert "CH1" in msg

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._preset_amp.timed_prompt", new_callable=AsyncMock)
    async def test_mute_all_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.mute_all()
        mock_prompt.assert_called_once()
        assert "Mute all" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_master_mute_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.set_master_mute(muted=True)
        mock_prompt.assert_called_once()
        assert "Mute master" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_master_unmute_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.set_master_mute(muted=False)
        assert "Unmute master" in mock_prompt.call_args[0][0]
