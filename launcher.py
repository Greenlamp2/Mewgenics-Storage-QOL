"""
Mewgenics Storage QOL — Auto-update Launcher

1. Checks GitHub Releases API for a newer version.
2. If found, asks the user via a native Windows dialog.
3. Downloads the new installer to %TEMP% and runs it, then exits.
4. Otherwise (or if user skips), launches MewgenicsStorageQOL.exe.

Uses only the standard library + ctypes so the frozen exe stays tiny.
"""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# ── configuration ─────────────────────────────────────────────────────────────
try:
    from version import APP_VERSION, GITHUB_REPO
except ImportError:
    APP_VERSION = "v0.0.0"
    GITHUB_REPO = ""

CURRENT_VERSION: str = APP_VERSION.lstrip("v")
GITHUB_API_URL: str = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
MAIN_EXE: str = "MewgenicsStorageQOL.exe"
APP_TITLE: str = "Mewgenics Storage QOL"

# ── native Windows dialogs (no Qt needed) ─────────────────────────────────────
_MB_YESNO: int = 0x04
_MB_ICONINFO: int = 0x40
_MB_ICONERROR: int = 0x10
_IDYES: int = 6


def _msgbox(title: str, text: str, style: int = 0) -> int:
    """Thin wrapper around MessageBoxW."""
    return ctypes.windll.user32.MessageBoxW(None, text, title, style)


# ── helpers ───────────────────────────────────────────────────────────────────
def _parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0, 0, 0)


# ── update check ──────────────────────────────────────────────────────────────
def check_for_update() -> tuple | None:
    """Return (latest_version, download_url) if a newer release exists, else None."""
    if not GITHUB_REPO or GITHUB_REPO.startswith("YOUR_"):
        return None
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": "MewgenicsStorageQOL-Launcher/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        latest: str = data["tag_name"].lstrip("v")
        if _parse_version(latest) <= _parse_version(CURRENT_VERSION):
            return None

        for asset in data.get("assets", []):
            name: str = asset.get("name", "")
            if name.lower().endswith(".exe") and "setup" in name.lower():
                return latest, asset["browser_download_url"]
    except Exception:
        pass
    return None


def _prompt_update(version: str) -> bool:
    result = _msgbox(
        f"{APP_TITLE} — Update Available",
        (
            f"Version v{version} is available.\n"
            f"You have v{CURRENT_VERSION}.\n\n"
            "Download and install the update now?"
        ),
        _MB_YESNO | _MB_ICONINFO,
    )
    return result == _IDYES


def _download_installer(url: str, version: str) -> str | None:
    """Download the installer to %TEMP%. Returns local path or None on error."""
    tmp = os.path.join(
        tempfile.gettempdir(),
        f"MewgenicsStorageQOL_Setup_v{version}.exe",
    )
    try:
        # Simple blocking download — no progress bar to keep the launcher tiny.
        # A "Downloading…" dialog would need Win32 TaskDialog; skip for now.
        urllib.request.urlretrieve(url, tmp)
        return tmp
    except Exception as exc:
        _msgbox(APP_TITLE, f"Download failed:\n{exc}", _MB_ICONERROR)
        return None


# ── app launch ────────────────────────────────────────────────────────────────
def _launch_main_app() -> None:
    """Start MewgenicsStorageQOL.exe from the same directory as the launcher."""
    if getattr(sys, "frozen", False):
        # Frozen (PyInstaller): launcher.exe and app.exe share the same folder.
        base = Path(sys.executable).parent
        exe = base / MAIN_EXE
    else:
        # Development: run main.py with the current Python interpreter.
        exe = None

    if exe and exe.exists():
        subprocess.Popen([str(exe)])
    else:
        here = Path(__file__).resolve().parent
        subprocess.Popen([sys.executable, str(here / "main.py")])


# ── entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    update = check_for_update()
    if update:
        latest_version, download_url = update
        if _prompt_update(latest_version):
            path = _download_installer(download_url, latest_version)
            if path:
                # Run the installer and let it handle the rest.
                subprocess.Popen([path])
                sys.exit(0)

    _launch_main_app()


if __name__ == "__main__":
    main()

