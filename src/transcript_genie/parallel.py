"""Parallel transcription: split the stitched WAV into N time-chunks and run one
faster-whisper worker process per chunk, then merge with time offsets.

CPU-bound ASR scales close to linearly with cores this way. Each worker loads
its own model, so keep `jobs` <= physical cores and mind RAM (each `small`
int8 model is ~0.5-1 GB).
"""

from __future__ import annotations

import os
import subprocess
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .asr import whisper_segments_to_model
from .model import Segment


def wav_duration(path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def split_plan(duration: float, n: int) -> list[tuple[float, float]]:
    """Return n (start, length) pairs covering [0, duration] without gaps."""
    n = max(1, int(n))
    step = duration / n
    plan = []
    for i in range(n):
        start = i * step
        length = (duration - start) if i == n - 1 else step
        plan.append((start, length))
    return plan


def _write_chunk(wav, start: float, length: float, out, ffmpeg: str) -> Path:
    out = Path(out)
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(wav),
            "-ac", "1", "-ar", "16000", str(out),
        ],
        check=True,
    )
    return out


def _worker(chunk_path: str, offset: float, model_size: str,
            glossary: list[str] | None, cpu_threads: int) -> list[Segment]:
    """Runs in a separate process: load a model, transcribe one chunk, offset."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=cpu_threads)
    prompt = ", ".join(glossary) if glossary else None
    raw, _info = model.transcribe(
        str(chunk_path), word_timestamps=True, initial_prompt=prompt, vad_filter=True
    )
    segs = whisper_segments_to_model(raw)
    for s in segs:
        s.start += offset
        s.end += offset
        for w in s.words:
            w.start += offset
            w.end += offset
    return segs


def transcribe_parallel(
    wav_path,
    model_size: str = "small",
    jobs: int = 4,
    glossary: list[str] | None = None,
    ffmpeg: str = "ffmpeg",
    cpu_threads: int | None = None,
    workdir=None,
    progress=None,
) -> list[Segment]:
    """Transcribe `wav_path` using `jobs` parallel worker processes."""
    wav_path = Path(wav_path)
    workdir = Path(workdir) if workdir else wav_path.parent
    jobs = max(1, int(jobs))
    duration = wav_duration(wav_path)
    plan = split_plan(duration, jobs)
    if cpu_threads is None:
        cpu_threads = max(1, (os.cpu_count() or 4) // jobs)

    chunks: list[tuple[Path, float]] = []
    for i, (start, length) in enumerate(plan):
        chunk = _write_chunk(wav_path, start, length, workdir / f"chunk_{i:02d}.wav", ffmpeg)
        chunks.append((chunk, start))

    if jobs == 1:
        return _worker(str(chunks[0][0]), chunks[0][1], model_size, glossary, cpu_threads)

    segments: list[Segment] = []
    done = 0
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futures = [
            ex.submit(_worker, str(c), off, model_size, glossary, cpu_threads)
            for c, off in chunks
        ]
        for fut in futures:
            segments.extend(fut.result())
            done += 1
            if progress:
                progress(done, jobs)

    segments.sort(key=lambda s: s.start)
    return segments
