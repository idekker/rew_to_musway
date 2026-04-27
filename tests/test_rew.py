"""Tests for REWController with mocked REWClient."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from aiorew import TargetShape as AioTargetShape
from rew_to_musway.config import TargetConfig, TargetShape
from rew_to_musway.rew import REWController

if TYPE_CHECKING:
    from rew_to_musway.config import Config

SAMPLE_UUID = UUID("12345678-1234-1234-1234-123456789abc")
_PREDICTED_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ARITH_UUID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a fully mocked REWClient."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.get_version = AsyncMock(return_value="5.40")

    # RTA
    client.rta = AsyncMock()
    client.rta.set_configuration = AsyncMock()
    client.rta.start = AsyncMock()
    client.rta.wait_until_stopped = AsyncMock()
    client.save_rta = AsyncMock(return_value=SAMPLE_UUID)

    # Measurements
    client.measurements = AsyncMock()
    client.measurements.set_title = AsyncMock()
    client.measurements.apply_smoothing = AsyncMock()
    client.measurements.set_equaliser = AsyncMock()
    client.measurements.get_target_settings = AsyncMock(
        return_value=MagicMock(shape="FullRange")
    )
    client.measurements.set_target_settings = AsyncMock()
    client.measurements.calculate_target_level = AsyncMock()
    client.measurements.get_target_level = AsyncMock(return_value=75.0)
    client.measurements.match_target = AsyncMock()
    client.measurements.generate_predicted_measurement = AsyncMock(return_value=None)
    client.measurements.get_filters = AsyncMock(return_value=[])
    client.measurements.delete_all = AsyncMock()
    client.measurements.save_all = AsyncMock()
    client.measurements.arithmetic = AsyncMock()

    # Default list returns SAMPLE_UUID only; tests override as needed
    _summary_sample = MagicMock()
    _summary_sample.uuid = SAMPLE_UUID
    client.measurements.list = AsyncMock(return_value=[_summary_sample])

    # SPL meter
    client.spl_meter = AsyncMock()
    spl_vals = MagicMock()
    spl_vals.spl = 75.0
    spl_vals.weighting = "Z"
    spl_vals.filter = "None"
    client.spl_meter.get_levels = AsyncMock(return_value=spl_vals)

    # Generator
    client.generator = AsyncMock()

    # Audio
    client.audio = AsyncMock()

    # EQ
    client.eq = AsyncMock()

    return client


@pytest.fixture
def rew_controller(sample_config: Config, mock_client: AsyncMock) -> REWController:
    """Create a REWController with an injected mock client."""
    controller = REWController(sample_config)
    controller._client = mock_client  # noqa: SLF001
    return controller


class TestRTA:
    @pytest.mark.asyncio
    async def test_run_rta(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        uuid = await rew_controller.run_rta()
        assert uuid == SAMPLE_UUID
        mock_client.rta.set_configuration.assert_called_once()
        mock_client.rta.start.assert_called_once()
        mock_client.rta.wait_until_stopped.assert_called_once()
        mock_client.save_rta.assert_called_once()

    @pytest.mark.asyncio
    async def test_rename_measurement(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.rename_measurement(SAMPLE_UUID, "test_name")
        mock_client.measurements.set_title.assert_called_once_with(
            SAMPLE_UUID, "test_name"
        )


class TestSPLMeter:
    @pytest.mark.asyncio
    async def test_measure_spl(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        spl = await rew_controller.measure_spl(warmup=0.0)
        expected_spl = 75.0
        assert spl.spl == expected_spl
        mock_client.spl_meter.open.assert_called_once()
        mock_client.spl_meter.start.assert_called_once()
        mock_client.spl_meter.get_levels.assert_called_once()
        mock_client.spl_meter.stop.assert_called_once()
        mock_client.spl_meter.close.assert_called_once()


class TestEQConfiguration:
    @pytest.mark.asyncio
    async def test_configure_equaliser(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.configure_equaliser(SAMPLE_UUID)
        mock_client.measurements.set_equaliser.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_target_bass_limited(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        """Bass-limited target sets shape and cutoff on TargetSettings."""
        target_cfg = TargetConfig(
            shape=TargetShape.BASS_LIMITED,
            cutoff_hz=55.0,
            slope_db_per_octave=24,
        )
        await rew_controller.configure_target(
            SAMPLE_UUID, target_cfg=target_cfg, target_offset=0.0
        )
        mock_client.measurements.set_target_settings.assert_called_once()
        settings = mock_client.measurements.set_target_settings.call_args.args[1]
        assert settings.shape == AioTargetShape.BASS_LIMITED
        assert settings.bassManagementCutoffHz == 55.0
        assert settings.bassManagementSlopedBPerOctave == 24

    @pytest.mark.asyncio
    async def test_configure_target_subwoofer(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        """Subwoofer target sets shape, cutoff, and low-freq rolloff."""
        target_cfg = TargetConfig(
            shape=TargetShape.SUBWOOFER,
            cutoff_hz=80.0,
            slope_db_per_octave=12,
            low_freq_cutoff_hz=20.0,
            low_freq_slope_db_per_octave=12,
        )
        await rew_controller.configure_target(
            SAMPLE_UUID, target_cfg=target_cfg, target_offset=0.0
        )
        mock_client.measurements.set_target_settings.assert_called_once()
        settings = mock_client.measurements.set_target_settings.call_args.args[1]
        assert settings.shape == AioTargetShape.SUBWOOFER
        assert settings.bassManagementCutoffHz == 80.0
        assert settings.bassManagementSlopedBPerOctave == 12
        assert settings.lowFreqCutoffHz == 20.0
        assert settings.lowFreqSlopedBPerOctave == 12

    @pytest.mark.asyncio
    async def test_configure_target_speaker_driver(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        """Speaker driver target sets shape, HP and LP on TargetSettings."""
        target_cfg = TargetConfig(
            shape=TargetShape.SPEAKER_DRIVER,
            highpass_hz=300.0,
            highpass_type="LR24",
            lowpass_hz=3500.0,
            lowpass_type="BU18",
        )
        await rew_controller.configure_target(
            SAMPLE_UUID, target_cfg=target_cfg, target_offset=0.0
        )
        mock_client.measurements.set_target_settings.assert_called_once()
        settings = mock_client.measurements.set_target_settings.call_args.args[1]
        assert settings.shape == AioTargetShape.DRIVER
        assert settings.highPassCutoffHz == 300.0
        assert settings.highPassCrossoverType == "LR24"
        assert settings.lowPassCutoffHz == 3500.0
        assert settings.lowPassCrossoverType == "BU18"

    @pytest.mark.asyncio
    async def test_configure_match_settings(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        start_freq, end_freq = 100.0, 5000.0
        await rew_controller.configure_match_settings(start_freq, end_freq)
        mock_client.eq.set_match_target_settings.assert_called_once()
        settings = mock_client.eq.set_match_target_settings.call_args.args[0]
        assert settings.startFrequency == start_freq
        assert settings.endFrequency == end_freq

    @pytest.mark.asyncio
    async def test_match_target(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.match_target(SAMPLE_UUID)
        mock_client.measurements.match_target.assert_called_once_with(SAMPLE_UUID)

    @pytest.mark.asyncio
    async def test_generate_predicted(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        # Before: only SAMPLE_UUID; after: SAMPLE_UUID + PREDICTED_UUID
        summary_before = MagicMock()
        summary_before.uuid = SAMPLE_UUID
        summary_after = MagicMock()
        summary_after.uuid = _PREDICTED_UUID
        mock_client.measurements.list = AsyncMock(
            side_effect=[[summary_before], [summary_before, summary_after]]
        )

        result = await rew_controller.generate_predicted(SAMPLE_UUID)
        assert result == _PREDICTED_UUID
        mock_client.measurements.generate_predicted_measurement.assert_called_once_with(
            SAMPLE_UUID
        )


class TestGenerator:
    @pytest.mark.asyncio
    async def test_generator_play(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.generator_play()
        mock_client.generator.set_signal.assert_called_once()
        mock_client.generator.set_level.assert_called_once()
        mock_client.generator.play.assert_called_once()

    @pytest.mark.asyncio
    async def test_generator_stop(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.generator_stop()
        mock_client.generator.stop.assert_called_once()


class TestMeasurementManagement:
    @pytest.mark.asyncio
    async def test_save_all_measurements(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        await rew_controller.save_all_measurements("C:\\output\\test.mdat")
        mock_client.measurements.save_all.assert_called_once()


class TestArithmetic:
    @pytest.mark.asyncio
    async def test_divide_measurements(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        uuid_a = SAMPLE_UUID
        uuid_b = _PREDICTED_UUID

        summary_a = MagicMock()
        summary_a.uuid = uuid_a
        summary_b = MagicMock()
        summary_b.uuid = uuid_b
        summary_new = MagicMock()
        summary_new.uuid = _ARITH_UUID

        mock_client.measurements.list = AsyncMock(
            side_effect=[
                [summary_a, summary_b],
                [summary_a, summary_b, summary_new],
            ]
        )

        result = await rew_controller.divide_measurements(uuid_a, uuid_b)
        assert result == _ARITH_UUID
        mock_client.measurements.arithmetic.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiply_measurements(
        self, rew_controller: REWController, mock_client: AsyncMock
    ) -> None:
        uuid_a = SAMPLE_UUID
        uuid_b = _PREDICTED_UUID

        summary_a = MagicMock()
        summary_a.uuid = uuid_a
        summary_b = MagicMock()
        summary_b.uuid = uuid_b
        summary_new = MagicMock()
        summary_new.uuid = _ARITH_UUID

        mock_client.measurements.list = AsyncMock(
            side_effect=[
                [summary_a, summary_b],
                [summary_a, summary_b, summary_new],
            ]
        )

        result = await rew_controller.multiply_measurements(uuid_a, uuid_b)
        assert result == _ARITH_UUID
        mock_client.measurements.arithmetic.assert_called_once()
