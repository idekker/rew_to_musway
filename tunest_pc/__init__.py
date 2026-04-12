"""
tunest_pc - Python automation library for Tunest PC (TUNEST_PC_V1).

Public surface::

    from tunest_pc import TunestPC, FilterType, FilterSlope
    from tunest_pc import TunestConnectionError, TunestAutomationError

Example::

    t = TunestPC()
    t.connect(r"D:\\Program Files (x86)\\TUNEST PC\\TUNEST_PC_FULL.exe")
    t.set_master_volume("-3dB")
    t.set_highpass(2, FilterType.LINKWITZ_RILEY, "80", FilterSlope.DB24)
    t.import_eq(2, r"C:\\presets\\my_eq.json")
"""

from ._client import FilterSlope, FilterType, TunestPC
from ._automation import TunestAutomationError
from ._launcher import TunestConnectionError

__all__ = [
    "TunestPC",
    "FilterType",
    "FilterSlope",
    "TunestConnectionError",
    "TunestAutomationError",
]

__version__ = "0.1.0"
