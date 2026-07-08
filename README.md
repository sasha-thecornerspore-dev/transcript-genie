# Transcript Genie

**Local-first, court-quality transcript generator for courtroom & legal audio.**

Transcript Genie turns courtroom recordings — starting with **CourtSmart / FTR
digital-recording discs** (multichannel OGG audio + a clerk-authored
`Sessions.csx` log) and any generic audio/video file — into **speaker-labeled,
court-formatted transcripts** you can review and export to DOCX. Speech-to-text
runs **fully offline by default** (faster-whisper); speaker attribution comes
from the clerk log and/or acoustic diarization.

> ⚠️ **Draft, not certified.** Transcript Genie produces a high-quality
> **working/draft transcript** for review, case preparation, and appeal
> support. It is **not** a certified transcript and has not been reviewed by an
> approved court transcriber. Every generated document is labeled accordingly.

---

## Why it exists

Ordering an official transcript is slow and expensive, and generic transcription
tools don't understand courtroom structure. Transcript Genie is purpose-built:

- It reads the **CourtSmart clerk log** to recover the case caption, judge, date,
  and speaker/section timeline — attribution no generic transcriber has.
- It renders output in the **official court format** (Courier, double-spaced,
  1–25 line numbering, caption page, colloquy, certification).
- It runs **on your machine** — confidential audio never leaves the device.

## Features

- **CourtSmart / FTR disc import** — parses `Sessions.csx`, stitches the OGG
  segments, and pulls case metadata + the clerk's speaker/section timeline.
- **Generic audio/video** — transcribe any `mp3` / `wav` / `m4a` / `mp4` /
  `flac` / `ogg` file (via ffmpeg).
- **Local ASR** — faster-whisper with word timestamps, confidence, and a custom
  glossary for proper names/legal terms. (Cloud ASR is a planned opt-in.)
- **Speaker attribution** — clerk-log alignment for CourtSmart, plus optional
  **ECAPA speaker diarization** that corrects sparse/mistimed log tags.
- **Case trimming** — automatically isolates the target case on a multi-case disc.
- **Speaker roster** — override labels (e.g. `THE COURT`, `MR. SMITH`).
- **Court-format DOCX** — caption title page, line-numbered colloquy, examination
  headers, event parentheticals, DRAFT certification page.
- **JSON transcript** — structured output (segments, words, timestamps,
  confidence, speakers) for downstream tooling.

## Status

Active development. The **transcription pipeline is working end-to-end** (CLI).
A desktop GUI (Electron/React) and cross-platform installers are on the roadmap.

| Area | State |
|---|---|
| CourtSmart disc → court-format DOCX/JSON | ✅ working (CLI) |
| Generic audio + speaker diarization | ✅ working (CLI) |
| Desktop GUI (drag-in, review editor, export) | 🚧 planned |
| Cloud ASR option, PDF/SRT/VTT export | 🚧 planned |
| Windows + macOS installers via GitHub Releases | 🚧 planned |

## Download

Grab a build from the [Releases](../../releases) page (published by CI on each `v*` tag):

- **Standalone CLI binary** — `transcript-genie-windows-x64.exe`,
  `transcript-genie-macos-arm64`, or `transcript-genie-linux-x64`. No Python needed;
  core transcription. Requires **ffmpeg** on your `PATH`. (Acoustic diarization needs
  the Python package below.)
- **Python package** — `pipx install transcript_genie-<version>-py3-none-any.whl`, or
  `pip install "transcript-genie[diarize]"` for acoustic speaker diarization.

> macOS: the binary is unsigned — the first run may need right-click → **Open** (or
> `xattr -d com.apple.quarantine transcript-genie-macos-arm64`).

## Requirements

- **Python 3.11 or 3.12** (ctranslate2/faster-whisper wheels aren't published for
  3.13+ yet).
- **ffmpeg** on your `PATH`.
- Optional (for acoustic diarization): PyTorch + SpeechBrain (`[diarize]` extra).

## Install (from source)

```bash
git clone <your-repo-url> transcript-genie
cd transcript-genie
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev]"          # core + tests
pip install -e ".[diarize]"      # optional: acoustic speaker diarization
```

## Usage

```bash
# CourtSmart / FTR disc (a folder containing Sessions.csx):
transcript-genie "E:/" --out-dir ./out --model small \
  --glossary "Smith, Doe, protective order"

# Any audio/video file, with automatic speaker diarization:
transcript-genie ./hearing.mp3 --out-dir ./out --model medium --speakers 3
```

Outputs `transcript.json` and `transcript.docx` in `--out-dir`.

Common flags: `--model` (`tiny`…`large-v3`), `--glossary` (comma-separated names),
`--diarize` / `--no-diarize`, `--speakers N`, `--title`, `--ffmpeg <path>`.

## How it works

```
CourtSmart disc / media file
        │
  ┌─────▼─────┐   ┌──────────┐   ┌───────────────┐   ┌──────────────┐   ┌────────────┐
  │  csx /    │──▶│  media   │──▶│      asr      │──▶│    align /   │──▶│  court_docx │
  │  decode   │   │ (ffmpeg) │   │(faster-whisper)│  │  diarize     │   │  → DOCX/JSON│
  └───────────┘   └──────────┘   └───────────────┘   └──────────────┘   └────────────┘
   parse log &    stitch/downmix   local transcription  speaker + case    official-style
   metadata       to mono WAV      + word confidence    attribution       formatting
```

Each module is small, single-responsibility, and independently tested.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Roadmap

See [`docs/superpowers/specs`](docs/superpowers/specs) for the design and
[`docs/superpowers/plans`](docs/superpowers/plans) for implementation plans.
Next: desktop GUI, cloud ASR opt-in, additional export formats, and
Windows/macOS installers published via GitHub Releases (GitHub Actions matrix).

## Acknowledgments

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[SpeechBrain](https://speechbrain.github.io/),
[python-docx](https://python-docx.readthedocs.io/), and
[ffmpeg](https://ffmpeg.org/).

## License

[MIT](LICENSE) © 2026 the Transcript Genie authors
