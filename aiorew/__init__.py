"""aiorew - async Python client for the REW (Room EQ Wizard) REST API.

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
            await rew.generator.set_signal(GeneratorSignal.PINK_NOISE)
            await rew.generator.play()
            await rew.rta.start()
            await rew.rta.wait_until_stopped()

            uuid = await rew.save_rta()
            fr = await rew.measurements.get_frequency_response(uuid, smoothing="1/12")
            print(fr.magnitude)

    asyncio.run(main())
"""

from uuid import UUID

from ._client import REWClient
from ._http import REWError
from ._models import (
    ArithmeticFunction,
    Equaliser,
    FilterSetting,
    FrequencyResponse,
    GeneratorLevelUnit,
    GeneratorSignal,
    GeneratorStatus,
    ImpulseResponse,
    InputCalAllInputs,
    InputCalConfig,
    InputLevels,
    InputLevelsUnit,
    IRWindows,
    MatchTargetSettings,
    MeasurementSummary,
    OutputCalConfig,
    OutputCalData,
    OutputCalSampleRate,
    ProcessResult,
    RoomCurveSettings,
    RTAConfiguration,
    RTAStatus,
    Smoothing,
    SPLFilter,
    SPLMeterConfiguration,
    SPLMode,
    SPLValues,
    SPLWeighing,
    TargetSettings,
    TargetShape,
    decode_float_array,
    encode_float_array,
)

__all__ = [
    # UUID type (re-exported for convenience)
    "UUID",
    "ArithmeticFunction",
    "Equaliser",
    "FilterSetting",
    "FrequencyResponse",
    "GeneratorLevelUnit",
    # Generator
    "GeneratorSignal",
    "GeneratorStatus",
    "IRWindows",
    "ImpulseResponse",
    "InputCalAllInputs",
    # Audio calibration
    "InputCalConfig",
    "InputLevels",
    # Input levels
    "InputLevelsUnit",
    # EQ defaults
    "MatchTargetSettings",
    # Measurement models
    "MeasurementSummary",
    "OutputCalConfig",
    "OutputCalData",
    "OutputCalSampleRate",
    "ProcessResult",
    # Client
    "REWClient",
    # Error
    "REWError",
    # RTA
    "RTAConfiguration",
    "RTAStatus",
    "RoomCurveSettings",
    "SPLFilter",
    "SPLMeterConfiguration",
    # SPL meter
    "SPLMode",
    "SPLValues",
    "SPLWeighing",
    "Smoothing",
    "TargetSettings",
    "TargetShape",
    # Array codec helpers
    "decode_float_array",
    "encode_float_array",
]

__version__ = "0.1.0"
