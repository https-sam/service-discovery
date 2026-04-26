"""Embedding + cosine retrieval primitives, multi-query, RRF fusion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
QUERY_TASK = "RETRIEVAL_QUERY"
EXPANSION_MODEL = "gemini-2.5-flash"


EXPANSION_PROMPT = """Generate {n} alternative phrasings of the user's query
to broaden retrieval coverage. Return ONLY a JSON array of {n} strings.

User query: {query}
"""


def expand_query(client, query, n):
    response = client.models.generate_content(
        model=EXPANSION_MODEL,
        contents=EXPANSION_PROMPT.format(query=query, n=n),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={"type": "array", "items": {"type": "string"}},
        ),
    )
    return json.loads(response.text)


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
    scores = doc_matrix @ query_vec
    idx = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in idx]



def rrf_fuse(rankings, k_const=60):
    """Reciprocal Rank Fusion across multiple rankings.

    Each chunk's fused score is the sum of 1 / (k_const + rank_in_each_list).
    k_const=60 is the value from the original RRF paper.
    """
    fused = {}
    for ranking in rankings:
        for rank, (idx, _) in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k_const + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])

def load_index(path):
    index = json.loads(Path(path).read_text())
    chunks = index["chunks"]
    doc_matrix = np.array([c["vector"] for c in chunks], dtype=np.float32)
    return chunks, doc_matrix
