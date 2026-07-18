"""Vorige Pages-artefact herstellen voor de stale_reused-fallback.

GitHub Actions-runs zijn stateless: het vorige artefact staat alleen op de
live Pages-site. Deze module haalt manifest plus lagen op naar de lokale
outputmap, zodat `artifact.build()` bij een gefaalde bron kan terugvallen
op de laatst gepubliceerde geldige laag. Herstel is best effort: elke fout
is een waarschuwing, nooit een blokkade.

Gebruik: uv run python -m pipeline.restore --base-url https://<site>/data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import http_get, redact


def restore(base_url: str, output_dir: Path) -> int:
    base_url = base_url.rstrip("/")
    try:
        manifest_bytes = http_get(f"{base_url}/manifest.json", retries=0)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[restore] geen vorig artefact bereikbaar: {redact(str(exc))}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    restored = 0
    for source, entry in manifest.get("sources", {}).items():
        paths = [entry["file"]] if entry.get("file") else []
        paths.extend(entry.get("files", []))
        for path in dict.fromkeys(paths):
            try:
                data = http_get(f"{base_url}/{path}", retries=0)
            except Exception as exc:  # noqa: BLE001
                print(f"[restore] bestand {source}/{path} niet opgehaald: {redact(str(exc))}")
                continue
            target = output_dir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            restored += 1
    print(f"[restore] {restored} bestanden hersteld uit vorig artefact")
    return restored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", default="public/data", type=Path)
    args = parser.parse_args(argv)
    restore(args.base_url, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
