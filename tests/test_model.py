from transcript_genie.model import Word, Segment, Speaker, Marker, Transcript


def test_transcript_json_roundtrip():
    t = Transcript(
        case_name="John Smith v. Jane Smith",
        case_number="C-03-FM-19-000000",
        court="Court 15",
        judge="Vance",
        hearing_date="April 3, 2019",
        speakers=[Speaker(id="court", label="THE COURT")],
        segments=[
            Segment(start=1.0, end=2.5, text="Good morning.", speaker_id="court",
                    words=[Word(text="Good", start=1.0, end=1.3, confidence=0.9)])
        ],
        markers=[Marker(time=0.0, kind="event", text="(Court in session.)")],
    )
    restored = Transcript.from_json(t.to_json())
    assert restored == t
    assert restored.segments[0].words[0].text == "Good"
    assert restored.markers[0].kind == "event"
