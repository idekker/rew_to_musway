"""Tests for the unified (combined) calibration flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

import pytest

from rew_to_musway.calibration import (
    MeasureResult,
    UnifiedContext,
    VerificationResult,
    run_finetune_loop,
    run_measure_loop,
    run_verification_loop,
)

if TYPE_CHECKING:
    from pathlib import Path

    from rew_to_musway.config import ChannelConfig, Config

_UUID1 = UUID("11111111-1111-1111-1111-111111111111")
_UUID2 = UUID("22222222-2222-2222-2222-222222222222")
_UUID_PRED = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_UUID_DIV = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_UUID_MUL = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _spl(value: float) -> MagicMock:
    mock = MagicMock()
    mock.spl = value
    return mock


@pytest.fixture
def mock_amp() -> AsyncMock:
    amp = AsyncMock()
    amp.set_phase = Mock()
    amp.set_channel_level = AsyncMock()
    amp.set_eq_filters = AsyncMock()
    amp.set_crossover = AsyncMock()
    amp.reset_eq = AsyncMock()
    amp.solo_channel = AsyncMock()
    amp.unmute_all_channels = AsyncMock()
    amp.set_master_mute = AsyncMock()
    amp.apply = AsyncMock()
    return amp


@pytest.fixture
def mock_rew() -> AsyncMock:
    rew = AsyncMock()
    rew.measure_spl = AsyncMock(return_value=_spl(75.0))
    rew.run_rta = AsyncMock(side_effect=[_UUID1, _UUID2])
    rew.rename_measurement = AsyncMock()
    rew.apply_smoothing = AsyncMock()
    rew.configure_equaliser = AsyncMock()
    rew.configure_target = AsyncMock()
    rew.configure_match_settings = AsyncMock()
    rew.match_target = AsyncMock()
    rew.generate_predicted = AsyncMock(return_value=_UUID_PRED)
    rew.get_filters = AsyncMock(return_value=[])
    rew.divide_measurements = AsyncMock(return_value=_UUID_DIV)
    rew.multiply_measurements = AsyncMock(return_value=_UUID_MUL)
    return rew


@pytest.fixture
def mock_playback() -> AsyncMock:
    pb = AsyncMock()
    pb.start_noise = AsyncMock()
    pb.stop_noise = AsyncMock()
    return pb


@pytest.fixture
def ctx(
    sample_config: Config,
    mock_amp: AsyncMock,
    mock_rew: AsyncMock,
    mock_playback: AsyncMock,
    tmp_path: Path,
) -> UnifiedContext:
    return UnifiedContext(
        config=sample_config,
        amp=mock_amp,
        rew=mock_rew,
        playback=mock_playback,
        session_dir=tmp_path / "session",
    )


# ---------------------------------------------------------------------------
# Measure loop (Phase 1+2)
# ---------------------------------------------------------------------------


class TestMeasureLoop:
    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_returns_measure_result(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # Only 2 channels for simplicity
        channels = sample_channels[:2]
        result = await run_measure_loop(ctx, channels)
        assert isinstance(result, MeasureResult)
        assert len(result.rta_uuids) == 2
        assert len(result.predicted_uuids) == 2

    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_buffers_eq_only(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_amp: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        channels = sample_channels[:2]
        await run_measure_loop(ctx, channels)
        # EQ filters buffered
        assert mock_amp.set_eq_filters.call_count == 2
        # Crossovers buffered
        assert mock_amp.set_crossover.call_count >= 2
        # Level offsets NOT set during measure loop (only initial reset to 0)
        level_calls = mock_amp.set_channel_level.call_args_list
        for call in level_calls:
            assert call.args[1] == -60.0, "Measure loop should only reset levels to 0"

    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_solos_each_channel(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_amp: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        channels = sample_channels[:2]
        await run_measure_loop(ctx, channels)
        solo_calls = [c.args[0] for c in mock_amp.solo_channel.call_args_list]
        assert solo_calls == [channels[0].number, channels[1].number]


# ---------------------------------------------------------------------------
# Finetune loop
# ---------------------------------------------------------------------------


class TestFinetuneLoop:
    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_returns_updated_predicted(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_rew: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        channels = sample_channels[:1]
        channels[0].finetune_loops = 1
        mock_rew.run_rta = AsyncMock(return_value=_UUID1)
        rta_uuids = {channels[0].number: _UUID1}
        predicted_uuids = {channels[0].number: _UUID_PRED}

        new_pred = await run_finetune_loop(
            ctx, channels, rta_uuids, predicted_uuids, iteration=1
        )
        assert channels[0].number in new_pred

    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_buffers_eq_filters(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_amp: AsyncMock,
        mock_rew: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        channels = sample_channels[:1]
        channels[0].finetune_loops = 1
        mock_rew.run_rta = AsyncMock(return_value=_UUID1)
        rta_uuids = {channels[0].number: _UUID1}
        predicted_uuids = {channels[0].number: _UUID_PRED}

        await run_finetune_loop(ctx, channels, rta_uuids, predicted_uuids, iteration=1)
        mock_amp.set_eq_filters.assert_called_once()


# ---------------------------------------------------------------------------
# Verification loop (Phase 3+4)
# ---------------------------------------------------------------------------


class TestVerificationLoop:
    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_returns_verification_result(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_rew: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        channels = sample_channels[:2]
        mock_rew.run_rta = AsyncMock(side_effect=[_UUID1, _UUID2])
        result = await run_verification_loop(ctx, channels)
        assert isinstance(result, VerificationResult)
        assert len(result.level_offsets.readings) == 2

    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_no_adjustments_when_balanced(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_rew: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # Both channels in different groups → 0 offset each
        ch1 = sample_channels[0]  # front
        ch5 = sample_channels[4]  # rear
        channels = [ch1, ch5]
        mock_rew.run_rta = AsyncMock(side_effect=[_UUID1, _UUID2])
        mock_rew.measure_spl = AsyncMock(return_value=_spl(75.0))

        result = await run_verification_loop(ctx, channels)
        assert result.adjustments == {}

    @pytest.mark.asyncio
    @patch("rew_to_musway.calibration._unified._countdown", new_callable=AsyncMock)
    async def test_adjustments_when_unbalanced(
        self,
        mock_cd: AsyncMock,  # noqa: ARG002
        ctx: UnifiedContext,
        mock_amp: AsyncMock,  # noqa: ARG002
        mock_rew: AsyncMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # Two front channels with 3 dB difference
        ch1 = sample_channels[0]  # front
        ch2 = sample_channels[1]  # front
        channels = [ch1, ch2]
        mock_rew.run_rta = AsyncMock(side_effect=[_UUID1, _UUID2])
        mock_rew.measure_spl = AsyncMock(side_effect=[_spl(78.0), _spl(75.0)])

        result = await run_verification_loop(ctx, channels)
        # CH1 is 3 dB louder → should get -3.0 offset
        assert ch1.number in result.adjustments
        assert result.adjustments[ch1.number] == -3.0
