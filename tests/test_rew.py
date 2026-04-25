"""Tests for REWController with mocked REWClient."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from rew_to_musway.rew import REWController

if TYPE_CHECKING:
    from rew_to_musway.config import Config

SAMPLE_UUID = UUID("12345678-1234-1234-1234-123456789abc")


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
        await rew_controller.generate_predicted(SAMPLE_UUID)
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
