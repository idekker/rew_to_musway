"""Tests for playback strategies."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rew_to_musway.config import LevelsConfig, PlaybackConfig, PlaybackMode
from rew_to_musway.playback._base import SPLCheckSkippedError, check_spl_level
from rew_to_musway.playback._manual import ManualPlayback
from rew_to_musway.playback._rew_generator import REWGeneratorPlayback

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


@contextmanager
def _patch_spl_loop(
    mock_rew: AsyncMock,
    readings: list[MagicMock],
    keys: list[bytes | None] | None = None,
) -> Generator[None]:
    """Patch Live, sleep, keypress and set up spl_open/read/close mocks."""
    mock_rew.spl_open = AsyncMock()
    mock_rew.spl_close = AsyncMock()
    mock_rew.spl_read = AsyncMock(side_effect=readings)

    # Default: no key until last poll, then Enter
    if keys is None:
        keys = [None] * (len(readings) - 1) + [b"\r"]

    keypress_mock = AsyncMock(side_effect=keys)

    with (
        patch("rew_to_musway.playback._base.Live", autospec=True),
        patch("rew_to_musway.playback._base.asyncio.sleep"),
        patch("rew_to_musway.playback._base._poll_keypress", keypress_mock),
    ):
        yield


# ---------------------------------------------------------------------------
# SPL check loop
# ---------------------------------------------------------------------------


class TestCheckSPLLevel:
    @pytest.mark.asyncio
    async def test_within_tolerance(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """SPL within tolerance, user presses Enter."""
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)

        with _patch_spl_loop(mock_rew, [mock_spl_values(75.0)]):
            result = await check_spl_level(mock_rew, levels)

        expected = 75.0
        assert result == expected
        mock_rew.spl_open.assert_called_once()
        mock_rew.spl_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_at_boundary(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """SPL exactly at boundary is OK."""
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)

        with _patch_spl_loop(mock_rew, [mock_spl_values(76.0)]):
            result = await check_spl_level(mock_rew, levels)

        expected = 76.0
        assert result == expected

    @pytest.mark.asyncio
    async def test_user_confirms_out_of_range(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """User presses Enter even when out of range — returns current value."""
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)

        with _patch_spl_loop(
            mock_rew,
            [mock_spl_values(70.0)],
            keys=[b"\r"],
        ):
            result = await check_spl_level(mock_rew, levels)

        expected = 70.0
        assert result == expected

    @pytest.mark.asyncio
    async def test_esc_raises_skipped(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """Esc key raises SPLCheckSkippedError."""
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)

        with (
            _patch_spl_loop(
                mock_rew,
                [mock_spl_values(70.0)],
                keys=[b"\x1b"],
            ),
            pytest.raises(SPLCheckSkippedError),
        ):
            await check_spl_level(mock_rew, levels)

        mock_rew.spl_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_polls_until_keypress(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """Polls multiple times before user presses Enter."""
        readings = [
            mock_spl_values(70.0),
            mock_spl_values(73.0),
            mock_spl_values(75.0),
        ]
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)

        with _patch_spl_loop(mock_rew, readings):
            result = await check_spl_level(mock_rew, levels)

        expected_spl = 75.0
        expected_reads = 3
        assert result == expected_spl
        assert mock_rew.spl_read.call_count == expected_reads


# ---------------------------------------------------------------------------
# ManualPlayback
# ---------------------------------------------------------------------------


class TestManualPlayback:
    @pytest.mark.asyncio
    async def test_start_noise_prompts_user(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)
        pb = ManualPlayback(mock_rew, levels)

        with (
            patch("rew_to_musway.playback._manual.console"),
            patch(
                "rew_to_musway.playback._manual.wait_for_enter", new_callable=AsyncMock
            ),
            _patch_spl_loop(mock_rew, [mock_spl_values(75.0)]),
        ):
            await pb.start_noise()

        mock_rew.spl_read.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_noise_prompts_user(self, mock_rew: AsyncMock) -> None:
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)
        pb = ManualPlayback(mock_rew, levels)

        with (
            patch("rew_to_musway.playback._manual.console"),
            patch(
                "rew_to_musway.playback._manual.wait_for_enter", new_callable=AsyncMock
            ),
        ):
            await pb.stop_noise()


# ---------------------------------------------------------------------------
# REWGeneratorPlayback
# ---------------------------------------------------------------------------


class TestREWGeneratorPlayback:
    @pytest.mark.asyncio
    async def test_start_noise_calls_generator(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        playback_cfg = PlaybackConfig(
            mode=PlaybackMode.REW_GENERATOR,
            output_device="Speakers",
            output_channel="L+R",
        )
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)
        pb = REWGeneratorPlayback(mock_rew, playback_cfg, levels)

        with (
            patch("rew_to_musway.playback._rew_generator.console"),
            patch("rew_to_musway.playback._rew_generator.asyncio.sleep"),
            _patch_spl_loop(mock_rew, [mock_spl_values(75.0)]),
        ):
            await pb.start_noise()

        mock_rew.generator_play.assert_called_once()
        mock_rew.spl_read.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_noise_prompts_user(self, mock_rew: AsyncMock) -> None:
        playback_cfg = PlaybackConfig(
            mode=PlaybackMode.REW_GENERATOR,
            output_device="Speakers",
            output_channel="L+R",
        )
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)
        pb = REWGeneratorPlayback(mock_rew, playback_cfg, levels)

        with patch("rew_to_musway.playback._rew_generator.console"):
            await pb.stop_noise()

        mock_rew.generator_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_device_configured_once(
        self,
        mock_rew: AsyncMock,
        mock_spl_values: Callable[..., MagicMock],
    ) -> None:
        """Output device is only configured on first start_noise call."""
        playback_cfg = PlaybackConfig(
            mode=PlaybackMode.REW_GENERATOR,
            output_device="Speakers",
            output_channel="L+R",
        )
        levels = LevelsConfig(target_spl=75.0, tolerance=1.0)
        pb = REWGeneratorPlayback(mock_rew, playback_cfg, levels)

        # Two calls — spl_read needs fresh side_effect each time
        readings_1 = [mock_spl_values(75.0)]
        readings_2 = [mock_spl_values(75.0)]

        with (
            patch("rew_to_musway.playback._rew_generator.console"),
            patch("rew_to_musway.playback._rew_generator.asyncio.sleep"),
            patch("rew_to_musway.playback._base.Live", autospec=True),
            patch("rew_to_musway.playback._base.asyncio.sleep"),
        ):
            # First call
            mock_rew.spl_open = AsyncMock()
            mock_rew.spl_close = AsyncMock()
            mock_rew.spl_read = AsyncMock(side_effect=readings_1)
            with patch(
                "rew_to_musway.playback._base._poll_keypress",
                AsyncMock(return_value=b"\r"),
            ):
                await pb.start_noise()

            # Second call
            mock_rew.spl_read = AsyncMock(side_effect=readings_2)
            with patch(
                "rew_to_musway.playback._base._poll_keypress",
                AsyncMock(return_value=b"\r"),
            ):
                await pb.start_noise()

        assert mock_rew.set_output_device_name.call_count == 1
        assert mock_rew.set_output_channel.call_count == 1
