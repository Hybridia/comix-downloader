"""
Build "Comix Downloader.app" — open the GUI with a double-click instead of
a terminal command.

    python scripts/make_mac_app.py            # installs into /Applications
    python scripts/make_mac_app.py ~/Desktop  # or anywhere else

The bundle is a thin launcher: it runs gui/main.py from THIS checkout with
its .venv, so code changes need no rebuild (only moving the folder does).
Output goes to ~/Library/Logs/ComixDownloader.log.
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Comix Downloader"

LAUNCHER = """#!/bin/bash
# Comix Downloader — built by scripts/make_mac_app.py
cd "{root}" || exit 1
mkdir -p "$HOME/Library/Logs"
exec "{python}" gui/main.py >> "$HOME/Library/Logs/ComixDownloader.log" 2>&1
"""


def build_app(dest: Path) -> Path:
    app = Path(dest).expanduser() / f"{NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    exe = app / "Contents" / "MacOS" / "launcher"
    exe.write_text(LAUNCHER.format(root=ROOT, python=ROOT / ".venv" / "bin" / "python"))
    exe.chmod(0o755)
    shutil.copy2(ROOT / "gui" / "resources" / "AppIcon.icns", app / "Contents" / "Resources" / "AppIcon.icns")
    info = {
        "CFBundleName": NAME, "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": "com.hybridia.comixdownloader",
        "CFBundleExecutable": "launcher", "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
    }
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    return app


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Applications")
    built = build_app(target)
    # Tell Finder / Launchpad about the (new) icon right away.
    subprocess.run(["touch", str(built)])
    print(f"Built {built}")
