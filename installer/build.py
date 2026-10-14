"""Build "Install Penwise.app", zipped: the one download that sets up Penwise on a Mac.

    python installer/build.py      # → dist/Install-Penwise.zip

The app is install.sh with this version of Penwise (a wheel) next to it.
"""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Install Penwise"
ZIP_NAME = "Install-Penwise.zip"


def build_wheel(out: Path) -> Path:
    if shutil.which("uv"):
        command = ["uv", "build", "--wheel", "--out-dir", str(out), str(ROOT)]
    else:
        command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(out), str(ROOT)]
    subprocess.run(command, check=True, capture_output=True)
    return next(out.glob("penwise-*.whl"))


def info_plist(version: str) -> dict:
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "io.github.luckyletter.penwise.installer",
        "CFBundleExecutable": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "LSUIElement": True,  # no Dock icon: it only shows dialogs
    }


def build(dist: Path) -> Path:
    """Write the zipped app to `dist` and return its path."""
    with tempfile.TemporaryDirectory() as temp:
        wheel = build_wheel(Path(temp) / "wheel")
        version = wheel.name.split("-")[1]  # penwise-1.2.3-py3-none-any.whl
        app = Path(temp) / f"{APP_NAME}.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Resources").mkdir()
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info_plist(version)))
        executable = app / "Contents" / "MacOS" / APP_NAME
        shutil.copyfile(ROOT / "installer" / "install.sh", executable)
        executable.chmod(0o755)
        shutil.copyfile(wheel, app / "Contents" / "Resources" / wheel.name)

        dist.mkdir(parents=True, exist_ok=True)
        archive = dist / ZIP_NAME
        # ZipFile.write keeps each file's mode, and the Mac keeps it when unzipping: the app's
        # script stays executable.
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted([app, *app.rglob("*")]):
                zipped.write(path, path.relative_to(app.parent))
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist", help="where to put the zip (default: dist)")
    print(build(parser.parse_args(argv).dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
