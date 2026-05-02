"""Tests for MuswayAmp backend."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from rew_to_musway.amp._musway import MuswayAmp
from rew_to_musway.amp._preset_amp import PresetPhase
from rew_to_musway.config import MuswayConfig, TimerConfig

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig

# Path to the reference preset file
_TEST_PRESET = Path(__file__).parent.parent / "test_files" / "default_preset.txt"

# Fake path to musway executable (never actually launched in tests)
_MUSWAY_PATH = Path("C:/musway/musway.exe")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_musway() -> MagicMock:
    """Patch the Musway class and return the mock instance.

    All methods on the instance are plain MagicMocks (sync) because
    MuswayAmp wraps every call in asyncio.to_thread via _run().
    """
    with patch("rew_to_musway.amp._musway.Musway") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


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
def config(default_preset: Path) -> MuswayConfig:
    return MuswayConfig(
        exe_path=str(_MUSWAY_PATH),
        default_preset_path=str(default_preset),
    )


@pytest.fixture
def timer_config() -> TimerConfig:
    return TimerConfig(
        action_timeout=1,
    )


@pytest.fixture
def musway_amp(
    config: MuswayConfig,
    timer_config: TimerConfig,
    session_dir: Path,
    sample_channels: list[ChannelConfig],
    mock_musway: MagicMock,  # noqa: ARG001
) -> MuswayAmp:
    return MuswayAmp(
        config=config,
        timer_config=timer_config,
        session_dir=session_dir,
        channels=sample_channels,
    )


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class TestMuswayAmpConnect:
    @pytest.mark.asyncio
    async def test_connect_calls_musway_connect(
        self, musway_amp: MuswayAmp, mock_musway: MagicMock
    ) -> None:
        await musway_amp.connect()
        mock_musway.connect.assert_called_once_with(path=_MUSWAY_PATH)


# ---------------------------------------------------------------------------
# Apply — delivery hook
# ---------------------------------------------------------------------------


class TestMuswayAmpApply:
    @pytest.mark.asyncio
    async def test_empty_apply_returns_none(
        self, musway_amp: MuswayAmp, mock_musway: MagicMock
    ) -> None:
        result = await musway_amp.apply()
        assert result is None
        mock_musway.load_preset.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_calls_load_preset_with_resolved_path(
        self,
        musway_amp: MuswayAmp,
        mock_musway: MagicMock,
        session_dir: Path,
    ) -> None:
        await musway_amp.set_channel_level(1, -3.0)
        result = await musway_amp.apply()
        assert result is not None
        assert result.exists()
        expected_path = (session_dir / "preset_initial.txt").resolve()
        mock_musway.load_preset.assert_called_once_with(path=expected_path)

    @pytest.mark.asyncio
    async def test_apply_clears_buffer(
        self, musway_amp: MuswayAmp, mock_musway: MagicMock
    ) -> None:
        await musway_amp.set_channel_level(1, -3.0)
        await musway_amp.apply()
        mock_musway.load_preset.reset_mock()
        result = await musway_amp.apply()
        assert result is None
        mock_musway.load_preset.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_cumulative_chain(
        self,
        musway_amp: MuswayAmp,
        mock_musway: MagicMock,
        session_dir: Path,
    ) -> None:
        await musway_amp.set_channel_level(1, -3.0)
        musway_amp.set_phase(PresetPhase.INITIAL)
        path1 = await musway_amp.apply()
        assert path1 == session_dir / "preset_initial.txt"

        await musway_amp.reset_eq(1)
        musway_amp.set_phase(PresetPhase.EQ)
        path2 = await musway_amp.apply()
        assert path2 == session_dir / "preset_eq.txt"

        assert mock_musway.load_preset.call_count == 2


# ---------------------------------------------------------------------------
# Immediate operations — automation hooks
# ---------------------------------------------------------------------------


class TestMuswayAmpImmediate:
    @pytest.mark.asyncio
    async def test_solo_channel_unmutes_target_mutes_others(
        self,
        musway_amp: MuswayAmp,
        mock_musway: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        await musway_amp.solo_channel(1)
        calls = mock_musway.set_channel_mute.call_args_list
        num_channels = len(sample_channels)
        assert len(calls) == num_channels
        ch1_call = next(c for c in calls if c.kwargs["channel"] == 1)
        assert ch1_call.kwargs["mute"] is False
        for c in calls:
            if c.kwargs["channel"] != 1:
                assert c.kwargs["mute"] is True

    @pytest.mark.asyncio
    async def test_solo_channels_unmutes_targets_mutes_others(
        self,
        musway_amp: MuswayAmp,
        mock_musway: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        await musway_amp.solo_channels([1, 2])
        calls = mock_musway.set_channel_mute.call_args_list
        num_channels = len(sample_channels)
        assert len(calls) == num_channels
        for c in calls:
            if c.kwargs["channel"] in (1, 2):
                assert c.kwargs["mute"] is False
            else:
                assert c.kwargs["mute"] is True

    @pytest.mark.asyncio
    async def test_unmute_all_channels(
        self,
        musway_amp: MuswayAmp,
        mock_musway: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        await musway_amp.unmute_all_channels()
        calls = mock_musway.set_channel_mute.call_args_list
        num_channels = len(sample_channels)
        assert len(calls) == num_channels
        for c in calls:
            assert c.kwargs["mute"] is False

    @pytest.mark.asyncio
    async def test_set_master_mute_true(
        self, musway_amp: MuswayAmp, mock_musway: MagicMock
    ) -> None:
        await musway_amp.set_master_mute(muted=True)
        mock_musway.set_master_mute.assert_called_once_with(mute=True)

    @pytest.mark.asyncio
    async def test_set_master_mute_false(
        self, musway_amp: MuswayAmp, mock_musway: MagicMock
    ) -> None:
        await musway_amp.set_master_mute(muted=False)
        mock_musway.set_master_mute.assert_called_once_with(mute=False)
