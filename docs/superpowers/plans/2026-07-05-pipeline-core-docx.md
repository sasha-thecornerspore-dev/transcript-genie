# Transcript Genie — Plan 1: Pipeline Core + DOCX

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-testable Python package that reads a CourtSmart/FTR disc (multichannel OGG + `Sessions.csx`), transcribes it locally with faster-whisper, attributes speakers/sections from the clerk log, and emits a court-formatted DOCX plus a transcript JSON.

**Architecture:** A pure-Python pipeline of small, single-responsibility modules — `csx` (parse log) → `media` (ffmpeg decode/stitch) → `asr` (faster-whisper) → `align` (merge log + ASR into a transcript model) → `format_docx` (render). A thin `cli` wires them. Every module is unit-testable in isolation; external tools (ffmpeg, whisper) are isolated behind functions so their pure logic is testable without them.

**Tech Stack:** Python 3.11–3.12, faster-whisper, python-docx, ffmpeg (system binary), pytest. Standard-library `xml.etree` for `.csx` parsing (no lxml).

## Global Constraints

- **Python 3.11–3.12** in a project venv (`.venv/`). Do NOT use 3.14 — `ctranslate2`/`faster-whisper` wheels are not yet published for it. Verify with `python --version` inside the venv before installing.
- **All ASR runs local by default.** No network calls in this plan. No cloud engine.
- **ffmpeg** is invoked as an external binary; its path is configurable (default `"ffmpeg"`), resolved from PATH.
- **No PII in the repository.** Test fixtures use placeholder names (e.g. "John Smith"), never the real parties/attorneys. The real disc is read only at manual/integration run time.
- **Package layout:** `src/` layout, importable as `transcript_genie`. Console script name: `transcript-genie`.
- **Every module has a single responsibility** (see File Structure). Keep files focused; do not merge modules.
- **Times are floats in seconds, audio-relative** (t=0 at the first audio segment's `starttime`). The `.csx` integer `indextime` is Unix epoch; convert with `t = indextime - session.audio_origin`, clamped to `>= 0`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, console script, pytest config |
| `src/transcript_genie/__init__.py` | Package marker + version |
| `src/transcript_genie/model.py` | Transcript data model + JSON (de)serialization |
| `src/transcript_genie/csx.py` | Parse `Sessions.csx` into a structured session |
| `src/transcript_genie/media.py` | Order audio segments + ffmpeg decode/stitch to WAV |
| `src/transcript_genie/asr.py` | ASR engine abstraction + local faster-whisper engine |
| `src/transcript_genie/align.py` | Classify log tags; merge log + ASR into a `Transcript` |
| `src/transcript_genie/format_docx.py` | Render a `Transcript` to court-formatted DOCX |
| `src/transcript_genie/cli.py` | CLI: disc dir → `transcript.json` + `transcript.docx` |
| `tests/…` | One test module per source module |

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/transcript_genie/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `transcript_genie` with `__version__: str`; a working `pytest` setup.

- [ ] **Step 1: Create the venv and confirm the Python version**

```bash
py -3.12 -m venv .venv 2>/dev/null || py -3.11 -m venv .venv
.venv/Scripts/python --version   # must print 3.11.x or 3.12.x
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "transcript-genie"
version = "0.1.0"
description = "Court-quality transcript generator for CourtSmart/FTR discs and generic audio"
requires-python = ">=3.11,<3.13"
dependencies = [
    "faster-whisper>=1.0.0",
    "python-docx>=1.1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
transcript-genie = "transcript_genie.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `src/transcript_genie/__init__.py`**

```python
"""Transcript Genie — court-quality transcript pipeline."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `tests/__init__.py`** (empty file) and `tests/test_smoke.py`

```python
import transcript_genie


def test_version_present():
    assert transcript_genie.__version__ == "0.1.0"
```

- [ ] **Step 5: Install and run**

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/transcript_genie/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold transcript_genie package"
```

---

## Task 2: Transcript data model

**Files:**
- Create: `src/transcript_genie/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Word(text: str, start: float, end: float, confidence: float = 1.0)`
  - `Segment(start: float, end: float, text: str, speaker_id: str | None = None, words: list[Word] = [])`
  - `Speaker(id: str, label: str, name: str | None = None)`
  - `Marker(time: float, kind: str, text: str)`  # kind ∈ {"section", "event"}
  - `Transcript(case_name, case_number, court, judge, hearing_date, speakers: list[Speaker], segments: list[Segment], markers: list[Marker])` (all str fields default `""`, lists default empty)
  - `Transcript.to_json() -> str`, `Transcript.from_json(s: str) -> Transcript`, `Transcript.to_dict() -> dict`, `Transcript.from_dict(d: dict) -> Transcript`

- [ ] **Step 1: Write the failing test**

```python
from transcript_genie.model import Word, Segment, Speaker, Marker, Transcript


def test_transcript_json_roundtrip():
    t = Transcript(
        case_name="John Smith v. Jane Smith",
        case_number="C-03-FM-19-000000",
        court="Court 15",
        judge="Vance",
        hearing_date="April 3, 2019",
        speakers=[Speaker(id="court", label="THE COURT")],
        segments=[
            Segment(start=1.0, end=2.5, text="Good morning.", speaker_id="court",
                    words=[Word(text="Good", start=1.0, end=1.3, confidence=0.9)])
        ],
        markers=[Marker(time=0.0, kind="event", text="(Court in session.)")],
    )
    restored = Transcript.from_json(t.to_json())
    assert restored == t
    assert restored.segments[0].words[0].text == "Good"
    assert restored.markers[0].kind == "event"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transcript_genie.model'`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker_id: str | None = None
    words: list[Word] = field(default_factory=list)


@dataclass
class Speaker:
    id: str
    label: str
    name: str | None = None


@dataclass
class Marker:
    time: float
    kind: str  # "section" | "event"
    text: str


@dataclass
class Transcript:
    case_name: str = ""
    case_number: str = ""
    court: str = ""
    judge: str = ""
    hearing_date: str = ""
    speakers: list[Speaker] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        return cls(
            case_name=d.get("case_name", ""),
            case_number=d.get("case_number", ""),
            court=d.get("court", ""),
            judge=d.get("judge", ""),
            hearing_date=d.get("hearing_date", ""),
            speakers=[Speaker(**s) for s in d.get("speakers", [])],
            segments=[
                Segment(
                    start=s["start"], end=s["end"], text=s["text"],
                    speaker_id=s.get("speaker_id"),
                    words=[Word(**w) for w in s.get("words", [])],
                )
                for s in d.get("segments", [])
            ],
            markers=[Marker(**m) for m in d.get("markers", [])],
        )

    @classmethod
    def from_json(cls, s: str) -> "Transcript":
        return cls.from_dict(json.loads(s))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/model.py tests/test_model.py
git commit -m "feat: add transcript data model with JSON roundtrip"
```

---

## Task 3: CourtSmart `.csx` parser

**Files:**
- Create: `src/transcript_genie/csx.py`
- Test: `tests/test_csx.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CsxFile(filename: str, sequence: int, starttime: int, stoptime: int, type: int, path: str)`
  - `CsxTag(indextime: int, entertime: int, text: str, username: str)`
  - `CsxSession(case, caption, judge, room, type, channels, samplerate, starttime, stoptime, timeoffset, firstfile, tags: list[CsxTag], files: list[CsxFile])`
    - property `audio_files -> list[CsxFile]` (type==2, sorted by `sequence`)
    - property `audio_origin -> int` (first audio file `starttime`, else session `starttime`)
  - `parse_csx(data: bytes) -> CsxSession`
  - `parse_csx_file(path) -> CsxSession`

- [ ] **Step 1: Write the failing test**

```python
from transcript_genie.csx import parse_csx

SAMPLE = (
    '<?xml version="1.0" encoding="utf-16"?>'
    '<cs:store xmlns:cs="http://www.courtsmart.com/XMLNS/csmtsoapstore1000">'
    '<cs:session room="Court 15" case="---" type="CRIMINAL/CIVIL" '
    'caption="Judges Vance - Sharon" judge="Vance" channels="4" samplerate="12000" '
    'starttime="1554293813" stoptime="1554311668" timeoffset="-240" '
    'firstfile="ppdws50c.ogg">'
    '<cs:tag indextime="1554301711" entertime="1554301615" private="0" username="sharon">'
    'DIRECT EXAM_______</cs:tag>'
    '<cs:file fileid="0" starttime="1554301396" stoptime="1554303369" sequence="0" '
    'type="0" filename="ppdws500.tpd" path=".\\00000000"/>'
    '<cs:file fileid="781297" starttime="1554301013" stoptime="1554301612" sequence="12" '
    'type="2" filename="ppdws50c.ogg" path=".\\00000000"/>'
    '<cs:file fileid="781304" starttime="1554301613" stoptime="1554302212" sequence="13" '
    'type="2" filename="ppdws50d.ogg" path=".\\00000000"/>'
    '</cs:session></cs:store>'
).encode("utf-16")


def test_parse_session_attributes():
    s = parse_csx(SAMPLE)
    assert s.judge == "Vance"
    assert s.channels == 4
    assert s.timeoffset == -240
    assert s.firstfile == "ppdws50c.ogg"


def test_audio_files_sorted_and_origin():
    s = parse_csx(SAMPLE)
    assert [f.filename for f in s.audio_files] == ["ppdws50c.ogg", "ppdws50d.ogg"]
    assert s.audio_origin == 1554301013  # first audio segment starttime, not the .tpd


def test_tags_parsed():
    s = parse_csx(SAMPLE)
    assert len(s.tags) == 1
    assert s.tags[0].text == "DIRECT EXAM_______"
    assert s.tags[0].username == "sharon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_csx.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass
class CsxFile:
    filename: str
    sequence: int
    starttime: int
    stoptime: int
    type: int
    path: str


@dataclass
class CsxTag:
    indextime: int
    entertime: int
    text: str
    username: str


@dataclass
class CsxSession:
    case: str = ""
    caption: str = ""
    judge: str = ""
    room: str = ""
    type: str = ""
    channels: int = 0
    samplerate: int = 0
    starttime: int = 0
    stoptime: int = 0
    timeoffset: int = 0
    firstfile: str = ""
    tags: list[CsxTag] = field(default_factory=list)
    files: list[CsxFile] = field(default_factory=list)

    @property
    def audio_files(self) -> list[CsxFile]:
        return sorted((f for f in self.files if f.type == 2), key=lambda f: f.sequence)

    @property
    def audio_origin(self) -> int:
        af = self.audio_files
        return af[0].starttime if af else self.starttime


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int(attrib: dict, key: str, default: int = 0) -> int:
    try:
        return int(attrib.get(key, default))
    except (TypeError, ValueError):
        return default


def parse_csx(data: bytes) -> CsxSession:
    root = ET.fromstring(data)
    session_el = next((el for el in root.iter() if _local(el.tag) == "session"), None)
    if session_el is None:
        raise ValueError("No <cs:session> element found in .csx data")
    a = session_el.attrib
    tags: list[CsxTag] = []
    files: list[CsxFile] = []
    for el in session_el:
        name = _local(el.tag)
        if name == "tag":
            tags.append(
                CsxTag(
                    indextime=_int(el.attrib, "indextime"),
                    entertime=_int(el.attrib, "entertime"),
                    text=(el.text or "").strip(),
                    username=el.attrib.get("username", ""),
                )
            )
        elif name == "file":
            fa = el.attrib
            files.append(
                CsxFile(
                    filename=fa.get("filename", ""),
                    sequence=_int(fa, "sequence"),
                    starttime=_int(fa, "starttime"),
                    stoptime=_int(fa, "stoptime"),
                    type=_int(fa, "type"),
                    path=fa.get("path", ""),
                )
            )
    return CsxSession(
        case=a.get("case", ""),
        caption=a.get("caption", ""),
        judge=a.get("judge", ""),
        room=a.get("room", ""),
        type=a.get("type", ""),
        channels=_int(a, "channels"),
        samplerate=_int(a, "samplerate"),
        starttime=_int(a, "starttime"),
        stoptime=_int(a, "stoptime"),
        timeoffset=_int(a, "timeoffset"),
        firstfile=a.get("firstfile", ""),
        tags=tags,
        files=files,
    )


def parse_csx_file(path) -> CsxSession:
    return parse_csx(Path(path).read_bytes())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_csx.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/csx.py tests/test_csx.py
git commit -m "feat: parse CourtSmart .csx session log"
```

---

## Task 4: Media — order + stitch audio to WAV

**Files:**
- Create: `src/transcript_genie/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `CsxSession`, `CsxFile` from `csx`.
- Produces:
  - `resolve_audio_paths(session: CsxSession, disc_dir) -> list[Path]` — audio segment paths in `sequence` order, each resolved as `disc_dir / <path-subdir> / filename` (the `.csx` `path` like `.\00000000` becomes subdir `00000000`).
  - `build_wav(session, disc_dir, out_path, samplerate: int = 16000, ffmpeg: str = "ffmpeg") -> Path` — concatenates the segments and downmixes to mono WAV via the ffmpeg concat demuxer; returns `out_path`.

- [ ] **Step 1: Write the failing test** (pure path logic; no ffmpeg needed)

```python
from pathlib import Path

from transcript_genie.csx import CsxFile, CsxSession
from transcript_genie.media import resolve_audio_paths


def _session():
    return CsxSession(
        files=[
            CsxFile("ppdws500.tpd", 0, 1554301396, 1554303369, 0, ".\\00000000"),
            CsxFile("ppdws50d.ogg", 13, 1554301613, 1554302212, 2, ".\\00000000"),
            CsxFile("ppdws50c.ogg", 12, 1554301013, 1554301612, 2, ".\\00000000"),
        ]
    )


def test_resolve_audio_paths_ordered_and_subdir():
    paths = resolve_audio_paths(_session(), Path("J:/"))
    names = [p.name for p in paths]
    assert names == ["ppdws50c.ogg", "ppdws50d.ogg"]  # sequence order, .tpd excluded
    assert paths[0].parent.name == "00000000"           # path subdir applied
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_media.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

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
    if not paths:
        raise ValueError("Session has no audio segments to stitch")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        list_file = Path(fh.name)
        for p in paths:
            # ffmpeg concat demuxer: escape single quotes in paths
            safe = p.resolve().as_posix().replace("'", r"'\''")
            fh.write(f"file '{safe}'\n")
    try:
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-ac", "1", "-ar", str(samplerate), str(out_path),
        ]
        subprocess.run(cmd, check=True)
    finally:
        list_file.unlink(missing_ok=True)
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_media.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Manual integration check against the real disc** (only if drive J: is loaded)

```bash
.venv/Scripts/python -c "from transcript_genie.csx import parse_csx_file; from transcript_genie.media import build_wav; s=parse_csx_file('J:/Sessions.csx'); print(build_wav(s,'J:/','out.wav'))"
```
Expected: prints `out.wav`; a ~40-min mono 16 kHz WAV exists. If drive not loaded, skip.

- [ ] **Step 6: Commit**

```bash
git add src/transcript_genie/media.py tests/test_media.py
git commit -m "feat: stitch CourtSmart audio segments to mono WAV via ffmpeg"
```

---

## Task 5: ASR engine abstraction + local faster-whisper

**Files:**
- Create: `src/transcript_genie/asr.py`
- Test: `tests/test_asr.py`

**Interfaces:**
- Consumes: `Segment`, `Word` from `model`.
- Produces:
  - `ASREngine` (typing.Protocol) with `transcribe(wav_path, glossary: list[str] | None = None) -> list[Segment]`.
  - `LocalWhisperEngine(model_size: str = "small", device: str = "auto", compute_type: str = "auto")` implementing `ASREngine`. Imports `faster_whisper` lazily inside `transcribe` so the module imports without the heavy dep installed.
  - `whisper_segments_to_model(raw_segments) -> list[Segment]` — pure adapter converting faster-whisper segment objects (attributes `start`, `end`, `text`, `words`; each word has `word`, `start`, `end`, `probability`) into our `Segment`/`Word`.

- [ ] **Step 1: Write the failing test** (tests the pure adapter with fakes; no whisper install)

```python
from types import SimpleNamespace

from transcript_genie.asr import whisper_segments_to_model


def test_adapter_maps_segments_and_words():
    raw = [
        SimpleNamespace(
            start=0.0, end=1.5, text=" Good morning.",
            words=[SimpleNamespace(word=" Good", start=0.0, end=0.4, probability=0.91)],
        )
    ]
    segs = whisper_segments_to_model(raw)
    assert len(segs) == 1
    assert segs[0].text == "Good morning."          # stripped
    assert segs[0].speaker_id is None
    assert segs[0].words[0].text == "Good"
    assert abs(segs[0].words[0].confidence - 0.91) < 1e-6


def test_adapter_handles_missing_words():
    raw = [SimpleNamespace(start=0.0, end=1.0, text="Hi", words=None)]
    segs = whisper_segments_to_model(raw)
    assert segs[0].words == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_asr.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import Protocol

from .model import Segment, Word


class ASREngine(Protocol):
    def transcribe(self, wav_path, glossary: list[str] | None = None) -> list[Segment]:
        ...


def whisper_segments_to_model(raw_segments) -> list[Segment]:
    segments: list[Segment] = []
    for s in raw_segments:
        words = []
        for w in (getattr(s, "words", None) or []):
            words.append(
                Word(
                    text=(w.word or "").strip(),
                    start=float(w.start),
                    end=float(w.end),
                    confidence=float(getattr(w, "probability", 1.0)),
                )
            )
        segments.append(
            Segment(
                start=float(s.start),
                end=float(s.end),
                text=(s.text or "").strip(),
                speaker_id=None,
                words=words,
            )
        )
    return segments


class LocalWhisperEngine:
    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "auto"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, wav_path, glossary: list[str] | None = None) -> list[Segment]:
        model = self._load()
        prompt = ", ".join(glossary) if glossary else None
        raw, _info = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            initial_prompt=prompt,
            vad_filter=True,
        )
        return whisper_segments_to_model(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_asr.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/asr.py tests/test_asr.py
git commit -m "feat: add ASR abstraction and local faster-whisper engine"
```

---

## Task 6: Align — classify tags + build the transcript

**Files:**
- Create: `src/transcript_genie/align.py`
- Test: `tests/test_align.py`

**Interfaces:**
- Consumes: `CsxSession`, `CsxTag` from `csx`; `Segment`, `Speaker`, `Marker`, `Transcript` from `model`.
- Produces:
  - `TagClass(kind: str, speaker_id: str | None = None, label: str | None = None, name: str | None = None)` — `kind` ∈ {"speaker", "section", "event", "blank"}.
  - `classify_tag(text: str) -> TagClass`.
  - `extract_case(session: CsxSession) -> tuple[str, str]` — returns `(case_name, case_number)`; parses the first tag matching `<A> v. <B> <C-##-XX-##-######>`; falls back to `("", "")`.
  - `format_hearing_date(session: CsxSession) -> str` — `audio_origin` + `timeoffset` minutes → `"April 3, 2019"`.
  - `build_transcript(session: CsxSession, segments: list[Segment]) -> Transcript` — assigns each segment the most-recent speaker turn from the tag timeline, collects section/event markers, fills case metadata.

**Classification rules (checked top to bottom; matching is case-insensitive on the cleaned text, where "cleaned" = strip leading `~`/`>` and collapse runs of `_`/`-`/`=`/`~` and whitespace):**

| If cleaned text contains… | kind | speaker_id | label |
|---|---|---|---|
| empty after cleaning | blank | — | — |
| `END OF CASE` | event | — | `(End of case.)` |
| `OFF THE RECORD` or `RECESS` | event | — | `(Off the record — recess.)` |
| `WITNESS CALLED AND SWORN` | event | — | `(Witness called and sworn.)` |
| `WITNESS STANDS DOWN` | event | — | `(Witness stands down.)` |
| `WITNESS:` | speaker | `witness` | `THE WITNESS` (name = text after `WITNESS:`) |
| `REDIRECT` | section | — | `REDIRECT EXAMINATION` |
| `RECROSS` | section | — | `RECROSS EXAMINATION` |
| `DIRECT EXAM` | section | — | `DIRECT EXAMINATION` |
| `CROSS EXAM` | section | — | `CROSS EXAMINATION` |
| `RULING` | section | — | `RULING OF THE COURT` |
| `JUDGE` | speaker | `court` | `THE COURT` |
| `PLT ATTY` / `PLAINTIFF ATTY` | speaker | `plt_atty` | `COUNSEL FOR PLAINTIFF` (name = trailing name) |
| `DEF ATTY` / `DEFENDANT ATTY` | speaker | `def_atty` | `COUNSEL FOR DEFENDANT` (name = trailing name) |
| starts with `PLT ` | speaker | `plt` | `PLAINTIFF` (name = trailing name) |
| starts with `DEF ` | speaker | `def` | `DEFENDANT` (name = trailing name) |
| otherwise | event | — | the cleaned text wrapped as `(<text>.)` |

- [ ] **Step 1: Write the failing test**

```python
from transcript_genie.csx import CsxFile, CsxSession, CsxTag
from transcript_genie.model import Segment
from transcript_genie.align import (
    classify_tag,
    extract_case,
    format_hearing_date,
    build_transcript,
)


def test_classify_speakers_sections_events():
    assert classify_tag("_______JUDGE_________").speaker_id == "court"
    assert classify_tag("~Plt Atty John Smith").speaker_id == "plt_atty"
    assert classify_tag("~Plt Atty John Smith").name == "John Smith"
    assert classify_tag(">Def Atty Jane Doe").label == "COUNSEL FOR DEFENDANT"
    assert classify_tag("Plt John Smith").speaker_id == "plt"
    assert classify_tag("DIRECT EXAM_______").kind == "section"
    assert classify_tag("DIRECT EXAM_______").label == "DIRECT EXAMINATION"
    assert classify_tag("__WITNESS: John Smith").speaker_id == "witness"
    assert classify_tag("__WITNESS: John Smith").name == "John Smith"
    assert classify_tag("---END OF CASE---").kind == "event"
    assert classify_tag("").kind == "blank"


def _session():
    s = CsxSession(
        judge="Vance", room="Court 15", timeoffset=-240,
        files=[CsxFile("ppdws50c.ogg", 12, 1554301013, 1554301612, 2, ".\\00000000")],
        tags=[
            CsxTag(1554301013, 0, "===JOHN SMITH v. JANE SMITH C-03-FM-19-000000", "sharon"),
            CsxTag(1554301113, 0, "_______JUDGE_________", "sharon"),          # +100s
            CsxTag(1554301213, 0, "DIRECT EXAM_______", "sharon"),             # +200s
            CsxTag(1554301313, 0, "~Plt Atty John Smith", "sharon"),           # +300s
        ],
    )
    return s


def test_extract_case_and_date():
    name, number = extract_case(_session())
    assert name == "John Smith v. Jane Smith"
    assert number == "C-03-FM-19-000000"
    assert format_hearing_date(_session()) == "April 3, 2019"


def test_build_transcript_assigns_speakers_and_markers():
    segs = [
        Segment(start=150.0, end=151.0, text="Good morning."),   # after JUDGE(100s)
        Segment(start=320.0, end=321.0, text="Objection."),      # after Plt Atty(300s)
    ]
    t = build_transcript(_session(), segs)
    assert t.case_number == "C-03-FM-19-000000"
    assert t.segments[0].speaker_id == "court"
    assert t.segments[1].speaker_id == "plt_atty"
    assert any(m.text == "DIRECT EXAMINATION" for m in t.markers)
    assert {sp.id for sp in t.speakers} >= {"court", "plt_atty"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_align.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from .csx import CsxSession
from .model import Marker, Segment, Speaker, Transcript

_NOISE = re.compile(r"[_\-=~>]+")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    t = text.lstrip("~>").strip()
    t = _NOISE.sub(" ", t)
    return _WS.sub(" ", t).strip()


@dataclass
class TagClass:
    kind: str
    speaker_id: str | None = None
    label: str | None = None
    name: str | None = None


def _trailing_name(cleaned: str, after: str) -> str | None:
    idx = cleaned.upper().find(after.upper())
    if idx == -1:
        return None
    rest = cleaned[idx + len(after):].strip(" :")
    return rest or None


def classify_tag(text: str) -> TagClass:
    c = _clean(text)
    u = c.upper()
    if not c:
        return TagClass("blank")
    if "END OF CASE" in u:
        return TagClass("event", label="(End of case.)")
    if "OFF THE RECORD" in u or "RECESS" in u:
        return TagClass("event", label="(Off the record — recess.)")
    if "WITNESS CALLED AND SWORN" in u:
        return TagClass("event", label="(Witness called and sworn.)")
    if "WITNESS STANDS DOWN" in u:
        return TagClass("event", label="(Witness stands down.)")
    if "WITNESS:" in u:
        return TagClass("speaker", "witness", "THE WITNESS", _trailing_name(c, "WITNESS:"))
    if "REDIRECT" in u:
        return TagClass("section", label="REDIRECT EXAMINATION")
    if "RECROSS" in u:
        return TagClass("section", label="RECROSS EXAMINATION")
    if "DIRECT EXAM" in u:
        return TagClass("section", label="DIRECT EXAMINATION")
    if "CROSS EXAM" in u:
        return TagClass("section", label="CROSS EXAMINATION")
    if "RULING" in u:
        return TagClass("section", label="RULING OF THE COURT")
    if "JUDGE" in u:
        return TagClass("speaker", "court", "THE COURT")
    if "PLT ATTY" in u or "PLAINTIFF ATTY" in u:
        return TagClass("speaker", "plt_atty", "COUNSEL FOR PLAINTIFF",
                        _trailing_name(c, "ATTY"))
    if "DEF ATTY" in u or "DEFENDANT ATTY" in u:
        return TagClass("speaker", "def_atty", "COUNSEL FOR DEFENDANT",
                        _trailing_name(c, "ATTY"))
    if u.startswith("PLT "):
        return TagClass("speaker", "plt", "PLAINTIFF", c[4:].strip() or None)
    if u.startswith("DEF "):
        return TagClass("speaker", "def", "DEFENDANT", c[4:].strip() or None)
    return TagClass("event", label=f"({c}.)")


_CASE_RE = re.compile(
    r"(?P<a>[A-Za-z.\- ]+?)\s+v\.?\s+(?P<b>[A-Za-z.\- ]+?)\s+"
    r"(?P<num>[A-Z]-\d{2}-[A-Z]{2}-\d{2}-\d+)",
    re.IGNORECASE,
)


def _titlecase(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def extract_case(session: CsxSession) -> tuple[str, str]:
    for tag in session.tags:
        # Match the RAW text: _clean() would strip the hyphens the case
        # number depends on. The lazy [A-Za-z.\- ] group skips leading "===".
        m = _CASE_RE.search(tag.text)
        if m:
            name = f"{_titlecase(m.group('a'))} v. {_titlecase(m.group('b'))}"
            return name, m.group("num").upper()
    return "", ""


def format_hearing_date(session: CsxSession) -> str:
    tz = timezone(timedelta(minutes=session.timeoffset))
    dt = datetime.fromtimestamp(session.audio_origin, tz=tz)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def build_transcript(session: CsxSession, segments: list[Segment]) -> Transcript:
    origin = session.audio_origin
    turns: list[tuple[float, str]] = []          # (time, speaker_id)
    speakers: dict[str, Speaker] = {}
    markers: list[Marker] = []
    for tag in sorted(session.tags, key=lambda t: t.indextime):
        t = max(0.0, float(tag.indextime - origin))
        tc = classify_tag(tag.text)
        if tc.kind == "speaker":
            turns.append((t, tc.speaker_id))
            if tc.speaker_id not in speakers:
                speakers[tc.speaker_id] = Speaker(id=tc.speaker_id, label=tc.label, name=tc.name)
            elif tc.name and not speakers[tc.speaker_id].name:
                speakers[tc.speaker_id].name = tc.name
        elif tc.kind in ("section", "event"):
            markers.append(Marker(time=t, kind=tc.kind, text=tc.label))

    turns.sort(key=lambda x: x[0])
    turn_times = [t for t, _ in turns]
    for seg in segments:
        idx = bisect_right(turn_times, seg.start) - 1
        seg.speaker_id = turns[idx][1] if idx >= 0 else None

    name, number = extract_case(session)
    return Transcript(
        case_name=name,
        case_number=number,
        court=session.room,
        judge=session.judge,
        hearing_date=format_hearing_date(session),
        speakers=list(speakers.values()),
        segments=segments,
        markers=markers,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_align.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/align.py tests/test_align.py
git commit -m "feat: classify log tags and build speaker-attributed transcript"
```

---

## Task 7: DOCX court formatter

**Files:**
- Create: `src/transcript_genie/format_docx.py`
- Test: `tests/test_format_docx.py`

**Interfaces:**
- Consumes: `Transcript`, `Speaker`, `Segment`, `Marker` from `model`.
- Produces: `write_docx(transcript: Transcript, out_path) -> Path`.

**Layout (v1):** a title/caption page (case name, number, court, judge, hearing date), an APPEARANCES block (each speaker's label + name), a body that interleaves markers (section headers centered/bold; event lines centered/italic) and speaker-labeled segments in timeline order (speaker label in caps followed by the text; the label repeats only when the speaker changes), and a final certification/disclaimer page reading **"This is a working draft transcript. It is NOT a certified transcript."** Strict 25-line-per-page numbering is deferred to a later plan and must not be claimed here.

- [ ] **Step 1: Write the failing test**

```python
from docx import Document

from transcript_genie.model import Marker, Segment, Speaker, Transcript
from transcript_genie.format_docx import write_docx


def _transcript():
    return Transcript(
        case_name="John Smith v. Jane Smith",
        case_number="C-03-FM-19-000000",
        court="Court 15",
        judge="Vance",
        hearing_date="April 3, 2019",
        speakers=[
            Speaker("court", "THE COURT"),
            Speaker("plt_atty", "COUNSEL FOR PLAINTIFF", name="John Smith"),
        ],
        segments=[
            Segment(0.0, 1.0, "Good morning.", speaker_id="court"),
            Segment(1.0, 2.0, "Still the Court speaking.", speaker_id="court"),
            Segment(2.0, 3.0, "Objection, your Honor.", speaker_id="plt_atty"),
        ],
        markers=[Marker(0.0, "section", "DIRECT EXAMINATION")],
    )


def test_write_docx_contains_key_content(tmp_path):
    out = write_docx(_transcript(), tmp_path / "t.docx")
    assert out.exists()
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "C-03-FM-19-000000" in text
    assert "DIRECT EXAMINATION" in text
    assert "THE COURT" in text
    assert "COUNSEL FOR PLAINTIFF" in text
    assert "NOT a certified transcript" in text
    # Body label appears once for the two consecutive THE COURT segments.
    # ("THE COURT:" with a colon is body-only; the appearances page uses
    # "THE COURT" without a colon, so this isolates the body's dedup.)
    assert text.count("THE COURT:") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_format_docx.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .model import Transcript


def _labels(transcript: Transcript) -> dict[str, str]:
    return {s.id: s.label for s in transcript.speakers}


def write_docx(transcript: Transcript, out_path) -> Path:
    out_path = Path(out_path)
    doc = Document()

    # --- Title / caption page ---
    for text, bold in [
        (transcript.court, False),
        ("", False),
        (transcript.case_name, True),
        (f"Case No. {transcript.case_number}", False),
        (f"Before the Honorable Judge {transcript.judge}", False),
        (transcript.hearing_date, False),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.bold = bold
    doc.add_page_break()

    # --- Appearances ---
    doc.add_paragraph("APPEARANCES").alignment = WD_ALIGN_PARAGRAPH.CENTER
    for sp in transcript.speakers:
        line = sp.label + (f" — {sp.name}" if sp.name else "")
        doc.add_paragraph(line)
    doc.add_page_break()

    # --- Body: merge markers + segments in time order ---
    labels = _labels(transcript)
    events = [("marker", m.time, m) for m in transcript.markers]
    events += [("segment", s.start, s) for s in transcript.segments]
    events.sort(key=lambda e: (e[1], 0 if e[0] == "marker" else 1))

    last_speaker: str | None = None
    for kind, _t, obj in events:
        if kind == "marker":
            last_speaker = None
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(obj.text)
            run.bold = obj.kind == "section"
            run.italic = obj.kind == "event"
        else:
            p = doc.add_paragraph()
            if obj.speaker_id != last_speaker:
                label = labels.get(obj.speaker_id, "SPEAKER")
                p.add_run(f"{label}: ").bold = True
                last_speaker = obj.speaker_id
            p.add_run(obj.text)

    # --- Certification / disclaimer ---
    doc.add_page_break()
    doc.add_paragraph("CERTIFICATION").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        "This is a working draft transcript produced by automated speech "
        "recognition and clerk-log alignment. It is NOT a certified transcript "
        "and has not been reviewed or certified by an approved court transcriber."
    )

    doc.save(str(out_path))
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_format_docx.py -v`
Expected: PASS. (If `python-docx` errors with `No module named 'typing_extensions'`, run `.venv/Scripts/python -m pip install typing_extensions` — it is a transitive dep missing in some environments.)

- [ ] **Step 5: Commit**

```bash
git add src/transcript_genie/format_docx.py tests/test_format_docx.py
git commit -m "feat: render court-formatted DOCX from transcript"
```

---

## Task 8: CLI — disc dir → JSON + DOCX

**Files:**
- Create: `src/transcript_genie/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> int`. Args: `input_dir` (positional), `--out-dir` (default `.`), `--model` (default `small`), `--ffmpeg` (default `ffmpeg`), `--engine` (default `local`; only `local` accepted in this plan), `--glossary` (comma-separated). Writes `<out-dir>/transcript.json` and `<out-dir>/transcript.docx`. Locates `Sessions.csx` inside `input_dir`. Accepts an injected engine for testing via `main(..., engine=...)`.

- [ ] **Step 1: Write the failing test** (injects a fake engine and a fake wav-builder; no ffmpeg/whisper)

```python
import json

from transcript_genie.model import Segment
from transcript_genie import cli


class FakeEngine:
    def transcribe(self, wav_path, glossary=None):
        return [Segment(150.0, 151.0, "Good morning.")]


def test_cli_end_to_end(tmp_path, monkeypatch):
    disc = tmp_path / "disc"
    (disc / "00000000").mkdir(parents=True)
    csx = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<cs:store xmlns:cs="http://www.courtsmart.com/XMLNS/csmtsoapstore1000">'
        '<cs:session room="Court 15" judge="Vance" channels="4" samplerate="12000" '
        'starttime="1554293813" timeoffset="-240" firstfile="ppdws50c.ogg">'
        '<cs:tag indextime="1554301013" entertime="0" username="sharon">'
        '===JOHN SMITH v. JANE SMITH C-03-FM-19-000000</cs:tag>'
        '<cs:tag indextime="1554301113" entertime="0" username="sharon">'
        '_______JUDGE_________</cs:tag>'
        '<cs:file starttime="1554301013" stoptime="1554301612" sequence="12" '
        'type="2" filename="ppdws50c.ogg" path=".\\00000000"/>'
        '</cs:session></cs:store>'
    ).encode("utf-16")
    (disc / "Sessions.csx").write_bytes(csx)

    # Do not actually call ffmpeg; pretend a wav was produced.
    monkeypatch.setattr(cli, "build_wav", lambda *a, **k: tmp_path / "out.wav")

    rc = cli.main([str(disc), "--out-dir", str(tmp_path)], engine=FakeEngine())
    assert rc == 0

    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert data["case_number"] == "C-03-FM-19-000000"
    assert data["segments"][0]["speaker_id"] == "court"
    assert (tmp_path / "transcript.docx").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .align import build_transcript
from .asr import LocalWhisperEngine
from .csx import parse_csx_file
from .format_docx import write_docx
from .media import build_wav


def _find_csx(input_dir: Path) -> Path:
    direct = input_dir / "Sessions.csx"
    if direct.exists():
        return direct
    for p in input_dir.rglob("*.csx"):
        return p
    raise FileNotFoundError(f"No .csx session log found under {input_dir}")


def main(argv: list[str] | None = None, engine=None) -> int:
    parser = argparse.ArgumentParser(prog="transcript-genie")
    parser.add_argument("input_dir")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--model", default="small")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--engine", default="local", choices=["local"])
    parser.add_argument("--glossary", default="")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = parse_csx_file(_find_csx(input_dir))
    wav = build_wav(session, input_dir, out_dir / "audio.wav", ffmpeg=args.ffmpeg)

    if engine is None:
        engine = LocalWhisperEngine(model_size=args.model)
    glossary = [g.strip() for g in args.glossary.split(",") if g.strip()]
    segments = engine.transcribe(wav, glossary=glossary or None)

    transcript = build_transcript(session, segments)
    (out_dir / "transcript.json").write_text(transcript.to_json(), encoding="utf-8")
    write_docx(transcript, out_dir / "transcript.docx")
    print(f"Wrote {out_dir / 'transcript.json'} and {out_dir / 'transcript.docx'}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Real end-to-end run on the disc** (manual; requires drive J: loaded, faster-whisper installed, ffmpeg on PATH)

```bash
.venv/Scripts/python -m pip install faster-whisper
.venv/Scripts/python -m transcript_genie.cli "J:/" --out-dir ./out --model small \
  --ffmpeg "C:/Users/sasha/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin/ffmpeg.exe" \
  --glossary "Barrett, Cortez, Vance, Whitfield"
```
Expected: `./out/transcript.json` and `./out/transcript.docx` produced; open the DOCX and confirm caption, appearances, examination headers, and speaker labels.

- [ ] **Step 7: Commit**

```bash
git add src/transcript_genie/cli.py tests/test_cli.py
git commit -m "feat: add CLI wiring disc to transcript JSON and DOCX"
```

---

## Self-Review (completed by author)

- **Spec coverage (Plan 1 slice):** `.csx` parse (T3), ffmpeg decode/stitch of the sequential OGG segments (T4), local faster-whisper with glossary + word confidence (T5), log→speaker/section alignment (T6), court DOCX with caption/appearances/examination headers/certification (T7), JSON transcript model (T2), CLI end-to-end on the disc (T8). Out of scope by design (later plans): Electron UI, review editor, cloud ASR, pyannote diarization, PDF/SRT/VTT, strict 25-line pagination, batch queue, packaging/docs.
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `Segment.speaker_id` set in T6 and read in T7; `whisper_segments_to_model` (T5) returns `list[Segment]` consumed by the `ASREngine` protocol and CLI; `build_wav`/`resolve_audio_paths` names consistent between T4 and T8; `build_transcript` signature consistent T6↔T8.
