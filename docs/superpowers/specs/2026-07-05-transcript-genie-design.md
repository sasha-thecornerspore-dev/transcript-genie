# Transcript Genie — Design Spec

**Date:** 2026-07-05
**Status:** Approved (brainstorming complete)
**First test target:** CourtSmart disc — *Alan Whitfield v. Diane Whitfield*, C-03-FM-19-001234 (Baltimore County, MD; Judge Vance; recorded 2019-04-03)

---

## 1. Summary

Transcript Genie is a **local-first desktop application** that converts courtroom and legal
audio into high-quality, court-formatted, speaker-labeled transcripts. It specializes in
**CourtSmart / FTR digital-recording discs** (multichannel OGG audio plus a clerk-authored
`Sessions.csx` event log) but also accepts generic audio/video files. Speech-to-text runs
**fully offline by default** (faster-whisper); a **cloud ASR engine is opt-in per job**.
Users review the transcript against synchronized audio in a built-in editor, then export to
DOCX, PDF, TXT, SRT/VTT, or JSON.

### Non-goals / honest scope boundary
- The app produces a **working/draft transcript**, clearly labeled as such. A *certified* or
  *official* transcript in Maryland (and most jurisdictions) must be produced by an approved
  court transcriber. The tool is for case prep, review, appeal support, and for ordering an
  official version — it does not itself certify.
- Not a general-purpose media editor. Audio processing exists only to serve transcription.

---

## 2. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| ASR | **Local default (faster-whisper) + optional cloud** | Confidential family-court audio stays on device; cloud available when the user opts in. |
| UI / packaging | **Electron + React/TypeScript**, packaged Windows installer | Lower build risk than Tauri; mature Python-sidecar + waveform patterns. |
| Backend | **Python FastAPI sidecar** | One language for the whole ML/export pipeline; independently CLI-testable. |
| Scope | **Full suite, staged delivery** | Working transcript out of the Whitfield disc early; remaining subsystems as follow-on plans. |
| License | **MIT** | Simple, permissive, standard for tooling. |

---

## 3. Architecture

