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
        return [float(np.abs(w).mean()), float((w > 0).mean())]


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
