import os
import sys


def resource_path(relative_path: str) -> str:
    """Return the absolute path to a bundled resource.

    Works both in development (running from source) and inside a
    PyInstaller bundle (where files are extracted to sys._MEIPASS).
    """
    try:
        # PyInstaller extracts bundled data to a temp folder in sys._MEIPASS
        base = sys._MEIPASS                          # type: ignore[attr-defined]
    except AttributeError:
        # Development mode — project root is one level above this utils/ folder
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

