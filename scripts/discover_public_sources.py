#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "source_registry.json"
DISCOVERED_PATH = ROOT / "data" / "source_registry_discovered.json"

ALLOWED_DOMAINS = {
    "www.colmenaseguros.com",
    "colmenaseguros.com",
    "sp.colmenaseguros.com",
}

SEED_SITEMAPS = [
    "https://www.colmenaseguros.com/robots.txt",
    "https://www.colmenaseguros.com/sitemap.xml",
    "https://sp.colmenaseguros.com/robots.txt",
]


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "colmena-source"


def infer_source_type(url: str, content_type: str) -> str:
    lowered = url.lower()
    content_type = content_type.lower()
    if "pdf" in content_type or lowered.endswith(".pdf"):
        return "pdf"
    if "tif" in content_type or "tiff" in content_type or lowered.endswith((".tif", ".tiff")):
        return "tiff"
    if content_type.startswith("image/") or lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "image"
    return "html"


def infer_topic(url: str, title: str) -> str:
    haystack = f"{url} {title}".lower()
    if any(token in haystack for token in ("decreto", "resolucion", "ley", "norma", "normativ")):
        return "normativa"
    if any(token in haystack for token in ("independiente", "independientes")):
        return "independientes"
    if any(token in haystack for token in ("incapacidad", "accidente", "enfermedad", "prestacion", "salud")):
        return "aportes"
    if any(token in haystack for token in ("tramite", "radic", "formulario", "reporte", "solicitud", "pqrs")):
        return "documentos"
    if any(token in haystack for token in ("prevencion", "sst", "mype", "alturas", "ergonomia", "estandares")):
        return "validaciones"
    if any(token in haystack for token in ("empresa", "empresas", "afili", "arl", "trabajadores")):
        return "empresas"
    return "general"


def infer_document_type(url: str, title: str, source_type: str) -> str:
    haystack = f"{url} {title}".lower()
    if source_type == "pdf":
        if any(token in haystack for token in ("informe", "gestion", "financiero")):
            return "informe"
        if any(token in haystack for token in ("formulario", "autorizacion")):
            return "formulario"
        return "documento"
    if any(token in haystack for token in ("tramite", "radic", "reporte", "solicitud", "pqrs")):
        return "tramites"
    if any(token in haystack for token in ("formulario", "autorizacion")):
        return "formulario"
    if any(token in haystack for token in ("prevencion", "mype", "capacit", "formar", "estandares")):
        return "guia_operativa"
    if any(token in haystack for token in ("accidente", "enfermedad", "prestacion")):
        return "asistencia"
    return "portal"


def build_entry(url: str, title: str, source_type: str) -> dict[str, str]:
    clean_title = title.strip() or urlparse(url).path.strip("/").replace("/", " ").replace("-", " ").title() or url
    return {
        "slug": slugify(urlparse(url).path or clean_title),
        "title": clean_title,
        "url": url,
        "source_type": source_type,
        "topic": infer_topic(url, clean_title),
        "document_type": infer_document_type(url, clean_title, source_type),
        "audience": "operaciones",
    }


def load_seed_urls() -> list[str]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    seeds = [item["url"] for item in payload if "colmena" in item["url"]]
    seeds.extend(SEED_SITEMAPS)
    return seeds


def allowed(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc in ALLOWED_DOMAINS


def fetch_xml_urls(client: httpx.Client, url: str) -> list[str]:
    try:
        response = client.get(url)
        response.raise_for_status()
    except Exception:
        return []

    content_type = response.headers.get("content-type", "").lower()
    body = response.text

    if "robots" in url:
        urls = []
        for line in body.splitlines():
            if line.lower().startswith("sitemap:"):
                urls.append(line.split(":", 1)[1].strip())
        return urls

    if "xml" not in content_type and not url.lower().endswith(".xml"):
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []

    urls: list[str] = []
    for loc in root.findall(".//{*}loc"):
        value = (loc.text or "").strip()
        if value:
            urls.append(value)
    return urls


def discover(max_pages: int) -> list[dict[str, str]]:
    queue = deque(load_seed_urls())
    seen: set[str] = set()
    discovered: dict[str, dict[str, str]] = {}
    known_xml: set[str] = set()

    with httpx.Client(headers={"User-Agent": "NOVA-Source-Discovery/1.0"}, follow_redirects=True, timeout=30.0) as client:
        while queue and len(seen) < max_pages:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if url.endswith(".xml") or "robots.txt" in url:
                if url in known_xml:
                    continue
                known_xml.add(url)
                for candidate in fetch_xml_urls(client, url):
                    if allowed(candidate) and candidate not in seen:
                        queue.append(candidate)
                continue

            if not allowed(url):
                continue

            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception:
                continue

            content_type = response.headers.get("content-type", "").lower()
            source_type = infer_source_type(str(response.url), content_type)
            title = ""

            if source_type != "html":
                discovered[str(response.url)] = build_entry(str(response.url), title, source_type)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            discovered[str(response.url)] = build_entry(str(response.url), title, source_type)

            for link in soup.find_all("a", href=True):
                candidate = urljoin(str(response.url), link["href"])
                if allowed(candidate) and candidate not in seen:
                    queue.append(candidate)
                if allowed(candidate) and candidate.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")):
                    discovered[candidate] = build_entry(candidate, "", infer_source_type(candidate, ""))

    return sorted(discovered.values(), key=lambda item: item["url"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Descubre URLs publicas de Colmena desde semillas iniciales.")
    parser.add_argument("--max-pages", type=int, default=60)
    args = parser.parse_args()

    discovered = discover(args.max_pages)
    DISCOVERED_PATH.write_text(json.dumps(discovered, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] {len(discovered)} urls guardadas en {DISCOVERED_PATH}")


if __name__ == "__main__":
    main()
