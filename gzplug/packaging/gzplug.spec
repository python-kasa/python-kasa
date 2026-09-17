# PyInstaller spec for the bench plug controller.
#
# One-DIR, shipped as a zip -- deliberately not one-file. A one-file build
# re-extracts itself into %TEMP% on every launch, which is slow and gets
# scanned by AV each time on a locked-down bench PC.
#
# Build:  pyinstaller gzplug/packaging/gzplug.spec --noconfirm
# Output: dist/gzplug/gzplug[.exe]

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# SPECPATH is the directory holding this file (gzplug/packaging), so the
# repository root is two levels up.
ROOT = Path(SPECPATH).resolve().parents[1]

datas = [
    # web_dir() looks under sys._MEIPASS for exactly this layout.
    (str(ROOT / "gzplug" / "web"), "gzplug/web"),
]

# kasa/__init__.py calls importlib.metadata.version("python-kasa") at import
# time. Without the distribution metadata in the bundle that raises
# PackageNotFoundError before anything else runs, and the executable dies on
# startup with no useful message.
datas += copy_metadata("python-kasa")

# uvicorn resolves its loop, protocol and lifespan implementations by name at
# runtime, so static analysis cannot see them. websockets is what makes the
# WebSocket upgrade work at all -- without it the server answers /ws with 404
# and the page silently never updates.
hiddenimports = [
    *collect_submodules("uvicorn"),
    *collect_submodules("kasa"),
    "websockets",
    "websockets.asyncio",
    "websockets.legacy",
]

a = Analysis(
    [str(ROOT / "gzplug" / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "IPython", "tkinter", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gzplug",
    debug=False,
    strip=False,
    upx=False,  # UPX-packed binaries trip corporate AV more often than not.
    console=True,  # The window shows the URL and stops the server on Ctrl-C.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="gzplug",
)
