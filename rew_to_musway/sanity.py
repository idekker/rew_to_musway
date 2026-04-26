"""sanity.py - SPL sanity check before measurements.

Quick SPL read to catch catastrophic errors (amp off, master muted,
cable disconnected) before committing to a full measurement.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rew_to_musway.rew import REWController

logger = logging.getLogger(__name__)

_DEFAULT_SPL_SANITY_THRESHOLD = -10.0  # dB below target
_QUICK_SPL_WARMUP = 0.5  # seconds — shorter than full measurement


class SanityResult(Enum):
    """Outcome of an SPL sanity check."""

    OK = auto()
    PROCEEDED = auto()


async def spl_sanity_check(
    rew: REWController,
    target_spl: float,
    *,
    threshold: float = _DEFAULT_SPL_SANITY_THRESHOLD,
    prompt_fn: object | None = None,
) -> SanityResult:
    """Quick SPL read; warn if too low.

    Parameters
    ----------
    rew:
        REW controller for SPL measurement.
    target_spl:
        Expected SPL level in dB.
    threshold:
        Negative offset from *target_spl*. If the reading is below
        ``target_spl + threshold``, a warning is shown.
    prompt_fn:
        Async callable ``(message: str, choices: list[str]) -> str``
        for user interaction.  If ``None``, always proceeds on failure.

    Returns
    -------
    SanityResult
        ``OK`` if level is acceptable, ``PROCEEDED`` if user chose to
        proceed despite low level.

    """
    min_spl = target_spl + threshold

    while True:
        spl_values = await rew.measure_spl(warmup=_QUICK_SPL_WARMUP)
        measured = spl_values.spl
        logger.debug(
            "SPL sanity: measured=%.1f dB, min=%.1f dB (target=%.1f, threshold=%.1f)",
            measured,
            min_spl,
            target_spl,
            threshold,
        )

        if measured >= min_spl:
            return SanityResult.OK

        logger.warning("SPL too low: %.1f dB (expected >= %.1f dB)", measured, min_spl)

        if prompt_fn is None:
            return SanityResult.PROCEEDED

        msg = (
            f"SPL too low ({measured:.0f} dB). "
            f"Is the channel unmuted? (expected >= {min_spl:.0f} dB)"
        )
        choice = await prompt_fn(msg, ["Retry", "Proceed"])  # type: ignore[operator]

        if choice != "Retry":
            return SanityResult.PROCEEDED

        logger.info("Retrying SPL sanity check")
