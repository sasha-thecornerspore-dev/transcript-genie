from transcript_genie.model import Segment
from transcript_genie.build import build_plain_transcript


def test_plain_transcript_rosters_speakers_in_order():
    segs = [
        Segment(0.0, 1.0, "a", speaker_id="spk1"),
        Segment(1.0, 2.0, "b", speaker_id="spk2"),
        Segment(2.0, 3.0, "c", speaker_id="spk1"),
    ]
    t = build_plain_transcript(segs, title="Interview 1", hearing_date="July 5, 2026")
    assert t.case_name == "Interview 1"
    assert t.case_number == ""
    assert {s.id: s.label for s in t.speakers} == {"spk1": "SPEAKER 1", "spk2": "SPEAKER 2"}
    assert all(s.name is None for s in t.speakers)   # generic → no names
    assert len(t.segments) == 3


def test_plain_transcript_no_diarization_has_no_speakers():
    segs = [Segment(0.0, 1.0, "a")]   # speaker_id None
    t = build_plain_transcript(segs)
    assert t.speakers == []
