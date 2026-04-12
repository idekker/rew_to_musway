"""
_audio.py - AudioClient for REW audio device and calibration control.

Covers:
  - Driver selection (/audio/driver)
  - Sample rate (/audio/samplerate)
  - Java audio settings (/audio/java/*)
  - ASIO audio settings (/audio/asio/*)
  - Input / output calibration (/audio/input-cal, /audio/output-cal)

Response-shape notes (confirmed against live API):
  - /audio/driver          -> {"driver": <str>}
  - /audio/samplerate      -> {"value": <float>, "unit": "Hz"}
  - /audio/samplerates     -> [{"value": <float>, "unit": "Hz"}, ...]
  - /audio/java/input-device  -> {"device": <str>}
  - /audio/java/output-device -> {"device": <str>}
  - /audio/java/input      -> {"input": <str>}   (assumed; unwrap "input" key)
  - /audio/java/output     -> {"output": <str>}  (assumed; unwrap "output" key)
  - /audio/java/input-channel  -> {"channel": <int>}
  - /audio/java/ref-input-channel -> {"channel": <int>}
  - /audio/java/output-channel -> {"channel": <str>}   (may be "L+R")
  - /audio/java/num-input-channels -> {"value": <int>} (assumed)
  - /audio/asio/device     -> {"device": <str>}
  - /audio/asio/input      -> {"input": <str>}   (assumed)
  - /audio/asio/output     -> {"output": <str>}  (assumed)
  - /audio/java/input-devices  -> plain list of str
  - /audio/java/output-devices -> plain list of str
  - /audio/java/inputs     -> plain list of str
  - /audio/java/outputs    -> plain list of str
  - /audio/asio/devices    -> plain list of str
  - /audio/asio/inputs     -> plain list of str
  - /audio/asio/outputs    -> plain list of str
  - /audio/driver-types    -> plain list of str
"""

from __future__ import annotations

from typing import List

from ._http import _HTTPClient
from ._models import InputCalConfig, OutputCalConfig


