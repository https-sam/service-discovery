from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
QUERY_TASK = "RETRIEVAL_QUERY"
EXPANSION_MODEL = "gemini-3-flash-preview"
ANSWER_MODEL = "gemini-3-flash-preview"

# for multi query rag fusion
EXPANSION_PROMPT = """The user is searching a corpus of microservice
documentation. Each service has sections like Overview, Language & framework,
APIs exposed, Services it depends on, Core functionalities, Notable dependencies.

Generate {n} alternative phrasings of the user's query that:
  - use related vocabulary / synonyms
  - vary specificity (broader and more specific framings)
  - approach from different angles (functional, technical, operational)

The point is to retrieve relevant chunks the original phrasing might miss.

Return ONLY a JSON array of {n} strings. No commentary.

User query: {query}
"""


ANSWER_PROMPT = """Answer the user's question about a microservice catalog
using ONLY the sources below. Be concise and direct.

Rules:
  - Cite sources inline with [N], where N matches the source number.
  - If the sources don't contain enough information, say "I don't have
    enough information to answer that." Do not guess or use general knowledge.
  - When multiple sources support the same claim, cite all of them: [1][3].

Question: {query}

Sources:
{sources}
"""


def expand_query(client: genai.Client, query: str, n: int) -> list[str]:
    response = client.models.generate_content(
        model=EXPANSION_MODEL,
        contents=EXPANSION_PROMPT.format(query=query, n=n),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={"type": "array", "items": {"type": "string"}},
        ),
    )
    return json.loads(response.text)


def _build_answer_prompt(query: str, hits: list[tuple[int, dict]]) -> str:
    sources = "\n\n".join(
        f"[{n}] {c['service_name']} · {c['section']}\n{c['text']}"
        for n, c in hits
    )
    return ANSWER_PROMPT.format(query=query, sources=sources)


def generate_answer(client: genai.Client, query: str,
                    hits: list[tuple[int, dict]]) -> str:
    """Synthesize an answer from the retrieved chunks.

    `hits` is `[(N, chunk_dict), ...]` where N is the citation number the
    model should use (1-indexed to match how we display them).
    """
    prompt = _build_answer_prompt(query, hits)
    response = client.models.generate_content(model=ANSWER_MODEL, contents=prompt)
    return response.text


def generate_answer_stream(client: genai.Client, query: str,
                           hits: list[tuple[int, dict]]):
    """Yield text deltas as Gemini emits them - for SSE streaming to a UI."""
    prompt = _build_answer_prompt(query, hits)
    for chunk in client.models.generate_content_stream(
        model=ANSWER_MODEL, contents=prompt
    ):
        if chunk.text:
            yield chunk.text


def embed_query(client: genai.Client, text: str) -> np.ndarray:
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=QUERY_TASK,
            output_dimensionality=EMBED_DIM,
        ),
    )
    return np.array(result.embeddings[0].values, dtype=np.float32)


def cosine_top_k(query_vec: np.ndarray, doc_matrix: np.ndarray,
                 k: int) -> list[tuple[int, float]]:
    """Top-K cosine similarity. Inputs are L2-normalized → dot = cosine."""
    scores = doc_matrix @ query_vec
    idx = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in idx]


def rrf_fuse(rankings: list[list[tuple[int, float]]],
             k_const: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion across multiple rankings.

    Each chunk's fused score = Σ 1 / (k_const + rank_in_that_list).
    k_const=60 is the value from the original RRF paper; it dampens
    contributions from low-ranked hits.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, (idx, _) in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k_const + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])


def load_index(path: Path) -> tuple[list[dict], np.ndarray]:
    """Load the persisted index and return (chunk list, stacked vector matrix)."""
    index = json.loads(path.read_text())
    chunks = index["chunks"]
    doc_matrix = np.array([c["vector"] for c in chunks], dtype=np.float32)
    return chunks, doc_matrix


def get_backend() -> str:
    """Return the currently-selected backend: ``"gemini"`` or ``"vertex"``."""
    return os.environ.get("GENAI_BACKEND", "gemini").lower()


def build_client() -> genai.Client:
    """Construct the single genai client used by the whole app.

    Backend chosen by the GENAI_BACKEND env var:
      - ``gemini`` → Developer API via GEMINI_API_KEY
      - ``vertex`` → Vertex AI via ADC + GOOGLE_CLOUD_PROJECT
    """
    backend = get_backend()
    if backend == "vertex":
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    if backend == "gemini":
        # Suppress any stale env-var that would force the SDK back to Vertex.
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    raise ValueError(f"GENAI_BACKEND must be 'vertex' or 'gemini', got {backend!r}")


def run_query(
    query_text: str,
    chunks: list[dict],
    doc_matrix: np.ndarray,
    client: genai.Client,
    k: int = 5,
    per_query_k: int = 10,
    expansions_n: int = 4,
) -> dict:
    """End-to-end: expand → embed → retrieve → fuse → answer.

    Returns ``{query, expansions, hits, answer}``. Used by the eval runner.
    """
    expansions = expand_query(client, query_text, expansions_n)
    queries = [query_text] + expansions
    query_vecs = [embed_query(client, q) for q in queries]
    rankings = [cosine_top_k(qv, doc_matrix, per_query_k) for qv in query_vecs]
    fused = rrf_fuse(rankings)[:k]

    hits = [
        {**chunks[idx], "rank": rank, "rrf_score": score}
        for rank, (idx, score) in enumerate(fused, 1)
    ]
    hits_for_prompt = [(h["rank"], h) for h in hits]
    answer = generate_answer(client, query_text, hits_for_prompt)

    return {
        "query": query_text,
        "expansions": expansions,
        "hits": hits,
        "answer": answer,
    }
