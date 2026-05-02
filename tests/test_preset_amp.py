"""Tests for _MuswayPresetAmp abstract base class.

A minimal concrete stub (``_StubAmp``) is defined here to exercise all
shared logic without depending on either ManualAmp or MuswayAmp.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiorew import FilterSetting
from rew_to_musway.amp._preset_amp import (
    PresetPhase,
    _MuswayPresetAmp,
    preset_filename,
)
from rew_to_musway.config import ChannelConfig, FilterConfig, FilterType

# Path to the reference preset file
_TEST_PRESET = Path(__file__).parent.parent / "test_files" / "default_preset.txt"


# ---------------------------------------------------------------------------
# Minimal concrete stub
# ---------------------------------------------------------------------------


class _StubAmp(_MuswayPresetAmp):
    """Concrete subclass that records hook calls for assertions."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.connect_called = False
        self.delivered: list[Path] = []
        self.solo_channel_calls: list[tuple[int, str]] = []
        self.solo_channels_calls: list[tuple[list[int], str]] = []
        self.master_mute_calls: list[tuple[bool, str]] = []

    async def connect(self) -> None:
        self.connect_called = True

    async def _deliver_preset(self, out_path: Path) -> None:
        self.delivered.append(out_path)

    async def _do_solo_channel(self, channel: int, msg: str) -> None:
        self.solo_channel_calls.append((channel, msg))

    async def _do_solo_channels(self, channels: list[int], msg: str) -> None:
        self.solo_channels_calls.append((channels, msg))

    async def _do_master_mute(self, muted: bool, msg: str) -> None:  # noqa: FBT001
        self.master_mute_calls.append((muted, msg))


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
def stub_amp(
    default_preset: Path,
    session_dir: Path,
    sample_channels: list[ChannelConfig],
) -> _StubAmp:
    return _StubAmp(
        default_preset_path=default_preset,
        session_dir=session_dir,
        channels=sample_channels,
        action_timeout=0.01,
    )


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
# Buffer / Apply
# ---------------------------------------------------------------------------


