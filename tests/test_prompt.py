"""Tests for timed_prompt utility."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from rew_to_musway.prompt import TimedPromptResult, timed_prompt

_KEY_ENTER = b"\r"
_KEY_BACKSPACE = b"\x08"


def _make_key_sequence(keys: list[bytes | None]) -> MagicMock:
    """Return a mock _read_key that yields keys then None forever."""
    it = iter(keys)

    def side_effect() -> bytes | None:
        return next(it, None)

    return MagicMock(side_effect=side_effect)


@pytest.fixture
def _no_live() -> Generator[MagicMock, None, None]:
    """Suppress rich Live rendering during tests."""
    with patch("rew_to_musway.prompt.Live") as mock_live_cls:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_live_cls.return_value = ctx
        yield ctx


@pytest.fixture
def _no_drain() -> Generator[MagicMock, None, None]:
    """Suppress msvcrt.kbhit drain in prompt setup."""
    with patch("rew_to_musway.prompt.msvcrt") as mock_msvcrt:
        mock_msvcrt.kbhit.return_value = False
        yield mock_msvcrt


class TestTimedPromptEnter:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_live", "_no_drain")
    async def test_enter_immediately(self) -> None:
        keys = [_KEY_ENTER]
        with patch("rew_to_musway.prompt._read_key", _make_key_sequence(keys)):
            result = await timed_prompt("Test", 10.0)
        assert result == TimedPromptResult.ENTER

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_live", "_no_drain")
    async def test_enter_after_some_ticks(self) -> None:
        keys: list[bytes | None] = [None, None, _KEY_ENTER]
        with patch("rew_to_musway.prompt._read_key", _make_key_sequence(keys)):
            result = await timed_prompt("Test", 10.0)
        assert result == TimedPromptResult.ENTER


class TestTimedPromptExpiry:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_live", "_no_drain")
    async def test_timer_expires(self) -> None:
        # 3 ticks at 0.1s each = 0.3s; timeout 0.2s should expire after 2 ticks
        keys: list[bytes | None] = [None] * 100
        with patch("rew_to_musway.prompt._read_key", _make_key_sequence(keys)):
            result = await timed_prompt("Test", 0.2)
        assert result == TimedPromptResult.TIMER_EXPIRED


class TestTimedPromptCancel:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_live", "_no_drain")
    async def test_backspace_cancels_then_enter(self) -> None:
        keys: list[bytes | None] = [_KEY_BACKSPACE, None, None, _KEY_ENTER]
        with patch("rew_to_musway.prompt._read_key", _make_key_sequence(keys)):
            result = await timed_prompt("Test", 0.2)
        # Timer would have expired at 0.2s but backspace cancelled it
        assert result == TimedPromptResult.ENTER

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_no_live", "_no_drain")
    async def test_backspace_prevents_expiry(self) -> None:
        # Backspace, then many Nones — timer should NOT expire
        keys: list[bytes | None] = [_KEY_BACKSPACE, *([None] * 50), _KEY_ENTER]
        with patch("rew_to_musway.prompt._read_key", _make_key_sequence(keys)):
            result = await timed_prompt("Test", 0.2)
        assert result == TimedPromptResult.ENTER
