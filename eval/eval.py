#!/usr/bin/env python3
"""Run the RAG pipeline over an evalset and score with RAGAS.

Four metrics cover the two RAG failure surfaces:

    RETRIEVAL                              GENERATION
    ─────────                              ──────────
    LLMContextPrecisionWithReference       Faithfulness
    LLMContextRecall                       ResponseRelevancy

Each is computed by an LLM judge (the same backend the pipeline uses). Higher
is better; scores are in [0, 1]. Faithfulness, for example, asks: "for
each claim in the answer, is it grounded in at least one retrieved chunk?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the project root importable when this script is run as `python scripts/eval.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)
from ragas.run_config import RunConfig

from google import genai

from queue import Queue

from core.pipeline import build_graph
from core.rag import build_client, get_backend, load_index


JUDGE_MODEL = "gemini-2.5-flash"  # GA, fast, higher quota - judge ≠ pipeline-under-test
JUDGE_EMBED_MODEL_VERTEX = "text-embedding-004"
JUDGE_EMBED_MODEL_GEMINI = "models/gemini-embedding-001"


def _build_judge():
    """Pick the LangChain LLM + embedding wrappers for the current backend."""
    if get_backend() == "vertex":
        from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
        project = os.environ["GOOGLE_CLOUD_PROJECT"]
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        llm = ChatVertexAI(model_name=JUDGE_MODEL, project=project, location=location)
        emb = VertexAIEmbeddings(
            model_name=JUDGE_EMBED_MODEL_VERTEX, project=project, location=location
        )
    else:
        from langchain_google_genai import (
            ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings,
        )
        api_key = os.environ["GEMINI_API_KEY"]
        llm = ChatGoogleGenerativeAI(model=JUDGE_MODEL, google_api_key=api_key)
        emb = GoogleGenerativeAIEmbeddings(
            model=JUDGE_EMBED_MODEL_GEMINI, google_api_key=api_key
        )
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(emb)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evalset", type=Path, default=Path("eval/evalset.json"))
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/eval_results.csv"))
    parser.add_argument("--limit", type=int, default=None,
                        help="Run only the first N queries (for fast iteration).")
    parser.add_argument("--max-workers", type=int, default=2,
                        help="Parallelism for RAGAS judge calls.")
    args = parser.parse_args()

    load_dotenv(override=False)

    evalset = json.loads(args.evalset.read_text())
    if args.limit:
        evalset = evalset[:args.limit]
    print(f"→ evalset: {len(evalset)} queries from {args.evalset}")

    # 1. Run the FULL pipeline once per query - same code path the web UI uses,
    # so eval measures what users actually experience (classifier + routed
    # retrieval, not the open-route-only `run_query` shortcut).
    chunks, doc_matrix = load_index(args.index)
    client = build_client()
    graph = build_graph()
    print(f"→ backend: {get_backend()}")

    samples = []
    for i, item in enumerate(evalset, 1):
        print(f"  [{i}/{len(evalset)}] {item['query'][:60]}")
        # The graph emits SSE events to a queue for the streaming UI.
        # In batch eval we don't need them; pass a queue and drain it.
        sink: Queue = Queue()
        state = graph.invoke({
            "query": item["query"],
            "chunks": chunks,
            "doc_matrix": doc_matrix,
            "client": client,
            "event_queue": sink,
        })
        # The router decides the strategy; we just take whatever hits + answer
        # came out the other side.
        strategy = state.get("strategy", "open")
        hits = state.get("hits", [])
        answer = state.get("answer", "")
        print(f"      strategy={strategy}  hits={len(hits)}")
        samples.append({
            "user_input": item["query"],
            "response": answer,
            "retrieved_contexts": [h["text"] for h in hits],
            "reference": item.get("reference", ""),
        })

    # 2. Score with RAGAS. The judge LLM + similarity-embedding model follow
    # the same backend as the rest of the pipeline.
    judge_llm, judge_embeddings = _build_judge()

    dataset = EvaluationDataset.from_list(samples)

    print(f"\n→ scoring {len(samples)} samples with RAGAS (judge={JUDGE_MODEL})")
    results = evaluate(
        dataset=dataset,
        metrics=[
            # Retrieval-side
            LLMContextPrecisionWithReference(),  # are the relevant contexts at the top?
            LLMContextRecall(),                  # do the contexts cover what the reference needs?
            # Generation-side
            Faithfulness(),                      # is every claim grounded in the contexts?
            ResponseRelevancy(),                 # does the answer actually address the question?
        ],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=RunConfig(max_workers=args.max_workers),
    )

    # 3. Print + persist.
    df = results.to_pandas()
    print("\n→ Per-query scores:\n")
    print(df.to_string(index=False))

    print("\n→ Aggregate (mean across queries):\n")
    metric_cols = [c for c in df.columns if c not in
                   ("user_input", "response", "retrieved_contexts", "reference")]
    for col in metric_cols:
        print(f"  {col:50s}  {df[col].mean():.3f}")

    df.to_csv(args.output, index=False)
    print(f"\n→ wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
