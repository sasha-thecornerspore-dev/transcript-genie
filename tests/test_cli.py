import json

from transcript_genie.model import Segment
from transcript_genie import cli


class FakeEngine:
    def transcribe(self, wav_path, glossary=None):
        return [Segment(150.0, 151.0, "Good morning.")]


def test_cli_end_to_end(tmp_path, monkeypatch):
    disc = tmp_path / "disc"
    (disc / "00000000").mkdir(parents=True)
    csx = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<cs:store xmlns:cs="http://www.courtsmart.com/XMLNS/csmtsoapstore1000">'
        '<cs:session room="Court 15" judge="Vance" channels="4" samplerate="12000" '
        'starttime="1554293813" timeoffset="-240" firstfile="ppdws50c.ogg">'
        '<cs:tag indextime="1554301013" entertime="0" username="sharon">'
        '===JOHN SMITH v. JANE SMITH C-03-FM-19-000000</cs:tag>'
        '<cs:tag indextime="1554301113" entertime="0" username="sharon">'
        '_______JUDGE_________</cs:tag>'
        '<cs:file starttime="1554301013" stoptime="1554301612" sequence="12" '
        'type="2" filename="ppdws50c.ogg" path=".\\00000000"/>'
        '</cs:session></cs:store>'
    ).encode("utf-16")
    (disc / "Sessions.csx").write_bytes(csx)

    # Do not actually call ffmpeg; pretend a wav was produced.
    monkeypatch.setattr(cli, "build_wav", lambda *a, **k: tmp_path / "out.wav")

    rc = cli.main([str(disc), "--out-dir", str(tmp_path)], engine=FakeEngine())
    assert rc == 0

    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert data["case_number"] == "C-03-FM-19-000000"
    assert data["segments"][0]["speaker_id"] == "court"
    assert (tmp_path / "transcript.docx").exists()
