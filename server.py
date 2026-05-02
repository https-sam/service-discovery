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

from core.pipeline import build_graph
from core.rag import load_index


load_dotenv(override=False)

_CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
_CHUNKS, _DOC_MATRIX = load_index(Path("data/index.json"))
_GRAPH = build_graph()



app = FastAPI()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_pipeline(query_text: str):
    """Run the graph in a thread, drain its event queue into SSE frames."""
    q: Queue = Queue()
    err: list[str] = []

    def run():
        try:
            _GRAPH.invoke({
                "query": query_text,
                "chunks": _CHUNKS,
                "doc_matrix": _DOC_MATRIX,
                "client": _CLIENT,
                "event_queue": q,
            })
        except Exception as exc:  # noqa: BLE001
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
        event_type, data = ev
        yield _sse(event_type, data)

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
