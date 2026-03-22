#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "offline_bundle"


def copy_path(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    EXPORT_DIR.mkdir(parents=True)

    copy_path(ROOT / "docker-compose.yml", EXPORT_DIR / "docker-compose.yml")
    copy_path(ROOT / "backend", EXPORT_DIR / "backend")
    copy_path(ROOT / "frontend-nova", EXPORT_DIR / "frontend-nova")
    copy_path(ROOT / "data" / "qdrant", EXPORT_DIR / "qdrant_data")
    copy_path(ROOT / "data" / "ollama", EXPORT_DIR / "ollama_models")
    copy_path(ROOT / "data" / "knowledge", EXPORT_DIR / "knowledge")
    copy_path(ROOT / "data" / "raw", EXPORT_DIR / "raw_snapshots")
    if (ROOT / "data" / "evals").exists():
        copy_path(ROOT / "data" / "evals", EXPORT_DIR / "evals")
    copy_path(ROOT / "data" / "source_registry.json", EXPORT_DIR / "source_registry.json")
    if (ROOT / "data" / "source_registry_discovered.json").exists():
        copy_path(ROOT / "data" / "source_registry_discovered.json", EXPORT_DIR / "source_registry_discovered.json")
    if (ROOT / "data" / "feed_report.json").exists():
        copy_path(ROOT / "data" / "feed_report.json", EXPORT_DIR / "feed_report.json")

    print(f"[ok] bundle offline generado en {EXPORT_DIR}")


if __name__ == "__main__":
    main()
