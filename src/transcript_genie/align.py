from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from .csx import CsxSession
from .model import Marker, Segment, Speaker, Transcript

_NOISE = re.compile(r"[_\-=~>]+")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    t = text.lstrip("~>").strip()
    t = _NOISE.sub(" ", t)
    return _WS.sub(" ", t).strip()


@dataclass
class TagClass:
    kind: str
    speaker_id: str | None = None
    label: str | None = None
    name: str | None = None


def _trailing_name(cleaned: str, after: str) -> str | None:
    idx = cleaned.upper().find(after.upper())
    if idx == -1:
        return None
    rest = cleaned[idx + len(after):].strip(" :")
    return rest or None


def classify_tag(text: str) -> TagClass:
    c = _clean(text)
    u = c.upper()
    if not c:
        return TagClass("blank")
    if "END OF CASE" in u:
        return TagClass("event", label="(End of case.)")
    if "OFF THE RECORD" in u or "RECESS" in u:
        return TagClass("event", label="(Off the record — recess.)")
    if "WITNESS CALLED AND SWORN" in u:
        return TagClass("event", label="(Witness called and sworn.)")
    if "WITNESS STANDS DOWN" in u:
        return TagClass("event", label="(Witness stands down.)")
    if "WITNESS:" in u:
        return TagClass("speaker", "witness", "THE WITNESS", _trailing_name(c, "WITNESS:"))
    if "REDIRECT" in u:
        return TagClass("section", label="REDIRECT EXAMINATION")
    if "RECROSS" in u:
        return TagClass("section", label="RECROSS EXAMINATION")
    if "DIRECT EXAM" in u:
        return TagClass("section", label="DIRECT EXAMINATION")
    if "CROSS EXAM" in u:
        return TagClass("section", label="CROSS EXAMINATION")
    if "RULING" in u:
        return TagClass("section", label="RULING OF THE COURT")
    if "JUDGE" in u:
        return TagClass("speaker", "court", "THE COURT")
    if "PLT ATTY" in u or "PLAINTIFF ATTY" in u:
        return TagClass("speaker", "plt_atty", "COUNSEL FOR PLAINTIFF",
                        _trailing_name(c, "ATTY"))
    if "DEF ATTY" in u or "DEFENDANT ATTY" in u:
        return TagClass("speaker", "def_atty", "COUNSEL FOR DEFENDANT",
                        _trailing_name(c, "ATTY"))
    if u.startswith("PLT "):
        return TagClass("speaker", "plt", "PLAINTIFF", c[4:].strip() or None)
    if u.startswith("DEF "):
        return TagClass("speaker", "def", "DEFENDANT", c[4:].strip() or None)
    return TagClass("event", label=f"({c}.)")


_CASE_RE = re.compile(
    r"(?P<a>[A-Za-z.\- ]+?)\s+(?:v\.?|vs\.?|versus)\s+(?P<b>[A-Za-z.\- ]+?)\s+"
    # Maryland case numbers: C-03-FM-19-807568 (MDEC) or 03-C-18-012834 (older).
    r"(?P<num>C-\d{2}-[A-Z]{2}-\d{2}-\d+|\d{2}-C-\d{2}-\d+)",
    re.IGNORECASE,
)


def _titlecase(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def extract_case(session: CsxSession) -> tuple[str, str]:
    for tag in session.tags:
        # Match the RAW text: _clean() would strip the hyphens the case
        # number depends on. The lazy [A-Za-z.\- ] group skips leading "===".
        m = _CASE_RE.search(tag.text)
        if m:
            name = f"{_titlecase(m.group('a'))} v. {_titlecase(m.group('b'))}"
            return name, m.group("num").upper()
    return "", ""


def format_hearing_date(session: CsxSession) -> str:
    tz = timezone(timedelta(minutes=session.timeoffset))
    dt = datetime.fromtimestamp(session.audio_origin, tz=tz)
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def speaker_anchors(session: CsxSession) -> list[tuple[float, str]]:
    """(audio-relative time, speaker_id) for every clerk speaker tag.

    These are sparse, approximately-timed anchors used to map acoustic
    diarization clusters back to courtroom roles.
    """
    origin = session.audio_origin
    out: list[tuple[float, str]] = []
    for tag in sorted(session.tags, key=lambda t: t.indextime):
        if _CASE_RE.search(tag.text):
            continue
        tc = classify_tag(tag.text)
        if tc.kind == "speaker" and tc.speaker_id:
            out.append((max(0.0, float(tag.indextime - origin)), tc.speaker_id))
    return out


def case_window(session: CsxSession) -> tuple[float | None, float | None]:
    """Audio-relative [start, end) seconds bounding the LAST case on the disc.

    A CourtSmart disc often carries the tail of a prior case before the target
    hearing. The clerk marks boundaries with "END OF CASE". The target case
    runs from the END-OF-CASE just before its caption to the next END-OF-CASE.
    Returns (None, None) when no caption tag is present (→ no trimming).
    """
    origin = session.audio_origin
    eoc = sorted(
        max(0.0, float(t.indextime - origin))
        for t in session.tags
        if classify_tag(t.text).label == "(End of case.)"
    )
    header_t: float | None = None
    for t in session.tags:
        if _CASE_RE.search(t.text):
            header_t = max(0.0, float(t.indextime - origin))
            break
    if header_t is None:
        return (None, None)
    start = max((t for t in eoc if t <= header_t), default=0.0)
    end = min((t for t in eoc if t > start + 1.0), default=None)
    return (start, end)


def build_transcript(
    session: CsxSession, segments: list[Segment], trim_to_case: bool = False
) -> Transcript:
    origin = session.audio_origin
    turns: list[tuple[float, str]] = []          # (time, speaker_id)
    speakers: dict[str, Speaker] = {}
    markers: list[Marker] = []
    for tag in sorted(session.tags, key=lambda t: t.indextime):
        # The case caption is rendered on the title page (see extract_case);
        # don't also echo it into the transcript body as a stray marker.
        if _CASE_RE.search(tag.text):
            continue
        t = max(0.0, float(tag.indextime - origin))
        tc = classify_tag(tag.text)
        if tc.kind == "speaker":
            turns.append((t, tc.speaker_id))
            if tc.speaker_id not in speakers:
                speakers[tc.speaker_id] = Speaker(id=tc.speaker_id, label=tc.label, name=tc.name)
            elif tc.name and not speakers[tc.speaker_id].name:
                speakers[tc.speaker_id].name = tc.name
        elif tc.kind in ("section", "event"):
            markers.append(Marker(time=t, kind=tc.kind, text=tc.label))

    turns.sort(key=lambda x: x[0])
    turn_times = [t for t, _ in turns]
    for seg in segments:
        idx = bisect_right(turn_times, seg.start) - 1
        seg.speaker_id = turns[idx][1] if idx >= 0 else None

    name, number = extract_case(session)
    transcript = Transcript(
        case_name=name,
        case_number=number,
        court=session.room,
        judge=session.judge,
        hearing_date=format_hearing_date(session),
        speakers=list(speakers.values()),
        segments=segments,
        markers=markers,
    )

    if trim_to_case:
        start, end = case_window(session)
        if start is not None:
            hi = end if end is not None else float("inf")
            transcript.segments = [s for s in transcript.segments if start <= s.start < hi]
            transcript.markers = [m for m in transcript.markers if start < m.time < hi]

    return transcript
