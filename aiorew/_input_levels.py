"""
_input_levels.py — InputLevelsClient for REW input level monitoring.

Covers /input-levels/* endpoints.
"""

from __future__ import annotations

from ._http import _HTTPClient
from ._models import InputLevels


class InputLevelsClient:
    """
    Start/stop REW input level monitoring and read the latest levels.

    Instantiated by REWClient — do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    async def start_monitoring(self) -> None:
        """Start input level monitoring."""
        await self._http.post("/input-levels/command", {"command": "Start"})

    async def stop_monitoring(self) -> None:
        """Stop input level monitoring."""
        await self._http.post("/input-levels/command", {"command": "Stop"})

    async def get_last_levels(self) -> InputLevels:
        """
        Return the most recent input levels snapshot.

        Monitoring must be active (call start_monitoring() first) for values
        to be meaningful.  Returns an InputLevels with rms and peak arrays
        (one value per channel) and the time span of the measurement.
        """
        data = await self._http.get("/input-levels/last-levels")
        return InputLevels.from_dict(data)

    async def get_units(self) -> list:
        """Return the available unit strings for input levels (e.g. 'dBFS', 'dBV')."""
        return await self._http.get("/input-levels/units")
