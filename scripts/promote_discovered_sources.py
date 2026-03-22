#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "source_registry.json"
DISCOVERED_PATH = ROOT / "data" / "source_registry_discovered.json"


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe(entries: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for entry in entries:
        url = entry["url"]
        unique[url] = entry
    return sorted(unique.values(), key=lambda item: item["url"])


def main() -> None:
    registry = load_json(REGISTRY_PATH)
    discovered = load_json(DISCOVERED_PATH)
    merged = dedupe(registry + discovered)
    REGISTRY_PATH.write_text(json.dumps(merged, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] {len(discovered)} fuentes descubiertas promovidas. Registro total: {len(merged)}")


if __name__ == "__main__":
    main()