```
┌─────────────────────────── Desktop App (Electron) ─────────────────────────┐
│  React / TypeScript UI                                                      │
│   • Import wizard        • Waveform + synced playback (wavesurfer.js)       │
│   • Transcript editor    • Speaker / label panel   • Export dialog          │
│   • Project / case manager   • Batch queue                                  │
└───────────────▲─────────────────────────────────────────────────────────────┘
                │  HTTP + WebSocket over localhost (job control + progress stream)
┌───────────────▼───────────────── Python backend (packaged sidecar) ─────────┐
│  FastAPI service                                                            │
│   • CourtSmart .csx / FTR parser      • ffmpeg decode + channel mix/merge    │
│   • ASR engine abstraction:                                                  │
│         - LocalWhisperEngine (faster-whisper, word timestamps + confidence)  │
│         - CloudEngine (adapter interface; opt-in)                            │
│   • Diarization: pyannote  +  per-channel  +  .csx-log alignment             │
│   • Transcript model (JSON: segments → words, timestamps, confidence, spkr)  │
│   • Formatter → DOCX / PDF / TXT / SRT / VTT / JSON                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **IPC:** Frontend talks to the sidecar over `127.0.0.1` HTTP (REST for actions) + WebSocket
  (progress/ASR streaming). Sidecar binds to a random free port, reported to the shell at launch.
- **Packaging:** electron-builder for the shell; the Python sidecar is frozen with PyInstaller;
  **ffmpeg is bundled**. No external runtime required by the end user.
- **State:** Projects are folders on disk (a `project.json` manifest + working audio + transcript
  JSON + exports). Optional at-rest encryption of the project folder.

---

## 4. Court-quality core (the differentiator)

### 4.1 CourtSmart importer
- Parse `Sessions.csx` (UTF-16 XML, `courtsmart.com` namespace). Extract:
  - **Session metadata:** room, case, type, caption, judge, channel count, sample rate,
    `starttime`/`stoptime`, `timeoffset` (tz), ordered audio file list (`<cs:file>` by `sequence`).
  - **Tag timeline:** every `<cs:tag>` with `indextime`/`entertime` and its label text
    (speaker turns, `WITNESS CALLED AND SWORN`, `DIRECT/CROSS EXAM`, `RULING`, `RECESS`,
    `END OF CASE`, etc.).
- Decode the OGG channels with ffmpeg; stitch by `sequence`/`starttime` into a continuous
  timeline; produce a working mixdown plus retained per-channel audio.

### 4.2 `.csx`-log alignment (key feature)
- Convert clerk tag timestamps to audio-relative offsets and align them to ASR segments.
- Derive **speaker labels** (THE COURT, MR. BARRETT, MS. CORTEZ, THE WITNESS, etc.)
  and **section headers** (examination headers, sworn/stand-down, rulings, recesses) directly
  from the log — attribution no generic transcriber has.
- Log is authoritative for structure; ASR fills the words; user can correct either.

### 4.3 ASR
- **faster-whisper** local: selectable model (tiny → large-v3), GPU when available, word-level
  timestamps and per-word confidence, language selection.
- **Custom vocabulary / glossary:** proper names and legal terms (e.g. "Barrett",
  "Cortez") biased so they transcribe correctly.
- **Cloud engine:** adapter interface (e.g. Deepgram/OpenAI-style) selectable per job; never
  used unless explicitly chosen.

### 4.4 Diarization (fallback when no log)
- pyannote speaker diarization and/or per-channel separation, merged with any partial log data.

---

## 5. Court formatting & export

- **Template engine** with jurisdiction presets (Maryland-family default; US-federal secondary):
  - Title / caption page (court, case name & number, hearing type, date, judge, location).
  - Appearances page (counsel and whom they represent).
  - Line-numbered body (25 lines/page default), speaker labels in caps, **Q./A.** during
    examination, examination headers, event parentheticals (`(Witness sworn.)`, `(Recess taken.)`).
  - Witness & exhibit index with page references.
  - **Certification / disclaimer page** ("working/draft transcript — not certified").
- **Exports:** DOCX (primary, via python-docx), PDF, TXT, SRT/VTT, JSON. Optional condensed
  (4-up) layout and configurable page/line numbering.

---

## 6. Review editor (high-utility)

Three-pane layout: **waveform + transport ⟷ transcript ⟷ speaker/label panel**.
- Click any word to seek audio; word-synced highlight during playback.
- Keyboard transport + foot-pedal support; adjustable playback speed.
- **Low-confidence words highlighted** for targeted verification.
- Inline editing; find/replace; mark `[inaudible]` / `[crosstalk]`.
- Rename / merge speakers globally; glossary manager.

---

## 7. Case management, privacy, deliverables

- **Projects** with case metadata, batch queue, exhibits and witness index.
- **Privacy:** local-only processing by default; optional encrypted project folder; clear
  draft/non-certified labeling; audit log of processing steps.
- **GitHub deliverables:** README with screenshots, install + usage walkthroughs, user guide,
  MIT `LICENSE`, Windows installer, and a tagged release.

---

## 8. Component boundaries (for isolation/testability)

| Unit | Purpose | Depends on |
|---|---|---|
| `csx_parser` | Parse `Sessions.csx` → structured session + tags | stdlib only |
| `media` | ffmpeg decode / channel mix / stitch | ffmpeg |
| `asr` | Engine abstraction; local + cloud implementations | faster-whisper / cloud SDK |
| `diarize` | Speaker segmentation fallback | pyannote |
| `align` | Merge ASR + diarization + `.csx` log → transcript model | csx_parser, asr, diarize |
| `transcript` | In-memory model + JSON (de)serialization | — |
| `format` | Transcript model → DOCX/PDF/TXT/SRT/VTT | transcript, python-docx, reportlab |
| `api` | FastAPI job control + progress WS | all above |
| `ui` | Electron/React shell, editor, wizards | api |

Each unit is independently testable; the pipeline (`csx_parser` → `media` → `asr` → `align` →
`format`) is exercisable from a CLI before any UI exists.

---

## 9. Error handling

- **Missing/locked disc or unreadable `.csx`:** surface a clear message; allow manual metadata entry.
- **ffmpeg/codec failures:** report the offending file; continue with the remaining channels.
- **ASR failure or OOM:** fall back to a smaller model; checkpoint completed segments so a job resumes.
- **Log/ASR timeline mismatch:** flag misaligned regions in the editor rather than guessing silently.
- **Cloud errors:** never silently fall back to cloud or from cloud; report and stop.

---

## 10. Testing strategy

- **Unit:** `csx_parser` against the real `Sessions.csx`; `format` against golden DOCX/PDF fixtures.
- **Integration:** full pipeline on the Whitfield disc → transcript JSON → DOCX, asserting caption,
  appearances, examination headers, and speaker attribution derived from the log.
- **Manual/UI:** editor sync (click-to-seek, highlight), export round-trips, batch queue.

---

## 11. Recommended build sequence (one product, staged plans)

1. **Python pipeline core** — `.csx` parse + ffmpeg decode/stitch + faster-whisper → transcript
   JSON, CLI-tested **on the Whitfield disc**.
2. **DOCX court formatter** — first real transcript out.
3. **`.csx`-log speaker alignment** + diarization fallback.
4. **Electron/React shell + review editor** wired to the backend.
5. **Cloud ASR option**, additional export formats, batch queue.
6. **Packaging, installer, screenshots, full docs, GitHub release.**

The **first implementation plan covers steps 1–2 (+ a thin UI to run it)** so a real transcript
of the hearing exists early; remaining steps become their own plans.
