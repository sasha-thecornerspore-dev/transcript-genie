import json
from dataclasses import asdict

from transcript_genie import parallel
from transcript_genie.model import Segment
from transcript_genie.parallel import resolve_pace


def test_resolve_pace_variants():
    assert resolve_pace("aggressive", 8) == (7, 2, False)
    assert resolve_pace("background", 8) == (2, 1, True)
    assert resolve_pace("balanced", 8) == (4, 2, False)


def test_resolve_pace_clamps_to_one():
    jobs, threads, low = resolve_pace("background", 2)
    assert jobs >= 1 and threads >= 1


def test_resume_uses_cached_chunks_without_running_worker(tmp_path, monkeypatch):
    # No ffmpeg / no whisper: fake duration + chunk writing, pre-seed both caches.
    monkeypatch.setattr(parallel, "wav_duration", lambda p: 20.0)
    monkeypatch.setattr(parallel, "_write_chunk", lambda wav, s, l, out, ff: __import__("pathlib").Path(out))

    for i, seg in enumerate([Segment(0.0, 1.0, "first"), Segment(10.0, 11.0, "second")]):
        (tmp_path / f"chunk_{i:02d}.segs.json").write_text(json.dumps([asdict(seg)]), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("worker ran despite a cached chunk")

    monkeypatch.setattr(parallel, "_worker", _boom)

    seen = []
    segs = parallel.transcribe_parallel(
        tmp_path / "x.wav", jobs=2, workdir=tmp_path, progress=lambda d, t: seen.append((d, t))
    )
    assert [s.text for s in segs] == ["first", "second"]   # merged in time order, from cache
    assert seen and seen[-1] == (2, 2)                      # progress reported completion
