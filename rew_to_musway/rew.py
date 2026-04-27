"""rew.py - Thin wrapper around aiorew for calibration operations."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING

from aiorew import (
    ArithmeticFunction,
    Equaliser,
    FilterSetting,
    GeneratorSignal,
    MatchTargetSettings,
    REWClient,
    RTAConfiguration,
    Smoothing,
    SPLValues,
    TargetSettings,
    TargetShape,
)

if TYPE_CHECKING:
    from uuid import UUID

    from .config import Config, TargetConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target shape mapping (config enum string → aiorew enum)
# ---------------------------------------------------------------------------

# Import here to avoid circular import at module level; config uses only
# basic types so this is safe inside TYPE_CHECKING for the type and here
# for the runtime mapping via string keys.
_TARGET_SHAPE_MAP: dict[str, TargetShape] = {
    "full_range": TargetShape.FULL_RANGE,
    "bass_limited": TargetShape.BASS_LIMITED,
    "subwoofer": TargetShape.SUBWOOFER,
    "speaker_driver": TargetShape.DRIVER,
}


def _apply_shape_settings(
    target: TargetSettings,
    shape: TargetShape,
    cfg: TargetConfig,
) -> bool:
    """Apply shape-specific parameters to *target*.  Return whether changed."""
    if shape in {TargetShape.BASS_LIMITED, TargetShape.SUBWOOFER}:
        target.bassManagementCutoffHz = cfg.cutoff_hz
        target.bassManagementSlopedBPerOctave = cfg.slope_db_per_octave
        logger.debug(
            "Target shape %s: cutoff=%.0f Hz, slope=%d dB/oct",
            shape.value,
            cfg.cutoff_hz,
            cfg.slope_db_per_octave,
        )

    if shape == TargetShape.SUBWOOFER and cfg.low_freq_cutoff_hz:
        target.lowFreqCutoffHz = cfg.low_freq_cutoff_hz
        target.lowFreqSlopedBPerOctave = cfg.low_freq_slope_db_per_octave
        logger.debug(
            "Target shape Subwoofer: low freq cutoff=%.0f Hz, slope=%d dB/oct",
            cfg.low_freq_cutoff_hz,
            cfg.low_freq_slope_db_per_octave,
        )

    if shape == TargetShape.DRIVER:
        if cfg.highpass_hz:
            target.highPassCutoffHz = cfg.highpass_hz
            target.highPassCrossoverType = cfg.highpass_type
        if cfg.lowpass_hz:
            target.lowPassCutoffHz = cfg.lowpass_hz
            target.lowPassCrossoverType = cfg.lowpass_type
        logger.debug(
            "Target shape Driver: HP=%.0f Hz (%s), LP=%.0f Hz (%s)",
            cfg.highpass_hz,
            cfg.highpass_type,
            cfg.lowpass_hz,
            cfg.lowpass_type,
        )

    return shape != TargetShape.FULL_RANGE


# ---------------------------------------------------------------------------
# Smoothing lookup
# ---------------------------------------------------------------------------

_SMOOTHING_MAP: dict[str, Smoothing] = {
    "1/1": Smoothing.S1,
    "1/2": Smoothing.S2,
    "1/3": Smoothing.S3,
    "1/6": Smoothing.S6,
    "1/12": Smoothing.S12,
    "1/24": Smoothing.S24,
    "1/48": Smoothing.S48,
    "None": Smoothing.NONE,
}


# ---------------------------------------------------------------------------
# REWController
# ---------------------------------------------------------------------------


class REWController:
    """Calibration-oriented controller for REW via the aiorew library."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: REWClient | None = None

    @property
    def client(self) -> REWClient:
        if self._client is None:
            msg = "Not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._client

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open connection to REW API."""
        logger.info(
            "Connecting to REW at %s:%d",
            self._config.rew.host,
            self._config.rew.port,
        )
        self._client = REWClient(
            host=self._config.rew.host,
            port=self._config.rew.port,
        )
        await self._client.connect()
        version = await self._client.get_version()
        logger.info("REW connected (version: %s)", version)

    async def close(self) -> None:
        """Close the REW connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # RTA measurement
    # ------------------------------------------------------------------

    async def run_rta(self) -> UUID:
        """Configure RTA, start, wait until done, save, and return UUID.

        Uses measurement config (rta_averages) from the loaded config.
        """
        averages = self._config.measurement.rta_averages
        logger.info("Starting RTA measurement (%d averages)", averages)

        await self.client.rta.set_configuration(
            RTAConfiguration(
                mode="RTA 1/48 octave",
                averaging="Forever",
                stopAt=True,
                stopAtValue=averages,
                stopGeneratorWithRTA=False,
                window="Rectangular",
                maximumOverlap="93.75%",
            )
        )

        await self.client.rta.start()
        logger.debug("RTA started, waiting for completion...")
        await self.client.rta.wait_until_stopped()
        logger.debug("RTA stopped.")

        uuid = await self.client.save_rta()
        logger.info("RTA saved, UUID: %s", uuid)
        return uuid

    async def rename_measurement(self, uuid: UUID, name: str) -> None:
        """Rename a measurement."""
        logger.debug("Renaming measurement %s to '%s'", uuid, name)
        await self.client.measurements.set_title(uuid, name)

    async def apply_smoothing(self, uuid: UUID) -> None:
        """Apply configured smoothing to a measurement."""
        smoothing_str = self._config.measurement.smoothing
        smoothing = _SMOOTHING_MAP.get(smoothing_str, Smoothing.S6)
        logger.debug("Applying %s smoothing to %s", smoothing_str, uuid)
        await self.client.measurements.apply_smoothing(uuid, smoothing)

    async def save_and_rename(self, name: str) -> UUID:
        """Run RTA, save, rename. Returns UUID."""
        uuid = await self.run_rta()
        await self.rename_measurement(uuid, name)
        return uuid

    # ------------------------------------------------------------------
    # SPL meter
    # ------------------------------------------------------------------

    _SPL_POLL_INTERVAL = 0.25
    _SPL_POLL_TIMEOUT = 10.0

    async def spl_open(self) -> None:
        """Open and start the SPL meter."""
        await self.client.spl_meter.open(meter_id=1)
        await self.client.spl_meter.start(meter_id=1)

    async def spl_read(self) -> SPLValues:
        """Read current SPL levels (meter must be open and started)."""
        return await self.client.spl_meter.get_levels(meter_id=1)

    async def spl_close(self) -> None:
        """Stop and close the SPL meter."""
        await self.client.spl_meter.stop(meter_id=1)
        await self.client.spl_meter.close(meter_id=1)

    async def measure_spl(self, warmup: float = 3) -> SPLValues:
        """Open SPL meter, wait for stable reading, return values, close.

        Parameters
        ----------
        warmup:
            Seconds to wait after starting the meter before the first read.

        After the warmup, the meter is polled until a non-NaN SPL value is
        returned or the poll timeout is reached.

        """
        logger.debug("Measuring SPL (warmup=%.1fs)", warmup)
        await self.client.spl_meter.open(meter_id=1)
        await self.client.spl_meter.start(meter_id=1)
        await asyncio.sleep(warmup)

        deadline = asyncio.get_event_loop().time() + self._SPL_POLL_TIMEOUT
        spl = await self.client.spl_meter.get_levels(meter_id=1)

        while math.isnan(spl.spl) and asyncio.get_event_loop().time() < deadline:
            logger.debug("SPL reading is NaN, retrying...")
            await asyncio.sleep(self._SPL_POLL_INTERVAL)
            spl = await self.client.spl_meter.get_levels(meter_id=1)

        if math.isnan(spl.spl):
            logger.warning("SPL meter returned NaN after %.1fs", self._SPL_POLL_TIMEOUT)

        logger.info("SPL: %.1f dB (%s, %s)", spl.spl, spl.weighting, spl.filter)

        await self.client.spl_meter.stop(meter_id=1)
        await self.client.spl_meter.close(meter_id=1)
        return spl

    # ------------------------------------------------------------------
    # EQ / filter generation
    # ------------------------------------------------------------------

    async def configure_equaliser(self, uuid: UUID) -> None:
        """Set the equaliser model for a measurement."""
        eq_cfg = self._config.eq
        logger.debug(
            "Setting equaliser to %s / %s for %s",
            eq_cfg.manufacturer,
            eq_cfg.model,
            uuid,
        )
        await self.client.measurements.set_equaliser(
            uuid,
            Equaliser(manufacturer=eq_cfg.manufacturer, model=eq_cfg.model),
        )

    async def configure_target(
        self,
        uuid: UUID,
        *,
        target_cfg: TargetConfig | None = None,
        target_offset: float = 0.0,
    ) -> None:
        """Set target shape, cutoff frequencies, and house curve.

        Parameters
        ----------
        uuid:
            Measurement UUID.
        target_cfg:
            Target shape configuration from the channel config.  When
            ``None``, defaults to full-range with no cutoff.
        target_offset:
            dB offset applied to the calculated target level.  Positive
            values raise the target (more boost), negative values lower it.

        """
        # Target shape + cutoff
        target = await self.client.measurements.get_target_settings(uuid)

        desired_shape = TargetShape.FULL_RANGE
        if target_cfg is not None:
            desired_shape = _TARGET_SHAPE_MAP[target_cfg.shape.value]

        changed = False
        if target.shape != desired_shape:
            target.shape = desired_shape
            changed = True

        if target_cfg is not None:
            changed = (
                _apply_shape_settings(target, desired_shape, target_cfg) or changed
            )

        if changed:
            await self.client.measurements.set_target_settings(uuid, target)

        # House curve
        house_curve = self._config.eq.house_curve
        if house_curve:
            house_curve_path = house_curve.replace("\\", "/")
            logger.debug("Setting house curve: %s", house_curve_path)
            await self.client.eq.set_house_curve(
                house_curve_path, log_interpolation=True
            )

        # Calculate target level from response
        await self.client.measurements.calculate_target_level(uuid)
        level = await self.client.measurements.get_target_level(uuid)
        logger.info("Calculated target level: %.1f dB", level)

        # Apply offset
        if target_offset != 0.0:
            level += target_offset
            await self.client.measurements.set_target_level(uuid, level)
            logger.info(
                "Target level after offset (%+.1f dB): %.1f dB",
                target_offset,
                level,
            )

    async def configure_match_settings(
        self,
        start_freq: float,
        end_freq: float,
    ) -> None:
        """Set the match-target settings with the given frequency range."""
        mt = self._config.eq.match_target
        logger.debug("Match settings: %.0f-%.0f Hz", start_freq, end_freq)
        await self.client.eq.set_match_target_settings(
            MatchTargetSettings(
                startFrequency=start_freq,
                endFrequency=end_freq,
                individualMaxBoostdB=mt.individual_max_boost,
                overallMaxBoostdB=mt.overall_max_boost,
                flatnessTargetdB=mt.flatness_target,
                allowNarrowFiltersBelow200Hz=mt.allow_narrow_filters_below_200hz,
                varyQAbove200Hz=mt.vary_q_above_200hz,
                allowLowShelf=mt.allow_low_shelf,
                lowShelfMin=mt.low_shelf_range[0],
                lowShelfMax=mt.low_shelf_range[1],
                allowHighShelf=mt.allow_high_shelf,
                highShelfMin=mt.high_shelf_range[0],
                highShelfMax=mt.high_shelf_range[1],
            )
        )

    async def match_target(self, uuid: UUID) -> None:
        """Match measurement response to target (generates filters)."""
        logger.info("Matching response to target for %s", uuid)
        await self.client.measurements.match_target(uuid)
        logger.info("Match complete.")

    async def generate_predicted(self, uuid: UUID) -> UUID:
        """Generate predicted measurement and return its UUID."""
        logger.info("Generating predicted measurement for %s", uuid)
        before = await self.get_measurement_uuids()
        await self.client.measurements.generate_predicted_measurement(uuid)
        after = await self.get_measurement_uuids()
        new = after - before
        if len(new) != 1:
            msg = f"Expected 1 new predicted measurement, got {len(new)}"
            raise RuntimeError(msg)
        predicted_uuid = new.pop()
        logger.info("Predicted measurement UUID: %s", predicted_uuid)
        return predicted_uuid

    async def get_filters(self, uuid: UUID) -> list[FilterSetting]:
        """Return the EQ filters for a measurement."""
        return await self.client.measurements.get_filters(uuid)

    # ------------------------------------------------------------------
    # Measurement arithmetic
    # ------------------------------------------------------------------

    async def get_measurement_uuids(self) -> set[UUID]:
        """Return the UUIDs of all current measurements."""
        summaries = await self.client.measurements.list()
        return {s.uuid for s in summaries}

    async def divide_measurements(self, a: UUID, b: UUID) -> UUID:
        """Compute *A / B* and return the UUID of the new measurement.

        Parameters
        ----------
        a:
            Numerator measurement UUID.
        b:
            Denominator measurement UUID.

        """
        before = await self.get_measurement_uuids()
        parameters = {"maxGain": 10.0, "lowerLimit": 20, "upperLimit": 20000}
        await self.client.measurements.arithmetic(
            [a, b], ArithmeticFunction.A_OVER_B, parameters
        )
        after = await self.get_measurement_uuids()
        new = after - before
        if len(new) != 1:
            msg = f"Expected 1 new measurement from A/B, got {len(new)}"
            raise RuntimeError(msg)
        result_uuid = new.pop()
        logger.info("A/B: %s / %s → %s", a, b, result_uuid)
        return result_uuid

    async def multiply_measurements(self, a: UUID, b: UUID) -> UUID:
        """Compute *A * B* and return the UUID of the new measurement.

        Parameters
        ----------
        a:
            First measurement UUID.
        b:
            Second measurement UUID.

        """
        before = await self.get_measurement_uuids()
        await self.client.measurements.arithmetic([a, b], ArithmeticFunction.A_TIMES_B)
        after = await self.get_measurement_uuids()
        new = after - before
        if len(new) != 1:
            msg = f"Expected 1 new measurement from A*B, got {len(new)}"
            raise RuntimeError(msg)
        result_uuid = new.pop()
        logger.info("A*B: %s * %s → %s", a, b, result_uuid)
        return result_uuid

    # ------------------------------------------------------------------
    # Measurements management
    # ------------------------------------------------------------------

    async def delete_all_measurements(self) -> None:
        """Delete all measurements in REW."""
        logger.debug("Deleting all measurements")
        await self.client.measurements.delete_all()

    async def save_all_measurements(self, path: str) -> None:
        """Save all measurements to an .mdat file."""
        mdat_path = path.replace("\\", "/")
        logger.info("Saving all measurements to %s", mdat_path)
        await self.client.measurements.save_all(mdat_path)

    # ------------------------------------------------------------------
    # Generator control (used by REWGeneratorPlayback)
    # ------------------------------------------------------------------

    async def generator_play(self) -> None:
        """Start the signal generator."""
        signal_name = self._config.playback.generator_signal
        # Map config string to GeneratorSignal enum
        signal_map = {
            "pink_periodic": GeneratorSignal.PINK_PERIODIC,
            "pink_noise": GeneratorSignal.PINK_NOISE,
            "white_periodic": GeneratorSignal.WHITE_PERIODIC,
            "white_noise": GeneratorSignal.WHITE_NOISE,
        }
        signal = signal_map.get(signal_name, GeneratorSignal.PINK_PERIODIC)

        logger.debug(
            "Generator: signal=%s level=%.1f dBFS",
            signal.value,
            self._config.playback.generator_level,
        )
        await self.client.generator.set_signal(signal)
        await self.client.generator.set_level(self._config.playback.generator_level)
        await self.client.generator.play()

    async def generator_stop(self) -> None:
        """Stop the signal generator."""
        logger.debug("Generator: stop")
        await self.client.generator.stop()

    async def set_output_device(self, device: str, channel: str) -> None:
        """Select the REW output device and channel."""
        logger.debug("Output device: %s, channel: %s", device, channel)
        await self.set_output_device_name(device)
        await self.set_output_channel(channel)

    async def set_output_device_name(self, device: str) -> None:
        """Select only the output device (without changing the channel)."""
        logger.debug("Output device: %s", device)
        await self.client.audio.set_java_output_device(device)

    async def set_output_channel(self, channel: str) -> None:
        """Select only the output channel on the current device."""
        logger.debug("Output channel: %s", channel)
        await self.client.audio.set_java_output_channel(channel)

    async def get_output_devices(self) -> list[str]:
        """Return available Java output device names."""
        return await self.client.audio.get_java_output_devices()

    async def get_output_channels(self) -> list[str]:
        """Return available Java output names for the selected device.

        These are the selectable channel/output options (e.g. ``'1'``,
        ``'2'``, ``'L+R'``) once a device has been chosen.
        """
        return await self.client.audio.get_java_output_channels()
