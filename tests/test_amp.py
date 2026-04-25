"""Tests for AmpController with mocked TunestPC."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from rew_to_musway.amp import AmpController
from tunest_pc import FilterSlope

if TYPE_CHECKING:
    from rew_to_musway.config import ChannelConfig, Config


@pytest.fixture
def mock_tunest() -> MagicMock:
    """Patch TunestPC class and return the mock instance."""
    with patch("rew_to_musway.amp.TunestPC") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance  # type: ignore[misc]


@pytest.fixture
def amp(
    sample_config: Config,
    mock_tunest: MagicMock,  # noqa: ARG001
) -> AmpController:
    """Create an AmpController backed by the patched TunestPC."""
    return AmpController(sample_config)


class TestAmpConnection:
    @pytest.mark.asyncio
    async def test_connect(self, amp: AmpController, mock_tunest: MagicMock) -> None:
        await amp.connect()
        mock_tunest.connect.assert_called_once()


class TestMasterControls:
    @pytest.mark.asyncio
    async def test_set_master_mute(
        self, amp: AmpController, mock_tunest: MagicMock
    ) -> None:
        await amp.set_master_mute(muted=True)
        mock_tunest.set_master_mute.assert_called_once_with(True)  # noqa: FBT003

    @pytest.mark.asyncio
    async def test_set_master_volume(
        self, amp: AmpController, mock_tunest: MagicMock
    ) -> None:
        await amp.set_master_volume(-10.0)
        mock_tunest.set_master_volume.assert_called_once_with(-10.0)


class TestChannelControls:
    @pytest.mark.asyncio
    async def test_solo_channel(
        self, amp: AmpController, mock_tunest: MagicMock
    ) -> None:
        await amp.solo_channel(1)
        calls = mock_tunest.set_channel_mute.call_args_list
        num_channels = 6
        assert len(calls) == num_channels
        # CH1 should be muted=False
        ch1_call = next(c for c in calls if c.args[0] == 1)
        assert ch1_call.args[1] is False
        # Others should be muted=True
        for c in calls:
            if c.args[0] != 1:
                assert c.args[1] is True

    @pytest.mark.asyncio
    async def test_mute_all(self, amp: AmpController, mock_tunest: MagicMock) -> None:
        await amp.mute_all()
        num_channels = 6
        assert mock_tunest.set_channel_mute.call_count == num_channels
        for c in mock_tunest.set_channel_mute.call_args_list:
            assert c.args[1] is True

    @pytest.mark.asyncio
    async def test_set_channel_level(
        self, amp: AmpController, mock_tunest: MagicMock
    ) -> None:
        await amp.set_channel_level(3, -2.5)
        mock_tunest.set_channel_level.assert_called_once_with(3, -2.5)


class TestFilterConfiguration:
    @pytest.mark.asyncio
    async def test_configure_filters_hp_and_lp(
        self,
        amp: AmpController,
        mock_tunest: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # CH3 has both HP and LP
        ch3 = sample_channels[2]
        await amp.configure_filters(ch3)
        mock_tunest.set_highpass.assert_called_once()
        mock_tunest.set_lowpass.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_filters_hp_only(
        self,
        amp: AmpController,
        mock_tunest: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        # CH1 has HP only
        ch1 = sample_channels[0]
        await amp.configure_filters(ch1)
        mock_tunest.set_highpass.assert_called_once()
        # LP not configured → set to OFF
        mock_tunest.set_lowpass.assert_called_once()
        call_args = mock_tunest.set_lowpass.call_args
        assert call_args[0][3] == FilterSlope.OFF


class TestEQOperations:
    @pytest.mark.asyncio
    async def test_bypass_eq(self, amp: AmpController, mock_tunest: MagicMock) -> None:
        await amp.bypass_eq()
        mock_tunest.bypass_eq.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_eq(self, amp: AmpController, mock_tunest: MagicMock) -> None:
        await amp.import_eq(1, "C:\\test.json")
        mock_tunest.import_eq.assert_called_once_with(1, "C:\\test.json")


class TestCompoundOperations:
    @pytest.mark.asyncio
    async def test_prepare_for_level_measurement(
        self, amp: AmpController, mock_tunest: MagicMock
    ) -> None:
        await amp.prepare_for_level_measurement()
        mock_tunest.bypass_eq.assert_called_once()
        num_channels = 6
        assert mock_tunest.set_channel_level.call_count == num_channels
        for c in mock_tunest.set_channel_level.call_args_list:
            assert c.args[1] == 0.0
        mock_tunest.set_master_mute.assert_called_with(False)  # noqa: FBT003

    @pytest.mark.asyncio
    async def test_prepare_channel(
        self,
        amp: AmpController,
        mock_tunest: MagicMock,
        sample_channels: list[ChannelConfig],
    ) -> None:
        ch1 = sample_channels[0]
        await amp.prepare_channel(ch1)
        mock_tunest.reset_eq.assert_called_once()
        mock_tunest.set_highpass.assert_called_once()
        num_channels = 6
        assert mock_tunest.set_channel_mute.call_count == num_channels
