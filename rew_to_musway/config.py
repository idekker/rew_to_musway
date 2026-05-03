"""config.py - Load and validate YAML configuration for rew_to_musway."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlaybackMode(Enum):
    MANUAL = "manual"
    REW_GENERATOR = "rew_generator"


class FilterType(Enum):
    BUTTERWORTH = "butterworth"
    BESSEL = "bessel"
    LINKWITZ_RILEY = "linkwitz_riley"


class TargetShape(Enum):
    """EQ target shape for a channel — maps to aiorew.TargetShape."""

    FULL_RANGE = "full_range"
    BASS_LIMITED = "bass_limited"
    SUBWOOFER = "subwoofer"
    SPEAKER_DRIVER = "speaker_driver"


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class REWConfig:
    host: str = "localhost"
    port: int = 4735


@dataclass
class TunestPCConfig:
    exe_path: str = ""
    model: str = "M6"


@dataclass
class TimerConfig:
    action_timeout: int = 10
    preset_load_timeout: int = 30
    spl_check_timeout: int = 30
    start_noise_timeout: int = 30


@dataclass
class MuswayConfig:
    exe_path: str = ""
    default_preset_path: str = ""


@dataclass
class ManualConfig:
    default_preset_path: str = ""


@dataclass
class PathsConfig:
    output_dir: str = "./output"


@dataclass
class PlaybackConfig:
    mode: PlaybackMode = PlaybackMode.MANUAL
    output_device: str | None = None
    output_channel: str | None = None
    generator_signal: str = "pink_periodic"
    generator_level: float = -12.0


@dataclass
class MeasurementConfig:
    rta_averages: int = 100
    smoothing: str = "1/6"


@dataclass
class MatchTargetConfig:
    individual_max_boost: float = 6.0
    overall_max_boost: float = 6.0
    flatness_target: float = 1.0
    allow_narrow_filters_below_200hz: bool = True
    vary_q_above_200hz: bool = True
    allow_low_shelf: bool = True
    low_shelf_range: tuple[float, float] = (-6.0, 6.0)
    allow_high_shelf: bool = True
    high_shelf_range: tuple[float, float] = (-6.0, 6.0)


@dataclass
class EQConfig:
    manufacturer: str = "Musway"
    model: str = "31 bands (Output)"
    match_range_margin: int = 1
    match_target: MatchTargetConfig = field(default_factory=MatchTargetConfig)
    house_curve: str = ""


@dataclass
class LevelsConfig:
    target_spl: float = 75.0
    tolerance: float = 1.0
    low_spl_offset: float = -10.0


@dataclass
class FilterConfig:
    type: FilterType = FilterType.LINKWITZ_RILEY
    frequency: int = 80
    slope: int = 24


@dataclass
class TargetConfig:
    """EQ target shape settings for a channel.

    ``shape`` selects the REW target curve type.  For ``bass_limited`` and
    ``subwoofer``, ``cutoff_hz`` and ``slope_db_per_octave`` define the
    bass-management rolloff.  ``subwoofer`` additionally supports
    ``low_freq_cutoff_hz`` and ``low_freq_slope_db_per_octave`` for the
    low-frequency rolloff.  For ``speaker_driver``, ``highpass_hz``,
    ``highpass_type``, ``lowpass_hz`` and ``lowpass_type`` define the
    driver crossover filters.  For ``full_range`` all are ignored.
    """

    shape: TargetShape = TargetShape.FULL_RANGE
    cutoff_hz: float = 80.0
    slope_db_per_octave: int = 24
    offset: float = 0.0  # dB offset applied to calculated target level
    # subwoofer low-frequency rolloff
    low_freq_cutoff_hz: float = 0.0
    low_freq_slope_db_per_octave: int = 0
    # speaker_driver fields
    highpass_hz: float = 0.0
    highpass_type: str = ""
    lowpass_hz: float = 0.0
    lowpass_type: str = ""


@dataclass
class ChannelConfig:
    number: int = 1
    name: str = ""
    group: str = "front"
    highpass: FilterConfig | None = None
    lowpass: FilterConfig | None = None
    target: TargetConfig = field(default_factory=TargetConfig)
    match_range: tuple[float, float] | None = None  # manual override
    finetune_loops: int = 0  # number of iterative refinement loops after phase 2


@dataclass
class CombinedMeasurement:
    """A group of channels to measure simultaneously after calibration."""

    name: str = ""
    channels: list[int] = field(default_factory=list)


@dataclass
class Config:
    rew: REWConfig = field(default_factory=REWConfig)
    tunest_pc: TunestPCConfig | None = None
    musway: MuswayConfig | None = None
    manual: ManualConfig = field(default_factory=ManualConfig)
    timer: TimerConfig = field(default_factory=TimerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    playback: PlaybackConfig = field(default_factory=PlaybackConfig)
    measurement: MeasurementConfig = field(default_factory=MeasurementConfig)
    eq: EQConfig = field(default_factory=EQConfig)
    levels: LevelsConfig = field(default_factory=LevelsConfig)
    channels: list[ChannelConfig] = field(default_factory=list)
    combined_measurements: list[CombinedMeasurement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _optional_str(value: Any) -> str | None:
    """Return *value* as a string, or ``None`` for missing / null values."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    return str(value)


