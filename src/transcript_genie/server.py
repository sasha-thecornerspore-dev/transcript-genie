"""Local web GUI backend for Transcript Genie.

A small FastAPI app that accepts an uploaded audio/video file, runs the
transcription pipeline in a background thread, and exposes the transcript for
review + a court-formatted DOCX for download. Serves a self-contained (no build
step, no external CDN) single-page frontend from ``static/index.html``.

This is the reusable UI core; an Electron shell can later wrap the same page and
spawn this server as a sidecar.
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from .build import apply_speaker_roster, build_plain_transcript
from .court_docx import write_court_docx
from .media import decode_to_wav
from .model import Transcript

STATIC = Path(__file__).parent / "static"


@dataclass
class Job:
    id: str
    workdir: Path
    filename: str
    status: str = "queued"        # queued | running | done | error
    message: str = ""
    progress: float = 0.0         # 0..1 during transcription
    error: str | None = None
    transcript: Transcript | None = field(default=None)
    embeddings: list | None = None   # cached voice embeddings -> instant re-diarize


def create_app(engine=None, embedder=None) -> FastAPI:
    """Build the app. ``engine``/``embedder`` can be injected for testing;
    otherwise they are constructed lazily per job from the request options."""
    app = FastAPI(title="Transcript Genie")
    jobs: dict[str, Job] = {}
    app.state.jobs = jobs

    def _make_engine(model: str):
        if engine is not None:
            return engine
        from .asr import LocalWhisperEngine

        return LocalWhisperEngine(model_size=model)

    def _make_embedder():
        if embedder is not None:
            return embedder
        from .diarize import EcapaEmbedder

        return EcapaEmbedder()

    def _save(job: Job, tr: Transcript) -> None:
        (job.workdir / "transcript.json").write_text(tr.to_json(), encoding="utf-8")
        write_court_docx(tr, job.workdir / "transcript.docx")

    def _run(job: Job, audio_path: Path, opts: dict) -> None:
        try:
            job.status = "running"
            job.message = "Decoding audio…"
            wav = decode_to_wav(audio_path, job.workdir / "audio.wav")

            def _progress(done: int, total: int) -> None:
                job.progress = (done / total) if total else 0.0
                job.message = f"Transcribing… {done}/{total} segments of audio"

            if engine is not None:                       # injected (tests)
                job.message = "Transcribing…"
                segments = engine.transcribe(wav, glossary=opts["glossary"])
            else:
                from .parallel import resolve_pace, transcribe_parallel

                n_jobs, cpu_threads, low = resolve_pace(opts["pace"])
                job.message = f"Transcribing… ({opts['pace']}, {n_jobs} workers)"
                segments = transcribe_parallel(
                    wav, model_size=opts["model"], jobs=n_jobs, glossary=opts["glossary"],
                    cpu_threads=cpu_threads, workdir=job.workdir, progress=_progress,
                    low_priority=low,
                )
            job.message = "Formatting…"
            job.progress = 1.0
            tr = build_plain_transcript(segments, title=opts["title"] or Path(job.filename).stem)
            if opts["diarize"]:
                from .diarize import diarize_transcript, embed_transcript

                job.message = "Identifying speakers…"
                emb = embed_transcript(tr, wav, _make_embedder())
                job.embeddings = emb                 # cached -> re-tuning is instant
                diarize_transcript(
                    tr, wav, _make_embedder(), threshold=opts["threshold"],
                    min_cluster=opts["min_cluster"], num_speakers=opts["speakers"],
                    embeddings=emb,
                )
            _save(job, tr)
            job.transcript = tr
            job.status = "done"
            job.message = "Done"
        except Exception as exc:  # surface any pipeline failure to the UI
            job.error = str(exc)
            job.message = f"Error: {exc}"
            job.status = "error"

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.post("/api/jobs")
    async def create_job(
        file: UploadFile = File(...),
        model: str = Form("small"),
        diarize: bool = Form(True),
        speakers: int | None = Form(None),
        glossary: str = Form(""),
        title: str = Form(""),
        pace: str = Form("balanced"),
        threshold: float = Form(0.80),
        min_cluster: int = Form(10),
    ) -> JSONResponse:
        job_id = uuid.uuid4().hex[:12]
        workdir = Path(tempfile.mkdtemp(prefix=f"tg_{job_id}_"))
        src = workdir / (file.filename or "input")
        src.write_bytes(await file.read())
        job = Job(id=job_id, workdir=workdir, filename=file.filename or "input")
        jobs[job_id] = job
        opts = {
            "model": model,
            "diarize": diarize,
            "speakers": speakers,
            "glossary": [g.strip() for g in glossary.split(",") if g.strip()] or None,
            "title": title,
            "pace": pace,
            "threshold": threshold,
            "min_cluster": min_cluster,
        }
        threading.Thread(target=_run, args=(job, src, opts), daemon=True).start()
        return JSONResponse({"id": job_id})

    def _get(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> JSONResponse:
        job = _get(job_id)
        body: dict = {
            "id": job.id, "status": job.status, "message": job.message,
            "progress": round(job.progress, 3),
        }
        if job.status == "done" and job.transcript is not None:
            body["transcript"] = job.transcript.to_dict()
        if job.status == "error":
            body["error"] = job.error
        return JSONResponse(body)

    @app.get("/api/jobs/{job_id}/audio")
    def job_audio(job_id: str) -> FileResponse:
        job = _get(job_id)
        wav = job.workdir / "audio.wav"
        if not wav.exists():
            raise HTTPException(404, "audio not ready")
        return FileResponse(wav, media_type="audio/wav")

    @app.post("/api/jobs/{job_id}/export")
    async def job_export(job_id: str, payload: dict) -> JSONResponse:
        """Persist an edited transcript (from the review UI) and regenerate DOCX."""
        job = _get(job_id)
        tr = Transcript.from_dict(payload)
        roster = payload.get("_roster")
        if isinstance(roster, dict):
            apply_speaker_roster(tr, roster)
        job.transcript = tr
        (job.workdir / "transcript.json").write_text(tr.to_json(), encoding="utf-8")
        write_court_docx(tr, job.workdir / "transcript.docx")
        return JSONResponse({"ok": True})

    @app.post("/api/jobs/{job_id}/rediarize")
    def job_rediarize(job_id: str, payload: dict) -> JSONResponse:
        """Re-cluster speakers with new settings. Instant once embeddings cached."""
        job = _get(job_id)
        if job.transcript is None:
            raise HTTPException(409, "transcript not ready")
        from .diarize import diarize_transcript, embed_transcript

        wav = job.workdir / "audio.wav"
        if job.embeddings is None:
            job.embeddings = embed_transcript(job.transcript, wav, _make_embedder())
        n = payload.get("num_speakers")
        diarize_transcript(
            job.transcript, wav, _make_embedder(),
            threshold=float(payload.get("threshold", 0.80)),
            min_cluster=int(payload.get("min_cluster", 10)),
            num_speakers=int(n) if n else None,
            embeddings=job.embeddings,
        )
        _save(job, job.transcript)
        return JSONResponse({"transcript": job.transcript.to_dict()})

    @app.get("/api/jobs/{job_id}/export.txt")
    def job_txt(job_id: str) -> PlainTextResponse:
        job = _get(job_id)
        if job.transcript is None:
            raise HTTPException(409, "transcript not ready")
        tr = job.transcript
        labels = {s.id: s.label for s in tr.speakers}
        lines: list[str] = []
        last: object = object()
        for seg in sorted(tr.segments, key=lambda s: s.start):
            if seg.speaker_id != last:
                lines.append(f"\n{labels.get(seg.speaker_id, 'SPEAKER')}:  {seg.text}")
                last = seg.speaker_id
            else:
                lines.append(seg.text)
        return PlainTextResponse("\n".join(lines).strip())

    @app.get("/api/jobs/{job_id}/export.json")
    def job_json(job_id: str) -> JSONResponse:
        job = _get(job_id)
        if job.transcript is None:
            raise HTTPException(409, "transcript not ready")
        return JSONResponse(job.transcript.to_dict())

    @app.get("/api/jobs/{job_id}/docx")
    def job_docx(job_id: str) -> FileResponse:
        job = _get(job_id)
        docx = job.workdir / "transcript.docx"
        if not docx.exists():
            raise HTTPException(404, "docx not ready")
        return FileResponse(
            docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="transcript.docx",
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8756, open_browser: bool = True) -> None:
    import uvicorn

    if open_browser:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    run()
