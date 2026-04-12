"""
_spl_meter.py — SPLMeterClient for REW SPL meter control.

Covers /spl-meter/{id}/* endpoints.

Each meter is identified by a numeric ID (1-indexed). Without a Pro upgrade
only meter 1 is available; with Pro upgrade up to four meters are available.
"""

from __future__ import annotations

from typing import List

from ._http import _HTTPClient
from ._models import SPLMeterConfiguration, SPLValues


class SPLMeterClient:
    """
    Open, configure, run, and read REW SPL meters.

    Instantiated by REWClient — do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # Lifecycle commands
    # ------------------------------------------------------------------

    async def open(self, meter_id: int = 1) -> None:
        """Open SPL meter *meter_id*."""
        await self._http.post(f"/spl-meter/{meter_id}/command", {"command": "Open"})

    async def close(self, meter_id: int = 1) -> None:
        """Close SPL meter *meter_id*."""
        await self._http.post(f"/spl-meter/{meter_id}/command", {"command": "Close"})

    async def start(self, meter_id: int = 1) -> None:
        """Start SPL meter *meter_id*. The meter must be open first."""
        await self._http.post(f"/spl-meter/{meter_id}/command", {"command": "Start"})

    async def stop(self, meter_id: int = 1) -> None:
        """Stop SPL meter *meter_id*."""
        await self._http.post(f"/spl-meter/{meter_id}/command", {"command": "Stop"})

    async def reset(self, meter_id: int = 1) -> None:
        """Reset SPL meter *meter_id* (clears accumulated Leq/SEL)."""
        await self._http.post(f"/spl-meter/{meter_id}/command", {"command": "Reset"})

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    async def get_configuration(self, meter_id: int = 1) -> SPLMeterConfiguration:
        """Return the current configuration of SPL meter *meter_id*."""
        data = await self._http.get(f"/spl-meter/{meter_id}/configuration")
        return SPLMeterConfiguration.from_dict(data)

    async def configure(
        self, meter_id: int = 1, config: SPLMeterConfiguration = None
    ) -> None:
        """
        Apply *config* to SPL meter *meter_id*.

        Parameters
        ----------
        meter_id:
            Target meter (default 1).
        config:
            Configuration to apply. A default SPLMeterConfiguration is used
            when None is passed.
        """
        if config is None:
            config = SPLMeterConfiguration()
        await self._http.post(f"/spl-meter/{meter_id}/configuration", config.to_dict())

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    async def calibrate(self, reference_spl: float, meter_id: int = 1) -> None:
        """
        Calibrate SPL meter *meter_id* to a known reference level.

        The meter must be running before calibrating.

        Parameters
        ----------
        reference_spl:
            The actual SPL in dB at the microphone (e.g. 94.0 for a pistonphone).
        meter_id:
            Target meter (default 1).
        """
        await self._http.post(
            f"/spl-meter/{meter_id}/command",
            {"command": "Calibrate", "parameters": [str(reference_spl)]},
        )

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    async def get_levels(self, meter_id: int = 1) -> SPLValues:
        """
        Return the last SPL reading from meter *meter_id*.

        For live monitoring, subscribe to the levels endpoint instead.
        """
        data = await self._http.get(f"/spl-meter/{meter_id}/levels")
        return SPLValues.from_dict(data)

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    async def get_modes(self) -> List[str]:
        """Return available SPL meter modes (e.g. 'SPL', 'Leq')."""
        return await self._http.get("/spl-meter/modes")

    async def get_weightings(self) -> List[str]:
        """Return available SPL weightings (e.g. 'A', 'C', 'Z')."""
        return await self._http.get("/spl-meter/weightings")

    async def get_filters(self) -> List[str]:
        """Return available SPL time-weighting filters (e.g. 'Fast', 'Slow')."""
        return await self._http.get("/spl-meter/filters")
