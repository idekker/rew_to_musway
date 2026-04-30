"""_amp_backend.py - Amp backend protocol.

The ``AmpBackend`` protocol defines the interface that calibration code
depends on.  DSP state mutations (levels, EQ filters, crossovers) are
buffered in memory and flushed when ``apply()`` is called.  Immediate
operations (solo, mute, master mute) take effect right away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from aiorew import FilterSetting
    from rew_to_musway.config import ChannelConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Buffered state
# ---------------------------------------------------------------------------


@dataclass
class _CrossoverState:
    filter_type: str  # config enum value, e.g. "linkwitz_riley"
    frequency: int
    slope: int


@dataclass
class _ChannelBuffer:
    """Pending DSP changes for a single channel."""

    level: float | None = None
    eq_filters: list[FilterSetting] | None = None
    eq_reset: bool = False
    highpass: _CrossoverState | None = None
    lowpass: _CrossoverState | None = None


@dataclass
class _AmpBuffer:
    """Pending DSP changes across all channels."""

    channels: dict[int, _ChannelBuffer] = field(default_factory=dict)

    def channel(self, ch: int) -> _ChannelBuffer:
        if ch not in self.channels:
            self.channels[ch] = _ChannelBuffer()
        return self.channels[ch]

    @property
    def is_empty(self) -> bool:
        return not self.channels

    def clear(self) -> None:
        self.channels.clear()


class PresetPhase(Enum):
    """Calibration phase for preset file naming."""

    INITIAL = auto()
    EQ = auto()
    FINETUNE = auto()
    VERIFICATION = auto()


# ---------------------------------------------------------------------------
# AmpBackend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AmpBackend(Protocol):
    """Unified interface for DSP amp control.

    Buffer operations accumulate state; ``apply()`` flushes them.
    Immediate operations take effect right away.
    """

    async def connect(self) -> None: ...

    def set_phase(self, phase: PresetPhase, iteration: int = 0) -> None: ...

    # -- Buffer operations (no side effects until apply) -------------------

    async def set_channel_level(self, channel: int, level_db: float) -> None: ...

    async def set_eq_filters(
        self, channel: int, filters: list[FilterSetting]
    ) -> None: ...

    async def set_crossover(self, channel_cfg: ChannelConfig) -> None: ...

    async def reset_eq(self, channel: int) -> None: ...

    # -- Immediate operations ----------------------------------------------

    async def solo_channel(self, channel: int) -> None: ...

    async def solo_channels(self, channels: list[int]) -> None:
        """Unmute *channels*, mute all others."""
        ...

    async def mute_all(self) -> None: ...

    async def set_master_mute(self, muted: bool) -> None: ...  # noqa: FBT001

    async def apply(self) -> None: ...

    # -- Compound operations -----------------------------------------------

    async def restore_eq(self) -> None: ...
