import math
import struct
import wave

from transcript_genie.model import Segment, Speaker, Transcript
from transcript_genie.build import combine_transcripts
from transcript_genie.diarize import diarize_transcript


def test_combine_offsets_sections_and_namespaces():
    a = Transcript(case_name="A v. B", case_number="1-C-2", court="Court 1",
                   segments=[Segment(0, 5, "one", speaker_id="spk1")],
                   speakers=[Speaker("spk1", "SPEAKER 1")])
    b = Transcript(segments=[Segment(0, 3, "two", speaker_id="spk1")],
                   speakers=[Speaker("spk1", "SPEAKER 1")])
    out = combine_transcripts([("Session 1", a), ("Session 2", b)])

    assert out.case_name == "A v. B" and out.case_number == "1-C-2"     # from first
    assert [m.text for m in out.markers if m.kind == "section"] == ["Session 1", "Session 2"]
    assert [s.text for s in out.segments] == ["one", "two"]
    assert out.segments[1].start >= 5                                   # second session offset
    assert out.segments[0].speaker_id == "s0:spk1"
    assert out.segments[1].speaker_id == "s1:spk1"                      # namespaced, no collision
    assert {sp.id for sp in out.speakers} == {"s0:spk1", "s1:spk1"}


class ToneEmbedder:
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


def test_diarize_transcript_labels_and_roster(tmp_path):
    p = tmp_path / "a.wav"
    _wav(p, [0.8, 0.05, 0.8])
    tr = Transcript(segments=[Segment(0, 1, "x"), Segment(1, 2, "y"), Segment(2, 3, "z")])
    diarize_transcript(tr, p, ToneEmbedder(), num_speakers=2, min_cluster=1)
    ids = [s.speaker_id for s in tr.segments]
    assert ids[0] == ids[2] and ids[0] != ids[1]                       # loud grouped, quiet apart
    assert all(sp.label.startswith("SPEAKER") for sp in tr.speakers)
    assert {s.speaker_id for s in tr.segments} == {sp.id for sp in tr.speakers}
