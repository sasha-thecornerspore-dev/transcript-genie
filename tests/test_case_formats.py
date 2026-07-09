from transcript_genie.csx import CsxFile, CsxSession, CsxTag
from transcript_genie.align import extract_case


def _sess(tag_text):
    return CsxSession(
        files=[CsxFile("a.ogg", 12, 1000, 2000, 2, ".")],
        tags=[CsxTag(1000, 0, tag_text, "clerk")],
    )


def test_mdec_format_v_dot():
    name, num = extract_case(_sess("===JOHN SMITH v. JANE SMITH C-03-FM-19-000000"))
    assert name == "John Smith v. Jane Smith"
    assert num == "C-03-FM-19-000000"


def test_older_baltimore_city_vs():
    name, num = extract_case(_sess("===Smith vs Smith 03-C-18-012834"))
    assert name == "Smith v. Smith"
    assert num == "03-C-18-012834"


def test_versus_word_form():
    name, num = extract_case(_sess("Doe versus Roe 24-C-20-001111"))
    assert name == "Doe v. Roe"
    assert num == "24-C-20-001111"


def test_no_match_returns_empty():
    assert extract_case(_sess("just some clerk note")) == ("", "")
