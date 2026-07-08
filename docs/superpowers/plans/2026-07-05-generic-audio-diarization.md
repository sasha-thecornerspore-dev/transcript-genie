# Transcript Genie — Plan 2: Generic Audio Ingest + Diarization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Transcribe ANY audio/video file (no CourtSmart log) into a speaker-diarized, timestamped transcript + DOCX, reusing the existing ASR and DOCX engine. The CLI auto-detects: a folder with `Sessions.csx` → the existing CourtSmart path; any media file → the new generic path.

**Architecture:** Add `media.decode_to_wav` (single-file decode→mono 16 kHz), a new `diarize` module (SpeechBrain ECAPA speaker embeddings + agglomerative clustering, behind an injectable `Embedder` interface), a `build.build_plain_transcript` (transcript with no case metadata), conditional generic rendering in `format_docx`, and a generic branch in `cli`.

**Tech Stack:** Python 3.11 venv, faster-whisper, python-docx, **torch/torchaudio (CPU)**, **speechbrain 1.1**, **scikit-learn 1.9**, ffmpeg. All already installed in `.venv`.

## Global Constraints

- **All deps already installed** in `.venv` (Python 3.11.9): torch 2.13.0+cpu, torchaudio 2.11.0+cpu, speechbrain 1.1.0, scikit-learn 1.9.0. Do NOT install anything.
- Run everything via `& ".\.venv\Scripts\python.exe"` (never bare `python`).
- **No network/cloud in unit tests.** SpeechBrain's ECAPA model downloads only in the real run — unit tests use an injected `Embedder` and never load the model. Diarization heavy imports (`speechbrain`, `torch`) are **lazy** (inside methods), like the ASR engine.
- **Times are floats in seconds.** Audio loaded for diarization is the mono 16 kHz PCM WAV that `decode_to_wav`/`build_wav` produce; load it with the stdlib `wave` module (not torchaudio) for cross-platform robustness.
- **Do not regress Plan 1.** The CourtSmart path (`build_wav`, `build_transcript`, existing `cli` behavior with a `Sessions.csx` folder) and all 17 existing tests must still pass. `format_docx` changes must keep the existing court output (named speakers + case number) rendering appearances and `Case No.`.
- Speaker ids from diarization are `"spk1"`, `"spk2"`, … in first-appearance order; their DOCX labels are `SPEAKER 1`, `SPEAKER 2`, …
- No PII in fixtures (placeholder names/among synthetic tones).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/transcript_genie/media.py` | modify | add `decode_to_wav` (single-file decode) |
| `src/transcript_genie/diarize.py` | create | `Embedder` protocol, `EcapaEmbedder`, `cluster_segments`, `assign_speakers` |
| `src/transcript_genie/build.py` | create | `build_plain_transcript` (no case metadata) |
| `src/transcript_genie/format_docx.py` | modify | conditional generic header + skip appearances when no named speakers |
| `src/transcript_genie/cli.py` | modify | auto-detect input; generic branch; `--title`/`--diarize`/`--speakers` |
| `tests/…` | create/modify | one test per change |

---

## Task 1: `media.decode_to_wav` — decode any file to mono WAV

**Files:**
- Modify: `src/transcript_genie/media.py`
- Test: `tests/test_media_decode.py`

**Interfaces:**
- Produces:
  - `ffmpeg_decode_cmd(input_path, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> list[str]` — pure command builder.
  - `decode_to_wav(input_path, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path` — runs ffmpeg, returns `out_path`.

- [ ] **Step 1: Write the failing test** (pure command builder; no ffmpeg)

```python
from transcript_genie.media import ffmpeg_decode_cmd


def test_decode_cmd_downmixes_mono_16k():
    cmd = ffmpeg_decode_cmd("in.mp3", "out.wav", ffmpeg="ffmpeg")
    assert cmd[0] == "ffmpeg"
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[-1] == "out.wav"
    assert "in.mp3" in cmd[cmd.index("-i") + 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_media_decode.py -v`
Expected: FAIL (`ImportError: cannot import name 'ffmpeg_decode_cmd'`).

- [ ] **Step 3: Add implementation to `media.py`** (append these functions; keep existing code)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_media_decode.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/media.py tests/test_media_decode.py
git commit -m "feat: decode any audio/video file to mono WAV"
```

---

## Task 2: `diarize.cluster_segments` — pure clustering

**Files:**
- Create: `src/transcript_genie/diarize.py`
- Test: `tests/test_diarize_cluster.py`

**Interfaces:**
- Produces:
  - `cluster_segments(embeddings: list[list[float]], num_speakers: int | None = None, threshold: float = 0.75) -> list[int]` — returns a cluster label per embedding, remapped to first-appearance order (first embedding's speaker is `0`). `<=1` embedding → all zeros. Uses cosine agglomerative clustering; `num_speakers` fixes the count, else `threshold` (cosine distance) decides.

- [ ] **Step 1: Write the failing test**

```python
from transcript_genie.diarize import cluster_segments


def test_two_clear_speakers_first_appearance_order():
    # A-ish, B-ish, A-ish, B-ish embeddings (well separated)
    embs = [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1], [0.1, 0.9]]
    labels = cluster_segments(embs, num_speakers=2)
    assert labels[0] == 0            # first speaker is 0
    assert labels[1] == 1
    assert labels[0] == labels[2]    # A grouped with A
    assert labels[1] == labels[3]    # B grouped with B


def test_single_embedding_is_speaker_zero():
    assert cluster_segments([[1.0, 2.0]]) == [0]


def test_empty_returns_empty():
    assert cluster_segments([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_diarize_cluster.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation** (create `diarize.py` with the clustering only for now)

```python
from __future__ import annotations


def _remap_first_appearance(labels: list[int]) -> list[int]:
    order: dict[int, int] = {}
    out: list[int] = []
    for lab in labels:
        if lab not in order:
            order[lab] = len(order)
        out.append(order[lab])
    return out


def cluster_segments(
    embeddings: list[list[float]],
    num_speakers: int | None = None,
    threshold: float = 0.75,
) -> list[int]:
    n = len(embeddings)
    if n == 0:
        return []
    if n == 1:
        return [0]

    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    x = np.asarray(embeddings, dtype=float)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    x = x / norms

    if num_speakers is not None:
        k = max(1, min(num_speakers, n))
        model = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
    else:
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average"
        )
    labels = model.fit_predict(x).tolist()
    return _remap_first_appearance(labels)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_diarize_cluster.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/diarize.py tests/test_diarize_cluster.py
git commit -m "feat: cosine agglomerative speaker clustering"
```

---

## Task 3: `diarize` embedder + `assign_speakers`

**Files:**
- Modify: `src/transcript_genie/diarize.py`
- Test: `tests/test_diarize_assign.py`

**Interfaces:**
- Consumes: `Segment` from `model`; `cluster_segments` (Task 2).
- Produces:
  - `Embedder` (typing.Protocol): `embed(waveform, sample_rate: int) -> list[float]` where `waveform` is a 1-D numpy float array of a segment's audio.
  - `EcapaEmbedder(savedir: str = "models/ecapa")` implementing `Embedder`; lazily loads `speechbrain.inference.speaker.EncoderClassifier` on `cpu`.
  - `load_wav_mono(path) -> tuple[numpy.ndarray, int]` — reads a PCM16 mono/stereo WAV via stdlib `wave`, returns float array in [-1,1] and sample rate (downmixes stereo).
  - `assign_speakers(wav_path, segments: list[Segment], embedder: Embedder, num_speakers: int | None = None, threshold: float = 0.75) -> list[Segment]` — embeds each segment's audio slice, clusters, sets `seg.speaker_id = f"spk{label+1}"`. Empty segments list → returns it unchanged.

- [ ] **Step 1: Write the failing test** (writes a real mono 16 kHz WAV with stdlib `wave`; uses a fake embedder — no ECAPA model)

```python
import wave
import struct
import math

from transcript_genie.model import Segment
from transcript_genie.diarize import assign_speakers, load_wav_mono


class ToneEmbedder:
    # Embeds a slice by its dominant amplitude sign pattern → separable per tone.
    def embed(self, waveform, sample_rate):
        import numpy as np
        w = np.asarray(waveform, dtype=float)
        return [float(w.mean()), float((w > 0).mean())]


def _write_wav(path, sr=16000):
    # 3 one-second segments: loud, quiet, loud (loud vs quiet are separable)
    frames = []
    for amp in (0.8, 0.05, 0.8):
        for i in range(sr):
            frames.append(int(amp * 32767 * math.sin(2 * math.pi * 200 * i / sr)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))


def test_load_wav_mono_roundtrip(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p)
    data, sr = load_wav_mono(p)
    assert sr == 16000
    assert len(data) == 48000
    assert -1.0 <= float(data.min()) and float(data.max()) <= 1.0


def test_assign_speakers_labels_by_cluster(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p)
    segs = [
        Segment(0.0, 1.0, "one"),
        Segment(1.0, 2.0, "two"),
        Segment(2.0, 3.0, "three"),
    ]
    out = assign_speakers(p, segs, ToneEmbedder(), num_speakers=2)
    assert out[0].speaker_id == "spk1"          # loud = first speaker
    assert out[1].speaker_id == "spk2"          # quiet = second speaker
    assert out[2].speaker_id == "spk1"          # loud again = first speaker


def test_assign_speakers_empty_is_noop(tmp_path):
    assert assign_speakers(tmp_path / "none.wav", [], ToneEmbedder()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_diarize_assign.py -v`
Expected: FAIL (`ImportError: cannot import name 'assign_speakers'`).

- [ ] **Step 3: Add to `diarize.py`** (append; keep `cluster_segments`)

```python
import wave
from pathlib import Path

from .model import Segment


def load_wav_mono(path):
    import numpy as np

    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


class EcapaEmbedder:
    def __init__(self, savedir: str = "models/ecapa"):
        self.savedir = savedir
        self._model = None

    def _load(self):
        if self._model is None:
            from speechbrain.inference.speaker import EncoderClassifier

            self._model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=self.savedir,
                run_opts={"device": "cpu"},
            )
        return self._model

    def embed(self, waveform, sample_rate):
        import torch

        model = self._load()
        wav = torch.tensor(waveform, dtype=torch.float32).unsqueeze(0)
        emb = model.encode_batch(wav)
        return emb.squeeze().detach().cpu().tolist()


def assign_speakers(
    wav_path,
    segments: list[Segment],
    embedder,
    num_speakers: int | None = None,
    threshold: float = 0.75,
) -> list[Segment]:
    if not segments:
        return segments
    data, sr = load_wav_mono(wav_path)
    min_len = int(0.1 * sr)
    embeddings = []
    for seg in segments:
        a = max(0, int(seg.start * sr))
        b = min(len(data), int(seg.end * sr))
        chunk = data[a:b]
        if len(chunk) < min_len:
            chunk = data[a : a + min_len] if a + min_len <= len(data) else data[-min_len:]
        embeddings.append(embedder.embed(chunk, sr))
    labels = cluster_segments(embeddings, num_speakers=num_speakers, threshold=threshold)
    for seg, lab in zip(segments, labels):
        seg.speaker_id = f"spk{lab + 1}"
    return segments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_diarize_assign.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/diarize.py tests/test_diarize_assign.py
git commit -m "feat: ECAPA embedder and per-segment speaker assignment"
```

---

## Task 4: `build.build_plain_transcript`

**Files:**
- Create: `src/transcript_genie/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `Segment`, `Speaker`, `Transcript` from `model`.
- Produces:
  - `build_plain_transcript(segments: list[Segment], title: str = "", hearing_date: str = "") -> Transcript` — no case metadata; speakers roster is `Speaker(id=sid, label=f"SPEAKER {i+1}")` for each distinct `speaker_id` in first-appearance order; `case_name = title`.

- [ ] **Step 1: Write the failing test**

```python
from transcript_genie.model import Segment
from transcript_genie.build import build_plain_transcript


def test_plain_transcript_rosters_speakers_in_order():
    segs = [
        Segment(0.0, 1.0, "a", speaker_id="spk1"),
        Segment(1.0, 2.0, "b", speaker_id="spk2"),
        Segment(2.0, 3.0, "c", speaker_id="spk1"),
    ]
    t = build_plain_transcript(segs, title="Interview 1", hearing_date="July 5, 2026")
    assert t.case_name == "Interview 1"
    assert t.case_number == ""
    assert {s.id: s.label for s in t.speakers} == {"spk1": "SPEAKER 1", "spk2": "SPEAKER 2"}
    assert all(s.name is None for s in t.speakers)   # generic → no names
    assert len(t.segments) == 3


def test_plain_transcript_no_diarization_has_no_speakers():
    segs = [Segment(0.0, 1.0, "a")]   # speaker_id None
    t = build_plain_transcript(segs)
    assert t.speakers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_build.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from .model import Segment, Speaker, Transcript


def build_plain_transcript(segments: list[Segment], title: str = "", hearing_date: str = "") -> Transcript:
    order: list[str] = []
    for s in segments:
        if s.speaker_id and s.speaker_id not in order:
            order.append(s.speaker_id)
    speakers = [Speaker(id=sid, label=f"SPEAKER {i + 1}") for i, sid in enumerate(order)]
    return Transcript(
        case_name=title,
        case_number="",
        court="",
        judge="",
        hearing_date=hearing_date,
        speakers=speakers,
        segments=list(segments),
        markers=[],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_build.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/build.py tests/test_build.py
git commit -m "feat: build plain (non-court) transcript from segments"
```

---

## Task 5: `format_docx` generic-header handling

**Files:**
- Modify: `src/transcript_genie/format_docx.py`
- Test: `tests/test_format_docx_generic.py`

**Interfaces:** unchanged signature `write_docx(transcript, out_path) -> Path`. New behavior when metadata is absent.

**Behavior:**
- Title page: render `court` line only if non-empty; the title = `case_name` if non-empty else `"TRANSCRIPT"`; render `Case No. <n>` only if `case_number` non-empty; render `Before the Honorable Judge <j>` only if `judge` non-empty; render `hearing_date` only if non-empty.
- Appearances page: render ONLY if at least one speaker has a `name`. (Generic diarized speakers have `name=None` → no appearances page; the existing court output has named speakers → unchanged.)
- Body and certification: unchanged.

- [ ] **Step 1: Write the failing test**

```python
from docx import Document

from transcript_genie.model import Segment, Speaker, Transcript
from transcript_genie.format_docx import write_docx


def test_generic_transcript_has_no_case_lines_and_no_appearances(tmp_path):
    t = Transcript(
        case_name="Interview 1",
        case_number="",
        judge="",
        court="",
        hearing_date="July 5, 2026",
        speakers=[Speaker("spk1", "SPEAKER 1"), Speaker("spk2", "SPEAKER 2")],
        segments=[
            Segment(0.0, 1.0, "Hello.", speaker_id="spk1"),
            Segment(1.0, 2.0, "Hi there.", speaker_id="spk2"),
        ],
        markers=[],
    )
    out = write_docx(t, tmp_path / "g.docx")
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "Interview 1" in text
    assert "Case No." not in text                 # no empty case number line
    assert "Before the Honorable Judge" not in text
    assert "APPEARANCES" not in text              # no named speakers → no appearances
    assert "SPEAKER 1:" in text and "SPEAKER 2:" in text
    assert "NOT a certified transcript" in text


def test_generic_untitled_falls_back_to_TRANSCRIPT(tmp_path):
    t = Transcript(segments=[Segment(0.0, 1.0, "x")])
    out = write_docx(t, tmp_path / "u.docx")
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "TRANSCRIPT" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_format_docx_generic.py -v`
Expected: FAIL (`Case No.` present, or `APPEARANCES` present).

- [ ] **Step 3: Modify `write_docx`** — replace the title-page and appearances blocks with conditional versions. The title-page loop becomes:

```python
    # --- Title / caption page ---
    title = transcript.case_name or "TRANSCRIPT"
    lines: list[tuple[str, bool]] = []
    if transcript.court:
        lines.append((transcript.court, False))
        lines.append(("", False))
    lines.append((title, True))
    if transcript.case_number:
        lines.append((f"Case No. {transcript.case_number}", False))
    if transcript.judge:
        lines.append((f"Before the Honorable Judge {transcript.judge}", False))
    if transcript.hearing_date:
        lines.append((transcript.hearing_date, False))
    for text, bold in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(text).bold = bold
    doc.add_page_break()
```

And guard the appearances block so it only renders with named speakers:

```python
    # --- Appearances (only when speakers have names, i.e. court transcripts) ---
    if any(sp.name for sp in transcript.speakers):
        doc.add_paragraph("APPEARANCES").alignment = WD_ALIGN_PARAGRAPH.CENTER
        for sp in transcript.speakers:
            line = sp.label + (f" — {sp.name}" if sp.name else "")
            doc.add_paragraph(line)
        doc.add_page_break()
```

Leave the body-merge, label-dedup (`_UNSET` sentinel), and certification sections unchanged.

- [ ] **Step 4: Run tests to verify they pass** (new + the existing Plan 1 docx tests must both pass)

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_format_docx_generic.py tests/test_format_docx.py -v`
Expected: all pass (existing court test still renders `Case No.` + appearances because it has a case number and a named speaker).

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/format_docx.py tests/test_format_docx_generic.py
git commit -m "feat: generic transcript header; skip appearances when unnamed speakers"
```

---

## Task 6: `cli` auto-detect + generic path

**Files:**
- Modify: `src/transcript_genie/cli.py`
- Test: `tests/test_cli_generic.py`

**Interfaces:**
- `main(argv=None, engine=None, embedder=None) -> int`. New optional `embedder` injection (for tests). New args: `--title` (default `""`), `--diarize` / `--no-diarize` (`argparse.BooleanOptionalAction`, default `True`), `--speakers` (`int`, default `None`).
- Input detection: if `input` is a directory containing a `.csx` → the existing CourtSmart path (unchanged). Else if `input` is a file → the generic path. Else raise a clear error.
- Generic path: `decode_to_wav` → `engine.transcribe` → (if `--diarize`) `assign_speakers` → `build_plain_transcript(title=args.title or input.stem)` → write `transcript.json` + `transcript.docx`.

- [ ] **Step 1: Write the failing test** (fake engine + fake embedder; monkeypatch `cli.decode_to_wav`; a real tiny WAV so `assign_speakers` can load it — but embedder is fake, no ECAPA)

```python
import json
import wave
import struct
import math

from transcript_genie.model import Segment
from transcript_genie import cli


class FakeEngine:
    def transcribe(self, wav_path, glossary=None):
        return [Segment(0.0, 1.0, "Hello."), Segment(1.0, 2.0, "Hi.")]


class FakeEmbedder:
    def embed(self, waveform, sample_rate):
        import numpy as np
        w = np.asarray(waveform, dtype=float)
        return [float(w.mean()), float((w > 0).mean())]


def _wav(path, sr=16000):
    frames = []
    for amp in (0.8, 0.05):
        for i in range(sr):
            frames.append(int(amp * 32767 * math.sin(2 * math.pi * 200 * i / sr)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))


def test_cli_generic_file_with_diarization(tmp_path, monkeypatch):
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"not-real-mp3")           # never actually decoded (patched)
    wav = tmp_path / "audio.wav"
    _wav(wav)
    # decode_to_wav is patched to return our prebuilt WAV instead of calling ffmpeg
    monkeypatch.setattr(cli, "decode_to_wav", lambda *a, **k: wav)

    rc = cli.main(
        [str(audio), "--out-dir", str(tmp_path), "--speakers", "2"],
        engine=FakeEngine(),
        embedder=FakeEmbedder(),
    )
    assert rc == 0
    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert data["case_number"] == ""                       # generic → no case
    assert data["case_name"] == "clip"                     # title defaults to file stem
    assert data["segments"][0]["speaker_id"] == "spk1"     # diarized
    assert (tmp_path / "transcript.docx").exists()


def test_cli_generic_no_diarize(tmp_path, monkeypatch):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"x")
    wav = tmp_path / "audio.wav"
    _wav(wav)
    monkeypatch.setattr(cli, "decode_to_wav", lambda *a, **k: wav)
    rc = cli.main([str(audio), "--out-dir", str(tmp_path), "--no-diarize"], engine=FakeEngine())
    assert rc == 0
    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert data["segments"][0]["speaker_id"] is None        # not diarized
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_cli_generic.py -v`
Expected: FAIL (new args / branch absent).

- [ ] **Step 3: Modify `cli.py`** — add imports, args, and the generic branch. New imports at top:

```python
from .media import build_wav, decode_to_wav
from .diarize import assign_speakers, EcapaEmbedder
from .build import build_plain_transcript
```

Replace the argument parser and body of `main` with:

```python
def main(argv=None, engine=None, embedder=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="transcript-genie")
    parser.add_argument("input")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--model", default="small")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--engine", default="local", choices=["local"])
    parser.add_argument("--glossary", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--diarize", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--speakers", type=int, default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if engine is None:
        engine = LocalWhisperEngine(model_size=args.model)
    glossary = [g.strip() for g in args.glossary.split(",") if g.strip()] or None

    if input_path.is_dir() and _has_csx(input_path):
        transcript = _run_courtsmart(input_path, out_dir, engine, glossary, args)
    elif input_path.is_file():
        transcript = _run_generic(input_path, out_dir, engine, glossary, embedder, args)
    else:
        raise FileNotFoundError(
            f"Input must be a CourtSmart folder (containing a .csx) or a media file: {input_path}"
        )

    (out_dir / "transcript.json").write_text(transcript.to_json(), encoding="utf-8")
    write_docx(transcript, out_dir / "transcript.docx")
    print(f"Wrote {out_dir / 'transcript.json'} and {out_dir / 'transcript.docx'}")
    return 0


def _has_csx(input_dir: Path) -> bool:
    if (input_dir / "Sessions.csx").exists():
        return True
    return next(input_dir.rglob("*.csx"), None) is not None


def _run_courtsmart(input_dir, out_dir, engine, glossary, args):
    session = parse_csx_file(_find_csx(input_dir))
    wav = build_wav(session, input_dir, out_dir / "audio.wav", ffmpeg=args.ffmpeg)
    segments = engine.transcribe(wav, glossary=glossary)
    return build_transcript(session, segments)


def _run_generic(input_path, out_dir, engine, glossary, embedder, args):
    wav = decode_to_wav(input_path, out_dir / "audio.wav", ffmpeg=args.ffmpeg)
    segments = engine.transcribe(wav, glossary=glossary)
    if args.diarize:
        if embedder is None:
            embedder = EcapaEmbedder()
        segments = assign_speakers(wav, segments, embedder, num_speakers=args.speakers)
    title = args.title or input_path.stem
    return build_plain_transcript(segments, title=title)
```

Keep the existing `_find_csx` helper. Ensure `parse_csx_file`, `build_transcript`, `build_wav`, `write_docx`, `LocalWhisperEngine` remain imported.

- [ ] **Step 4: Run tests to verify they pass** (new generic tests + the existing Plan 1 CLI test)

Run: `& ".\.venv\Scripts\python.exe" -m pytest tests/test_cli_generic.py tests/test_cli.py -v`
Expected: all pass (the existing CourtSmart CLI test still routes through `_run_courtsmart` because it passes a folder with a `Sessions.csx`).

- [ ] **Step 5: Full suite**

Run: `& ".\.venv\Scripts\python.exe" -m pytest -q`
Expected: all pass (Plan 1's 17 + the new tests).

- [ ] **Step 6: Commit**

```bash
git add src/transcript_genie/cli.py tests/test_cli_generic.py
git commit -m "feat: auto-detect input; generic audio path with optional diarization"
```

---

## Self-Review (author)

- **Spec coverage:** any-file decode (T1), speaker clustering (T2) + embedding/assignment (T3), non-court transcript (T4), generic DOCX header (T5), CLI auto-detect + generic path with diarization (T6). Reuses Plan 1 ASR + DOCX body/certification.
- **No regressions:** `format_docx` changes are additive/conditional and keep court output (named speakers + case number) identical; `cli` keeps the CourtSmart branch via `_run_courtsmart`; existing tests targeted in T5/T6 steps.
- **Placeholder scan:** none — all code present.
- **Type consistency:** `assign_speakers`/`build_plain_transcript`/`decode_to_wav` names match between tasks and the CLI wiring; `Embedder.embed(waveform, sample_rate)` used identically in `EcapaEmbedder`, the fakes, and `assign_speakers`.
- **Deferred (future plan):** pyannote gold-standard diarization (needs HF token + license), threshold auto-tuning, PDF/SRT export, richer generic metadata.
