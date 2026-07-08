from pathlib import Path

from transcript_genie.csx import CsxFile, CsxSession
from transcript_genie.media import resolve_audio_paths


def _session():
    return CsxSession(
        files=[
            CsxFile("ppdws500.tpd", 0, 1554301396, 1554303369, 0, ".\\00000000"),
            CsxFile("ppdws50d.ogg", 13, 1554301613, 1554302212, 2, ".\\00000000"),
            CsxFile("ppdws50c.ogg", 12, 1554301013, 1554301612, 2, ".\\00000000"),
        ]
    )


def test_resolve_audio_paths_ordered_and_subdir():
    paths = resolve_audio_paths(_session(), Path("J:/"))
    names = [p.name for p in paths]
    assert names == ["ppdws50c.ogg", "ppdws50d.ogg"]  # sequence order, .tpd excluded
    assert paths[0].parent.name == "00000000"           # path subdir applied
