from types import SimpleNamespace

from transcript_genie.asr import whisper_segments_to_model


def test_adapter_maps_segments_and_words():
    raw = [
        SimpleNamespace(
            start=0.0, end=1.5, text=" Good morning.",
            words=[SimpleNamespace(word=" Good", start=0.0, end=0.4, probability=0.91)],
        )
    ]
    segs = whisper_segments_to_model(raw)
    assert len(segs) == 1
    assert segs[0].text == "Good morning."          # stripped
    assert segs[0].speaker_id is None
    assert segs[0].words[0].text == "Good"
    assert abs(segs[0].words[0].confidence - 0.91) < 1e-6


def test_adapter_handles_missing_words():
    raw = [SimpleNamespace(start=0.0, end=1.0, text="Hi", words=None)]
    segs = whisper_segments_to_model(raw)
    assert segs[0].words == []
