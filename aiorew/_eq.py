"""
_eq.py - EQDefaultsClient for REW global EQ default settings.

Covers /eq/* endpoints:
  - Equaliser list / manufacturers
  - Default equaliser
  - Default target settings and target level
  - Default room curve settings
  - House curve file
  - Match-target settings
  - Global EQ commands
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._http import _HTTPClient
from ._models import Equaliser, MatchTargetSettings, RoomCurveSettings, TargetSettings


class EQDefaultsClient:
    """
    Read and write REW's global EQ defaults (applied to new measurements).

    These settings are distinct from per-measurement settings - see
    MeasurementsClient for per-measurement EQ control.

    Instantiated by REWClient - do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # Equaliser list
    # ------------------------------------------------------------------

    async def get_equalisers(
        self, manufacturer: Optional[str] = None
    ) -> List[Equaliser]:
        """
        Return the list of available equalisers.

        Parameters
        ----------
        manufacturer:
            Filter by manufacturer name (e.g. 'MiniDSP', 'Musway').
            Returns all equalisers when omitted.
        """
        data = await self._http.get(
            "/eq/equalisers",
            manufacturer=manufacturer,
        )
        # API returns a plain list (confirmed via httpx against live REW)
        return [Equaliser.from_dict(e) for e in data]

    async def get_manufacturers(self) -> List[str]:
        """Return the list of equaliser manufacturer names."""
        return await self._http.get("/eq/manufacturers")

    # ------------------------------------------------------------------
    # Default equaliser
    # ------------------------------------------------------------------

    async def get_default_equaliser(self) -> Equaliser:
        """Return the default equaliser applied to new measurements."""
        data = await self._http.get("/eq/default-equaliser")
        return Equaliser.from_dict(data)

    async def set_default_equaliser(self, equaliser: Equaliser) -> None:
        """Set the default equaliser for new measurements."""
        await self._http.post("/eq/default-equaliser", equaliser.to_dict())

    # ------------------------------------------------------------------
    # Default target settings
    # ------------------------------------------------------------------

    async def get_default_target_settings(self) -> TargetSettings:
        """Return the default EQ target shape settings."""
        data = await self._http.get("/eq/default-target-settings")
        return TargetSettings.from_dict(data)

    async def set_default_target_settings(self, settings: TargetSettings) -> None:
        """Update the default EQ target shape settings."""
        await self._http.post("/eq/default-target-settings", settings.to_dict())

    # ------------------------------------------------------------------
    # Default target level
    # ------------------------------------------------------------------

    async def get_default_target_level(self) -> float:
        """Return the default EQ target level in dB."""
        val = await self._http.get("/eq/default-target-level")
        return float(val)

    async def set_default_target_level(self, level: float) -> None:
        """Set the default EQ target level in dB."""
        await self._http.post("/eq/default-target-level", level)

    # ------------------------------------------------------------------
    # Default room curve settings
    # ------------------------------------------------------------------

    async def get_default_room_curve_settings(self) -> RoomCurveSettings:
        """Return the default room curve settings."""
        data = await self._http.get("/eq/default-room-curve-settings")
        return RoomCurveSettings.from_dict(data)

    async def set_default_room_curve_settings(
        self, settings: RoomCurveSettings
    ) -> None:
        """Update the default room curve settings."""
        await self._http.post("/eq/default-room-curve-settings", settings.to_dict())

    # ------------------------------------------------------------------
    # House curve
    # ------------------------------------------------------------------

    async def get_house_curve(self) -> str:
        """Return the path to the house curve file (empty string if none set)."""
        val = await self._http.get("/eq/house-curve")
        return str(val) if val is not None else ""

    async def set_house_curve(
        self, path: str, *, log_interpolation: bool = True
    ) -> None:
        """
        Set the house curve file path.

        Parameters
        ----------
        path:
            Path to the house curve file (forward slashes recommended).
        log_interpolation:
            Whether to use log interpolation when reading the file.
            Must be set before the file path - this method handles the order.
        """
        await self._http.post("/eq/house-curve-log-interpolation", log_interpolation)
        await self._http.post("/eq/house-curve", path)

    async def delete_house_curve(self) -> None:
        """Remove the house curve (set path to empty string)."""
        await self._http.post("/eq/house-curve", "")

    # ------------------------------------------------------------------
    # Match-target settings
    # ------------------------------------------------------------------

    async def get_match_target_settings(self) -> MatchTargetSettings:
        """Return the settings used when matching a measurement response to its target."""
        data = await self._http.get("/eq/match-target-settings")
        return MatchTargetSettings.from_dict(data)

    async def set_match_target_settings(self, settings: MatchTargetSettings) -> None:
        """Update the match-target settings."""
        await self._http.post("/eq/match-target-settings", settings.to_dict())

    # ------------------------------------------------------------------
    # Global EQ commands
    # ------------------------------------------------------------------

    async def get_commands(self) -> List[str]:
        """Return the list of global EQ command names."""
        return await self._http.get("/eq/commands")

    async def _run_command(
        self, command: str, parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Issue a global EQ command (e.g. 'Match target' across all measurements).

        Parameters
        ----------
        command:
            Command name. Available: get_commands().
        parameters:
            Optional parameters dict.
        """
        body: Dict[str, Any] = {"command": command}
        if parameters:
            body["parameters"] = parameters
        await self._http.post("/eq/command", body)
