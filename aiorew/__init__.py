"""
aiorew — async Python client for the REW (Room EQ Wizard) REST API.

Public surface::

    from aiorew import REWClient
    from aiorew import RTAConfiguration, RTAStatus
    from aiorew import MeasurementSummary, FrequencyResponse, ImpulseResponse
    from aiorew import FilterSetting, Equaliser, TargetSettings, RoomCurveSettings
    from aiorew import GeneratorStatus, SPLMeterConfiguration, SPLValues
    from aiorew import InputLevels, IRWindows, ProcessResult, MatchTargetSettings
    from aiorew import REWError

Example::

    import asyncio
    from aiorew import REWClient, RTAConfiguration

    async def main():
        async with REWClient(host="localhost", port=4735) as rew:
            await rew.rta.set_configuration(RTAConfiguration(
                stopAt=True,
                stopAtValue=100,
                stopGeneratorWithRTA=True,
            ))
            await rew.generator.set_signal("pinknoise")
            await rew.generator.play()
            await rew.rta.start()
            await rew.rta.wait_until_stopped()

            uuid = await rew.save_rta()
            fr = await rew.measurements.get_frequency_response(uuid, smoothing="1/12")
            print(fr.magnitude)

    asyncio.run(main())
"""

from ._client import REWClient
from ._http import REWError
from ._models import (
    Equaliser,
    FilterSetting,
    FrequencyResponse,
    GeneratorStatus,
    ImpulseResponse,
    InputCalAllInputs,
    InputCalConfig,
    InputLevels,
    IRWindows,
    MatchTargetSettings,
    MeasurementSummary,
    OutputCalConfig,
    OutputCalData,
    OutputCalSampleRate,
    ProcessResult,
    RTAConfiguration,
    RTAStatus,
    RoomCurveSettings,
    SPLMeterConfiguration,
    SPLValues,
    TargetSettings,
    decode_float_array,
    encode_float_array,
)

__all__ = [
    # Client
    "REWClient",
    # Error
    "REWError",
    # Measurement models
    "MeasurementSummary",
    "FrequencyResponse",
    "ImpulseResponse",
    "IRWindows",
    "FilterSetting",
    "Equaliser",
    "TargetSettings",
    "RoomCurveSettings",
    "ProcessResult",
    # Generator
    "GeneratorStatus",
    # SPL meter
    "SPLMeterConfiguration",
    "SPLValues",
    # RTA
    "RTAConfiguration",
    "RTAStatus",
    # Input levels
    "InputLevels",
    # EQ defaults
    "MatchTargetSettings",
    # Audio calibration
    "InputCalConfig",
    "InputCalAllInputs",
    "OutputCalConfig",
    "OutputCalData",
    "OutputCalSampleRate",
    # Array codec helpers
    "decode_float_array",
    "encode_float_array",
]

__version__ = "0.1.0"
