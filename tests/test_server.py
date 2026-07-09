import math
import struct
import time
import wave

from fastapi.testclient import TestClient

from transcript_genie import server
from transcript_genie.model import Segment


class FakeEngine:
    def transcribe(self, wav_path, glossary=None):
        return [Segment(0.0, 1.0, "Hello."), Segment(1.0, 2.0, "World.")]


def _fake_decode(src, out, **kwargs):
    from pathlib import Path

    out = Path(out)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(0.1 * 32767 * math.sin(2 * math.pi * 200 * i / 16000)))
                for i in range(16000)
            )
        )
    return out


def _wait(client, jid, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/jobs/{jid}").json()
        if s["status"] in ("done", "error"):
            return s
        time.sleep(0.1)
    return client.get(f"/api/jobs/{jid}").json()


def test_index_served():
    client = TestClient(server.create_app(engine=FakeEngine()))
    assert "Transcript Genie" in client.get("/").text


def test_full_web_flow(monkeypatch):
    monkeypatch.setattr(server, "decode_to_wav", _fake_decode)
    client = TestClient(server.create_app(engine=FakeEngine()))

    r = client.post(
        "/api/jobs",
        files={"file": ("clip.mp3", b"not-a-real-mp3", "audio/mpeg")},
        data={"diarize": "false", "model": "small"},
    )
    jid = r.json()["id"]

    s = _wait(client, jid)
    assert s["status"] == "done", s
    assert s["transcript"]["case_name"] == "clip"          # title from filename stem
    assert s["transcript"]["segments"][0]["text"] == "Hello."

    assert client.get(f"/api/jobs/{jid}/audio").status_code == 200
    assert client.get(f"/api/jobs/{jid}/docx").status_code == 200

    edited = s["transcript"]
    edited["segments"][0]["text"] = "Edited."
    assert client.post(f"/api/jobs/{jid}/export", json=edited).json()["ok"] is True


def test_unknown_job_404():
    client = TestClient(server.create_app(engine=FakeEngine()))
    assert client.get("/api/jobs/nope").status_code == 404
