"""Tests for verification measurement flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rew_to_musway.calibration._verification import save_session

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import AsyncMock


class TestSaveSession:
    @pytest.mark.asyncio
    async def test_saves_mdat(self, mock_rew: AsyncMock, tmp_path: Path) -> None:
        path = await save_session(mock_rew, tmp_path)
        assert path == tmp_path / "calibration.mdat"
        mock_rew.save_all_measurements.assert_called_once_with(
            str(tmp_path / "calibration.mdat")
        )
