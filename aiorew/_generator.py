"""
_generator.py — GeneratorClient for REW signal generator control.

Covers /generator/* endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._http import _HTTPClient
from ._models import GeneratorStatus, GeneratorSignal


class GeneratorClient:
    """
    Control the REW signal generator: signal selection, level, and play/stop.

    Instantiated by REWClient — do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_status(self) -> GeneratorStatus:
        """Return the current generator status (enabled, playing, signal, level)."""
        data = await self._http.get("/generator/status")
        return GeneratorStatus.from_dict(data)

    # ------------------------------------------------------------------
    # Signal selection
    # ------------------------------------------------------------------

    async def get_signals(self) -> List[str]:
        """Return the list of available signal names."""
        return await self._http.get("/generator/signals")

    async def get_signal(self) -> GeneratorSignal:
        """Return the currently selected signal name."""
        d = await self._http.get("/generator/signal")
        return GeneratorSignal(d["signal"])

    async def set_signal(self, signal_name: GeneratorSignal) -> None:
        """
        Select a signal.
        """
        await self._http.post("/generator/signal", {"signal": signal_name.value})

    # ------------------------------------------------------------------
    # Signal configuration
    # ------------------------------------------------------------------

    async def get_signal_configuration(self) -> Dict[str, Any]:
        """
        Return the configuration for the currently selected signal.

        The shape of the returned dict depends on the signal type.
        """
        return await self._http.get("/generator/signal/configuration")

    async def set_signal_configuration(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration for the currently selected signal.

        Pass only the fields you want to change — both POST and PUT accept
        partial objects.
        """
        await self._http.post("/generator/signal/configuration", config)

    async def get_signal_commands(self) -> List[str]:
        """Return the commands available for the currently selected signal."""
        return await self._http.get("/generator/signal/commands")

    async def send_signal_command(self, command: str) -> None:
        """Send a command to the currently selected signal (e.g. 'Next frequency')."""
        await self._http.post("/generator/signal/command", {"command": command})

    # ------------------------------------------------------------------
    # Level
    # ------------------------------------------------------------------

    async def get_level(self) -> float:
        """Return the current output level in dBFS.

        API returns {"value": <float>, "unit": "dBFS"} — the value is extracted.
        """
        d = await self._http.get("/generator/level")
        return float(d["value"])

    async def set_level(self, level: float, unit: str = "dBFS") -> None:
        """
        Set the generator output level.

        Parameters
        ----------
        level:
            Numeric level value.
        unit:
            Unit string (e.g. 'dBFS', 'dBV'). Defaults to 'dBFS'.
        """
        await self._http.post("/generator/level", {"value": level, "unit": unit})

    async def get_level_units(self) -> List[str]:
        """Return the available unit strings for generator level."""
        return await self._http.get("/generator/level/units")

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    async def get_frequency(self) -> Optional[float]:
        """Return the current generator frequency in Hz, or None for non-tone signals.

        API returns {"unit": "Hz"} with no "value" key when the current signal
        is not a tone (e.g. pink noise) — returns None in that case.
        """
        d = await self._http.get("/generator/frequency")
        if isinstance(d, dict):
            val = d.get("value")
            return float(val) if val is not None and isinstance(val, str) else None
        # bare scalar (future-proofing)
        return float(d) if d is not None else None

    async def set_frequency(self, frequency: float) -> None:
        """Set the generator frequency in Hz."""
        await self._http.post("/generator/frequency", frequency)

    # ------------------------------------------------------------------
    # Play / stop
    # ------------------------------------------------------------------

    async def play(self) -> None:
        """Start the generator."""
        await self._http.post("/generator/command", {"command": "Play"})

    async def stop(self) -> None:
        """Stop the generator."""
        await self._http.post("/generator/command", {"command": "Stop"})

    async def get_commands(self) -> List[str]:
        """Return the available generator start/stop command names."""
        return await self._http.get("/generator/commands")
