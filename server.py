#!/usr/bin/env python3
"""FastAPI server. Serves the static UI and streams the RAG pipeline over SSE."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from queue import Empty, Queue

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from google import genai

from core.rag import (
    cosine_top_k, embed_query, expand_query, generate_answer,
    load_index, rrf_fuse,
)


load_dotenv(override=False)

_CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
_CHUNKS, _DOC_MATRIX = load_index(Path("data/index.json"))

app = FastAPI()


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_pipeline(query_text):
    q = Queue()
    err = []

    def run():
        try:
            q.put(("step_started", {"id": "expand", "label": "query expansion"}))
            expansions = expand_query(_CLIENT, query_text, 4)
            queries = [query_text] + expansions
            q.put(("step_done", {"id": "expand", "data": {"queries": queries}}))

            q.put(("step_started", {"id": "embed", "label": "embed queries"}))
            query_vecs = [embed_query(_CLIENT, qx) for qx in queries]
            q.put(("step_done", {"id": "embed", "data": {"count": len(query_vecs)}}))

            q.put(("step_started", {"id": "retrieve", "label": "retrieve top-k"}))
            rankings = [cosine_top_k(qv, _DOC_MATRIX, 10) for qv in query_vecs]
            q.put(("step_done", {"id": "retrieve", "data": {}}))

            q.put(("step_started", {"id": "fuse", "label": "rrf fusion"}))
            fused = rrf_fuse(rankings)[:5]
            hits = []
            for rank, (idx, score) in enumerate(fused, 1):
                c = _CHUNKS[idx]
                hits.append({**{k: v for k, v in c.items() if k != "vector"},
                             "rank": rank, "rrf_score": round(score, 4)})
            q.put(("step_done", {"id": "fuse", "data": {"hits": hits}}))

            q.put(("step_started", {"id": "answer", "label": "answer synthesis"}))
            hits_for_prompt = [(h["rank"], h) for h in hits]
            answer = generate_answer(_CLIENT, query_text, hits_for_prompt)
            q.put(("answer_token", {"text": answer}))
            q.put(("step_done", {"id": "answer"}))
        except Exception as exc:
            err.append(str(exc))
        finally:
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

    while True:
        try:
            ev = q.get(timeout=180)
        except Empty:
            yield _sse("error", {"message": "timeout"})
            return
        if ev is None:
            break
        ev_type, data = ev
        yield _sse(ev_type, data)

    if err:
        yield _sse("error", {"message": err[0]})
    else:
        yield _sse("complete", {})


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/query")
def query(q: str):
    return StreamingResponse(
        stream_pipeline(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
