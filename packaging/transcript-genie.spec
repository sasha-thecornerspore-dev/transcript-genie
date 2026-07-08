# PyInstaller spec — standalone Transcript Genie CLI (core transcription).
#
# Bundles faster-whisper + its native deps (ctranslate2, av, onnxruntime,
# tokenizers) and the package. The heavy diarization stack (torch/speechbrain)
# is intentionally EXCLUDED to keep the binary a reasonable size — acoustic
# diarization (--refine / generic --diarize) requires the pip package with the
# `[diarize]` extra. ffmpeg must be on PATH.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers", "huggingface_hub"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# scikit-learn pulls a few dynamically-loaded submodules PyInstaller can miss.
hiddenimports += [
    "sklearn.utils._typedefs",
    "sklearn.utils._heap",
    "sklearn.utils._sorting",
    "sklearn.neighbors._partition_nodes",
]

a = Analysis(
    # Paths in a .spec are resolved relative to the spec file's directory.
    ["entry.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "speechbrain", "matplotlib", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="transcript-genie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
