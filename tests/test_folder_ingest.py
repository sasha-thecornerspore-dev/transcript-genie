from types import SimpleNamespace

from transcript_genie.media import folder_audio_files
from transcript_genie.model import Transcript
from transcript_genie.cli import _apply_metadata


def test_folder_audio_files_sorted_and_filtered(tmp_path):
    for name in ["b.ogg", "a.ogg", "c.mp3", "notes.txt", "d.wav", "cover.jpg"]:
        (tmp_path / name).write_bytes(b"x")
    files = folder_audio_files(tmp_path)
    assert [p.name for p in files] == ["a.ogg", "b.ogg", "c.mp3", "d.wav"]


def test_apply_metadata_overrides_when_given():
    tr = Transcript()
    args = SimpleNamespace(
        case_name="Doe v. Roe", case_number="1-C-2-3", court="Court 9", judge="Kim", date="Jan 1, 2020",
    )
    _apply_metadata(tr, args)
    assert tr.case_name == "Doe v. Roe"
    assert tr.case_number == "1-C-2-3"
    assert tr.court == "Court 9"
    assert tr.judge == "Kim"
    assert tr.hearing_date == "Jan 1, 2020"


def test_apply_metadata_leaves_empty_alone():
    tr = Transcript(case_name="Existing")
    args = SimpleNamespace(case_name="", case_number="", court="", judge="", date="")
    _apply_metadata(tr, args)
    assert tr.case_name == "Existing"
