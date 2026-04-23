#!/usr/bin/env python3
"""Chunk per-service summaries on H2 headers, embed each chunk."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
TASK_TYPE = "RETRIEVAL_DOCUMENT"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def chunk_markdown(text):
    chunks = []
    title = None
    lines = []
    index = -1

    def flush():
        if title is not None:
            chunks.append((index, title, "\n".join(lines).strip()))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            index += 1
            title = re.sub(r"^\*+|\*+$", "", line[3:].strip()).strip()
            lines = [line]
        elif title is not None:
            lines.append(line)
    flush()
    return chunks


def embed_text(client, text):
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=TASK_TYPE,
            output_dimensionality=EMBED_DIM,
        ),
    )
    return list(result.embeddings[0].values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summaries-dir", type=Path, default=Path("summaries"))
    parser.add_argument("--output", type=Path, default=Path("data/index.json"))
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--rpm", type=int, default=30)
    args = parser.parse_args()

    load_dotenv(override=False)

    summary_paths = sorted(args.summaries_dir.glob("*.md"))
    if not summary_paths:
        print(f"no .md files in {args.summaries_dir}", file=sys.stderr)
        return 1

    records = []
    for path in summary_paths:
        service_name = path.stem
        for chunk_index, title, body in chunk_markdown(path.read_text()):
            records.append({
                "text": body,
                "service_name": service_name,
                "section": slugify(title),
                "chunk_index": chunk_index,
                "source_path": str(path),
            })

    print(f"-> {len(summary_paths)} summary file(s), {len(records)} chunks")

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    interval = 60.0 / args.rpm

    def embed_one(rec):
        rec["vector"] = embed_text(client, rec["text"])
        time.sleep(interval)
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for _ in pool.map(embed_one, records):
            done += 1
            if done % 10 == 0 or done == len(records):
                print(f"  {done}/{len(records)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    index = {
        "meta": {
            "embedding_model": EMBED_MODEL,
            "dim": EMBED_DIM,
            "task_type": TASK_TYPE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "chunk_count": len(records),
        },
        "chunks": records,
    }
    args.output.write_text(json.dumps(index))
    print(f"-> wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
