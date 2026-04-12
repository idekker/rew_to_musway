"""
_models.py — typed dataclasses for all REW API request/response shapes.

Naming follows the REW API documentation. All fields that are absent on some
measurement types (e.g. RTA vs sweep) are typed as Optional.

Array fields (magnitude, phase, data) are decoded from the API's Base64
big-endian 32-bit float format into numpy ndarrays by the client methods;
the models themselves store the final numpy arrays.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
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
    """
    Summary metadata for a single REW measurement.

    *uuid* is the stable identifier — use it for all sub-resource calls.
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
    groupName: Optional[str] = None
    groupNotes: Optional[str] = None
    groupID: Optional[str] = None
    cumulativeIRShiftSeconds: Optional[float] = None
    clockAdjustmentPPM: Optional[float] = None
    timeOfIRStartSeconds: Optional[float] = None
    timeOfIRPeakSeconds: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MeasurementSummary":
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
    """
    Frequency response data from the REW API.

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
    ppo: Optional[int] = None          # log-spaced
    freqStep: Optional[float] = None   # linear-spaced
    phase: Optional[np.ndarray] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FrequencyResponse":
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
    """
    Impulse response data from the REW API.

    Not available for RTA-derived measurements — the API returns 400 for those.
    """
    unit: str
    startTime: float
    sampleInterval: float
    sampleRate: float
    timingReference: str
    data: np.ndarray

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ImpulseResponse":
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
    """
    Impulse response window settings for a measurement.

    Not available for RTA-derived measurements.
    """
    leftWindowType: str
    rightWindowType: str
    leftWindowWidthms: float
    rightWindowWidthms: float
    refTimems: float
    addFDW: bool
    addMTW: bool
    fdwWidthCycles: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IRWindows":
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

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
    """
    A single EQ filter slot for a measurement.

    frequency, gaindB, and q are absent when type is "None".
    """
    index: int
    type: str
    enabled: bool
    isAuto: bool
    frequency: Optional[float] = None
    gaindB: Optional[float] = None
    q: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FilterSetting":
        return cls(
            index=d["index"],
            type=d["type"],
            enabled=d["enabled"],
            isAuto=d["isAuto"],
            frequency=d.get("frequency"),
            gaindB=d.get("gaindB"),
            q=d.get("q"),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
    def from_dict(cls, d: Dict[str, Any]) -> "Equaliser":
        return cls(manufacturer=d["manufacturer"], model=d["model"])

    def to_dict(self) -> Dict[str, Any]:
        return {"manufacturer": self.manufacturer, "model": self.model}


@dataclass
class TargetSettings:
    """EQ target shape settings for a measurement."""
    shape: str
    bassManagementSlopedBPerOctave: int
    bassManagementCutoffHz: float
    lowFreqSlopedBPerOctave: int
    lowFreqCutoffHz: float
    lowPassCrossoverType: str
    highPassCrossoverType: str
    lowPassCutoffHz: float
    highPassCutoffHz: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TargetSettings":
        return cls(
            shape=d["shape"],
            bassManagementSlopedBPerOctave=d["bassManagementSlopedBPerOctave"],
            bassManagementCutoffHz=d["bassManagementCutoffHz"],
            lowFreqSlopedBPerOctave=d["lowFreqSlopedBPerOctave"],
            lowFreqCutoffHz=d["lowFreqCutoffHz"],
            lowPassCrossoverType=d["lowPassCrossoverType"],
            highPassCrossoverType=d["highPassCrossoverType"],
            lowPassCutoffHz=d["lowPassCutoffHz"],
            highPassCutoffHz=d["highPassCutoffHz"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape": self.shape,
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
    def from_dict(cls, d: Dict[str, Any]) -> "RoomCurveSettings":
        return cls(
            addRoomCurve=d["addRoomCurve"],
            lowFreqRiseStartHz=d["lowFreqRiseStartHz"],
            lowFreqRiseEndHz=d["lowFreqRiseEndHz"],
            lowFreqRiseSlopedBPerOctave=d["lowFreqRiseSlopedBPerOctave"],
            highFreqFallStartHz=d["highFreqFallStartHz"],
            highFreqFallSlopedBPerOctave=d["highFreqFallSlopedBPerOctave"],
        )

    def to_dict(self) -> Dict[str, Any]:
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
    processName: Optional[int] = None
    message: Optional[str] = None
    # Additional key/value results from the command (e.g. waterfall, spectrogram data)
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcessResult":
        known = {"processName", "message"}
        return cls(
            processName=d.get("processName"),
            message=d.get("message"),
            data={k: v for k, v in d.items() if k not in known},
        )


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

@dataclass
class InputCalAllInputs:
    """Cal data shared across all inputs."""
    calFilePath: str = ""
    dBFSAt94dBSPL: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InputCalAllInputs":
        return cls(
            calFilePath=d.get("calFilePath", ""),
            dBFSAt94dBSPL=d.get("dBFSAt94dBSPL"),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"calFilePath": self.calFilePath}
        if self.dBFSAt94dBSPL is not None:
            d["dBFSAt94dBSPL"] = self.dBFSAt94dBSPL
        return d


@dataclass
class InputCalConfig:
    """
    Input calibration configuration.

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
    def from_dict(cls, d: Dict[str, Any]) -> "InputCalConfig":
        cal_raw = d.get("calDataAllInputs", {})
        return cls(
            currentInputSelection=d.get("currentInputSelection", ""),
            separateCalFileForEachInput=d.get("separateCalFileForEachInput", False),
            inputDeviceIsCWeighted=d.get("inputDeviceIsCWeighted", False),
            calDataAllInputs=InputCalAllInputs.from_dict(cal_raw if isinstance(cal_raw, dict) else {}),
        )

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, d: Dict[str, Any]) -> "OutputCalSampleRate":
        return cls(value=d.get("value", 0.0), unit=d.get("unit", "Hz"))

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit}