class AudioClient:
    """
    Control REW's audio input/output devices and calibration.

    Instantiated by REWClient - do not construct directly.
    """

    def __init__(self, http: _HTTPClient) -> None:
        self._http = http

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------

    async def get_driver(self) -> str:
        """Return the active audio driver name (e.g. 'Java', 'ASIO')."""
        d = await self._http.get("/audio/driver")
        return d["driver"]

    async def set_driver(self, driver: str) -> None:
        """Set the active audio driver. Available choices: get_driver_types()."""
        await self._http.post("/audio/driver", driver)

    async def get_driver_types(self) -> List[str]:
        """Return the list of available audio driver names."""
        return await self._http.get("/audio/driver-types")

    # ------------------------------------------------------------------
    # Sample rate
    # ------------------------------------------------------------------

    async def get_sample_rate(self) -> int:
        """Return the current sample rate in Hz."""
        d = await self._http.get("/audio/samplerate")
        return int(d["value"])

    async def set_sample_rate(self, rate: int) -> None:
        """Set the sample rate. *rate* in Hz (e.g. 48000)."""
        await self._http.post("/audio/samplerate", rate)

    async def get_sample_rates(self) -> List[int]:
        """Return the sample rates supported by the current interface."""
        items = await self._http.get("/audio/samplerates")
        return [int(r["value"]) for r in items]

    # ------------------------------------------------------------------
    # Java - devices
    # ------------------------------------------------------------------

    async def get_java_input_devices(self) -> List[str]:
        """Return available Java input device names."""
        return await self._http.get("/audio/java/input-devices")

    async def get_java_output_devices(self) -> List[str]:
        """Return available Java output device names."""
        return await self._http.get("/audio/java/output-devices")

    async def get_java_input_device(self) -> str:
        """Return the selected Java input device name."""
        d = await self._http.get("/audio/java/input-device")
        return d["device"]

    async def set_java_input_device(self, device: str) -> None:
        """Select a Java input device by name."""
        await self._http.post("/audio/java/input-device", device)

    async def get_java_output_device(self) -> str:
        """Return the selected Java output device name."""
        d = await self._http.get("/audio/java/output-device")
        return d["device"]

    async def set_java_output_device(self, device: str) -> None:
        """Select a Java output device by name."""
        await self._http.post("/audio/java/output-device", device)

    # ------------------------------------------------------------------
    # Java - inputs / outputs
    # ------------------------------------------------------------------

    async def get_java_inputs(self) -> List[str]:
        """Return available Java input names for the selected device."""
        return await self._http.get("/audio/java/inputs")

    async def get_java_outputs(self) -> List[str]:
        """Return available Java output names for the selected device."""
        return await self._http.get("/audio/java/outputs")

    async def get_java_input(self) -> str:
        """Return the selected Java input name."""
        d = await self._http.get("/audio/java/input")
        # unwrap {"input": <str>} wrapper
        return d["input"] if isinstance(d, dict) else d

    async def set_java_input(self, input_name: str) -> None:
        """Select a Java input by name."""
        await self._http.post("/audio/java/input", input_name)

    async def get_java_output(self) -> str:
        """Return the selected Java output name."""
        d = await self._http.get("/audio/java/output")
        # unwrap {"output": <str>} wrapper
        return d["output"] if isinstance(d, dict) else d

    async def set_java_output(self, output_name: str) -> None:
        """Select a Java output by name."""
        await self._http.post("/audio/java/output", output_name)

    # ------------------------------------------------------------------
    # Java - channels
    # ------------------------------------------------------------------

    async def get_java_input_channel(self) -> int:
        """Return the selected Java input channel (1-indexed)."""
        d = await self._http.get("/audio/java/input-channel")
        return int(d["channel"])

    async def set_java_input_channel(self, channel: int) -> None:
        """Set the Java input channel (1-indexed)."""
        await self._http.post("/audio/java/input-channel", channel)

    async def get_java_ref_input_channel(self) -> int:
        """Return the timing reference / loopback input channel."""
        d = await self._http.get("/audio/java/ref-input-channel")
        return int(d["channel"])

    async def set_java_ref_input_channel(self, channel: int) -> None:
        """Set the timing reference / loopback input channel."""
        await self._http.post("/audio/java/ref-input-channel", channel)

    async def get_java_output_channel(self) -> str:
        """Return the selected Java output channel (string, may be 'L+R')."""
        d = await self._http.get("/audio/java/output-channel")
        ch = d["channel"]
        return str(ch)

    async def set_java_output_channel(self, channel: str) -> None:
        """Set the Java output channel (e.g. '1', '2', 'L+R')."""
        await self._http.post("/audio/java/output-channel", channel)

    async def get_java_num_input_channels(self) -> int:
        """Return the number of available Java input channels."""
        d = await self._http.get("/audio/java/num-input-channels")
        return int(d)

    # ------------------------------------------------------------------
    # ASIO - device
    # ------------------------------------------------------------------

    async def get_asio_devices(self) -> List[str]:
        """Return available ASIO device names."""
        return await self._http.get("/audio/asio/devices")

    async def get_asio_device(self) -> str:
        """Return the selected ASIO device name."""
        d = await self._http.get("/audio/asio/device")
        return d["device"] if isinstance(d, dict) else d

    async def set_asio_device(self, device: str) -> None:
        """Select an ASIO device by name."""
        await self._http.post("/audio/asio/device", device)

    # ------------------------------------------------------------------
    # ASIO - inputs / outputs
    # ------------------------------------------------------------------

    async def get_asio_inputs(self) -> List[str]:
        """Return available ASIO input names for the selected device."""
        return await self._http.get("/audio/asio/inputs")

    async def get_asio_outputs(self) -> List[str]:
        """Return available ASIO output names for the selected device."""
        return await self._http.get("/audio/asio/outputs")

    async def get_asio_input(self) -> str:
        """Return the selected ASIO input name."""
        d = await self._http.get("/audio/asio/input")
        return d["input"] if isinstance(d, dict) else d

    async def set_asio_input(self, input_name: str) -> None:
        """Select an ASIO input by name."""
        await self._http.post("/audio/asio/input", input_name)

    async def get_asio_output(self) -> str:
        """Return the selected ASIO output name."""
        d = await self._http.get("/audio/asio/output")
        return d["output"] if isinstance(d, dict) else d

    async def set_asio_output(self, output_name: str) -> None:
        """Select an ASIO output by name."""
        await self._http.post("/audio/asio/output", output_name)

    async def reload_asio_driver(self) -> None:
        """Force a reload of the ASIO driver."""
        await self._http.post("/audio/asio/command", {"command": "Reload"})

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    async def get_input_cal(self) -> InputCalConfig:
        """Return the current input calibration configuration."""
        data = await self._http.get("/audio/input-cal")
        return InputCalConfig.from_dict(data)

    async def set_input_cal(self, config: InputCalConfig) -> None:
        """
        Update the input calibration configuration.

        To clear the cal file, set config.calDataAllInputs.calFilePath to "".
        Use forward slashes or double-backslashes in file paths.
        """
        await self._http.put("/audio/input-cal", config.to_dict())

    async def get_output_cal(self) -> OutputCalConfig:
        """Return the current output calibration configuration."""
        data = await self._http.get("/audio/output-cal")
        return OutputCalConfig.from_dict(data)

    async def set_output_cal(self, config: OutputCalConfig) -> None:
        """
        Update the output calibration configuration.

        To clear the cal file, set config.calData.calFilePath to "".
        """
        await self._http.put("/audio/output-cal", config.to_dict())
