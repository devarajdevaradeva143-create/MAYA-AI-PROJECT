# -*- mode: python ; coding: utf-8 -*-

import os

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
JARVIS_ROOT = os.path.join(PROJECT_ROOT, "JARVIS")
INTEL_ROOT = os.path.join(PROJECT_ROOT, "MAYA INTELLIGENCE")

a = Analysis(
    ['app\\main.py'],
    pathex=[JARVIS_ROOT, INTEL_ROOT],
    binaries=[],
    datas=[
        (INTEL_ROOT, "MAYA INTELLIGENCE"),
    ],
    hiddenimports=[
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
        'custom', 'custom.intelligence_bridge',
        'maya_intelligence', 'maya_intelligence.orchestrator',
        'maya_intelligence.language', 'maya_intelligence.adapters',
        'maya_intelligence.engines', 'maya_intelligence.engines.skills',
        'maya_intelligence.memory', 'maya_intelligence.config',
        'numpy', 'numpy._core', 'numpy._core._exceptions', 'numpy._core._multiarray_umath',
        'numpy._core.multiarray', 'numpy.core', 'numpy.core.multiarray',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mayaai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# One-folder build: no per-launch extraction to %TEMP%, so the app opens fast.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='mayaai',
)
