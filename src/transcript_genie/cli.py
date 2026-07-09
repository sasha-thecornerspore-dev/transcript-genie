from __future__ import annotations

import argparse
import json
from pathlib import Path

from .align import build_transcript, speaker_anchors
from .asr import LocalWhisperEngine
from .build import apply_speaker_roster, build_plain_transcript
from .court_docx import write_court_docx
from .csx import parse_csx_file
from .diarize import EcapaEmbedder, assign_speakers, refine_speakers
from .media import build_wav, decode_to_wav


def _find_csx(input_dir: Path) -> Path:
    direct = input_dir / "Sessions.csx"
    if direct.exists():
        return direct
    for p in input_dir.rglob("*.csx"):
        return p
    raise FileNotFoundError(f"No .csx session log found under {input_dir}")


def _has_csx(input_dir: Path) -> bool:
    if (input_dir / "Sessions.csx").exists():
        return True
    return next(input_dir.rglob("*.csx"), None) is not None


def _load_roster(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None, engine=None, embedder=None) -> int:
    parser = argparse.ArgumentParser(prog="transcript-genie")
    parser.add_argument("input", help="CourtSmart folder (contains Sessions.csx) or a media file")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--model", default="small", help="faster-whisper model: tiny..large-v3")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--engine", default="local", choices=["local"])
    parser.add_argument("--glossary", default="", help="comma-separated proper names/terms to bias ASR")
    parser.add_argument("--title", default="", help="generic audio: document title (defaults to filename)")
    parser.add_argument(
        "--diarize", action=argparse.BooleanOptionalAction, default=True,
        help="generic audio: acoustic speaker diarization (needs the 'diarize' extra)",
    )
    parser.add_argument(
        "--refine", action=argparse.BooleanOptionalAction, default=False,
        help="CourtSmart: correct clerk-log speaker drift with acoustic diarization "
             "(needs the 'diarize' extra; slower)",
    )
    parser.add_argument(
        "--trim", action=argparse.BooleanOptionalAction, default=True,
        help="CourtSmart: trim to the target case (drop a prior case on the same disc)",
    )
    parser.add_argument("--speakers", type=int, default=None, help="fixed number of speakers, if known")
    parser.add_argument("--roster", default=None, help="path to a JSON {speaker_id: label} roster override")
    parser.add_argument(
        "--jobs", type=int, default=1,
        help="parallel ASR worker processes — splits the audio to speed up long recordings",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if engine is None:
        engine = LocalWhisperEngine(model_size=args.model)
    glossary = [g.strip() for g in args.glossary.split(",") if g.strip()] or None

    if input_path.is_dir() and _has_csx(input_path):
        transcript = _run_courtsmart(input_path, out_dir, engine, glossary, embedder, args)
    elif input_path.is_file():
        transcript = _run_generic(input_path, out_dir, engine, glossary, embedder, args)
    else:
        raise FileNotFoundError(
            f"Input must be a CourtSmart folder (containing a .csx) or a media file: {input_path}"
        )

    roster = _load_roster(args.roster)
    if roster:
        apply_speaker_roster(transcript, roster)

    (out_dir / "transcript.json").write_text(transcript.to_json(), encoding="utf-8")
    write_court_docx(transcript, out_dir / "transcript.docx")
    print(f"Wrote {out_dir / 'transcript.json'} and {out_dir / 'transcript.docx'}")
    return 0


def _transcribe(engine, wav, glossary, args):
    """Single-engine transcription, or parallel workers when --jobs > 1."""
    if getattr(args, "jobs", 1) and args.jobs > 1:
        from .parallel import transcribe_parallel

        return transcribe_parallel(
            wav, model_size=args.model, jobs=args.jobs, glossary=glossary,
            ffmpeg=args.ffmpeg, workdir=wav.parent,
        )
    return engine.transcribe(wav, glossary=glossary)


def _run_courtsmart(input_dir, out_dir, engine, glossary, embedder, args):
    session = parse_csx_file(_find_csx(input_dir))
    wav = build_wav(session, input_dir, out_dir / "audio.wav", ffmpeg=args.ffmpeg)
    segments = _transcribe(engine, wav, glossary, args)
    transcript = build_transcript(session, segments, trim_to_case=args.trim)
    if args.refine:
        if embedder is None:
            embedder = EcapaEmbedder()
        refine_speakers(
            wav, transcript.segments, speaker_anchors(session), embedder, num_speakers=args.speakers
        )
    return transcript


def _run_generic(input_path, out_dir, engine, glossary, embedder, args):
    wav = decode_to_wav(input_path, out_dir / "audio.wav", ffmpeg=args.ffmpeg)
    segments = _transcribe(engine, wav, glossary, args)
    if args.diarize:
        if embedder is None:
            embedder = EcapaEmbedder()
        assign_speakers(wav, segments, embedder, num_speakers=args.speakers)
    return build_plain_transcript(segments, title=args.title or input_path.stem)


if __name__ == "__main__":
    raise SystemExit(main())
