import io
import json
from unittest.mock import patch

from transcript_genie.update import check_for_update, _parts


def _mock(payload):
    return patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode()))


def test_parts_orders_versions():
    assert _parts("v1.2.10") > _parts("1.2.9")
    assert _parts("0.1.0") == (0, 1, 0)


def test_update_available():
    with _mock({"tag_name": "v9.9.9", "html_url": "http://example/rel"}):
        info = check_for_update(current="0.1.0")
    assert info["update_available"] is True
    assert info["latest"] == "9.9.9"
    assert info["url"] == "http://example/rel"


def test_up_to_date():
    with _mock({"tag_name": "v0.1.0", "html_url": "http://example/rel"}):
        info = check_for_update(current="0.1.0")
    assert info["update_available"] is False


def test_cli_version_flag(capsys):
    from transcript_genie import cli, __version__

    rc = cli.main(["--version"])
    assert rc == 0
    assert __version__ in capsys.readouterr().out
