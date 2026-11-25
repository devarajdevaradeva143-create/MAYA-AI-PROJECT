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
    a.binaries,
    a.datas,
    [],
    name='mayaai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
