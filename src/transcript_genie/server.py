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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

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
    error: str | None = None
    transcript: Transcript | None = field(default=None)


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

    def _run(job: Job, audio_path: Path, opts: dict) -> None:
        try:
            job.status = "running"
            job.message = "Decoding audio…"
            wav = decode_to_wav(audio_path, job.workdir / "audio.wav")
            job.message = "Transcribing… (this can take a while)"
            segments = _make_engine(opts["model"]).transcribe(wav, glossary=opts["glossary"])
            if opts["diarize"]:
                from .diarize import assign_speakers

                job.message = "Identifying speakers…"
                assign_speakers(wav, segments, _make_embedder(), num_speakers=opts["speakers"])
            job.message = "Formatting…"
            tr = build_plain_transcript(segments, title=opts["title"] or Path(job.filename).stem)
            (job.workdir / "transcript.json").write_text(tr.to_json(), encoding="utf-8")
            write_court_docx(tr, job.workdir / "transcript.docx")
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
        body: dict = {"id": job.id, "status": job.status, "message": job.message}
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