def _parse_filter(data: dict[str, Any] | None) -> FilterConfig | None:
    if data is None:
        return None
    return FilterConfig(
        type=FilterType(data.get("type", "linkwitz_riley")),
        frequency=int(data.get("frequency", 80)),
        slope=int(data.get("slope", 24)),
    )


def _parse_target(data: dict[str, Any] | None) -> TargetConfig:
    if data is None:
        return TargetConfig()
    return TargetConfig(
        shape=TargetShape(data.get("shape", "full_range")),
        cutoff_hz=float(data.get("cutoff_hz", 80.0)),
        slope_db_per_octave=int(data.get("slope_db_per_octave", 24)),
        offset=float(data.get("offset", 0.0)),
        low_freq_cutoff_hz=float(data.get("low_freq_cutoff_hz", 0.0)),
        low_freq_slope_db_per_octave=int(data.get("low_freq_slope_db_per_octave", 0)),
        highpass_hz=float(data.get("highpass_hz", 0.0)),
        highpass_type=str(data.get("highpass_type", "")),
        lowpass_hz=float(data.get("lowpass_hz", 0.0)),
        lowpass_type=str(data.get("lowpass_type", "")),
    )


def _parse_match_target(data: dict[str, Any]) -> MatchTargetConfig:
    low_shelf = data.get("low_shelf_range", [-6.0, 6.0])
    high_shelf = data.get("high_shelf_range", [-6.0, 6.0])
    return MatchTargetConfig(
        individual_max_boost=float(data.get("individual_max_boost", 6.0)),
        overall_max_boost=float(data.get("overall_max_boost", 6.0)),
        flatness_target=float(data.get("flatness_target", 1.0)),
        allow_narrow_filters_below_200hz=bool(
            data.get("allow_narrow_filters_below_200hz", True)
        ),
        vary_q_above_200hz=bool(data.get("vary_q_above_200hz", True)),
        allow_low_shelf=bool(data.get("allow_low_shelf", True)),
        low_shelf_range=(float(low_shelf[0]), float(low_shelf[1])),
        allow_high_shelf=bool(data.get("allow_high_shelf", True)),
        high_shelf_range=(float(high_shelf[0]), float(high_shelf[1])),
    )


def _parse_tunest_pc(data: dict[str, Any] | None) -> TunestPCConfig | None:
    if data is None:
        return None
    return TunestPCConfig(
        exe_path=str(data.get("exe_path", "")),
        model=str(data.get("model", "M6")),
    )


def _parse_musway(data: dict[str, Any] | None) -> MuswayConfig | None:
    if data is None:
        return None
    return MuswayConfig(
        exe_path=str(data.get("exe_path", "")),
        default_preset_path=str(data.get("default_preset_path", "")),
    )


def _parse_manual(data: dict[str, Any]) -> ManualConfig:
    return ManualConfig(
        default_preset_path=str(data.get("default_preset_path", "")),
    )


def _parse_timer(data: dict[str, Any]) -> TimerConfig:
    return TimerConfig(
        action_timeout=int(data.get("action_timeout", 10)),
        preset_load_timeout=int(data.get("preset_load_timeout", 30)),
        spl_check_timeout=int(data.get("spl_check_timeout", 30)),
        start_noise_timeout=int(data.get("start_noise_timeout", 10)),
    )


