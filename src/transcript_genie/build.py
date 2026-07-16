from __future__ import annotations

from .model import Marker, Segment, Speaker, Transcript


def combine_transcripts(sections: list[tuple[str, Transcript]]) -> Transcript:
    """Merge several session transcripts into one, in order, with a centered
    section header before each. Times are offset so sessions don't overlap, and
    speaker ids are namespaced per section (`s0:spk1`) to avoid collisions.
    Case metadata is taken from the first section.
    """
    if not sections:
        return Transcript()
    base = sections[0][1]
    out = Transcript(
        case_name=base.case_name, case_number=base.case_number, court=base.court,
        judge=base.judge, hearing_date=base.hearing_date,
    )
    speakers: dict[str, Speaker] = {}
    offset = 0.0
    for i, (title, tr) in enumerate(sections):
        out.markers.append(Marker(time=offset, kind="section", text=title))
        span = max([s.end for s in tr.segments] + [m.time for m in tr.markers] + [0.0])
        for s in tr.segments:
            sid = f"s{i}:{s.speaker_id}" if s.speaker_id else None
            out.segments.append(
                Segment(s.start + offset, s.end + offset, s.text, sid, list(s.words))
            )
        for m in tr.markers:
            out.markers.append(Marker(m.time + offset, m.kind, m.text))
        for sp in tr.speakers:
            nid = f"s{i}:{sp.id}"
            speakers.setdefault(nid, Speaker(id=nid, label=sp.label, name=sp.name))
        offset += span + 1.0
    out.speakers = list(speakers.values())
    return out


def apply_speaker_roster(transcript: Transcript, roster: dict[str, str]) -> Transcript:
    """Override speaker display labels by speaker id (in place).

    `roster` maps a speaker id (e.g. "court", "plt_atty") to a display label
    (e.g. "THE COURT", "MR. BARRETT"). Unlisted speakers keep their label.
    This is how a user's roster edits (or a per-case preset) are applied.
    """
    for sp in transcript.speakers:
        if sp.id in roster:
            sp.label = roster[sp.id]
    return transcript


def build_plain_transcript(segments: list[Segment], title: str = "", hearing_date: str = "") -> Transcript:
    order: list[str] = []
    for s in segments:
        if s.speaker_id and s.speaker_id not in order:
            order.append(s.speaker_id)
    speakers = [Speaker(id=sid, label=f"SPEAKER {i + 1}") for i, sid in enumerate(order)]
    return Transcript(
        case_name=title,
        case_number="",
        court="",
        judge="",
        hearing_date=hearing_date,
        speakers=speakers,
        segments=list(segments),
        markers=[],
    )
