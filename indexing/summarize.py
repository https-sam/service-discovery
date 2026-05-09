#!/usr/bin/env python3
"""Generate a Markdown summary for each microservice in a demo repo.

For each subdirectory of <repo>/src/, we collect the files most likely to
describe the service (README, Dockerfile, manifest, protos, entry-point
source) and ask Gemini to write a single summary document.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Make the project root importable when this script is run from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from google import genai

from core.rag import build_client, get_backend


PROMPT = """You are documenting a microservice from a polyglot demo repo so
that someone unfamiliar with it can answer questions about it later. You will be 
producing a markdown file which will be used as a document in a RAG system. 
This markdown will be chunked by the h2 header, so make sure each h2 header is chunkable
and contains meaningful information to be able to answer any generic questions.

Read the files below and produce a single Markdown document with these
sections, in this order:

1. **Overview** - one paragraph: what the service does and its role in the
   wider system.
2. **Language & framework** - primary language + notable framework / runtime.
3. **APIs exposed** - endpoints or RPCs this service serves (HTTP routes,
   gRPC methods, message handlers). Include the path or method name.
4. **Services it depends on** - other services this one calls. For each, say
   how (gRPC / HTTP / queue) and why.
5. **Core functionalities** - bulleted list of the main things this service
   is responsible for.
6. **Notable dependencies** - key libraries: database clients, ML SDKs,
   tracing, auth, etc.
7. **Anything unusual** - anything that surprised you about this service
   (custom protocols, weird config, dead code, etc.). One short paragraph.
   Skip the section if nothing stands out.

Only state things the files actually support. If a section has no evidence,
write "Not evident from the provided files." rather than guessing.

Service name: {service_name}

Files:

{files}
"""


# Skip whole subtrees that are vendored deps, build output, or VCS.
SKIP_DIRS = {
    "node_modules", "vendor", "target", "build", "dist", "out", "bin", "obj",
    "__pycache__", ".git", ".venv", "venv", ".gradle", ".idea", ".vscode",
    "genproto",  # generated grpc stubs (microservices-demo go services)
}

# Skip files that are auto-generated and only add noise.
GENERATED_SUFFIXES = (
    "_pb2.py", "_pb2_grpc.py",     # python grpc
    ".pb.go",                       # go grpc
    ".pb.cc", ".pb.h",              # c++ grpc
)

# Per-file size cap. Anything bigger is almost certainly minified, generated,
# or otherwise not what we want in a summary prompt.
MAX_FILE_BYTES = 100_000


def is_binary(path: Path) -> bool:
    """Heuristic: a file is binary if its first 8KB contains a null byte."""
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def is_relevant(path: Path) -> bool:
    """Is this file plausibly useful for understanding the service?"""
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.name.startswith("."):
        return False
    if path.name.endswith(GENERATED_SUFFIXES):
        return False
    # Skip lockfiles - manifests already tell us the deps.
    if path.name in {"package-lock.json", "yarn.lock", "go.sum", "Cargo.lock"}:
        return False
    return True


def collect_files(service_dir: Path, repo_root: Path) -> list[tuple[Path, str]]:
    paths: list[Path] = []

    # Everything inside the service dir.
    for p in service_dir.rglob("*"):
        if p.is_file() and is_relevant(p.relative_to(service_dir)):
            paths.append(p)

    # Shared protos at repo root (e.g. microservices-demo keeps demo.proto in /protos).
    for proto in repo_root.rglob("*.proto"):
        if not proto.is_file():
            continue
        if proto.is_relative_to(service_dir):
            continue
        if any(part in SKIP_DIRS for part in proto.relative_to(repo_root).parts):
            continue
        paths.append(proto)

    out: list[tuple[Path, str]] = []
    for p in sorted(set(paths)):
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        if is_binary(p):
            continue
        try:
            text = p.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        label = p.relative_to(repo_root) if p.is_relative_to(repo_root) else p
        out.append((label, text))
    return out


def summarize(client: genai.Client, model: str, service_name: str,
              files: list[tuple[Path, str]]) -> str:
    formatted = "\n\n".join(
        f"### `{path}`\n```\n{content}\n```" for path, content in files
    )
    prompt = PROMPT.format(service_name=service_name, files=formatted)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_path", type=Path,
                        help="Path to a local clone of the demo repo.")
    parser.add_argument("--services-dir", type=Path, default=None,
                        help="Subdir containing services (default: <repo>/src).")
    parser.add_argument("--output-dir", type=Path, default=Path("summaries"),
                        help="Where to write per-service Markdown files.")
    parser.add_argument("--only", action="append", default=None,
                        help="Limit to specific service names. Repeatable.")
    parser.add_argument("--model", default="gemini-3-flash-preview",
                        help="Vertex AI Gemini model id.")
    parser.add_argument("--concurrency", type=int, default=6,
                        help="Number of services to summarize in parallel.")
    args = parser.parse_args()

    load_dotenv(override=False)

    services_dir = args.services_dir or (args.repo_path / "src")
    if not services_dir.is_dir():
        print(f"✗ Services dir not found: {services_dir}", file=sys.stderr)
        return 1

    client = build_client()
    print(f"→ backend: {get_backend()}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    services = sorted(
        p for p in services_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if args.only:
        wanted = set(args.only)
        services = [s for s in services if s.name in wanted]

    print(f"→ {len(services)} service(s) under {services_dir}")
    print(f"→ model: {args.model}")
    print(f"→ output: {args.output_dir}")
    print(f"→ concurrency: {args.concurrency}")
    print()

    def process(service_dir: Path) -> str:
        name = service_dir.name
        files = collect_files(service_dir, args.repo_path)
        if not files:
            return f"  {name}: no relevant files, skipping"
        total_bytes = sum(len(c) for _, c in files)
        summary = summarize(client, args.model, name, files)
        out_path = args.output_dir / f"{name}.md"
        out_path.write_text(summary)
        return f"  {name}: {len(files)} file(s), {total_bytes:,} bytes → {out_path}"

    failures: list[tuple[str, BaseException]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(process, s): s.name for s in services}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                print(fut.result())
            except BaseException as exc:  # noqa: BLE001
                print(f"  {name}: ✗ {exc}", file=sys.stderr)
                failures.append((name, exc))

    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
