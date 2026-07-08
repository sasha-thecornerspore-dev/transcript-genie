from transcript_genie.csx import CsxFile, CsxSession, CsxTag
from transcript_genie.model import Segment, Speaker, Transcript
from transcript_genie.align import build_transcript, case_window
from transcript_genie.build import apply_speaker_roster


def _session():
    # origin = 1000 (first audio file starttime). Prior case, END OF CASE at +100,
    # target caption at +130, target END OF CASE at +900.
    return CsxSession(
        judge="Vance", room="Court 15", timeoffset=-240,
        files=[CsxFile("a.ogg", 12, 1000, 2000, 2, ".\\00000000")],
        tags=[
            CsxTag(1100, 0, "------ END OF CASE ------", "sharon"),      # +100
            CsxTag(1130, 0, "===JOHN SMITH v. JANE SMITH C-03-FM-19-000000", "sharon"),  # +130
            CsxTag(1140, 0, "_______JUDGE_________", "sharon"),          # +140
            CsxTag(1900, 0, "------ END OF CASE ------", "sharon"),      # +900
        ],
    )


def test_case_window_bounds_the_target_case():
    start, end = case_window(_session())
    assert start == 100.0     # END OF CASE just before the caption
    assert end == 900.0       # next END OF CASE


def test_trim_drops_prior_case_segments():
    segs = [
        Segment(50.0, 51.0, "prior case tail"),      # before window → dropped
        Segment(150.0, 151.0, "target case"),        # in window → kept, court
        Segment(950.0, 951.0, "after window"),       # after window → dropped
    ]
    t = build_transcript(_session(), segs, trim_to_case=True)
    assert len(t.segments) == 1
    assert t.segments[0].text == "target case"
    assert t.segments[0].speaker_id == "court"


def test_no_trim_by_default_keeps_everything():
    segs = [Segment(50.0, 51.0, "a"), Segment(150.0, 151.0, "b")]
    t = build_transcript(_session(), segs)          # trim_to_case defaults False
    assert len(t.segments) == 2


def test_apply_speaker_roster_overrides_labels():
    t = Transcript(speakers=[
        Speaker("court", "THE COURT"),
        Speaker("plt_atty", "COUNSEL FOR PLAINTIFF", name="Todd Barrett"),
    ])
    apply_speaker_roster(t, {"plt_atty": "MR. BARRETT"})
    labels = {s.id: s.label for s in t.speakers}
    assert labels["plt_atty"] == "MR. BARRETT"
    assert labels["court"] == "THE COURT"           # unlisted unchanged
