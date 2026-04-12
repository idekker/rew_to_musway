"""
_client.py — REWClient, the top-level async client for the REW API.

Usage::

    import asyncio
    from aiorew import REWClient, RTAConfiguration

    async def main():
        async with REWClient(host="localhost", port=4735) as rew:
            # Configure and run a 100-average RTA measurement
            await rew.rta.set_configuration(RTAConfiguration(
                maxAverages=100,
                stopAt=True,
                stopAtValue=100,
                stopGeneratorWithRTA=True,
            ))
            await rew.generator.set_signal("pinknoise")
            await rew.generator.play()
            await rew.rta.start()
            await rew.rta.wait_until_stopped()

            # Save and get the new measurement UUID in one call
            uuid = await rew.save_rta()  # returns UUID

            # Work with the measurement
            fr = await rew.measurements.get_frequency_response(uuid, smoothing="1/12")
            print(fr.magnitude)

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio

from typing import Any, Optional
from uuid import UUID

from ._audio import AudioClient
from ._eq import EQDefaultsClient
from ._generator import GeneratorClient
from ._http import _HTTPClient
from ._input_levels import InputLevelsClient
from ._measurements import MeasurementsClient
from ._rta import RTAClient
from ._spl_meter import SPLMeterClient


class REWClient:
    """
    Async client for the REW (Room EQ Wizard) REST API.

    All network I/O is async (asyncio + httpx).  Use as an async context
    manager to ensure the underlying HTTP connection is properly closed::

        async with REWClient() as rew:
            measurements = await rew.measurements.list()

    Or manage the lifecycle manually::

        rew = REWClient()
        await rew.connect()
        ...
        await rew.close()

    Parameters
    ----------
    host:
        Hostname or IP address of the REW API server (default: 'localhost').
    port:
        Port number of the REW API server (default: 4735).
    """

    def __init__(self, host: str = "localhost", port: int = 4735) -> None:
        self._http = _HTTPClient(host=host, port=port)

        # Sub-clients — each exposes a focused slice of the API
        self.audio = AudioClient(self._http)
        self.input_levels = InputLevelsClient(self._http)
        self.measurements = MeasurementsClient(self._http)
        self.eq = EQDefaultsClient(self._http)
        self.generator = GeneratorClient(self._http)
        self.spl_meter = SPLMeterClient(self._http)
        self.rta = RTAClient(self._http)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the underlying HTTP connection pool."""
        await self._http.start()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.close()

    async def __aenter__(self) -> "REWClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def save_rta(self) -> UUID:
        """
        Save the current RTA data as a new measurement and return its UUID.

        This is a convenience method that combines two separate API concerns:

        1. ``rta.save()`` — issues ``POST /rta/command {"command": "Save current"}``,
           which creates a new measurement and selects it.
        2. ``measurements.get_selected_uuid()`` — reads the UUID of the
           measurement that REW selected after the save.

        The assumption that REW selects the newly saved measurement is
        documented here explicitly.  If you need finer control (e.g. to
        observe the measurement list before and after), call the two methods
        separately.

        Returns
        -------
        UUID
            UUID of the newly saved measurement.
        """
        await self.rta.save()
        await asyncio.sleep(1)
        return await self.measurements.get_selected_uuid()

    # ------------------------------------------------------------------
    # Application-level helpers
    # ------------------------------------------------------------------

    async def get_version(self) -> str:
        """Return the REW application version string."""
        data = await self._http.get("/application")
        if isinstance(data, dict):
            return data.get("version", str(data))
        return str(data)

    async def set_blocking(self, enabled: bool) -> None:
        """
        Enable or disable REW's blocking mode.

        When blocking is enabled, the API waits up to 10 seconds for commands
        to complete before responding.  Polling (the default approach used by
        this library) is generally safer for long-running operations.
        """
        await self._http.post("/application/blocking", enabled)

    async def set_inhibit_graph_updates(self, enabled: bool) -> None:
        """
        Inhibit REW graph updates.

        Useful when batch-modifying or deleting measurements to prevent REW
        from attempting to redraw graphs with partial data.
        """
        await self._http.post("/application/inhibit-graph-updates", enabled)

    async def shutdown(self) -> None:
        """
        Shut down REW.

        Only meaningful when REW is running without a GUI (``-nogui`` flag).
        """
        await self._http.post("/application/command", {"command": "Shutdown"})
