import math
import struct
import wave

from transcript_genie.csx import CsxFile, CsxSession, CsxTag
from transcript_genie.model import Segment
from transcript_genie.align import speaker_anchors
from transcript_genie.diarize import refine_speakers


class ToneEmbedder:
    # Direction-distinct embedding (clustering L2-normalizes, so magnitude-only
    # differences would collapse — mirror how real ECAPA vectors differ in angle).
    def embed(self, waveform, sample_rate):
        import numpy as np
        w = np.asarray(waveform, dtype=float)
        m = min(1.0, float(np.abs(w).mean()))
        return [m, 1.0 - m]


def _wav(path, amps, sr=16000):
    frames = []
    for amp in amps:
        for i in range(sr):
            frames.append(int(amp * 32767 * math.sin(2 * math.pi * 200 * i / sr)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))


def test_refine_reclaims_cluster_from_sparse_anchor(tmp_path):
    # Segments: loud, quiet, loud. Only ONE anchor per voice.
    p = tmp_path / "a.wav"
    _wav(p, [0.8, 0.05, 0.8])
    segs = [
        Segment(0.0, 1.0, "one", speaker_id="def"),   # wrong initial label
        Segment(1.0, 2.0, "two", speaker_id="def"),
        Segment(2.0, 3.0, "three", speaker_id="def"),  # wrong initial label
    ]
    anchors = [(0.5, "court"), (1.5, "def")]           # sparse, one per voice
    out = refine_speakers(p, segs, anchors, ToneEmbedder(), num_speakers=2)
    assert out[0].speaker_id == "court"    # loud cluster reclaimed by the court anchor
    assert out[1].speaker_id == "def"      # quiet cluster
    assert out[2].speaker_id == "court"    # second loud segment fixed despite no anchor


def test_speaker_anchors_from_log():
    s = CsxSession(
        files=[CsxFile("a.ogg", 12, 1000, 2000, 2, ".")],
        tags=[
            CsxTag(1130, 0, "===A v. B C-03-FM-19-000000", "x"),   # caption → skipped
            CsxTag(1140, 0, "_______JUDGE_________", "x"),         # +140 court
            CsxTag(1200, 0, "~Def Judy Roe", "x"),                 # +200 def
        ],
    )
    anchors = speaker_anchors(s)
    assert anchors == [(140.0, "court"), (200.0, "def")]


def test_refine_empty_is_noop(tmp_path):
    assert refine_speakers(tmp_path / "x.wav", [], [], ToneEmbedder()) == []
