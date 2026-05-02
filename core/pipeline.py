"""LangGraph pipeline. Classifier emits {strategy, filter}.

This first cut wires the classifier and an open multi-query retrieval node.
Specialized routes (scoped, aggregate) come next.
"""

from __future__ import annotations

import json
from queue import Queue
from typing import Any, TypedDict

import numpy as np
from google import genai
from google.genai import types
from langgraph.graph import END, StateGraph

from .rag import (
    cosine_top_k,
    embed_query,
    expand_query,
    rrf_fuse,
    generate_answer_stream,
)


CLASSIFIER_MODEL = "gemini-2.5-flash"

CLASSIFIER_PROMPT = """Classify the user's query against a microservice catalog.

Available filter fields:
  service_name: one of [{services}]
  section:      one of [{sections}]

Strategies:
  "open"      — rank across the whole corpus semantically
  "scoped"    — about specific service(s); filter then rank within
  "aggregate" — asks for every match; filter and return all

If unsure, choose "open".

User query: {query}
"""


class State(TypedDict, total=False):
    query: str
    strategy: str
    filter: dict[str, str]
    expansions: list[str]
    hits: list[dict]
    answer: str
    chunks: list[dict]
    doc_matrix: np.ndarray
    client: genai.Client
    event_queue: Queue


def _emit(state, event, data):
    state["event_queue"].put((event, data))


def _strip_vector(chunk):
    return {k: v for k, v in chunk.items() if k != "vector"}


def classify_node(state):
    _emit(state, "step_started", {"id": "classify", "label": "classify query"})
    services = sorted({c["service_name"] for c in state["chunks"]})
    sections = sorted({c["section"] for c in state["chunks"]})
    prompt = CLASSIFIER_PROMPT.format(
        services=", ".join(services),
        sections=", ".join(sections),
        query=state["query"],
    )
    response = state["client"].models.generate_content(
        model=CLASSIFIER_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "strategy": {"type": "string", "enum": ["open", "scoped", "aggregate"]},
                    "filter": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string"},
                            "section": {"type": "string"},
                        },
                    },
                },
                "required": ["strategy"],
            },
        ),
    )
    plan = json.loads(response.text)
    strategy = plan["strategy"]
    filter_ = plan.get("filter", {}) or {}
    _emit(state, "step_done", {"id": "classify",
                               "data": {"strategy": strategy, "filter": filter_}})
    return {"strategy": strategy, "filter": filter_}


def open_retrieve_node(state):
    chunks = state["chunks"]
    doc_matrix = state["doc_matrix"]
    client = state["client"]

    _emit(state, "step_started", {"id": "expand", "label": "query expansion"})
    expansions = expand_query(client, state["query"], 4)
    queries = [state["query"]] + expansions
    _emit(state, "step_done", {"id": "expand", "data": {"queries": queries}})

    _emit(state, "step_started", {"id": "embed", "label": "embed queries"})
    query_vecs = [embed_query(client, q) for q in queries]
    _emit(state, "step_done", {"id": "embed", "data": {"count": len(query_vecs)}})

    _emit(state, "step_started", {"id": "retrieve", "label": "retrieve top-k"})
    rankings = [cosine_top_k(qv, doc_matrix, 10) for qv in query_vecs]
    _emit(state, "step_done", {"id": "retrieve", "data": {}})

    _emit(state, "step_started", {"id": "fuse", "label": "rrf fusion"})
    fused = rrf_fuse(rankings)[:5]
    hits = [
        {**_strip_vector(chunks[idx]), "rank": rank, "rrf_score": round(score, 4)}
        for rank, (idx, score) in enumerate(fused, 1)
    ]
    _emit(state, "step_done", {"id": "fuse", "data": {"hits": hits}})
    return {"expansions": expansions, "hits": hits}


def _matches(chunk, flt):
    for field, expected in flt.items():
        if chunk.get(field) != expected:
            return False
    return True


def scoped_retrieve_node(state):
    chunks = state["chunks"]
    flt = state["filter"]
    client = state["client"]

    _emit(state, "step_started", {"id": "filter", "label": "metadata filter"})
    subset_idx = [i for i, c in enumerate(chunks) if _matches(c, flt)]
    _emit(state, "step_done", {"id": "filter",
                               "data": {"filter": flt,
                                        "matched_chunks": len(subset_idx)}})

    _emit(state, "step_started", {"id": "embed", "label": "embed query"})
    qv = embed_query(client, state["query"])
    _emit(state, "step_done", {"id": "embed", "data": {"count": 1}})

    _emit(state, "step_started", {"id": "retrieve",
                                  "label": "rank within filter"})
    subset_matrix = state["doc_matrix"][subset_idx]
    local = cosine_top_k(qv, subset_matrix, min(5, len(subset_idx)))
    hits = [
        {**_strip_vector(chunks[subset_idx[i]]),
         "rank": rank,
         "rrf_score": round(score, 4)}
        for rank, (i, score) in enumerate(local, 1)
    ]
    _emit(state, "step_done", {"id": "retrieve", "data": {"hits": hits}})
    return {"hits": hits}


def aggregate_retrieve_node(state):
    chunks = state["chunks"]
    flt = state["filter"]

    _emit(state, "step_started", {"id": "filter", "label": "metadata filter"})
    subset = [c for c in chunks if _matches(c, flt)]
    hits = [
        {**_strip_vector(c), "rank": i, "rrf_score": None}
        for i, c in enumerate(subset, 1)
    ]
    _emit(state, "step_done", {"id": "filter",
                               "data": {"filter": flt, "hits": hits}})
    return {"hits": hits}


def route_after_classify(state):
    return state["strategy"]


def answer_node(state):
    _emit(state, "step_started", {"id": "answer", "label": "answer synthesis"})
    hits = state["hits"]
    hits_for_prompt = [(h["rank"], h) for h in hits]
    buf = []
    for delta in generate_answer_stream(state["client"], state["query"], hits_for_prompt):
        buf.append(delta)
        _emit(state, "answer_token", {"text": delta})
    _emit(state, "step_done", {"id": "answer"})
    return {"answer": "".join(buf)}


def build_graph():
    g = StateGraph(State)
    g.add_node("classify", classify_node)
    g.add_node("open_retrieve", open_retrieve_node)
    g.add_node("scoped_retrieve", scoped_retrieve_node)
    g.add_node("aggregate_retrieve", aggregate_retrieve_node)
    g.add_node("answer", answer_node)
    g.set_entry_point("classify")
    g.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "open": "open_retrieve",
            "scoped": "scoped_retrieve",
            "aggregate": "aggregate_retrieve",
        },
    )
    g.add_edge("open_retrieve", "answer")
    g.add_edge("scoped_retrieve", "answer")
    g.add_edge("aggregate_retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()
