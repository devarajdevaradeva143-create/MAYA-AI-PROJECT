# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
JARVIS_ROOT = os.path.join(PROJECT_ROOT, "JARVIS")
INTEL_ROOT = os.path.join(PROJECT_ROOT, "MAYA INTELLIGENCE")

# Vosk ships native DLLs next to its __init__.py; collect them all so the
# frozen build can load libvosk.dll.
vosk_datas, vosk_binaries, vosk_hidden = collect_all("vosk")
# Kuyil TTS deps: cmudict ships data files + metadata; uraikal too.
cmudict_datas, cmudict_binaries, cmudict_hidden = collect_all("cmudict")
uraikal_datas, uraikal_binaries, uraikal_hidden = collect_all("uraikal")
onnx_datas, onnx_binaries, onnx_hidden = collect_all("onnxruntime")

a = Analysis(
    ['app\\main.py'],
    pathex=[JARVIS_ROOT, INTEL_ROOT],
    binaries=vosk_binaries + cmudict_binaries + uraikal_binaries + onnx_binaries,
    datas=[
        (INTEL_ROOT, "MAYA INTELLIGENCE"),
    ] + vosk_datas + cmudict_datas + uraikal_datas + onnx_datas,
    hiddenimports=[
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
        'custom', 'custom.intelligence_bridge',
        'maya_intelligence', 'maya_intelligence.orchestrator',
        'maya_intelligence.language', 'maya_intelligence.adapters',
        'maya_intelligence.engines', 'maya_intelligence.engines.skills',
        'maya_intelligence.memory', 'maya_intelligence.config',
        'numpy', 'numpy._core', 'numpy._core._exceptions', 'numpy._core._multiarray_umath',
        'numpy.core', 'numpy.core.multiarray',
        'vosk',
        'cmudict', 'uraikal', 'uraikal.numbers',
        'torch', 'onnxruntime', 'safetensors', 'safetensors.torch',
        'scipy', 'soundfile',
    ] + vosk_hidden + cmudict_hidden + uraikal_hidden + onnx_hidden,
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
