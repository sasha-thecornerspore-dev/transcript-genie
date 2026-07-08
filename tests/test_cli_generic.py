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
