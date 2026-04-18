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


def collect_files(service_dir):
    out = []
    for p in service_dir.rglob("*"):
        if p.is_file():
            try:
                out.append((p.relative_to(service_dir), p.read_text(errors="replace")))
            except OSError:
                continue
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
        files = collect_files(service_dir)
        if not files:
            continue
        summary = summarize(client, args.model, name, files)
        (args.output_dir / f"{name}.md").write_text(summary)
        print(f"  {name}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