@dataclass
class OutputCalData:
    """Cal data nested inside OutputCalConfig."""
    calFilePath: str = ""
    sampleRate: OutputCalSampleRate = field(default_factory=OutputCalSampleRate)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OutputCalData":
        sr_raw = d.get("sampleRate", {})
        return cls(
            calFilePath=d.get("calFilePath", ""),
            sampleRate=OutputCalSampleRate.from_dict(sr_raw if isinstance(sr_raw, dict) else {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"calFilePath": self.calFilePath, "sampleRate": self.sampleRate.to_dict()}


@dataclass
class OutputCalConfig:
    """
    Output calibration configuration.

    Actual shape returned by GET /audio/output-cal:
      {
        "currentOutputSelection": <str>,
        "calData": {"calFilePath": <str>, "sampleRate": {"value": <float>, "unit": "Hz"}}
      }
    """
    currentOutputSelection: str = ""
    calData: OutputCalData = field(default_factory=OutputCalData)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OutputCalConfig":
        cal_raw = d.get("calData", {})
        return cls(
            currentOutputSelection=d.get("currentOutputSelection", ""),
            calData=OutputCalData.from_dict(cal_raw if isinstance(cal_raw, dict) else {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currentOutputSelection": self.currentOutputSelection,
            "calData": self.calData.to_dict(),
        }


# ---------------------------------------------------------------------------
# Input levels
# ---------------------------------------------------------------------------

@dataclass
class InputLevels:
    """
    Last input levels snapshot from the REW input-levels monitor.

    rms and peak are lists of per-channel values.
    """
    unit: str
    rms: List[float]
    peak: List[float]
    timeSpanSeconds: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InputLevels":
        return cls(
            unit=d["unit"],
            rms=list(d["rms"]),
            peak=list(d["peak"]),
            timeSpanSeconds=d["timeSpanSeconds"],
        )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

@dataclass
class GeneratorStatus:
    """Current state of the REW signal generator."""
    enabled: bool
    playing: bool
    signal: Optional[str] = None
    level: Optional[float] = None
    levelUnit: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GeneratorStatus":
        return cls(
            enabled=d.get("enabled", False),
            playing=d.get("playing", False),
            signal=d.get("signal"),
            level=d.get("level"),
            levelUnit=d.get("levelUnit"),
        )


# ---------------------------------------------------------------------------
# SPL meter
# ---------------------------------------------------------------------------

@dataclass
class SPLMeterConfiguration:
    """Configuration for a single REW SPL meter."""
    mode: str = "SPL"
    weighting: str = "C"
    filter: str = "Slow"
    highPassActive: bool = False
    rollingLeqActive: bool = False
    rollingLeqMinutes: int = 15

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SPLMeterConfiguration":
        return cls(
            mode=d.get("mode", "SPL"),
            weighting=d.get("weighting", "C"),
            filter=d.get("filter", "Slow"),
            highPassActive=d.get("highPassActive", False),
            rollingLeqActive=d.get("rollingLeqActive", False),
            rollingLeqMinutes=d.get("rollingLeqMinutes", 15),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "weighting": self.weighting,
            "filter": self.filter,
            "highPassActive": self.highPassActive,
            "rollingLeqActive": self.rollingLeqActive,
            "rollingLeqMinutes": self.rollingLeqMinutes,
        }


@dataclass
class SPLValues:
    """SPL meter readings."""
    meterNumber: int
    weighting: str
    filter: str
    spl: float
    leq: float
    isRollingLeq: bool
    rollingLeqMinutes: int
    leq1m: float
    leq10m: float
    sel: float
    elapsedTime: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SPLValues":
        return cls(
            meterNumber=d["meterNumber"],
            weighting=d["weighting"],
            filter=d["filter"],
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
    """
    RTA configuration.

    All fields use the actual names/types returned by GET /rta/config.
    Only the fields being set need to be populated when sending to the API
    (POST / PUT both accept partial objects).

    fftLength is a string like "64k", "128k", etc. (not an int).
    stopAt is a string like "Max averages", "Never", etc. (not a bool).
    stopAtValue is a string.
    """
    mode: Optional[str] = None
    smoothing: Optional[Smoothing] = None
    fftLength: Optional[str] = None            # e.g. "64k"
    window: Optional[str] = None
    averaging: Optional[str] = None
    stopAt: Optional[bool] = None              # True = stop at stopAtValue averages
    stopAtValue: Optional[int] = None          # number of averages before auto-stop
    maximumOverlap: Optional[str] = None
    calcDistortionEnabled: Optional[bool] = None
    restartCaptureOnGeneratorChange: Optional[bool] = None
    stopGeneratorWithRTA: Optional[bool] = None
    use64BitFFT: Optional[bool] = None
    adjustRTALevels: Optional[bool] = None
    fundamentalFromSineGen: Optional[bool] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RTAConfiguration":
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

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in {
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
        }.items() if v is not None}


@dataclass
class RTAStatus:
    """Current run state of the REW RTA."""
    enabled: bool
    running: bool

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RTAStatus":
        return cls(
            enabled=d.get("enabled", False),
            running=d.get("running", False),
        )


# ---------------------------------------------------------------------------
# EQ defaults
# ---------------------------------------------------------------------------

@dataclass
class MatchTargetSettings:
    """
    Settings that control how REW matches an EQ response to its target.

    Actual fields from GET /eq/match-target-settings.
    Only populated fields are sent when doing PUT/POST.
    """
    startFrequency: Optional[float] = None
    endFrequency: Optional[float] = None
    individualMaxBoostdB: Optional[float] = None
    overallMaxBoostdB: Optional[float] = None
    flatnessTargetdB: Optional[float] = None
    allowNarrowFiltersBelow200Hz: Optional[bool] = None
    varyQAbove200Hz: Optional[bool] = None
    allowLowShelf: Optional[bool] = None
    lowShelfMin: Optional[float] = None
    lowShelfMax: Optional[float] = None
    allowHighShelf: Optional[bool] = None
    highShelfMin: Optional[float] = None
    highShelfMax: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MatchTargetSettings":
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

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in {
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
        }.items() if v is not None}
