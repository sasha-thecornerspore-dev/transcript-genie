from __future__ import annotations

from .model import Segment, Speaker, Transcript


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
