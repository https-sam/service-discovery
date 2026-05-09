#!/usr/bin/env python3
"""Chunk per-service summaries by H2 header, embed each chunk, save the index.

Reads every ``summaries/*.md`` produced by ``summarize.py``, splits each
document on ``## `` headers, embeds each chunk with gemini-embedding-001 (768d,
RETRIEVAL_DOCUMENT task), and writes the result to ``data/index.json``.

Each stored record has shape::

    {
      "vector": [...],            # 768 floats
      "text": "## APIs exposed\\n\\n- ...",
      "service_name": "productcatalogservice",
      "section": "apis_exposed",  # slugified H2 title
      "chunk_index": 2,           # position in source doc
      "source_path": "summaries/productcatalogservice.md"
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# Make the project root importable when this script is run from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from core.rag import build_client, get_backend


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
TASK_TYPE = "RETRIEVAL_DOCUMENT"


def slugify(text: str) -> str:
    """`"APIs exposed"` → `"apis_exposed"`. Stable filter values across docs."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def chunk_markdown(text: str) -> list[tuple[int, str, str]]:
    """Split a doc on ``## `` headers.

    Returns ``[(chunk_index, title, body), ...]`` where:
      - chunk_index reflects position *in the source doc* (not in the filtered list)
      - body includes the ``## `` header line as its first line
    """
    chunks: list[tuple[int, str, str]] = []
    title: str | None = None
    lines: list[str] = []
    index = -1

    def flush():
        if title is not None:
            chunks.append((index, title, "\n".join(lines).strip()))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            index += 1
            # strip leading/trailing markdown bolding ("## **Foo**" → "Foo")
            title = re.sub(r"^\*+|\*+$", "", line[3:].strip()).strip()
            lines = [line]
        elif title is not None:
            lines.append(line)

    flush()
    return chunks


def embed_text(client: genai.Client, text: str) -> list[float]:
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=TASK_TYPE,
            output_dimensionality=EMBED_DIM,
        ),
    )
    return list(result.embeddings[0].values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summaries-dir", type=Path, default=Path("summaries"),
                        help="Where the per-service .md files live.")
    parser.add_argument("--output", type=Path, default=Path("data/index.json"),
                        help="Where to write the JSON index.")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Parallel embedding calls.")
    parser.add_argument("--rpm", type=int, default=30,
                        help="Pace dispatches at this many requests per minute.")
    args = parser.parse_args()

    load_dotenv(override=False)

    summary_paths = sorted(args.summaries_dir.glob("*.md"))
    if not summary_paths:
        print(f"✗ No .md files in {args.summaries_dir}", file=sys.stderr)
        return 1

    # 1. Chunk every summary.
    records: list[dict] = []
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

    print(f"→ {len(summary_paths)} summary file(s) → {len(records)} chunk(s)")
    if records:
        sample = records[0]
        print(f"  sample: [{sample['service_name']} · {sample['section']}] "
              f"({len(sample['text'])} chars)")

    # 2. Embed. Contextual prefix is prepended *only for the embedding call*; the
    # stored `text` stays clean so callers can quote it verbatim.
    client = build_client()
    print(f"→ backend: {get_backend()}")

    interval = 60.0 / args.rpm

    def embed_one(rec: dict) -> dict:
        prefix = f"[{rec['service_name']} · {rec['section']}]\n"
        rec["vector"] = embed_text(client, prefix + rec["text"])
        time.sleep(interval)
        return rec

    eta_seconds = len(records) * interval
    print(f"→ embedding with {EMBED_MODEL} (dim={EMBED_DIM}, task={TASK_TYPE}, "
          f"concurrency={args.concurrency}, {args.rpm} RPM, ETA ~{eta_seconds:.0f}s)")
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for _ in pool.map(embed_one, records):
            done += 1
            if done % 10 == 0 or done == len(records):
                print(f"  {done}/{len(records)}")

    # 3. Persist.
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
    print(f"→ wrote {args.output} ({args.output.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
