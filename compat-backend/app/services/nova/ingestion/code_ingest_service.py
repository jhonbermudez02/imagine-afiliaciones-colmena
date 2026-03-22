from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".md"}
FUNC_RE = re.compile(r"^\s*(def|class|function)\s+[A-Za-z_][A-Za-z0-9_]*", re.MULTILINE)


class CodeIngestService:
    def __init__(self, max_files_default: int = 200) -> None:
        self.max_files_default = max_files_default

    @staticmethod
    def _make_chunks(text: str, max_chars: int = 1800) -> list[str]:
        lines = text.splitlines()
        if not lines:
            return []
        chunks: list[str] = []
        buf: list[str] = []
        count = 0
        for line in lines:
            trigger_split = bool(FUNC_RE.search(line))
            if trigger_split and buf and count > 300:
                chunks.append("\n".join(buf).strip())
                buf = []
                count = 0
            buf.append(line)
            count += len(line) + 1
            if count >= max_chars:
                chunks.append("\n".join(buf).strip())
                buf = []
                count = 0
        if buf:
            chunks.append("\n".join(buf).strip())
        return [c for c in chunks if c]

    def ingest_path(
        self,
        repo_path: str,
        *,
        source: str = "codebase",
        max_files: int | None = None,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        root = Path(repo_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"ok": False, "message": f"Ruta invalida para ingesta: {root}"}

        limit = max_files if isinstance(max_files, int) and max_files > 0 else self.max_files_default
        docs: list[dict[str, Any]] = []
        scanned = 0

        for path in root.rglob("*"):
            if scanned >= limit:
                break
            if not path.is_file():
                continue
            if path.suffix.lower() not in CODE_EXT:
                continue
            rel = path.relative_to(root).as_posix()
            if not include_hidden and any(part.startswith(".") for part in rel.split("/")):
                continue
            if "/node_modules/" in f"/{rel}/" or "/.venv/" in f"/{rel}/" or "/dist/" in f"/{rel}/":
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            scanned += 1
            for idx, chunk in enumerate(self._make_chunks(content), start=1):
                docs.append(
                    {
                        "doc_id": f"{source}:{rel}:{idx}",
                        "source": source,
                        "text": chunk,
                        "metadata": {"path": rel, "chunk_index": idx, "size_chars": len(chunk)},
                    }
                )

        return {"ok": True, "repo_path": str(root), "files_scanned": scanned, "documents": docs}

    def ingest_texts(self, items: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
        docs = []
        for i, item in enumerate(items, start=1):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            doc_id = str(item.get("doc_id", "")).strip() or f"{source}:{i}"
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            docs.append({"doc_id": doc_id, "source": source, "text": text, "metadata": metadata})
        return {"ok": True, "documents": docs, "count": len(docs)}

