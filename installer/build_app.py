"""Build Penwise.app: everything Penwise needs inside it, so setting it up downloads nothing.

    python installer/build_app.py            # → dist/Penwise.dmg (or, without the tools for it, dist/Penwise.zip)

Inside the app: Python (python-build-standalone), with a program for Apple and one for Intel Macs
sharing one library, Penwise and the little it needs, and Hammerspoon (as it is released,
signature and all), which gives Penwise its shortcut. The app's script (installer/app/launcher.sh)
sets them up the first time it opens.

The disk image is compressed with LZMA, the strongest compression macOS opens: on a Mac with
hdiutil; elsewhere with mkfs.hfsplus (hfsprogs) and the `hfsplus` and `dmg` tools of
https://github.com/mozilla/libdmg-hfsplus (built with liblzma), found on the PATH or in
PENWISE_DMG_TOOLS. On a Mac, PENWISE_SIGN_IDENTITY ("Developer ID Application: …") signs the app,
and PENWISE_NOTARY_PROFILE (a `xcrun notarytool store-credentials` profile) has Apple notarize it:
then it opens like any app from the internet, without a trip to Privacy & Security.
"""

from __future__ import annotations

import argparse
import math
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "Penwise.app"
BUNDLE_ID = "io.github.luckyletter.penwise"
MIN_MACOS = "13.0"  # what Hammerspoon 1.1 needs
PYTHON = "3.13.14"
PYTHON_RELEASE = "20260718"
PYTHON_URL = (
    "https://releases.astral.sh/github/python-build-standalone/releases/download/"
    "{release}/cpython-{version}%2B{release}-{arch}-apple-darwin-install_only_stripped.tar.gz"
)
ARCHES = {"arm64": "aarch64", "x86_64": "x86_64"}  # macOS's name: python-build-standalone's
HAMMERSPOON = "1.1.1"
HAMMERSPOON_URL = "https://github.com/Hammerspoon/hammerspoon/releases/download/{0}/Hammerspoon-{0}.zip"
# Parts of Python Penwise never uses: the Tk toolkit for windows, IDLE, and the like. And the
# library form of Python, for programs that embed it: the `python3` program has all of it in itself.
UNUSED = [
    "lib/libpython3.13.dylib",
    "lib/pkgconfig",
    "lib/python3.13/config-3.13-darwin",
    "include",
    "share",
    "lib/tcl9.0",
    "lib/tcl9",
    "lib/tk9.0",
    "lib/itcl4.3.5",
    "lib/thread3.0.4",
    "lib/libtcl9.0.dylib",
    "lib/libtcl9tk9.0.dylib",
    "lib/python3.13/tkinter",
    "lib/python3.13/idlelib",
    "lib/python3.13/turtledemo",
    "lib/python3.13/ensurepip",
    "lib/python3.13/pydoc_data",
    "lib/python3.13/unittest",
    "lib/python3.13/site-packages",  # pip: Penwise's updates unpack themselves
]
UNUSED_MODULES = ("_tkinter", "_dbm")  # compiled ones, in lib-dynload (which Python needs, even empty)
# What Penwise uses of Python's own library, beyond what importing it loads: compiled ahead.
USED = (
    "argparse concurrent.futures dataclasses datetime difflib email.parser hashlib http.client "
    "importlib.metadata json platform plistlib shutil socket ssl subprocess tempfile tomllib "
    "unicodedata urllib.request xml.etree.ElementTree zipfile compileall py_compile"
)


def build_wheel(out: Path) -> Path:
    """This version of Penwise as a wheel, in `out`."""
    if shutil.which("uv"):
        command = ["uv", "build", "--wheel", "--out-dir", str(out), str(ROOT)]
    else:
        command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(out), str(ROOT)]
    subprocess.run(command, check=True, capture_output=True)
    return next(out.glob("penwise-*.whl"))


def download(url: str, cache: Path) -> Path:
    """The file at `url`, downloaded once into `cache`."""
    path = cache / urllib.request.url2pathname(url.rsplit("/", 1)[-1]).replace("%2B", "+")
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        # A name of its own: releases.astral.sh refuses Python's ("Python-urllib", 403).
        request = urllib.request.Request(url, headers={"User-Agent": "penwise-build"})
        with urllib.request.urlopen(request, timeout=300) as response:
            part = path.with_suffix(".part")
            part.write_bytes(response.read())
            part.rename(path)
    return path


