"""_rta.py - RTAClient for REW Real-Time Analyzer control.

Covers /rta/* endpoints:
  - Start / stop commands
  - Configuration (read/write)
  - Status (enabled, running) with polling
  - Captured RTA data as FrequencyResponse (numpy arrays)
  - Save current RTA data as a measurement
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ._models import FrequencyResponse, RTAConfiguration, RTAStatus

if TYPE_CHECKING:
    from ._http import _HTTPClient


class RTAClient:
    """Control the REW Real-Time Analyzer.

    Instantiated by REWClient - do not construct directly.

    Typical usage::

        await rew.rta.set_configuration(RTAConfiguration(
            maxAverages=100,
            stopAt=True,
            stopAtValue=100,
            stopGeneratorWithRTA=True,
        ))
        await rew.rta.start()
        await rew.rta.wait_until_stopped()
        data = await rew.rta.get_captured_data()
        # Save and retrieve UUID via REWClient.save_rta()
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the RTA."""
        await self._http.post("/rta/command", {"command": "Start"})

    async def stop(self) -> None:
        """Stop the RTA."""
        await self._http.post("/rta/command", {"command": "Stop"})

    async def save(self) -> None:
        """Save the current RTA data as a new measurement.

        This method returns None - to obtain the UUID of the saved measurement
        use REWClient.save_rta(), which calls this method then queries the
        selected-measurement UUID.
        """
        await self._http.post("/rta/command", {"command": "Save current"})

    async def get_commands(self) -> list[str]:
        """Return the list of available RTA command names."""
        return cast("list", await self._http.get("/rta/commands"))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_status(self) -> RTAStatus:
        """Return the current RTA status (enabled, running)."""
        data = await self._http.get("/rta/status")
        return RTAStatus.from_dict(cast("dict", data))

    async def wait_until_stopped(
        self,
        poll_interval: float = 0.5,
        timeout: float | None = None,
    ) -> None:
        """Block until the RTA stops running.

        First waits for the RTA to report running=True (it may take a moment
        to start after the Start command), then polls until running=False.
        Both phases use the same *poll_interval* and share the *timeout* budget.

        Parameters
        ----------
        poll_interval:
            Seconds between status polls (default 0.5).
        timeout:
            Optional maximum seconds to wait before raising TimeoutError.

        """

        async def _check() -> RTAStatus:
            return await self.get_status()

        # Phase 1: wait for running=True (startup lag)
        await self._http.poll_until(
            _check,
            condition=lambda s: s.running,
            poll_interval=poll_interval,
            timeout=timeout,
        )

        # Phase 2: wait for running=False (measurement complete)
        await self._http.poll_until(
            _check,
            condition=lambda s: not s.running,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    async def get_configuration(self) -> RTAConfiguration:
        """Return the current RTA configuration."""
        data = await self._http.get("/rta/configuration")
        return RTAConfiguration.from_dict(cast("dict", data))

    async def set_configuration(self, config: RTAConfiguration) -> None:
        """Update the RTA configuration.

        The API requires a complete configuration object - partial objects are
        rejected with HTTP 400.  This method reads the current configuration
        first, merges the non-None fields from *config* into it, then POSTs
        the merged result.
        """
        current = cast("dict", await self._http.get("/rta/configuration"))
        current.update(config.to_dict())
        await self._http.post("/rta/configuration", current)

    # ------------------------------------------------------------------
    # Captured data
    # ------------------------------------------------------------------

    async def get_captured_data(
        self,
        unit: str | None = None,
        index: int | None = None,
    ) -> FrequencyResponse:
        """Return the current RTA RMS-averaged captured data as a FrequencyResponse.

        magnitude is a numpy array; phase is absent for RTA data.

        Parameters
        ----------
        unit:
            Magnitude unit (e.g. 'SPL', 'dBFS'). Defaults to SPL.
        index:
            Input index for multi-input setups (default: RMS average of all
            inputs).

        """
        data = await self._http.get("/rta/captured-data", unit=unit, index=index)
        return FrequencyResponse.from_dict(cast("dict", data))

    async def get_captured_peak_data(
        self,
        unit: str | None = None,
        index: int | None = None,
    ) -> FrequencyResponse:
        """Return the current RTA peak captured data as a FrequencyResponse.

        Parameters
        ----------
        unit:
            Magnitude unit (e.g. 'SPL', 'dBFS'). Defaults to SPL.
        index:
            Input index for multi-input setups.

        """
        data = await self._http.get("/rta/captured-peak-data", unit=unit, index=index)
        return FrequencyResponse.from_dict(cast("dict", data))
