from transcript_genie.csx import CsxFile, CsxSession, CsxTag
from transcript_genie.model import Segment
from transcript_genie.align import (
    classify_tag,
    extract_case,
    format_hearing_date,
    build_transcript,
)


def test_classify_speakers_sections_events():
    assert classify_tag("_______JUDGE_________").speaker_id == "court"
    assert classify_tag("~Plt Atty John Smith").speaker_id == "plt_atty"
    assert classify_tag("~Plt Atty John Smith").name == "John Smith"
    assert classify_tag(">Def Atty Jane Doe").label == "COUNSEL FOR DEFENDANT"
    assert classify_tag("Plt John Smith").speaker_id == "plt"
    assert classify_tag("DIRECT EXAM_______").kind == "section"
    assert classify_tag("DIRECT EXAM_______").label == "DIRECT EXAMINATION"
    assert classify_tag("__WITNESS: John Smith").speaker_id == "witness"
    assert classify_tag("__WITNESS: John Smith").name == "John Smith"
    assert classify_tag("---END OF CASE---").kind == "event"
    assert classify_tag("").kind == "blank"


def _session():
    s = CsxSession(
        judge="Vance", room="Court 15", timeoffset=-240,
        files=[CsxFile("ppdws50c.ogg", 12, 1554301013, 1554301612, 2, ".\\00000000")],
        tags=[
            CsxTag(1554301013, 0, "===JOHN SMITH v. JANE SMITH C-03-FM-19-000000", "sharon"),
            CsxTag(1554301113, 0, "_______JUDGE_________", "sharon"),          # +100s
            CsxTag(1554301213, 0, "DIRECT EXAM_______", "sharon"),             # +200s
            CsxTag(1554301313, 0, "~Plt Atty John Smith", "sharon"),           # +300s
        ],
    )
    return s


def test_extract_case_and_date():
    name, number = extract_case(_session())
    assert name == "John Smith v. Jane Smith"
    assert number == "C-03-FM-19-000000"
    assert format_hearing_date(_session()) == "April 3, 2019"


def test_build_transcript_assigns_speakers_and_markers():
    segs = [
        Segment(start=150.0, end=151.0, text="Good morning."),   # after JUDGE(100s)
        Segment(start=320.0, end=321.0, text="Objection."),      # after Plt Atty(300s)
    ]
    t = build_transcript(_session(), segs)
    assert t.case_number == "C-03-FM-19-000000"
    assert t.segments[0].speaker_id == "court"
    assert t.segments[1].speaker_id == "plt_atty"
    assert any(m.text == "DIRECT EXAMINATION" for m in t.markers)
    assert {sp.id for sp in t.speakers} >= {"court", "plt_atty"}


def test_case_header_not_emitted_as_marker():
    s = CsxSession(
        judge="Vance", room="Court 15", timeoffset=-240,
        files=[CsxFile("ppdws50c.ogg", 12, 1554301013, 1554301612, 2, ".\\00000000")],
        tags=[
            CsxTag(1554301013, 0, "===JOHN SMITH v. JANE SMITH C-03-FM-19-000000", "sharon"),
            CsxTag(1554301113, 0, "_______JUDGE_________", "sharon"),
            CsxTag(1554301213, 0, "DIRECT EXAM_______", "sharon"),
        ],
    )
    t = build_transcript(s, [])
    # Case number should still be extracted for the title page
    assert t.case_number == "C-03-FM-19-000000"
    # Case header should NOT be echoed into the body as a stray marker
    marker_texts = " ".join(m.text for m in t.markers)
    assert "v." not in marker_texts
    assert "C-03" not in marker_texts
    assert "C 03" not in marker_texts
    # Legitimate section markers should still be present
    assert any(m.text == "DIRECT EXAMINATION" for m in t.markers)
