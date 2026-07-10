"""Parallel, resumable transcription with a CPU pace control.

Splits the stitched WAV into N time-chunks and runs one faster-whisper worker
process per chunk, merging with time offsets. Each finished chunk is
checkpointed to disk, so an interrupted run resumes instead of restarting. A
`pace` picks how many cores to use and whether to run at low OS priority.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from .asr import whisper_segments_to_model
from .model import Segment, Word


# ----- pace / CPU control -------------------------------------------------

def resolve_pace(pace: str, cpu_count: int | None = None) -> tuple[int, int, bool]:
    """Map a pace name to (jobs, cpu_threads_per_worker, low_priority)."""
    n = cpu_count or (os.cpu_count() or 4)
    if pace == "aggressive":
        return max(1, n - 1), 2, False
    if pace == "background":
        return max(1, n // 4), 1, True
    # balanced (default)
    return max(1, n // 2), 2, False


def set_low_priority() -> None:
    """Best-effort: drop this process to below-normal scheduling priority."""
    try:
        if sys.platform == "win32":
            import ctypes

            below_normal = 0x00004000
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), below_normal)
        else:
            os.nice(10)
    except Exception:
        pass


# ----- audio splitting ----------------------------------------------------

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


# ----- checkpoint (segment <-> json) --------------------------------------

def _seg_from_dict(d: dict) -> Segment:
    return Segment(
        d["start"], d["end"], d["text"], d.get("speaker_id"),
        [Word(**w) for w in d.get("words", [])],
    )


def _load_cache(path: Path) -> list[Segment]:
    return [_seg_from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


# ----- worker -------------------------------------------------------------

def _worker(chunk_path, offset, model_size, glossary, cpu_threads, cache_path, low_priority):
    """Runs in a separate process: transcribe one chunk, offset, checkpoint."""
    if low_priority:
        set_low_priority()
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
    if cache_path:
        Path(cache_path).write_text(
            json.dumps([asdict(s) for s in segs]), encoding="utf-8"
        )
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
    resume: bool = True,
    low_priority: bool = False,
) -> list[Segment]:
    """Transcribe `wav_path` with `jobs` worker processes, resumably.

    `progress(done, total)` is called after each chunk completes (including
    cached ones on resume). Finished chunks are cached to
    `<workdir>/chunk_NN.segs.json`; a re-run with `resume=True` reuses them.
    """
    wav_path = Path(wav_path)
    workdir = Path(workdir) if workdir else wav_path.parent
    jobs = max(1, int(jobs))
    duration = wav_duration(wav_path)
    plan = split_plan(duration, jobs)
    if cpu_threads is None:
        cpu_threads = max(1, (os.cpu_count() or 4) // jobs)

    chunks = []
    for i, (start, length) in enumerate(plan):
        chunk = _write_chunk(wav_path, start, length, workdir / f"chunk_{i:02d}.wav", ffmpeg)
        chunks.append((chunk, start))
    total = len(chunks)

    results: dict[int, list[Segment]] = {}
    todo = []
    for i, (chunk, offset) in enumerate(chunks):
        cache = workdir / f"chunk_{i:02d}.segs.json"
        if resume and cache.exists():
            results[i] = _load_cache(cache)
        else:
            todo.append((i, str(chunk), offset, str(cache)))
    if progress:
        progress(len(results), total)

    if todo:
        if jobs == 1:
            for i, chunk, offset, cache in todo:
                results[i] = _worker(chunk, offset, model_size, glossary, cpu_threads, cache, low_priority)
                if progress:
                    progress(len(results), total)
        else:
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                fut_index = {
                    ex.submit(_worker, chunk, offset, model_size, glossary, cpu_threads, cache, low_priority): i
                    for (i, chunk, offset, cache) in todo
                }
                for fut in as_completed(fut_index):
                    results[fut_index[fut]] = fut.result()
                    if progress:
                        progress(len(results), total)

    segments: list[Segment] = []
    for i in range(total):
        segments.extend(results.get(i, []))
    segments.sort(key=lambda s: s.start)
    return segments