def add_python(resources: Path, arches: tuple[str, ...], cache: Path) -> None:
    """Python in Resources/python: bin/python3-arm64 and bin/python3-x86_64, one program for each
    kind of Mac, and one library for both. The two builds differ only in their programs (and in
    what Python knows of how it was built, which Penwise never asks)."""
    target = resources / "python"
    for mac_arch in arches:
        url = PYTHON_URL.format(release=PYTHON_RELEASE, version=PYTHON, arch=ARCHES[mac_arch])
        with tempfile.TemporaryDirectory() as temp, tarfile.open(download(url, cache)) as archive:
            archive.extractall(temp, filter="tar")  # links stay links
            if not target.exists():
                shutil.move(Path(temp) / "python", target)
                program = target / "bin" / "python3.13"
            else:
                program = Path(temp) / "python" / "bin" / "python3.13"
            shutil.move(program, target / "bin" / f"python3-{mac_arch}")
    for path in (target / "bin").iterdir():  # pip, idle, and links to the program
        if not path.name.startswith("python3-") or path.name.endswith("-config"):
            path.unlink()
    for part in UNUSED:
        path = target / part
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    for module in UNUSED_MODULES:
        for path in (target / "lib" / "python3.13" / "lib-dynload").glob(module + ".*"):
            path.unlink()


def add_hammerspoon(resources: Path, cache: Path) -> None:
    """Hammerspoon, zipped as it is released but stored, not compressed: the disk image compresses
    it much better (LZMA). Each entry as it was, links and modes too, for `ditto -x -k`."""
    released = download(HAMMERSPOON_URL.format(HAMMERSPOON), cache)
    with zipfile.ZipFile(released) as source, zipfile.ZipFile(resources / "Hammerspoon.zip", "w") as stored:
        for entry in source.infolist():
            data = source.read(entry)
            entry.compress_type = zipfile.ZIP_STORED
            stored.writestr(entry, data)
    (resources / "hammerspoon-version").write_text(HAMMERSPOON + "\n")


def add_penwise(resources: Path, wheel: Path) -> None:
    """Penwise and what it needs: pure Python, so one copy serves both Pythons."""
    lib = str(resources / "lib")
    if shutil.which("uv"):
        command = ["uv", "pip", "install", "--quiet", "--target", lib, "--python-version", "3.13"]
        command += ["--python-platform", "aarch64-apple-darwin", str(wheel)]
    else:
        command = [sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--target", lib]
        command += ["--python-version", "3.13", "--platform", "macosx_13_0_universal2", "--only-binary=:all:"]
        command += [str(wheel)]
    subprocess.run(command, check=True)
    shutil.rmtree(resources / "lib" / "bin", ignore_errors=True)  # commands for the Python that built it


# Run by a Python 3.13 (the app's version): compile Penwise, and the parts of Python's library it
# uses (the modules importing it all loads), into `python3.13` folders given after the library.
COMPILE = """
import importlib, importlib.util, os, pkgutil, py_compile, sys
lib, *stdlibs = sys.argv[1:]
sys.path.insert(0, lib)
import penwise
for module in pkgutil.iter_modules(penwise.__path__, "penwise."):
    if module.name != "penwise.__main__":  # that one runs Penwise
        importlib.import_module(module.name)
for name in USED.split():
    importlib.import_module(name)
mode = py_compile.PycInvalidationMode.UNCHECKED_HASH
import compileall
compileall.compile_dir(lib, quiet=1, invalidation_mode=mode)
for stdlib in stdlibs:
    for name in sorted(sys.modules):
        base = stdlib + "/" + name.replace(".", "/")
        for source in (base + ".py", base + "/__init__.py"):
            if os.path.exists(source):
                py_compile.compile(source, importlib.util.cache_from_source(source), invalidation_mode=mode)
"""


def precompile(resources: Path) -> None:
    """Compile Penwise and the parts of Python it uses now: the app never writes in itself (that
    would break its signature), so without this every start would compile them again.
    "unchecked-hash": the compiled files hold however the files' times change in the zip."""
    stdlibs = [str(resources / "python" / "lib" / "python3.13")]
    if sys.version_info[:2] == (3, 13):
        python = [sys.executable]
    elif shutil.which("uv"):
        python = ["uv", "run", "--no-project", "--python", "3.13", "python"]
    else:
        print("No Python 3.13 here to compile with: Penwise.app will start a little slower.")
        return
    code = COMPILE.replace("USED.split()", repr(USED.split()))
    subprocess.run([*python, "-c", code, str(resources / "lib"), *stdlibs], check=True)


def info_plist(version: str) -> dict:
    """What macOS reads about the app, with every key Xcode writes for one."""
    return {
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleDevelopmentRegion": "en",
        "CFBundleName": "Penwise",
        "CFBundleDisplayName": "Penwise",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": "Penwise",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "CFBundleIconFile": "Penwise",  # in Applications, and in the Dock while it opens
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Penwise: Apache-2.0. Python: PSF License. Hammerspoon: MIT License.",
    }


def assemble(out: Path, cache: Path, arches: tuple[str, ...] = tuple(ARCHES)) -> Path:
    """Penwise.app in `out`, for Macs with these chips (both, unless smaller is needed)."""
    with tempfile.TemporaryDirectory() as temp:
        wheel = build_wheel(Path(temp))
        version = wheel.name.split("-")[1]
        app = out / APP
        if app.exists():
            shutil.rmtree(app)
        contents = app / "Contents"
        resources = contents / "Resources"
        (contents / "MacOS").mkdir(parents=True)
        (resources / "bin").mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plistlib.dumps(info_plist(version)))
        (contents / "PkgInfo").write_text("APPL????")  # its type, for the Finder
        scripts = {"launcher.sh": contents / "MacOS" / "Penwise", "penwise.sh": resources / "bin" / "penwise"}
        for script, place in scripts.items():
            shutil.copyfile(ROOT / "installer" / "app" / script, place)
            place.chmod(0o755)
        (resources / "version").write_text(version + "\n")
        shutil.copyfile(ROOT / "installer" / "app" / "Penwise.icns", resources / "Penwise.icns")
        add_penwise(resources, wheel)
    add_python(resources, arches, cache)
    precompile(resources)
    add_hammerspoon(resources, cache)
    return app


