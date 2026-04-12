"""
_measurements.py — MeasurementsClient for REW measurement access and processing.

Covers /measurements/* endpoints:
  - List, get, delete measurements
  - Save individual or all measurements
  - Selected measurement UUID
  - Frequency response, group delay, impulse response, IR windows
  - Name / notes changes
  - Filters (read/write)
  - Equaliser selection
  - Target settings, target level, room curve settings
  - Target response, EQ predicted response
  - Per-measurement commands (Smooth, Scale IR, Add SPL offset, etc.)
  - EQ commands (Match target, Optimise gains, etc.) — with polling
  - Process-measurements (Align SPL, Arithmetic, etc.) — with polling
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._http import _HTTPClient
from ._models import (
    Equaliser,
    FilterSetting,
    FrequencyResponse,
    ImpulseResponse,
    IRWindows,
    MeasurementSummary,
    ProcessResult,
    RoomCurveSettings,
    TargetSettings,
)


class MeasurementsClient:
    """
    Access and manipulate REW measurements.

    All methods that operate on a specific measurement accept *uuid* as the
    first argument.  Always use UUIDs — indices change when measurements are
    added, removed, or grouped.

    Instantiated by REWClient — do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # List / get / delete
    # ------------------------------------------------------------------

    async def list(self) -> List[MeasurementSummary]:
        """
        Return all current measurements as a list of MeasurementSummary objects.

        The API returns a dict keyed by 1-based index string; this method
        converts it to a plain list ordered by index.
        """
        data = await self._http.get("/measurements")
        if not data:
            return []
        return [MeasurementSummary.from_dict(v) for v in data.values()]

    async def get(self, uuid: str) -> MeasurementSummary:
        """Return the summary for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}")
        return MeasurementSummary.from_dict(data)

    async def delete(self, uuid: str) -> None:
        """Delete measurement *uuid*. No confirmation is requested."""
        await self._http.delete(f"/measurements/{uuid}")

    async def delete_all(self) -> None:
        """Delete all measurements. No confirmation is requested."""
        await self._http.delete("/measurements")

    # ------------------------------------------------------------------
    # Selected measurement
    # ------------------------------------------------------------------

    async def get_selected_uuid(self) -> str:
        """Return the UUID of the currently selected measurement."""
        val = await self._http.get("/measurements/selected-uuid")
        return str(val)

    async def set_selected_uuid(self, uuid: str) -> None:
        """Select a measurement by UUID."""
        await self._http.post("/measurements/selected-uuid", uuid)

    # ------------------------------------------------------------------
    # Name / notes
    # ------------------------------------------------------------------

    async def set_title(self, uuid: str, title: str) -> None:
        """Rename measurement *uuid*."""
        await self._http.put(f"/measurements/{uuid}", {"title": title})

    async def set_notes(self, uuid: str, notes: str) -> None:
        """Set the notes for measurement *uuid*."""
        await self._http.put(f"/measurements/{uuid}", {"notes": notes})

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    async def save(self, uuid: str, path: str) -> None:
        """
        Save measurement *uuid* to *path*.

        Uses the per-measurement "Save" command.
        """
        await self._http.post(
            f"/measurements/{uuid}/command",
            {"command": "Save", "parameters": {"path": path}},
        )

    async def save_all(self, path: str, note: Optional[str] = None) -> None:
        """
        Save all measurements to *path* (a .mdat file).

        Parameters
        ----------
        path:
            Destination file path (forward slashes recommended).
        note:
            Optional note to embed in the file.
        """
        params: List[str] = [path]
        if note is not None:
            params.append(note)
        await self._http.post(
            "/measurements/command",
            {"command": "Save all", "parameters": params},
        )

    async def load(self, *paths: str) -> None:
        """
        Load one or more measurement files (.mdat).

        Parameters
        ----------
        paths:
            One or more file paths to load.
        """
        await self._http.post(
            "/measurements/command",
            {"command": "Load", "parameters": list(paths)},
        )

    # ------------------------------------------------------------------
    # Frequency response
    # ------------------------------------------------------------------

    async def get_frequency_response(
        self,
        uuid: str,
        *,
        unit: Optional[str] = None,
        smoothing: Optional[str] = None,
        ppo: Optional[int] = None,
    ) -> FrequencyResponse:
        """
        Return the frequency response for measurement *uuid*.

        Parameters
        ----------
        uuid:
            Measurement UUID.
        unit:
            Magnitude unit (e.g. 'SPL', 'dBFS'). Defaults to SPL.
        smoothing:
            Smoothing amount (e.g. '1/12', '1/3', 'None').
        ppo:
            Force log-spaced output at this PPO (e.g. 96).

        Returns
        -------
        FrequencyResponse with numpy magnitude (and phase when available).
        """
        data = await self._http.get(
            f"/measurements/{uuid}/frequency-response",
            unit=unit,
            smoothing=smoothing,
            ppo=ppo,
        )
        return FrequencyResponse.from_dict(data)

    async def get_group_delay(
        self,
        uuid: str,
        *,
        unit: Optional[str] = None,
        smoothing: Optional[str] = None,
        ppo: Optional[int] = None,
    ) -> FrequencyResponse:
        """
        Return the group delay for measurement *uuid*.

        The magnitude field contains group delay values in seconds.
        """
        data = await self._http.get(
            f"/measurements/{uuid}/group-delay",
            unit=unit,
            smoothing=smoothing,
            ppo=ppo,
        )
        return FrequencyResponse.from_dict(data)

    async def get_impulse_response(
        self,
        uuid: str,
        *,
        unit: Optional[str] = None,
        windowed: Optional[bool] = None,
        normalised: Optional[bool] = None,
    ) -> ImpulseResponse:
        """
        Return the impulse response for measurement *uuid*.

        Raises REWError (HTTP 400) for RTA-derived measurements, which have
        no impulse response.

        Parameters
        ----------
        unit:
            Unit for the response data (default: Percent).
        windowed:
            If True, return only the windowed portion.
        normalised:
            If False, return non-normalised data.
        """
        data = await self._http.get(
            f"/measurements/{uuid}/impulse-response",
            unit=unit,
            windowed=windowed,
            normalised=normalised,
        )
        return ImpulseResponse.from_dict(data)

    # ------------------------------------------------------------------
    # IR windows
    # ------------------------------------------------------------------

    async def get_ir_windows(self, uuid: str) -> IRWindows:
        """
        Return the IR window settings for measurement *uuid*.

        Raises REWError (HTTP 400) for RTA-derived measurements.
        """
        data = await self._http.get(f"/measurements/{uuid}/ir-windows")
        return IRWindows.from_dict(data)

    async def set_ir_windows(self, uuid: str, windows: IRWindows) -> None:
        """Update the IR window settings for measurement *uuid*."""
        await self._http.put(f"/measurements/{uuid}/ir-windows", windows.to_dict())

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    async def get_filters(self, uuid: str) -> List[FilterSetting]:
        """Return the EQ filter list for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/filters")
        return [FilterSetting.from_dict(f) for f in data]

    async def set_filters(self, uuid: str, filters: List[FilterSetting]) -> None:
        """
        Write EQ filters for measurement *uuid*.

        Pass the complete filter list (including unchanged slots).
        """
        await self._http.put(
            f"/measurements/{uuid}/filters",
            [f.to_dict() for f in filters],
        )

    # ------------------------------------------------------------------
    # Equaliser
    # ------------------------------------------------------------------

    async def get_equaliser(self, uuid: str) -> Equaliser:
        """Return the equaliser selection for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/equaliser")
        return Equaliser.from_dict(data)

    async def set_equaliser(self, uuid: str, equaliser: Equaliser) -> None:
        """Set the equaliser for measurement *uuid*."""
        await self._http.post(f"/measurements/{uuid}/equaliser", equaliser.to_dict())

    # ------------------------------------------------------------------
    # Target settings / level / room curve
    # ------------------------------------------------------------------

    async def get_target_settings(self, uuid: str) -> TargetSettings:
        """Return the EQ target shape settings for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/target-settings")
        return TargetSettings.from_dict(data)

    async def set_target_settings(self, uuid: str, settings: TargetSettings) -> None:
        """Update the EQ target shape settings for measurement *uuid*."""
        await self._http.post(f"/measurements/{uuid}/target-settings", settings.to_dict())

    async def get_target_level(self, uuid: str) -> float:
        """Return the EQ target level (dB) for measurement *uuid*."""
        val = await self._http.get(f"/measurements/{uuid}/target-level")
        return float(val)

    async def set_target_level(self, uuid: str, level: float) -> None:
        """Set the EQ target level (dB) for measurement *uuid*."""
        await self._http.post(f"/measurements/{uuid}/target-level", level)

    async def get_room_curve_settings(self, uuid: str) -> RoomCurveSettings:
        """Return the room curve settings for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/room-curve-settings")
        return RoomCurveSettings.from_dict(data)

    async def set_room_curve_settings(self, uuid: str, settings: RoomCurveSettings) -> None:
        """Update the room curve settings for measurement *uuid*."""
        await self._http.post(
            f"/measurements/{uuid}/room-curve-settings", settings.to_dict()
        )

    # ------------------------------------------------------------------
    # Target / EQ predicted responses
    # ------------------------------------------------------------------

    async def get_target_response(
        self, uuid: str, *, ppo: Optional[int] = None
    ) -> FrequencyResponse:
        """
        Return the EQ target response for measurement *uuid*.

        The magnitude field contains SPL values; phase is absent.
        """
        data = await self._http.get(f"/measurements/{uuid}/target-response", ppo=ppo)
        return FrequencyResponse.from_dict(data)

    async def get_eq_frequency_response(
        self, uuid: str, *, unit: Optional[str] = None, ppo: Optional[int] = None
    ) -> FrequencyResponse:
        """Return the predicted post-EQ frequency response for measurement *uuid*."""
        data = await self._http.get(
            f"/measurements/{uuid}/eq/frequency-response", unit=unit, ppo=ppo
        )
        return FrequencyResponse.from_dict(data)

    async def get_eq_group_delay(self, uuid: str) -> FrequencyResponse:
        """Return the predicted post-EQ group delay for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/eq/group-delay")
        return FrequencyResponse.from_dict(data)

    async def get_eq_impulse_response(self, uuid: str) -> ImpulseResponse:
        """Return the predicted post-EQ impulse response for measurement *uuid*."""
        data = await self._http.get(f"/measurements/{uuid}/eq/impulse-response")
        return ImpulseResponse.from_dict(data)

    # ------------------------------------------------------------------
    # Per-measurement commands
    # ------------------------------------------------------------------

    async def get_commands(self, uuid: str) -> List[str]:
        """Return the list of commands available for measurement *uuid*."""
        return await self._http.get(f"/measurements/{uuid}/commands")

    async def run_command(
        self,
        uuid: str,
        command: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Issue a single-measurement command (e.g. 'Smooth', 'Scale IR', 'Add SPL offset').

        Parameters
        ----------
        uuid:
            Measurement UUID.
        command:
            Command name. Available names: get_commands(uuid).
        parameters:
            Optional dict of command parameters (varies by command).
        """
        body: Dict[str, Any] = {"command": command}
        if parameters:
            body["parameters"] = parameters
        await self._http.post(f"/measurements/{uuid}/command", body)

    # ------------------------------------------------------------------
    # EQ commands (per-measurement, with polling)
    # ------------------------------------------------------------------

    async def get_eq_commands(self) -> List[str]:
        """Return the list of EQ commands (global, not per-measurement)."""
        return await self._http.get("/measurements/eq/commands")

    async def run_eq_command(
        self,
        uuid: str,
        command: str,
        *,
        poll_interval: float = 0.5,
        timeout: Optional[float] = None,
    ) -> ProcessResult:
        """
        Issue an EQ command for measurement *uuid* and poll until it completes.

        Commands include: 'Match target', 'Optimise gains', 'Calculate target
        level', 'Generate predicted measurement', etc.

        Parameters
        ----------
        uuid:
            Measurement UUID.
        command:
            EQ command name. Available: get_eq_commands().
        poll_interval:
            Seconds between status polls (default 0.5).
        timeout:
            Optional maximum seconds to wait before raising TimeoutError.

        Returns
        -------
        ProcessResult with the command outcome.
        """
        await self._http.post(f"/measurements/{uuid}/eq/command", {"command": command})

        async def _check() -> Any:
            return await self._http.get("/measurements/process-result")

        result_data = await self._http.poll_until(
            _check,
            condition=lambda d: isinstance(d, dict) and d.get("message") is not None,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        return ProcessResult.from_dict(result_data)

    # ------------------------------------------------------------------
    # Process measurements (multi-measurement, with polling)
    # ------------------------------------------------------------------

    async def get_process_commands(self) -> List[str]:
        """Return the available process-measurements command names."""
        return await self._http.get("/measurements/process-commands")

    async def process_measurements(
        self,
        uuids: List[str],
        process_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        poll_interval: float = 0.5,
        timeout: Optional[float] = None,
    ) -> ProcessResult:
        """
        Run a multi-measurement processing command and poll until complete.

        Parameters
        ----------
        uuids:
            List of measurement UUIDs to process.
        process_name:
            Process command name (e.g. 'Align SPL', 'Arithmetic', 'dB average').
            Available: get_process_commands().
        parameters:
            Optional dict of process-specific parameters.
        poll_interval:
            Seconds between status polls (default 0.5).
        timeout:
            Optional maximum seconds to wait before raising TimeoutError.

        Returns
        -------
        ProcessResult with the process outcome.

        Examples
        --------
        Align SPL to 85 dB at 1 kHz::

            await measurements.process_measurements(
                [uuid_a, uuid_b],
                "Align SPL",
                {"targetdB": "85.0", "frequencyHz": "1000", "spanOctaves": 2},
            )

        Arithmetic A * B::

            await measurements.process_measurements(
                [uuid_a, uuid_b],
                "Arithmetic",
                {"function": "A * B"},
            )
        """
        body: Dict[str, Any] = {
            "processName": process_name,
            "measurementIndices": uuids,
        }
        if parameters:
            body["parameters"] = parameters

        await self._http.post("/measurements/process-measurements", body)

        async def _check() -> Any:
            return await self._http.get("/measurements/process-result")

        result_data = await self._http.poll_until(
            _check,
            condition=lambda d: isinstance(d, dict) and d.get("message") is not None,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        return ProcessResult.from_dict(result_data)
