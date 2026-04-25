"""Embedding + cosine retrieval primitives."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
QUERY_TASK = "RETRIEVAL_QUERY"


def embed_query(client, text):
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=QUERY_TASK,
            output_dimensionality=EMBED_DIM,
        ),
    )
    return np.array(result.embeddings[0].values, dtype=np.float32)


def cosine_top_k(query_vec, doc_matrix, k):
    """Top-K cosine similarity. Inputs are L2-normalized so dot is cosine."""
    scores = doc_matrix @ query_vec
    idx = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in idx]


def load_index(path):
    index = json.loads(Path(path).read_text())
    chunks = index["chunks"]
    doc_matrix = np.array([c["vector"] for c in chunks], dtype=np.float32)
    return chunks, doc_matrix
