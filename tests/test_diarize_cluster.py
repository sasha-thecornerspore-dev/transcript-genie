from transcript_genie.diarize import cluster_segments


def test_two_clear_speakers_first_appearance_order():
    # A-ish, B-ish, A-ish, B-ish embeddings (well separated)
    embs = [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1], [0.1, 0.9]]
    labels = cluster_segments(embs, num_speakers=2)
    assert labels[0] == 0            # first speaker is 0
    assert labels[1] == 1
    assert labels[0] == labels[2]    # A grouped with A
    assert labels[1] == labels[3]    # B grouped with B


def test_single_embedding_is_speaker_zero():
    assert cluster_segments([[1.0, 2.0]]) == [0]


def test_empty_returns_empty():
    assert cluster_segments([]) == []