class TestMuswayPresetAmpBuffer:
    @pytest.mark.asyncio
    async def test_empty_apply_returns_none(self, stub_amp: _StubAmp) -> None:
        result = await stub_amp.apply()
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_apply_does_not_call_deliver(self, stub_amp: _StubAmp) -> None:
        await stub_amp.apply()
        assert stub_amp.delivered == []

    @pytest.mark.asyncio
    async def test_apply_writes_preset_and_calls_deliver(
        self,
        stub_amp: _StubAmp,
        session_dir: Path,
    ) -> None:
        await stub_amp.set_channel_level(1, -3.0)
        result = await stub_amp.apply()
        assert result == session_dir / "preset_initial.txt"
        assert result is not None
        assert result.exists()
        assert stub_amp.delivered == [session_dir / "preset_initial.txt"]

    @pytest.mark.asyncio
    async def test_apply_clears_buffer(self, stub_amp: _StubAmp) -> None:
        await stub_amp.set_channel_level(1, -3.0)
        await stub_amp.apply()
        result = await stub_amp.apply()
        assert result is None

    @pytest.mark.asyncio
    async def test_cumulative_preset_chain(
        self,
        stub_amp: _StubAmp,
        session_dir: Path,
    ) -> None:
        await stub_amp.set_channel_level(1, -3.0)
        stub_amp.set_phase(PresetPhase.INITIAL)
        path1 = await stub_amp.apply()
        assert path1 == session_dir / "preset_initial.txt"

        await stub_amp.reset_eq(1)
        stub_amp.set_phase(PresetPhase.EQ)
        path2 = await stub_amp.apply()
        assert path2 == session_dir / "preset_eq.txt"

        await stub_amp.set_channel_level(2, -1.0)
        stub_amp.set_phase(PresetPhase.FINETUNE, iteration=1)
        path3 = await stub_amp.apply()
        assert path3 == session_dir / "preset_finetune_1.txt"

        await stub_amp.set_channel_level(2, -1.0)
        stub_amp.set_phase(PresetPhase.FINETUNE, iteration=2)
        path4 = await stub_amp.apply()
        assert path4 == session_dir / "preset_finetune_2.txt"

        await stub_amp.set_channel_level(2, -1.0)
        stub_amp.set_phase(PresetPhase.VERIFICATION)
        path5 = await stub_amp.apply()
        assert path5 == session_dir / "preset_verification.txt"

    @pytest.mark.asyncio
    async def test_crossover_hp_and_lp(
        self,
        stub_amp: _StubAmp,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # CH3 (index 2) has both HP (300 Hz) and LP (3500 Hz)
        ch3 = sample_channels[2]
        await stub_amp.set_crossover(ch3)
        result = await stub_amp.apply()
        assert result is not None
        assert result.exists()

    @pytest.mark.asyncio
    async def test_crossover_hp_only_defaults_lp(
        self,
        stub_amp: _StubAmp,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # CH1 (index 0) has HP only — LP should default to BUTTERWORTH/20000/OFF
        ch1 = sample_channels[0]
        await stub_amp.set_crossover(ch1)
        result = await stub_amp.apply()
        assert result is not None
        assert result.exists()

    @pytest.mark.asyncio
    async def test_crossover_lp_only_defaults_hp(self, stub_amp: _StubAmp) -> None:
        # Build a channel that has LP only (no HP)
        ch = ChannelConfig(
            number=1,
            name="LF",
            group="front",
            highpass=None,
            lowpass=FilterConfig(
                type=FilterType.LINKWITZ_RILEY, frequency=80, slope=24
            ),
        )
        await stub_amp.set_crossover(ch)
        result = await stub_amp.apply()
        assert result is not None
        assert result.exists()

    @pytest.mark.asyncio
    async def test_set_eq_filters_clears_eq_reset(self, stub_amp: _StubAmp) -> None:
        """set_eq_filters after reset_eq should clear the reset flag."""
        await stub_amp.reset_eq(1)
        filters = [MagicMock(spec=FilterSetting)]
        await stub_amp.set_eq_filters(1, filters)
        # eq_reset should be False, eq_filters should be set
        buf = stub_amp._buffer.channel(1)  # noqa: SLF001
        assert buf.eq_reset is False
        assert buf.eq_filters == filters

    @pytest.mark.asyncio
    async def test_last_write_wins_for_level(self, stub_amp: _StubAmp) -> None:
        await stub_amp.set_channel_level(1, -1.0)
        await stub_amp.set_channel_level(1, -5.0)
        buf = stub_amp._buffer.channel(1)  # noqa: SLF001
        assert buf.level == -5.0


# ---------------------------------------------------------------------------
# Immediate operations
# ---------------------------------------------------------------------------


class TestMuswayPresetAmpImmediate:
    @pytest.mark.asyncio
    async def test_solo_channel_delegates_with_message(
        self, stub_amp: _StubAmp
    ) -> None:
        await stub_amp.solo_channel(1)
        assert len(stub_amp.solo_channel_calls) == 1
        channel, msg = stub_amp.solo_channel_calls[0]
        assert channel == 1
        assert "LF" in msg
        assert "CH1" in msg

    @pytest.mark.asyncio
    async def test_solo_channel_unknown_channel_uses_fallback_name(
        self, stub_amp: _StubAmp
    ) -> None:
        await stub_amp.solo_channel(99)
        _, msg = stub_amp.solo_channel_calls[0]
        assert "CH99" in msg

    @pytest.mark.asyncio
    async def test_solo_channels_delegates_with_message(
        self, stub_amp: _StubAmp
    ) -> None:
        await stub_amp.solo_channels([1, 2])
        assert len(stub_amp.solo_channels_calls) == 1
        channels, msg = stub_amp.solo_channels_calls[0]
        assert channels == [1, 2]
        assert "CH1" in msg
        assert "CH2" in msg

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._preset_amp.timed_prompt", new_callable=AsyncMock)
    async def test_mute_all_calls_timed_prompt(
        self, mock_prompt: AsyncMock, stub_amp: _StubAmp
    ) -> None:
        await stub_amp.mute_all()
        mock_prompt.assert_called_once()
        assert "Mute all" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    async def test_master_mute_true_delegates(self, stub_amp: _StubAmp) -> None:
        await stub_amp.set_master_mute(muted=True)
        assert len(stub_amp.master_mute_calls) == 1
        muted, msg = stub_amp.master_mute_calls[0]
        assert muted is True
        assert "Mute" in msg

    @pytest.mark.asyncio
    async def test_master_mute_false_delegates(self, stub_amp: _StubAmp) -> None:
        await stub_amp.set_master_mute(muted=False)
        muted, msg = stub_amp.master_mute_calls[0]
        assert muted is False
        assert "Unmute" in msg

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._preset_amp.timed_prompt", new_callable=AsyncMock)
    async def test_restore_eq_calls_timed_prompt_with_preset_name(
        self, mock_prompt: AsyncMock, stub_amp: _StubAmp, session_dir: Path
    ) -> None:
        # Set a last_preset_path so it shows the filename
        stub_amp._last_preset_path = session_dir / "preset_eq.txt"  # noqa: SLF001
        await stub_amp.restore_eq()
        mock_prompt.assert_called_once()
        assert "preset_eq.txt" in mock_prompt.call_args[0][0]

    @pytest.mark.asyncio
    @patch("rew_to_musway.amp._preset_amp.timed_prompt", new_callable=AsyncMock)
    async def test_restore_eq_no_preset_uses_fallback(
        self, mock_prompt: AsyncMock, stub_amp: _StubAmp
    ) -> None:
        await stub_amp.restore_eq()
        assert "latest preset" in mock_prompt.call_args[0][0]
