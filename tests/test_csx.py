import pytest

from transcript_genie.csx import parse_csx, CsxSession, CsxFile

SAMPLE = (
    '<?xml version="1.0" encoding="utf-16"?>'
    '<cs:store xmlns:cs="http://www.courtsmart.com/XMLNS/csmtsoapstore1000">'
    '<cs:session room="Court 15" case="---" type="CRIMINAL/CIVIL" '
    'caption="Judges Vance - Sharon" judge="Vance" channels="4" samplerate="12000" '
    'starttime="1554293813" stoptime="1554311668" timeoffset="-240" '
    'firstfile="ppdws50c.ogg">'
    '<cs:tag indextime="1554301711" entertime="1554301615" private="0" username="sharon">'
    'DIRECT EXAM_______</cs:tag>'
    '<cs:file fileid="0" starttime="1554301396" stoptime="1554303369" sequence="0" '
    'type="0" filename="ppdws500.tpd" path=".\\00000000"/>'
    '<cs:file fileid="781297" starttime="1554301013" stoptime="1554301612" sequence="12" '
    'type="2" filename="ppdws50c.ogg" path=".\\00000000"/>'
    '<cs:file fileid="781304" starttime="1554301613" stoptime="1554302212" sequence="13" '
    'type="2" filename="ppdws50d.ogg" path=".\\00000000"/>'
    '</cs:session></cs:store>'
).encode("utf-16")


def test_parse_session_attributes():
    s = parse_csx(SAMPLE)
    assert s.judge == "Vance"
    assert s.channels == 4
    assert s.timeoffset == -240
    assert s.firstfile == "ppdws50c.ogg"


def test_audio_files_sorted_and_origin():
    s = parse_csx(SAMPLE)
    assert [f.filename for f in s.audio_files] == ["ppdws50c.ogg", "ppdws50d.ogg"]
    assert s.audio_origin == 1554301013  # first audio segment starttime, not the .tpd


def test_tags_parsed():
    s = parse_csx(SAMPLE)
    assert len(s.tags) == 1
    assert s.tags[0].text == "DIRECT EXAM_______"
    assert s.tags[0].username == "sharon"


def test_malformed_integer_attribute_raises():
    """Test that a present but non-integer attribute raises ValueError."""
    malformed = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<cs:store xmlns:cs="http://www.courtsmart.com/XMLNS/csmtsoapstore1000">'
        '<cs:session room="Court 15" case="---" type="CRIMINAL/CIVIL" '
        'caption="Judges Vance - Sharon" judge="Vance" channels="4" samplerate="12000" '
        'starttime="1554293813" stoptime="1554311668" timeoffset="-240" '
        'firstfile="ppdws50c.ogg">'
        '<cs:file fileid="0" starttime="1554301396" stoptime="1554303369" sequence="NaN" '
        'type="0" filename="ppdws500.tpd" path=".\\00000000"/>'
        '</cs:session></cs:store>'
    ).encode("utf-16")
    with pytest.raises(ValueError, match="attribute 'sequence'"):
        parse_csx(malformed)


def test_audio_origin_fallback_to_session_starttime():
    """Test that audio_origin falls back to session starttime when no type-2 files."""
    session = CsxSession(
        starttime=999,
        files=[CsxFile("x.tpd", 0, 111, 222, 0, ".")],
    )
    assert session.audio_files == []
    assert session.audio_origin == 999
