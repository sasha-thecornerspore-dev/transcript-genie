from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .csx import CsxSession


def _subdir(csx_path: str) -> str:
    # ".\\00000000" or "./00000000" -> "00000000"; "" -> ""
    return csx_path.lstrip(".\\/").replace("\\", "/").strip("/")


def resolve_audio_paths(session: CsxSession, disc_dir) -> list[Path]:
    disc_dir = Path(disc_dir)
    out: list[Path] = []
    for f in session.audio_files:
        sub = _subdir(f.path)
        out.append((disc_dir / sub / f.filename) if sub else (disc_dir / f.filename))
    return out


def build_wav(session, disc_dir, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path:
    out_path = Path(out_path)
    paths = resolve_audio_paths(session, disc_dir)
    # Skip segments not present on disk (e.g. bad sectors on a damaged/recovered
    # disc). The transcript will have a gap there rather than failing outright.
    present = [p for p in paths if p.exists()]
    missing = [p for p in paths if not p.exists()]
    if missing:
        import sys

        print(
            f"warning: {len(missing)} of {len(paths)} audio segments missing "
            f"(unreadable/unrecovered); stitching the rest with gaps:",
            file=sys.stderr,
        )
        for p in missing:
            print(f"  missing: {p.name}", file=sys.stderr)
    if not present:
        raise ValueError("Session has no audio segments to stitch")
    return _concat_to_wav(present, out_path, samplerate, ffmpeg)


def _concat_to_wav(paths, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path:
    """Concatenate audio files (in the given order) into one mono WAV."""
    out_path = Path(out_path)
    fd, tmp_name = tempfile.mkstemp(suffix=".txt")
    list_file = Path(tmp_name)
    try:
        # Whole body inside try/finally so the temp list file is removed even
        # if writing it (or ffmpeg) raises.
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for p in paths:
                # ffmpeg concat demuxer: escape single quotes in paths
                safe = Path(p).resolve().as_posix().replace("'", r"'\''")
                fh.write(f"file '{safe}'\n")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-ac", "1", "-ar", str(samplerate), str(out_path)],
            check=True,
        )
    finally:
        list_file.unlink(missing_ok=True)
    return out_path


AUDIO_EXTS = {".ogg", ".mp3", ".wav", ".m4a", ".flac", ".mp4", ".aac", ".wma", ".opus"}


def folder_audio_files(folder) -> list[Path]:
    """Loose audio files directly in `folder`, sorted by filename."""
    folder = Path(folder)
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS),
        key=lambda p: p.name,
    )


def stitch_folder_wav(folder, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path:
    """Stitch a folder of loose audio files (name order) into one mono WAV."""
    paths = folder_audio_files(folder)
    if not paths:
        raise ValueError(f"No audio files found in {folder}")
    return _concat_to_wav(paths, out_path, samplerate, ffmpeg)


def ffmpeg_decode_cmd(input_path, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> list[str]:
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(Path(input_path).resolve()),
        "-ac", "1", "-ar", str(samplerate), str(out_path),
    ]


def decode_to_wav(input_path, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path:
    out_path = Path(out_path)
    subprocess.run(ffmpeg_decode_cmd(input_path, out_path, samplerate, ffmpeg), check=True)
    return out_path
