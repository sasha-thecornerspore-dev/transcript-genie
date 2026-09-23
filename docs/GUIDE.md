# Transcript Genie — User Guide

A step-by-step walkthrough of producing a court-quality draft transcript, from
raw audio to a reviewed, speaker-labeled DOCX. Everything runs on your machine.

> ⚠️ **Draft, not certified.** Output is a working transcript for review and case
> preparation, not a certified court transcript. Every document is labeled as a draft.

---

## 1. Install and launch

Use a standalone binary from the [Releases](../../releases) page (no Python
needed — just make sure **ffmpeg** is on your `PATH`), or install from source:

```bash
pip install "transcript-genie[web]"     # add [diarize] for acoustic speaker ID
transcript-genie-web
```

The command starts a local server at `http://127.0.0.1:8756` and opens your
browser. Nothing is uploaded anywhere.

## 2. Import your audio

![Import screen](images/import-screen.png)

Drop an audio or video file onto the drop zone (or click to choose), then set:

| Control | What it does |
|---|---|
| **Model** | Accuracy vs. speed. `small` is a good default; `medium` / `large-v3` are more accurate but slower. |
| **Speakers (optional)** | Leave blank to auto-detect, or set a known count. |
| **Identify speakers** | Turn on acoustic diarization (needs the `diarize` extra). |
| **Glossary** | Comma-separated proper names and legal terms to bias recognition — e.g. party names, `protective order`. This markedly improves name spelling. |
| **Title** | Document title (defaults to the filename). |
| **CPU pace** | **Aggressive** (fastest, most cores), **Balanced** (~half your cores), or **Background** (few cores + low priority, so your machine stays usable during a long run). |

Click **Transcribe**. A progress bar tracks the run, and long jobs checkpoint as
they go — if the app is interrupted, restarting resumes where it left off.

## 3. Review the transcript

When transcription finishes, the **review desk** opens:

![Review desk](images/review-desk.png)

### Playback
- **▶ Play / ⏸ Pause**, **⏪ 5s / 5s ⏩** skip, and a **Speed** slider (0.5–2×).
- Keyboard: **Space** = play/pause, **←/→** = skip 5 seconds.
- **Click any line** to jump the audio to that moment. The currently-playing line
  is highlighted as the audio advances.

### Reading and searching
- Each line shows its **timestamp** and a color-coded **speaker**.
- **Find in transcript** filters/highlights matching lines and shows a match count.
- Lines whose recognition confidence is low get an **amber marker** and a tooltip —
  these are the spots worth checking against the audio.

### Fixing the text
- Click into any line to **edit the words** directly.

## 4. Get the speakers right

Diarization gives a first pass; a court transcript has to be right line by line.
The left panel gives you both bulk and per-line control.

### Bulk re-detection (Speaker detection panel)

Voice fingerprints are cached after the first pass, so re-detecting is **instant**.
Adjust and click **Re-detect speakers**:

| Slider | Effect |
|---|---|
| **Sensitivity** | Lower splits more voices apart; higher merges them together. |
| **Ignore clusters under N lines** | Folds tiny noise clusters into “SPEAKER (unclear)”. |
| **Force speaker count** | `0` = auto; set it if you know exactly how many voices there are. |

The hint line reports how many voices it found, so you can nudge the settings and
re-detect until it matches reality.

> **Tuning tip.** There is no single “correct” setting — it depends on the
> recording. A long session can over-split into many spurious voices; raise
> **Sensitivity** and/or **Ignore clusters under** and re-detect. A short, clean
> two-party hearing usually needs almost no tuning. Because re-detection is
> instant, iterate freely.

### Per-line correction

For anything diarization missed:
- Change a single line's speaker from its **dropdown** — reassign one
  misattributed line without touching the rest.
- **+ Add speaker** creates a new labelled voice (works even with diarization
  off), and it immediately appears in every line's dropdown — useful to split a
  merged voice or tag a speaker the pass missed.
- **Rename** a speaker once in the roster and every line updates.

## 5. Export

- **Save & download DOCX** — the official-style court transcript: caption page,
  Courier double-spaced body, 1–25 line numbering, colloquy, and a DRAFT
  certification page.
- **Download .txt** — plain speaker-labeled text.
- **Download .json** — structured data (segments, words, timestamps, confidence,
  speakers) for downstream tooling.

All exports reflect your edits — text changes, speaker reassignments, and renames.

---

## CLI equivalent

Everything above is also available headless. See the
[README](../README.md#cli) for the full flag list. Common runs:

```bash
# A single media file, auto speaker detection, all cores:
transcript-genie ./hearing.mp3 --out-dir ./out --model medium --pace aggressive

# A CourtSmart / FTR disc folder (contains Sessions.csx):
transcript-genie "E:/" --out-dir ./out --glossary "Smith, Doe, protective order"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg not found` | Install ffmpeg and ensure it's on your `PATH`, or pass `--ffmpeg /path/to/ffmpeg`. |
| Names spelled wrong | Add them to the **Glossary**. |
| Too many / too few speakers | Re-detect with a different **Sensitivity** or **Ignore clusters under**, or set **Force speaker count**. |
| macOS won't open the binary | It's unsigned: right-click → **Open**, or `xattr -d com.apple.quarantine transcript-genie-macos-arm64`. |
| A long run got interrupted | Just start it again — it resumes from the last checkpoint. |