def _parse_channel(data: dict[str, Any]) -> ChannelConfig:
    match_range_raw = data.get("match_range")
    match_range = None
    if match_range_raw is not None:
        match_range = (float(match_range_raw[0]), float(match_range_raw[1]))

    return ChannelConfig(
        number=int(data["number"]),
        name=str(data["name"]),
        group=str(data.get("group", "front")),
        highpass=_parse_filter(data.get("highpass")),
        lowpass=_parse_filter(data.get("lowpass")),
        target=_parse_target(data.get("target")),
        match_range=match_range,
        finetune_loops=int(data.get("finetune_loops", 0)),
    )


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_config(path: str | Path) -> Config:  # noqa: PLR0915
    """Load and validate a YAML configuration file.

    Parameters
    ----------
    path:
        Path to the YAML config file.

    Returns
    -------
    Parsed and validated Config object.

    Raises
    ------
    FileNotFoundError:
        If the config file does not exist.
    ValueError:
        If required fields are missing or invalid.

    """
    config_path = Path(path)
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        msg = "Config file must contain a YAML mapping"
        raise TypeError(msg)

    # REW
    rew_raw = raw.get("rew", {})
    rew = REWConfig(
        host=str(rew_raw.get("host", "localhost")),
        port=int(rew_raw.get("port", 4735)),
    )

    # Tunest PC (optional — absence implies Musway or manual mode)
    tunest_pc = _parse_tunest_pc(raw.get("tunest_pc"))

    # Musway (optional — absence implies Tunest PC or manual mode)
    musway = _parse_musway(raw.get("musway"))

    # Manual config
    manual = _parse_manual(raw.get("manual", {}))

    # Timer config
    timer = _parse_timer(raw.get("timers", {}))

    # Validate: either tunest_pc or musway, not both
    if tunest_pc is not None and musway is not None:
        msg = (
            "Config requires either 'tunest_pc' section or 'musway' section, not both."
        )
        raise ValueError(msg)

    # Validate: if no tunest_pc and no musway, manual.default_preset_path must be set
    if tunest_pc is None and musway is None and not manual.default_preset_path:
        msg = (
            "Config requires either 'tunest_pc' section or "
            "'musway' section, or 'manual.default_preset_path' to be set"
        )
        raise ValueError(msg)

    # Paths
    paths_raw = raw.get("paths", {})
    paths = PathsConfig(
        output_dir=str(paths_raw.get("output_dir", "./output")),
    )

    # Playback
    pb_raw = raw.get("playback", {})
    playback = PlaybackConfig(
        mode=PlaybackMode(pb_raw.get("mode", "manual")),
        output_device=_optional_str(pb_raw.get("output_device")),
        output_channel=_optional_str(pb_raw.get("output_channel")),
        generator_signal=str(pb_raw.get("generator_signal", "pink_periodic")),
        generator_level=float(pb_raw.get("generator_level", -12.0)),
    )

    # Measurement
    meas_raw = raw.get("measurement", {})
    measurement = MeasurementConfig(
        rta_averages=int(meas_raw.get("rta_averages", 100)),
        smoothing=str(meas_raw.get("smoothing", "1/6")),
    )

    # EQ
    eq_raw = raw.get("eq", {})
    mt_raw = eq_raw.get("match_target", {})
    house_curve_raw = str(eq_raw.get("house_curve", ""))
    house_curve = str(Path(house_curve_raw).resolve()) if house_curve_raw else ""
    eq = EQConfig(
        manufacturer=str(eq_raw.get("manufacturer", "Musway")),
        model=str(eq_raw.get("model", "31 bands (Output)")),
        match_range_margin=int(eq_raw.get("match_range_margin", 1)),
        match_target=_parse_match_target(mt_raw),
        house_curve=house_curve,
    )

    # Levels
    lvl_raw = raw.get("levels", {})
    levels = LevelsConfig(
        target_spl=float(lvl_raw.get("target_spl", 75.0)),
        tolerance=float(lvl_raw.get("tolerance", 1.0)),
        low_spl_offset=float(lvl_raw.get("low_spl_offset", -10.0)),
    )

    # Channels
    channels_raw = raw.get("channels", [])
    if not channels_raw:
        msg = "Config must define at least one channel"
        raise ValueError(msg)
    channels = [_parse_channel(ch) for ch in channels_raw]

    # Validate channel numbers are unique
    numbers = [ch.number for ch in channels]
    if len(numbers) != len(set(numbers)):
        msg = "Channel numbers must be unique"
        raise ValueError(msg)

    # Combined measurements
    combined_raw = raw.get("combined_measurements", [])
    number_set = set(numbers)
    combined_measurements: list[CombinedMeasurement] = []
    for cm in combined_raw:
        cm_channels = [int(n) for n in cm["channels"]]
        for n in cm_channels:
            if n not in number_set:
                msg = f"Combined measurement '{cm['name']}' references unknown channel {n}"
                raise ValueError(msg)
        combined_measurements.append(
            CombinedMeasurement(name=str(cm["name"]), channels=cm_channels),
        )

    return Config(
        rew=rew,
        tunest_pc=tunest_pc,
        musway=musway,
        manual=manual,
        timer=timer,
        paths=paths,
        playback=playback,
        measurement=measurement,
        eq=eq,
        levels=levels,
        channels=channels,
        combined_measurements=combined_measurements,
    )
