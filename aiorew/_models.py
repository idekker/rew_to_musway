"""_models.py - typed dataclasses for all REW API request/response shapes.

Naming follows the REW API documentation. All fields that are absent on some
measurement types (e.g. RTA vs sweep) are typed as Optional.

Array fields (magnitude, phase, data) are decoded from the API's Base64
big-endian 32-bit float format into numpy ndarrays by the client methods;
the models themselves store the final numpy arrays.
"""

# ruff: noqa: N815

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import numpy as np

# ---------------------------------------------------------------------------
# Array codec (Base64 big-endian float32 <-> numpy)
# ---------------------------------------------------------------------------


def decode_float_array(b64: str) -> np.ndarray:
    """Decode a REW Base64-encoded big-endian float32 array to a numpy array."""
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=">f4").astype("<f4")


def encode_float_array(arr: np.ndarray) -> str:
    """Encode a numpy float32 array to a REW Base64 big-endian string."""
    return base64.b64encode(arr.astype(">f4").tobytes()).decode()


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


@dataclass
class MeasurementSummary:
    """Summary metadata for a single REW measurement.

    *uuid* is the stable identifier - use it for all sub-resource calls.
    Group fields and IR timing fields are absent on some measurement types
    (e.g. RTA-derived measurements have no IR timing).
    """

    title: str
    uuid: UUID
    date: str
    startFreq: float
    endFreq: float
    inverted: bool
    sampleRate: float
    rewVersion: str
    splOffsetdB: float
    alignSPLOffsetdB: float
    notes: str = ""
    groupName: str | None = None
    groupNotes: str | None = None
    groupID: str | None = None
    cumulativeIRShiftSeconds: float | None = None
    clockAdjustmentPPM: float | None = None
    timeOfIRStartSeconds: float | None = None
    timeOfIRPeakSeconds: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MeasurementSummary:
        return cls(
            title=d["title"],
            uuid=UUID(d["uuid"]),
            date=d["date"],
            startFreq=d["startFreq"],
            endFreq=d["endFreq"],
            inverted=d["inverted"],
            sampleRate=d["sampleRate"],
            rewVersion=d["rewVersion"],
            splOffsetdB=d["splOffsetdB"],
            alignSPLOffsetdB=d["alignSPLOffsetdB"],
            notes=d.get("notes", ""),
            groupName=d.get("groupName"),
            groupNotes=d.get("groupNotes"),
            groupID=d.get("groupID"),
            cumulativeIRShiftSeconds=d.get("cumulativeIRShiftSeconds"),
            clockAdjustmentPPM=d.get("clockAdjustmentPPM"),
            timeOfIRStartSeconds=d.get("timeOfIRStartSeconds"),
            timeOfIRPeakSeconds=d.get("timeOfIRPeakSeconds"),
        )


@dataclass
class FrequencyResponse:
    """Frequency response data from the REW API.

    Spacing is either log (ppo is set, freqStep is None) or linear
    (freqStep is set, ppo is None).  phase is absent for RTA-derived
    measurements, target responses, and group-delay responses.

    Frequency at zero-based index i for log-spaced data:
        startFreq * exp(i * ln(2) / ppo)
    Frequency at zero-based index i for linear-spaced data:
        startFreq + i * freqStep
    """

    unit: str
    smoothing: Smoothing
    startFreq: float
    magnitude: np.ndarray
    ppo: int | None = None  # log-spaced
    freqStep: float | None = None  # linear-spaced
    phase: np.ndarray | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FrequencyResponse:
        return cls(
            unit=d["unit"],
            smoothing=Smoothing(d["smoothing"]),
            startFreq=d["startFreq"],
            magnitude=decode_float_array(d["magnitude"]),
            ppo=d.get("ppo"),
            freqStep=d.get("freqStep"),
            phase=decode_float_array(d["phase"]) if "phase" in d else None,
        )


class Smoothing(Enum):
    NONE = "None"
    S1 = "1/1"
    S2 = "1/2"
    S3 = "1/3"
    S6 = "1/6"
    S12 = "1/12"
    S24 = "1/24"
    S48 = "1/48"
    VAR = "Var"
    PSY = "Psy"
    ERB = "ERB"


