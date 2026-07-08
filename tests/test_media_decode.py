from transcript_genie.media import ffmpeg_decode_cmd


def test_decode_cmd_downmixes_mono_16k():
    cmd = ffmpeg_decode_cmd("in.mp3", "out.wav", ffmpeg="ffmpeg")
    assert cmd[0] == "ffmpeg"
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[-1] == "out.wav"
    assert "in.mp3" in cmd[cmd.index("-i") + 1]
