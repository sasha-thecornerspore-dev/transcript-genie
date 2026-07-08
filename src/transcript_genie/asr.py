from __future__ import annotations

from typing import Protocol

from .model import Segment, Word


class ASREngine(Protocol):
    def transcribe(self, wav_path, glossary: list[str] | None = None) -> list[Segment]:
        ...


def whisper_segments_to_model(raw_segments) -> list[Segment]:
    segments: list[Segment] = []
    for s in raw_segments:
        words = []
        for w in (getattr(s, "words", None) or []):
            words.append(
                Word(
                    text=(w.word or "").strip(),
                    start=float(w.start),
                    end=float(w.end),
                    confidence=float(getattr(w, "probability", 1.0)),
                )
            )
        segments.append(
            Segment(
                start=float(s.start),
                end=float(s.end),
                text=(s.text or "").strip(),
                speaker_id=None,
                words=words,
            )
        )
    return segments


class LocalWhisperEngine:
    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "auto"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, wav_path, glossary: list[str] | None = None) -> list[Segment]:
        model = self._load()
        prompt = ", ".join(glossary) if glossary else None
        raw, _info = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            initial_prompt=prompt,
            vad_filter=True,
        )
        return whisper_segments_to_model(raw)
