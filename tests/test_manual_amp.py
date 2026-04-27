"""Tests for ManualAmp backend."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from rew_to_musway.manual_amp import ManualAmp, PresetPhase, preset_filename

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig

# Path to the reference preset file
_TEST_PRESET = Path(__file__).parent.parent / "test_files" / "default_preset.txt"


# ---------------------------------------------------------------------------
# Preset naming
# ---------------------------------------------------------------------------


class TestPresetFilename:
    def test_initial(self) -> None:
        assert preset_filename(PresetPhase.INITIAL) == "preset_initial.txt"

    def test_eq(self) -> None:
        assert preset_filename(PresetPhase.EQ) == "preset_eq.txt"

    def test_finetune(self) -> None:
        assert (
            preset_filename(PresetPhase.FINETUNE, iteration=2)
            == "preset_finetune_2.txt"
        )

    def test_verification(self) -> None:
        assert preset_filename(PresetPhase.VERIFICATION) == "preset_verification.txt"


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
def manual_amp(
    default_preset: Path,
    session_dir: Path,
    sample_channels: list[ChannelConfig],
) -> ManualAmp:
    return ManualAmp(
        default_preset_path=default_preset,
        session_dir=session_dir,
        channels=sample_channels,
        action_timeout=1.0,
        preset_load_timeout=1.0,
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
    @patch("rew_to_musway.manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
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
    @patch("rew_to_musway.manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
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
    @patch("rew_to_musway.manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_cumulative_preset_chain(
        self,
        mock_prompt: AsyncMock,  # noqa: ARG002
        mock_clipboard: AsyncMock,  # noqa: ARG002
        manual_amp: ManualAmp,
        session_dir: Path,
    ) -> None:
        # First apply → preset_initial.txt
        await manual_amp.set_channel_level(1, -3.0)
        path1 = await manual_amp.apply()
        assert path1 is not None
        assert path1 == session_dir / "preset_initial.txt"

        # Second apply → preset_eq.txt (loads from preset_initial.txt)
        await manual_amp.reset_eq(1)
        path2 = await manual_amp.apply()
        assert path2 is not None
        assert path2 == session_dir / "preset_eq.txt"

        # Third apply → preset_finetune_1.txt
        await manual_amp.set_channel_level(2, -1.0)
        path3 = await manual_amp.apply()
        assert path3 is not None
        assert path3 == session_dir / "preset_finetune_1.txt"

    @pytest.mark.asyncio
    @patch("rew_to_musway.manual_amp._copy_to_clipboard")
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
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
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_solo_channel_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.solo_channel(1)
        mock_prompt.assert_called_once()
        msg = mock_prompt.call_args[0][0]
        assert "LF" in msg
        assert "CH1" in msg

    @pytest.mark.asyncio
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_mute_all_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.mute_all()
        mock_prompt.assert_called_once()
        assert "Mute all" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_master_mute_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.set_master_mute(muted=True)
        mock_prompt.assert_called_once()
        assert "Mute master" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    @patch("rew_to_musway.manual_amp.timed_prompt", new_callable=AsyncMock)
    async def test_master_unmute_prompts(
        self, mock_prompt: AsyncMock, manual_amp: ManualAmp
    ) -> None:
        await manual_amp.set_master_mute(muted=False)
        assert "Unmute master" in mock_prompt.call_args[0][0]
