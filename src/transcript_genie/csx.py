from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass
class CsxFile:
    filename: str
    sequence: int
    starttime: int
    stoptime: int
    type: int
    path: str


@dataclass
class CsxTag:
    indextime: int
    entertime: int
    text: str
    username: str


@dataclass
class CsxSession:
    case: str = ""
    caption: str = ""
    judge: str = ""
    room: str = ""
    type: str = ""
    channels: int = 0
    samplerate: int = 0
    starttime: int = 0
    stoptime: int = 0
    timeoffset: int = 0
    firstfile: str = ""
    tags: list[CsxTag] = field(default_factory=list)
    files: list[CsxFile] = field(default_factory=list)

    @property
    def audio_files(self) -> list[CsxFile]:
        return sorted((f for f in self.files if f.type == 2), key=lambda f: f.sequence)

    @property
    def audio_origin(self) -> int:
        af = self.audio_files
        return af[0].starttime if af else self.starttime


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int(attrib: dict, key: str, default: int = 0) -> int:
    if key not in attrib:
        return default
    try:
        return int(attrib[key])
    except (TypeError, ValueError):
        raise ValueError(
            f"CourtSmart .csx: attribute {key!r}={attrib[key]!r} is not an integer"
        ) from None


def parse_csx(data: bytes) -> CsxSession:
    root = ET.fromstring(data)
    session_el = next((el for el in root.iter() if _local(el.tag) == "session"), None)
    if session_el is None:
        raise ValueError("No <cs:session> element found in .csx data")
    a = session_el.attrib
    tags: list[CsxTag] = []
    files: list[CsxFile] = []
    for el in session_el:
        name = _local(el.tag)
        if name == "tag":
            tags.append(
                CsxTag(
                    indextime=_int(el.attrib, "indextime"),
                    entertime=_int(el.attrib, "entertime"),
                    text=(el.text or "").strip(),
                    username=el.attrib.get("username", ""),
                )
            )
        elif name == "file":
            fa = el.attrib
            files.append(
                CsxFile(
                    filename=fa.get("filename", ""),
                    sequence=_int(fa, "sequence"),
                    starttime=_int(fa, "starttime"),
                    stoptime=_int(fa, "stoptime"),
                    type=_int(fa, "type"),
                    path=fa.get("path", ""),
                )
            )
    return CsxSession(
        case=a.get("case", ""),
        caption=a.get("caption", ""),
        judge=a.get("judge", ""),
        room=a.get("room", ""),
        type=a.get("type", ""),
        channels=_int(a, "channels"),
        samplerate=_int(a, "samplerate"),
        starttime=_int(a, "starttime"),
        stoptime=_int(a, "stoptime"),
        timeoffset=_int(a, "timeoffset"),
        firstfile=a.get("firstfile", ""),
        tags=tags,
        files=files,
    )


def parse_csx_file(path) -> CsxSession:
    return parse_csx(Path(path).read_bytes())