def zip_app(app: Path, archive: Path) -> Path:
    """Zip the app as macOS does: modes kept (scripts stay runnable), links stored as links."""
    archive.unlink(missing_ok=True)
    if shutil.which("ditto"):  # on a Mac: also the signature of the app's script, kept beside it
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
        return archive
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted([app, *app.rglob("*")]):
            name = str(path.relative_to(app.parent))
            if path.is_symlink():
                info = zipfile.ZipInfo(name)
                info.create_system = 3  # Unix: the mode below is read
                info.external_attr = (stat.S_IFLNK | 0o755) << 16
                zipped.writestr(info, os.readlink(path))
            else:
                zipped.write(path, name)
    return archive


def sign(app: Path, identity: str) -> None:
    """Sign every program in the app, then the app: with the hardened runtime notarizing asks for."""
    entitlements = Path(tempfile.mkstemp(suffix=".plist")[1])
    # Python makes code at run time (ctypes) and loads its own modules.
    entitlements.write_bytes(
        plistlib.dumps(
            {
                "com.apple.security.cs.allow-unsigned-executable-memory": True,
                "com.apple.security.cs.disable-library-validation": True,
            }
        )
    )
    codesign = ["codesign", "--force", "--timestamp", "--options", "runtime", "--sign", identity]
    for path in sorted(app.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.read_bytes()[:4] in MACH_O:
            subprocess.run([*codesign, "--entitlements", str(entitlements), str(path)], check=True)
    subprocess.run([*codesign, "--entitlements", str(entitlements), str(app)], check=True)


MACH_O = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def make_dmg(app: Path, dmg: Path, identity: str = "", notary_profile: str = "") -> Path | None:
    """A disk image with Penwise and a link to Applications, to drag it into: compressed with LZMA,
    which macOS 10.15 and later open. None when this computer has no way to make one."""
    dmg.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / "Penwise"
        stage.mkdir()
        # Its window: big icons, Penwise on the left, Applications on the right (make_dmg_window.py).
        shutil.copyfile(ROOT / "installer" / "app" / "dmg.DS_Store", stage / ".DS_Store")
        # Its icon on the desktop once opened: Penwise's (with the "custom icon" flag, set below).
        shutil.copyfile(ROOT / "installer" / "app" / "Penwise.icns", stage / ".VolumeIcon.icns")
        if shutil.which("hdiutil"):  # as Firefox's is made on a Mac
            subprocess.run(["ditto", str(app), str(stage / APP)], check=True)
            (stage / "Applications").symlink_to("/Applications")
            if shutil.which("SetFile"):
                subprocess.run(["SetFile", "-a", "C", str(stage)], check=True)
            hybrid = Path(temp) / "hybrid.dmg"
            make = ["hdiutil", "makehybrid", "-hfs", "-hfs-volume-name", "Penwise", "-hfs-openfolder", str(stage)]
            subprocess.run([*make, "-ov", str(stage), "-o", str(hybrid)], check=True)
            subprocess.run(["hdiutil", "convert", "-format", "ULMO", "-ov", str(hybrid), "-o", str(dmg)], check=True)
        else:
            shutil.copytree(app, stage / APP, symlinks=True)
            (stage / "Applications").symlink_to("/Applications")
            if not hfs_dmg(stage, dmg, Path(temp) / "Penwise.hfs"):
                return None
    if identity:
        subprocess.run(["codesign", "--force", "--timestamp", "--sign", identity, str(dmg)], check=True)
    if notary_profile:
        notarize(dmg, notary_profile)
    return dmg


DMG_TOOLS = ("mkfs.hfsplus", "hfsplus", "dmg")


def hfs_dmg(folder: Path, dmg: Path, image: Path) -> bool:
    """The disk image without a Mac, as Firefox's is made: an HFS+ volume with `folder` in it (links
    and modes kept), compressed into a disk image. False when the tools aren't here."""
    search = os.pathsep.join([os.environ.get("PENWISE_DMG_TOOLS", ""), os.environ.get("PATH", ""), "/usr/sbin:/sbin"])
    tools = {name: shutil.which(name, path=search) for name in DMG_TOOLS}
    if not all(tools.values()):
        missing = ", ".join(name for name, path in tools.items() if not path)
        print(f"No disk image: {missing} not found (see the top of installer/build_app.py).")
        return False
    # Room for every file, in 4 KB blocks, and then some: empty space compresses to nothing.
    used = sum(math.ceil(path.lstat().st_size / 4096) * 4096 + 4096 for path in folder.rglob("*"))
    with open(image, "wb") as file:
        file.truncate(math.ceil((used * 1.25 + 16 * 2**20) / 2**20) * 2**20)
    quiet = {"check": True, "stdout": subprocess.DEVNULL}
    subprocess.run([tools["mkfs.hfsplus"], "-v", "Penwise", str(image)], **quiet)
    addall = [tools["hfsplus"], "--symlinks", "clone_link", "--special-modes", "no", str(image), "addall", str(folder)]
    subprocess.run(addall, **quiet)
    subprocess.run([tools["hfsplus"], str(image), "attr", "/", "C"], **quiet)  # the volume's own icon
    # Firefox's settings: LZMA at level 5, in chunks of 1 MB (2048 sectors).
    compress = ["--compression", "lzma", "--level", "5", "--run-sectors", "2048"]
    subprocess.run([tools["dmg"], *compress, "build", str(image), str(dmg)], **quiet)
    return True


def notarize(path: Path, profile: str) -> None:
    """Have Apple check it, and attach its answer, so it opens even offline."""
    submit = path
    if path.suffix == ".app":  # Apple takes an app zipped
        submit = path.with_suffix(".notarize.zip")
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(path), str(submit)], check=True)
    subprocess.run(["xcrun", "notarytool", "submit", str(submit), "--keychain-profile", profile, "--wait"], check=True)
    subprocess.run(["xcrun", "stapler", "staple", str(path)], check=True)
    if submit != path:
        submit.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist", help="where to put it (default: dist)")
    parser.add_argument("--cache", type=Path, default=ROOT / "build" / "cache", help="downloads, kept for next time")
    parser.add_argument("--chip", choices=["apple", "intel"], help="for one kind of Mac only: a smaller download")
    parser.add_argument("--zip", action="store_true", help="also zip the app, as earlier versions came")
    args = parser.parse_args(argv)
    args.dist.mkdir(parents=True, exist_ok=True)
    arches = {"apple": ("arm64",), "intel": ("x86_64",)}.get(args.chip, tuple(ARCHES))
    app = assemble(args.dist, args.cache, arches)
    identity = os.environ.get("PENWISE_SIGN_IDENTITY", "")
    profile = os.environ.get("PENWISE_NOTARY_PROFILE", "")
    if identity:
        sign(app, identity)
        if profile:
            notarize(app, profile)  # the app too: once dragged out of the disk image it stands alone
    name = {"apple": "Penwise-Apple-chip", "intel": "Penwise-Intel"}.get(args.chip, "Penwise")
    dmg = make_dmg(app, args.dist / f"{name}.dmg", identity, profile)
    if dmg:
        print(dmg)
    if args.zip or not dmg:
        print(zip_app(app, args.dist / f"{name}.zip"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
