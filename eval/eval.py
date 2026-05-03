#!/usr/bin/env python3
"""Run the open-route RAG pipeline over an evalset and score with RAGAS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
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

from core.rag import (
    cosine_top_k, embed_query, expand_query, generate_answer, load_index, rrf_fuse,
)
from google import genai


JUDGE_MODEL = "gemini-2.5-flash"


def run_open(query, chunks, doc_matrix, client):
    expansions = expand_query(client, query, 4)
    queries = [query] + expansions
    query_vecs = [embed_query(client, q) for q in queries]
    rankings = [cosine_top_k(qv, doc_matrix, 10) for qv in query_vecs]
    fused = rrf_fuse(rankings)[:5]
    hits = [
        {**chunks[idx], "rank": rank, "rrf_score": score}
        for rank, (idx, score) in enumerate(fused, 1)
    ]
    hits_for_prompt = [(h["rank"], h) for h in hits]
    answer = generate_answer(client, query, hits_for_prompt)
    return {"hits": hits, "answer": answer}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evalset", type=Path, default=Path("eval/evalset.json"))
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/eval_results.csv"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(override=False)

    evalset = json.loads(args.evalset.read_text())
    if args.limit:
        evalset = evalset[:args.limit]
    print(f"-> {len(evalset)} queries")

    chunks, doc_matrix = load_index(args.index)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    samples = []
    for i, item in enumerate(evalset, 1):
        print(f"  [{i}/{len(evalset)}] {item['query'][:60]}")
        result = run_open(item["query"], chunks, doc_matrix, client)
        samples.append({
            "user_input": item["query"],
            "response": result["answer"],
            "retrieved_contexts": [h["text"] for h in result["hits"]],
            "reference": item.get("reference", ""),
        })

    api_key = os.environ["GEMINI_API_KEY"]
    judge_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model=JUDGE_MODEL, google_api_key=api_key)
    )
    judge_emb = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", google_api_key=api_key,
        )
    )

    dataset = EvaluationDataset.from_list(samples)
    results = evaluate(
        dataset=dataset,
        metrics=[
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
            Faithfulness(),
            ResponseRelevancy(),
        ],
        llm=judge_llm,
        embeddings=judge_emb,
        run_config=RunConfig(max_workers=2),
    )
    df = results.to_pandas()
    df.to_csv(args.output, index=False)
    print(f"-> wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
