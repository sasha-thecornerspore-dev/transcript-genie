"""Check GitHub Releases for a newer version (self-update helper).

Uses only the standard library so it works from a frozen binary. Compares the
installed version against the latest *stable* release (GitHub's
`/releases/latest` excludes the rolling `latest` prerelease).
"""

from __future__ import annotations

import json
import urllib.request

from . import __version__

REPO = "sasha-thecornerspore-dev/transcript-genie"


def _parts(v: str) -> tuple[int, ...]:
    out = []
    for token in v.lstrip("vV").split("."):
        num = "".join(ch for ch in token if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def check_for_update(repo: str = REPO, current: str | None = None, timeout: float = 5.0) -> dict:
    """Return {current, latest, url, update_available}. Raises on network error."""
    current = current or __version__
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "transcript-genie"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    latest = (data.get("tag_name") or "").lstrip("vV")
    return {
        "current": current,
        "latest": latest,
        "url": data.get("html_url", ""),
        "update_available": bool(latest) and _parts(latest) > _parts(current),
    }
