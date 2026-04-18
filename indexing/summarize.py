#!/usr/bin/env python3
"""Generate a Markdown summary for each microservice in a demo repo."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai


PROMPT = """Read the files below and produce a Markdown summary
of the microservice with sections: Overview, Language & framework,
APIs exposed, Services it depends on, Core functionalities,
Notable dependencies, Anything unusual.

Service name: {service_name}

Files:

{files}
"""

SKIP_DIRS = {
    "node_modules", "vendor", "target", "build", "dist", "out", "bin", "obj",
    "__pycache__", ".git", ".venv", "venv", ".gradle", ".idea", ".vscode",
    "genproto",
}

GENERATED_SUFFIXES = (
    "_pb2.py", "_pb2_grpc.py",
    ".pb.go",
    ".pb.cc", ".pb.h",
)

MAX_FILE_BYTES = 100_000


def is_binary(path):
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def is_relevant(path):
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.name.startswith("."):
        return False
    if path.name.endswith(GENERATED_SUFFIXES):
        return False
    if path.name in {"package-lock.json", "yarn.lock", "go.sum", "Cargo.lock"}:
        return False
    return True


def collect_files(service_dir, repo_root):
    paths = []
    for p in service_dir.rglob("*"):
        if p.is_file() and is_relevant(p.relative_to(service_dir)):
            paths.append(p)
    for proto in repo_root.rglob("*.proto"):
        if not proto.is_file():
            continue
        if proto.is_relative_to(service_dir):
            continue
        if any(part in SKIP_DIRS for part in proto.relative_to(repo_root).parts):
            continue
        paths.append(proto)
    out = []
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


def summarize(client, model, service_name, files):
    formatted = "\n\n".join(
        f"### `{path}`\n```\n{content}\n```" for path, content in files
    )
    response = client.models.generate_content(
        model=model,
        contents=PROMPT.format(service_name=service_name, files=formatted),
    )
    return response.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("summaries"))
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()

    load_dotenv(override=False)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    services_dir = args.repo_path / "src"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    services = sorted(p for p in services_dir.iterdir() if p.is_dir())
    print(f"-> {len(services)} services")

    for service_dir in services:
        name = service_dir.name
        files = collect_files(service_dir, args.repo_path)
        if not files:
            continue
        summary = summarize(client, args.model, name, files)
        (args.output_dir / f"{name}.md").write_text(summary)
        print(f"  {name}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
