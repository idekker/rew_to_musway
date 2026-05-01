r"""musway - Python automation library for Musway.

Public surface::

    from musway import Musway

Example::

    m = Musway()
    m.connect(r"D:\\Program Files (x86)\\TUNEST PC\\Musway Software-240813.exe")
    m.set_master_mute(True)
    m.load_preset(r"C:\\presets\\presets.txt")
"""

from ._client import Musway, MuswayBadStateError, MuswayUnknownWindowStateError

__all__ = [
    "Musway",
    "MuswayBadStateError",
    "MuswayUnknownWindowStateError",
]

__version__ = "0.1.0"
