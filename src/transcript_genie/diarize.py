from __future__ import annotations

import wave

from .model import Segment, Speaker


def _remap_first_appearance(labels: list[int]) -> list[int]:
    order: dict[int, int] = {}
    out: list[int] = []
    for lab in labels:
        if lab not in order:
            order[lab] = len(order)
        out.append(order[lab])
    return out


def cluster_segments(
    embeddings: list[list[float]],
    num_speakers: int | None = None,
    threshold: float = 0.75,
) -> list[int]:
    n = len(embeddings)
    if n == 0:
        return []
    if n == 1:
        return [0]

    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    x = np.asarray(embeddings, dtype=float)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    x = x / norms

    if num_speakers is not None:
        k = max(1, min(num_speakers, n))
        model = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
    else:
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average"
        )
    labels = model.fit_predict(x).tolist()
    return _remap_first_appearance(labels)


def load_wav_mono(path):
    import numpy as np

    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


class EcapaEmbedder:
    def __init__(self, savedir: str = "models/ecapa"):
        self.savedir = savedir
        self._model = None

    def _load(self):
        if self._model is None:
            from speechbrain.inference.speaker import EncoderClassifier

            self._model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=self.savedir,
                run_opts={"device": "cpu"},
            )
        return self._model

    def embed(self, waveform, sample_rate):
        import torch

        model = self._load()
        wav = torch.tensor(waveform, dtype=torch.float32).unsqueeze(0)
        emb = model.encode_batch(wav)
        return emb.squeeze().detach().cpu().tolist()


def assign_speakers(
    wav_path,
    segments: list[Segment],
    embedder,
    num_speakers: int | None = None,
    threshold: float = 0.75,
) -> list[Segment]:
    if not segments:
        return segments
    data, sr = load_wav_mono(wav_path)
    min_len = int(0.1 * sr)
    embeddings = []
    for seg in segments:
        a = max(0, int(seg.start * sr))
        b = min(len(data), int(seg.end * sr))
        chunk = data[a:b]
        if len(chunk) < min_len:
            chunk = data[a : a + min_len] if a + min_len <= len(data) else data[-min_len:]
        embeddings.append(embedder.embed(chunk, sr))
    labels = cluster_segments(embeddings, num_speakers=num_speakers, threshold=threshold)
    for seg, lab in zip(segments, labels):
        seg.speaker_id = f"spk{lab + 1}"
    return segments


def _embed_segments(data, sr, segments, embedder):
    min_len = int(0.1 * sr)
    embeddings = []
    for seg in segments:
        a = max(0, int(seg.start * sr))
        b = min(len(data), int(seg.end * sr))
        chunk = data[a:b]
        if len(chunk) < min_len:
            chunk = data[a : a + min_len] if a + min_len <= len(data) else data[-min_len:]
        embeddings.append(embedder.embed(chunk, sr))
    return embeddings


def refine_speakers(
    wav_path,
    segments: list[Segment],
    anchors: list[tuple[float, str]],
    embedder,
    num_speakers: int | None = None,
    threshold: float = 0.6,
) -> list[Segment]:
    """Correct speaker ids using acoustic clustering anchored to clerk tags.

    The clerk log is sparse and mistimed, so a pure time-bisect mislabels long
    stretches (e.g. the judge speaking after a party was last tagged). Here we
    cluster segments acoustically, then map each acoustic cluster to the role of
    the clerk speaker-tags (`anchors`, as (time, speaker_id)) that fall on it —
    so a few correct JUDGE tags reclaim the judge's entire voice cluster.
    Segments in a cluster that no anchor lands on keep their existing id.
    """
    if not segments:
        return segments
    from collections import Counter, defaultdict

    data, sr = load_wav_mono(wav_path)
    embeddings = _embed_segments(data, sr, segments, embedder)
    clusters = cluster_segments(embeddings, num_speakers=num_speakers, threshold=threshold)

    bounds = [(s.start, s.end) for s in segments]
    votes: dict[int, Counter] = defaultdict(Counter)
    for atime, role in anchors:
        idx = next((i for i, (st, en) in enumerate(bounds) if st <= atime < en), None)
        if idx is None:
            idx = min(range(len(bounds)), key=lambda i: abs(bounds[i][0] - atime))
        votes[clusters[idx]][role] += 1
    cluster_role = {c: cnt.most_common(1)[0][0] for c, cnt in votes.items() if cnt}

    for seg, c in zip(segments, clusters):
        if c in cluster_role:
            seg.speaker_id = cluster_role[c]
    return segments


def embed_transcript(transcript, wav_path, embedder) -> list[list[float]]:
    """Voice embeddings for each segment — the slow part. Cache and reuse these
    to re-cluster (re-tune speakers) instantly."""
    data, sr = load_wav_mono(wav_path)
    return _embed_segments(data, sr, transcript.segments, embedder)


def diarize_transcript(transcript, wav_path, embedder, threshold: float = 0.80,
                       min_cluster: int = 10, num_speakers: int | None = None,
                       embeddings: list[list[float]] | None = None):
    """Assign acoustic speaker labels to a transcript (in place).

    Clusters segments by voice (cosine, tuned for single-mic courtroom audio),
    folds tiny noise clusters into "SPEAKER (unclear)", and labels the real
    voices SPEAKER 1..N by cluster size. Speech-only labels — no case roles.

    Pass `embeddings` (from `embed_transcript`) to skip re-embedding — this makes
    re-tuning `threshold`/`num_speakers`/`min_cluster` effectively instant.
    """
    from collections import Counter

    segs = transcript.segments
    if not segs:
        return transcript
    if embeddings is None:
        embeddings = embed_transcript(transcript, wav_path, embedder)
    labels = cluster_segments(embeddings, num_speakers=num_speakers, threshold=threshold)

    sizes = Counter(labels)
    big = [cid for cid, _ in sizes.most_common() if sizes[cid] >= min_cluster]
    rank = {cid: i + 1 for i, cid in enumerate(big)}
    for seg, lab in zip(segs, labels):
        seg.speaker_id = f"spk{rank[lab]}" if lab in rank else "spk_unclear"

    roster: dict[str, str] = {}
    for seg in segs:
        if seg.speaker_id not in roster:
            roster[seg.speaker_id] = (
                "SPEAKER (unclear)" if seg.speaker_id == "spk_unclear"
                else f"SPEAKER {seg.speaker_id[3:]}"
            )
    transcript.speakers = [Speaker(id=k, label=v) for k, v in roster.items()]
    return transcript
