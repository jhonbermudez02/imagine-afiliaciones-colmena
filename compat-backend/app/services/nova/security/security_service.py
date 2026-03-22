from __future__ import annotations

import os
import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DOC_RE = re.compile(r"\b\d{8,12}\b")

ROLE_PERMS: dict[str, set[str]] = {
    "admin": {"chat", "rag_index", "rag_query", "ocr", "ingestion", "db_query", "eval"},
    "analista": {"chat", "rag_query", "ocr", "ingestion"},
    "viewer": {"chat", "rag_query"},
}


class SecurityService:
    def mask_enabled(self) -> bool:
        return os.getenv("AI_MASK_SENSITIVE", "true").strip().lower() not in {"0", "false", "no", "off"}

    def required_api_key(self) -> str:
        return os.getenv("AI_API_KEY", "").strip()

    def assert_api_key(self, x_api_key: str | None) -> tuple[bool, str]:
        required = self.required_api_key()
        if not required:
            return True, "ok"
        if x_api_key and x_api_key.strip() == required:
            return True, "ok"
        return False, "API key invalida para modulo AI."

    def can(self, role: str, action: str) -> bool:
        perms = ROLE_PERMS.get(role.strip().lower(), ROLE_PERMS["viewer"])
        return action in perms

    def mask_sensitive(self, text: str) -> str:
        if not self.mask_enabled():
            return text
        masked = EMAIL_RE.sub("[email_masked]", text)
        masked = DOC_RE.sub("[doc_masked]", masked)
        return masked

    def sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str):
                out[k] = self.mask_sensitive(v)
            else:
                out[k] = v
        return out
