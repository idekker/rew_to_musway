"""Tests for SPL sanity check."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rew_to_musway.sanity import SanityResult, spl_sanity_check


def _spl_values(spl: float) -> MagicMock:
    """Create a mock SPLValues with given *spl*."""
    mock = MagicMock()
    mock.spl = spl
    return mock


class TestSPLSanityCheck:
    @pytest.mark.asyncio
    async def test_ok_when_above_threshold(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(return_value=_spl_values(70.0))
        result = await spl_sanity_check(rew, target_spl=75.0, threshold=-10.0)
        assert result == SanityResult.OK

    @pytest.mark.asyncio
    async def test_ok_at_exact_threshold(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(return_value=_spl_values(65.0))
        result = await spl_sanity_check(rew, target_spl=75.0, threshold=-10.0)
        assert result == SanityResult.OK

    @pytest.mark.asyncio
    async def test_proceeded_when_below_and_no_prompt(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(return_value=_spl_values(40.0))
        result = await spl_sanity_check(rew, target_spl=75.0, threshold=-10.0)
        assert result == SanityResult.PROCEEDED

    @pytest.mark.asyncio
    async def test_proceeded_when_user_chooses_proceed(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(return_value=_spl_values(40.0))
        prompt_fn = AsyncMock(return_value="Proceed")
        result = await spl_sanity_check(
            rew, target_spl=75.0, threshold=-10.0, prompt_fn=prompt_fn
        )
        assert result == SanityResult.PROCEEDED
        prompt_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_then_ok(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(side_effect=[_spl_values(40.0), _spl_values(70.0)])
        prompt_fn = AsyncMock(return_value="Retry")
        result = await spl_sanity_check(
            rew, target_spl=75.0, threshold=-10.0, prompt_fn=prompt_fn
        )
        assert result == SanityResult.OK
        assert rew.measure_spl.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_then_proceed(self) -> None:
        rew = AsyncMock()
        rew.measure_spl = AsyncMock(side_effect=[_spl_values(40.0), _spl_values(40.0)])
        prompt_fn = AsyncMock(side_effect=["Retry", "Proceed"])
        result = await spl_sanity_check(
            rew, target_spl=75.0, threshold=-10.0, prompt_fn=prompt_fn
        )
        assert result == SanityResult.PROCEEDED
        assert prompt_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_custom_threshold(self) -> None:
        rew = AsyncMock()
        # 55 dB, target 75, threshold -15 → min is 60 → 55 < 60 → low
        rew.measure_spl = AsyncMock(return_value=_spl_values(55.0))
        result = await spl_sanity_check(rew, target_spl=75.0, threshold=-15.0)
        assert result == SanityResult.PROCEEDED