@dataclass
class ImpulseResponse:
    """Impulse response data from the REW API.

    Not available for RTA-derived measurements - the API returns 400 for those.
    """

    unit: str
    startTime: float
    sampleInterval: float
    sampleRate: float
    timingReference: str
    data: np.ndarray

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ImpulseResponse:
        return cls(
            unit=d["unit"],
            startTime=d["startTime"],
            sampleInterval=d["sampleInterval"],
            sampleRate=d["sampleRate"],
            timingReference=d["timingReference"],
            data=decode_float_array(d["data"]),
        )


@dataclass
class IRWindows:
    """Impulse response window settings for a measurement.

    Not available for RTA-derived measurements.
    """

    leftWindowType: str
    rightWindowType: str
    leftWindowWidthms: float
    rightWindowWidthms: float
    refTimems: float
    addFDW: bool
    addMTW: bool
    fdwWidthCycles: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IRWindows:
        return cls(
            leftWindowType=d["leftWindowType"],
            rightWindowType=d["rightWindowType"],
            leftWindowWidthms=d["leftWindowWidthms"],
            rightWindowWidthms=d["rightWindowWidthms"],
            refTimems=d["refTimems"],
            addFDW=d["addFDW"],
            addMTW=d["addMTW"],
            fdwWidthCycles=d.get("fdwWidthCycles"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "leftWindowType": self.leftWindowType,
            "rightWindowType": self.rightWindowType,
            "leftWindowWidthms": self.leftWindowWidthms,
            "rightWindowWidthms": self.rightWindowWidthms,
            "refTimems": self.refTimems,
            "addFDW": self.addFDW,
            "addMTW": self.addMTW,
        }
        if self.fdwWidthCycles is not None:
            d["fdwWidthCycles"] = self.fdwWidthCycles
        return d


@dataclass
class FilterSetting:
    """A single EQ filter slot for a measurement.

    frequency, gaindB, and q are absent when type is "None".
    """

    index: int
    type: str
    enabled: bool
    isAuto: bool
    frequency: float | None = None
    gaindB: float | None = None
    q: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FilterSetting:
        return cls(
            index=d["index"],
            type=d["type"],
            enabled=d["enabled"],
            isAuto=d["isAuto"],
            frequency=d.get("frequency"),
            gaindB=d.get("gaindB"),
            q=d.get("q"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "type": self.type,
            "enabled": self.enabled,
            "isAuto": self.isAuto,
        }
        if self.frequency is not None:
            d["frequency"] = self.frequency
        if self.gaindB is not None:
            d["gaindB"] = self.gaindB
        if self.q is not None:
            d["q"] = self.q
        return d


@dataclass
class Equaliser:
    """Equaliser selection for a measurement."""

    manufacturer: str
    model: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Equaliser:
        return cls(manufacturer=d["manufacturer"], model=d["model"])

    def to_dict(self) -> dict[str, Any]:
        return {"manufacturer": self.manufacturer, "model": self.model}


class TargetShape(Enum):
    FULL_RANGE = "Full range"
    BASS_LIMITED = "Bass limited"
    SUBWOOFER = "Subwoofer"
    DRIVER = "Driver"
    NONE = "None"


@dataclass
class TargetSettings:
    """EQ target shape settings for a measurement."""

    shape: TargetShape
    bassManagementSlopedBPerOctave: int
    bassManagementCutoffHz: float
    lowFreqSlopedBPerOctave: int
    lowFreqCutoffHz: float
    lowPassCrossoverType: str
    highPassCrossoverType: str
    lowPassCutoffHz: float
    highPassCutoffHz: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TargetSettings:
        return cls(
            shape=TargetShape(d["shape"]),
            bassManagementSlopedBPerOctave=d["bassManagementSlopedBPerOctave"],
            bassManagementCutoffHz=d["bassManagementCutoffHz"],
            lowFreqSlopedBPerOctave=d["lowFreqSlopedBPerOctave"],
            lowFreqCutoffHz=d["lowFreqCutoffHz"],
            lowPassCrossoverType=d["lowPassCrossoverType"],
            highPassCrossoverType=d["highPassCrossoverType"],
            lowPassCutoffHz=d["lowPassCutoffHz"],
            highPassCutoffHz=d["highPassCutoffHz"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape.value,
            "bassManagementSlopedBPerOctave": self.bassManagementSlopedBPerOctave,
            "bassManagementCutoffHz": self.bassManagementCutoffHz,
            "lowFreqSlopedBPerOctave": self.lowFreqSlopedBPerOctave,
            "lowFreqCutoffHz": self.lowFreqCutoffHz,
            "lowPassCrossoverType": self.lowPassCrossoverType,
            "highPassCrossoverType": self.highPassCrossoverType,
            "lowPassCutoffHz": self.lowPassCutoffHz,
            "highPassCutoffHz": self.highPassCutoffHz,
        }


@dataclass
class RoomCurveSettings:
    """Room curve settings for a measurement."""

    addRoomCurve: bool
    lowFreqRiseStartHz: float
    lowFreqRiseEndHz: float
    lowFreqRiseSlopedBPerOctave: float
    highFreqFallStartHz: float
    highFreqFallSlopedBPerOctave: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoomCurveSettings:
        return cls(
            addRoomCurve=d["addRoomCurve"],
            lowFreqRiseStartHz=d["lowFreqRiseStartHz"],
            lowFreqRiseEndHz=d["lowFreqRiseEndHz"],
            lowFreqRiseSlopedBPerOctave=d["lowFreqRiseSlopedBPerOctave"],
            highFreqFallStartHz=d["highFreqFallStartHz"],
            highFreqFallSlopedBPerOctave=d["highFreqFallSlopedBPerOctave"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "addRoomCurve": self.addRoomCurve,
            "lowFreqRiseStartHz": self.lowFreqRiseStartHz,
            "lowFreqRiseEndHz": self.lowFreqRiseEndHz,
            "lowFreqRiseSlopedBPerOctave": self.lowFreqRiseSlopedBPerOctave,
            "highFreqFallStartHz": self.highFreqFallStartHz,
            "highFreqFallSlopedBPerOctave": self.highFreqFallSlopedBPerOctave,
        }


@dataclass
class ProcessResult:
    """Result from a long-running REW command."""

    processName: int | None = None
    message: str | None = None
    # Additional key/value results from the command (e.g. waterfall, spectrogram data)
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProcessResult:
        known = {"processName", "message"}
        return cls(
            processName=d.get("processName"),
            message=d.get("message"),
            data={k: v for k, v in d.items() if k not in known},
        )


class ProcessCommand(Enum):
    """Represents a long-running REW command."""

    ALIGN_SPL = "Align SPL"
    TIME_ALIGN = "Time align"
    ALIGN_IR_START = "Align IR start"
    CROSS_CORR_ALIGN = "Cross corr align"
    VECTOR_AVERAGE = "Vector average"
    RMS_AVERAGE = "RMS average"
    DB_AVERAGE = "dB average"
    MAGN_PLUS_PHASE_AVERAGE = "Magn plus phase average"
    DB_PLUS_PHASE_AVERAGE = "dB plus phase average"
    VECTOR_SUM = "Vector sum"
    SMOOTH = "Smooth"
    ARITHMETIC = "Arithmetic"
    REMOVE_IR_DELAYS = "Remove IR delays"


class ArithmeticFunction(Enum):
    A_PLUS_B = "A + B"
    A_MIN_B = "A - B"
    A_TIMES_B = "A * B"
    A_TIMES_B_CONJUGATE = "A * B conjugate"
    A_OVER_B = "A / B"
    A_MAGN_OVER_B_MAGN = "|A| / |B|"
    A_PLUS_B_OVER_2 = "(A + B) / 2"
    MERGE_B_TO_A = "Merge B to A"
    ONE_OVER_A = "1 / A"
    ONE_OVER_B = "1 / B"
    ONE_OVER_A_MAGN = "1 / |A|"
    ONE_OVER_B_MAGN = "1 / |B|"
    INVERT_A_PHASE = "Invert A phase"
    INVERT_B_PHASE = "Invert B phase"


@dataclass
class ProcessMeasurements:
    """Measurements for a long-running REW command."""

    processName: ProcessCommand
    measurementIndices: list[int]
    measurementUUIDs: list[UUID]
    parameters: dict[str, Any]
    resultUrl: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "processName": self.processName.value,
            "measurementIndices": self.measurementIndices,
            "measurementUUIDs": [str(uuid) for uuid in self.measurementUUIDs],
            "parameters": self.parameters,
            "resultUrl": self.resultUrl,
        }


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


@dataclass
class InputCalAllInputs:
    """Cal data shared across all inputs."""

    calFilePath: str = ""
    dBFSAt94dBSPL: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InputCalAllInputs:
        return cls(
            calFilePath=d.get("calFilePath", ""),
            dBFSAt94dBSPL=d.get("dBFSAt94dBSPL"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"calFilePath": self.calFilePath}
        if self.dBFSAt94dBSPL is not None:
            d["dBFSAt94dBSPL"] = self.dBFSAt94dBSPL
        return d


@dataclass
class InputCalConfig:
    """Input calibration configuration.

    Actual shape returned by GET /audio/input-cal:
      {
        "currentInputSelection": <str>,
        "separateCalFileForEachInput": <bool>,
        "inputDeviceIsCWeighted": <bool>,
        "calDataAllInputs": {"calFilePath": <str>, "dBFSAt94dBSPL": <float>}
      }
    """

    currentInputSelection: str = ""
    separateCalFileForEachInput: bool = False
    inputDeviceIsCWeighted: bool = False
    calDataAllInputs: InputCalAllInputs = field(default_factory=InputCalAllInputs)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InputCalConfig:
        cal_raw = d.get("calDataAllInputs", {})
        return cls(
            currentInputSelection=d.get("currentInputSelection", ""),
            separateCalFileForEachInput=d.get("separateCalFileForEachInput", False),
            inputDeviceIsCWeighted=d.get("inputDeviceIsCWeighted", False),
            calDataAllInputs=InputCalAllInputs.from_dict(
                cal_raw if isinstance(cal_raw, dict) else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "currentInputSelection": self.currentInputSelection,
            "separateCalFileForEachInput": self.separateCalFileForEachInput,
            "inputDeviceIsCWeighted": self.inputDeviceIsCWeighted,
            "calDataAllInputs": self.calDataAllInputs.to_dict(),
        }


@dataclass
class OutputCalSampleRate:
    """Sample rate info nested inside OutputCalConfig."""

    value: float = 0.0
    unit: str = "Hz"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutputCalSampleRate:
        return cls(value=d.get("value", 0.0), unit=d.get("unit", "Hz"))

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "unit": self.unit}


@dataclass
class OutputCalData:
    """Cal data nested inside OutputCalConfig."""

    calFilePath: str = ""
    sampleRate: OutputCalSampleRate = field(default_factory=OutputCalSampleRate)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutputCalData:
        sr_raw = d.get("sampleRate", {})
        return cls(
            calFilePath=d.get("calFilePath", ""),
            sampleRate=OutputCalSampleRate.from_dict(
                sr_raw if isinstance(sr_raw, dict) else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "calFilePath": self.calFilePath,
            "sampleRate": self.sampleRate.to_dict(),
        }


@dataclass
class OutputCalConfig:
    """Output calibration configuration.

    Actual shape returned by GET /audio/output-cal:
      {
        "currentOutputSelection": <str>,
        "calData": {"calFilePath": <str>, "sampleRate": {"value": <float>, "unit": "Hz"}}
      }
    """

    currentOutputSelection: str = ""
    calData: OutputCalData = field(default_factory=OutputCalData)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutputCalConfig:
        cal_raw = d.get("calData", {})
        return cls(
            currentOutputSelection=d.get("currentOutputSelection", ""),
            calData=OutputCalData.from_dict(
                cal_raw if isinstance(cal_raw, dict) else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "currentOutputSelection": self.currentOutputSelection,
            "calData": self.calData.to_dict(),
        }


# ---------------------------------------------------------------------------
# Input levels
# ---------------------------------------------------------------------------


class InputLevelsUnit(Enum):
    SPL = "SPL"
    DBFS = "dBFS"
    DBU = "dBu"
    DBV = "dBV"
    DBW = "dBW"
    V = "V"
    W = "W"


@dataclass
class InputLevels:
    """Last input levels snapshot from the REW input-levels monitor.

    rms and peak are lists of per-channel values.
    """

    unit: InputLevelsUnit
    rms: list[float]
    peak: list[float]
    timeSpanSeconds: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InputLevels:
        return cls(
            unit=InputLevelsUnit(d["unit"]),
            rms=list(d["rms"]),
            peak=list(d["peak"]),
            timeSpanSeconds=d["timeSpanSeconds"],
        )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class GeneratorSignal(Enum):
    SINE = "sine"
    SQUARE = "square"
    SAW_TOOTH = "sawtooth"
    TONE_BURST = "toneburst"
    CEA_BURST = "cea-burst"
    J_TEST = "j-test"
    DUAL_TONE = "dualtone"
    TRIPLE_TONE = "tripletone"
    QUAD_TONE = "quadtone"
    MULTI_TONE = "multitone"
    PINK_NOISE = "pinknoise"
    WHITE_NOISE = "whitenoise"
    PINK_PERIODIC = "pinkpn"
    WHITE_PERIODIC = "whitepn"
    LINEAR_SWEEP = "linearsweep"
    LOG_SWEEP = "logsweep"
    MEAS_SWEEP = "meassweep"
    FSAF_NOISE = "fsafnoise"


class GeneratorLevelUnit(Enum):
    DBU = "dBu"
    DBV = "dBV"
    V = "V"
    DBFS = "dBFS"


@dataclass
class GeneratorStatus:
    """Current state of the REW signal generator."""

    enabled: bool
    playing: bool
    signal: GeneratorSignal | None = None
    level: float | None = None
    levelUnit: GeneratorLevelUnit | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GeneratorStatus:
        return cls(
            enabled=d.get("enabled", False),
            playing=d.get("playing", False),
            signal=GeneratorSignal(d.get("signal")) if d.get("signal") else None,
            level=d.get("level"),
            levelUnit=GeneratorLevelUnit(d.get("levelUnit"))
            if d.get("levelUnit")
            else None,
        )


# ---------------------------------------------------------------------------
# SPL meter
# ---------------------------------------------------------------------------


class SPLMode(Enum):
    SPL = "SPL"
    LEQ = "LEQ"
    SEL = "SEL"


class SPLWeighing(Enum):
    A = "A"
    C = "C"
    Z = "Z"


class SPLFilter(Enum):
    SLOW = "Slow"
    FAST = "Fast"


@dataclass
class SPLMeterConfiguration:
    """Configuration for a single REW SPL meter."""

    mode: SPLMode = SPLMode.SPL
    weighting: SPLWeighing = SPLWeighing.C
    filter: SPLFilter = SPLFilter.SLOW
    highPassActive: bool = False
    rollingLeqActive: bool = False
    rollingLeqMinutes: int = 15

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SPLMeterConfiguration:
        return cls(
            mode=SPLMode(d.get("mode")),
            weighting=SPLWeighing(d.get("weighting")),
            filter=SPLFilter(d.get("filter")),
            highPassActive=d.get("highPassActive", False),
            rollingLeqActive=d.get("rollingLeqActive", False),
            rollingLeqMinutes=d.get("rollingLeqMinutes", 15),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "weighting": self.weighting.value,
            "filter": self.filter.value,
            "highPassActive": self.highPassActive,
            "rollingLeqActive": self.rollingLeqActive,
            "rollingLeqMinutes": self.rollingLeqMinutes,
        }


@dataclass
class SPLValues:
    """SPL meter readings."""

    meterNumber: int
    weighting: SPLWeighing
    filter: SPLFilter
    spl: float
    leq: float
    isRollingLeq: bool
    rollingLeqMinutes: int
    leq1m: float
    leq10m: float
    sel: float
    elapsedTime: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SPLValues:
        return cls(
            meterNumber=d["meterNumber"],
            weighting=SPLWeighing(d["weighting"]),
            filter=SPLFilter(d["filter"]),
            spl=d["spl"],
            leq=d["leq"],
            isRollingLeq=d["isRollingLeq"],
            rollingLeqMinutes=d["rollingLeqMinutes"],
            leq1m=d["leq1m"],
            leq10m=d["leq10m"],
            sel=d["sel"],
            elapsedTime=d["elapsedTime"],
        )


# ---------------------------------------------------------------------------
# RTA
# ---------------------------------------------------------------------------


@dataclass
class RTAConfiguration:
    """RTA configuration.

    All fields use the actual names/types returned by GET /rta/config.
    Only the fields being set need to be populated when sending to the API
    (POST / PUT both accept partial objects).

    fftLength is a string like "64k", "128k", etc. (not an int).
    stopAt is a string like "Max averages", "Never", etc. (not a bool).
    stopAtValue is a string.
    """

    mode: str | None = None
    smoothing: Smoothing | None = None
    fftLength: str | None = None  # e.g. "64k"
    window: str | None = None
    averaging: str | None = None
    stopAt: bool | None = None  # True = stop at stopAtValue averages
    stopAtValue: int | None = None  # number of averages before auto-stop
    maximumOverlap: str | None = None
    calcDistortionEnabled: bool | None = None
    restartCaptureOnGeneratorChange: bool | None = None
    stopGeneratorWithRTA: bool | None = None
    use64BitFFT: bool | None = None
    adjustRTALevels: bool | None = None
    fundamentalFromSineGen: bool | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RTAConfiguration:
        return cls(
            mode=d.get("mode"),
            smoothing=Smoothing(d.get("smoothing")) if "smoothing" in d else None,
            fftLength=d.get("fftLength"),
            window=d.get("window"),
            averaging=d.get("averaging"),
            stopAt=bool(d["stopAt"]) if "stopAt" in d else None,
            stopAtValue=int(d["stopAtValue"]) if "stopAtValue" in d else None,
            maximumOverlap=d.get("maximumOverlap"),
            calcDistortionEnabled=d.get("calcDistortionEnabled"),
            restartCaptureOnGeneratorChange=d.get("restartCaptureOnGeneratorChange"),
            stopGeneratorWithRTA=d.get("stopGeneratorWithRTA"),
            use64BitFFT=d.get("use64BitFFT"),
            adjustRTALevels=d.get("adjustRTALevels"),
            fundamentalFromSineGen=d.get("fundamentalFromSineGen"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "mode": self.mode,
                "smoothing": self.smoothing.value if self.smoothing else None,
                "fftLength": self.fftLength,
                "window": self.window,
                "averaging": self.averaging,
                "stopAt": self.stopAt,
                "stopAtValue": self.stopAtValue,
                "maximumOverlap": self.maximumOverlap,
                "calcDistortionEnabled": self.calcDistortionEnabled,
                "restartCaptureOnGeneratorChange": self.restartCaptureOnGeneratorChange,
                "stopGeneratorWithRTA": self.stopGeneratorWithRTA,
                "use64BitFFT": self.use64BitFFT,
                "adjustRTALevels": self.adjustRTALevels,
                "fundamentalFromSineGen": self.fundamentalFromSineGen,
            }.items()
            if v is not None
        }


@dataclass
class RTAStatus:
    """Current run state of the REW RTA."""

    enabled: bool
    running: bool

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RTAStatus:
        return cls(
            enabled=d.get("enabled", False),
            running=d.get("running", False),
        )


# ---------------------------------------------------------------------------
# EQ defaults
# ---------------------------------------------------------------------------


@dataclass
class MatchTargetSettings:
    """Settings that control how REW matches an EQ response to its target.

    Actual fields from GET /eq/match-target-settings.
    Only populated fields are sent when doing PUT/POST.
    """

    startFrequency: float | None = None
    endFrequency: float | None = None
    individualMaxBoostdB: float | None = None
    overallMaxBoostdB: float | None = None
    flatnessTargetdB: float | None = None
    allowNarrowFiltersBelow200Hz: bool | None = None
    varyQAbove200Hz: bool | None = None
    allowLowShelf: bool | None = None
    lowShelfMin: float | None = None
    lowShelfMax: float | None = None
    allowHighShelf: bool | None = None
    highShelfMin: float | None = None
    highShelfMax: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MatchTargetSettings:
        return cls(
            startFrequency=d.get("startFrequency"),
            endFrequency=d.get("endFrequency"),
            individualMaxBoostdB=d.get("individualMaxBoostdB"),
            overallMaxBoostdB=d.get("overallMaxBoostdB"),
            flatnessTargetdB=d.get("flatnessTargetdB"),
            allowNarrowFiltersBelow200Hz=d.get("allowNarrowFiltersBelow200Hz"),
            varyQAbove200Hz=d.get("varyQAbove200Hz"),
            allowLowShelf=d.get("allowLowShelf"),
            lowShelfMin=d.get("lowShelfMin"),
            lowShelfMax=d.get("lowShelfMax"),
            allowHighShelf=d.get("allowHighShelf"),
            highShelfMin=d.get("highShelfMin"),
            highShelfMax=d.get("highShelfMax"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "startFrequency": self.startFrequency,
                "endFrequency": self.endFrequency,
                "individualMaxBoostdB": self.individualMaxBoostdB,
                "overallMaxBoostdB": self.overallMaxBoostdB,
                "flatnessTargetdB": self.flatnessTargetdB,
                "allowNarrowFiltersBelow200Hz": self.allowNarrowFiltersBelow200Hz,
                "varyQAbove200Hz": self.varyQAbove200Hz,
                "allowLowShelf": self.allowLowShelf,
                "lowShelfMin": self.lowShelfMin,
                "lowShelfMax": self.lowShelfMax,
                "allowHighShelf": self.allowHighShelf,
                "highShelfMin": self.highShelfMin,
                "highShelfMax": self.highShelfMax,
            }.items()
            if v is not None
        }
