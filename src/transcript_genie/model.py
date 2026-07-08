from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker_id: str | None = None
    words: list[Word] = field(default_factory=list)


@dataclass
class Speaker:
    id: str
    label: str
    name: str | None = None


@dataclass
class Marker:
    time: float
    kind: str  # "section" | "event"
    text: str


@dataclass
class Transcript:
    case_name: str = ""
    case_number: str = ""
    court: str = ""
    judge: str = ""
    hearing_date: str = ""
    speakers: list[Speaker] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        return cls(
            case_name=d.get("case_name", ""),
            case_number=d.get("case_number", ""),
            court=d.get("court", ""),
            judge=d.get("judge", ""),
            hearing_date=d.get("hearing_date", ""),
            speakers=[Speaker(**s) for s in d.get("speakers", [])],
            segments=[
                Segment(
                    start=s["start"], end=s["end"], text=s["text"],
                    speaker_id=s.get("speaker_id"),
                    words=[Word(**w) for w in s.get("words", [])],
                )
                for s in d.get("segments", [])
            ],
            markers=[Marker(**m) for m in d.get("markers", [])],
        )

    @classmethod
    def from_json(cls, s: str) -> "Transcript":
        return cls.from_dict(json.loads(s))
