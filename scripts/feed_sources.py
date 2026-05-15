#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import httpx
    from bs4 import BeautifulSoup
    from pdf2image import convert_from_path
    from PIL import Image, ImageFilter, ImageOps
    from pypdf import PdfReader
    from paddleocr import PaddleOCR
except ModuleNotFoundError as exc:
    missing = getattr(exc, "name", "dependencia")
    raise SystemExit(
        f"Falta la dependencia '{missing}'. "
        "Ejecuta `python3 -m pip install -r backend/requirements.txt` "
        "o usa `bash scripts/feed_sources_docker.sh`."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
REGISTRY_PATH = DATA_DIR / "source_registry.json"
CATALOG_PATH = KNOWLEDGE_DIR / "catalog.json"
FEED_REPORT_PATH = DATA_DIR / "feed_report.json"

MIN_DIRECT_PDF_TEXT = 500
OCR_PAGE_LIMIT = 8
OCR_LANG = "es"
_PADDLE_OCR_ENGINE = None


@dataclass
class SourceEntry:
    slug: str
    title: str
    url: str
    source_type: str
    topic: str
    document_type: str
    audience: str


@dataclass
class SnapshotResult:
    raw_path: str
    markdown: str
    source_url: str
    source_type: str
    content_type: str
    used_ocr: bool
    ocr_pages: int
    ocr_strategy: str


def load_registry() -> list[SourceEntry]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [SourceEntry(**item) for item in payload]


def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def save_catalog(catalog: dict[str, Any]) -> None:
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def save_feed_report(report: list[dict[str, Any]]) -> None:
    FEED_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def sanitize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def html_to_markdown(html: str, source_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    chunks: list[str] = []
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        chunks.append(f"# {title}")
    chunks.append(f"Fuente: {source_url}")

    for node in soup.find_all(["h1", "h2", "h3", "p", "li", "a"]):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        if node.name == "h1":
            chunks.append(f"# {text}")
        elif node.name == "h2":
            chunks.append(f"## {text}")
        elif node.name == "h3":
            chunks.append(f"### {text}")
        elif node.name == "li":
            chunks.append(f"- {text}")
        else:
            chunks.append(text)

    return sanitize_text("\n".join(chunks))


def preprocess_variants_for_ocr(image: Image.Image) -> list[tuple[str, Image.Image, str]]:
    base = ImageOps.autocontrast(image.convert("L"))
    denoised = denoise_ocr_image(base)
    resized = denoised.resize((max(denoised.width * 2, 1), max(denoised.height * 2, 1)))
    adaptive = adaptive_threshold_ocr_image(denoised)
    adaptive_resized = adaptive.resize((max(adaptive.width * 2, 1), max(adaptive.height * 2, 1)))
    binary = resized.point(lambda pixel: 255 if pixel > 180 else 0)
    binary_soft = resized.point(lambda pixel: 255 if pixel > 150 else 0)
    inverted = ImageOps.invert(binary)
    return [
        ("gray", base, ""),
        ("denoised", resized, ""),
        ("adaptive", adaptive_resized, ""),
        ("binary", binary, ""),
        ("binary_soft", binary_soft, ""),
        ("inverted", inverted, ""),
    ]


def denoise_ocr_image(image: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np

        arr = np.array(image.convert("L"))
        arr = cv2.fastNlMeansDenoising(arr, None, h=12, templateWindowSize=7, searchWindowSize=21)
        arr = cv2.medianBlur(arr, 3)
        arr = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(arr)
        return Image.fromarray(arr)
    except Exception:
        return ImageOps.autocontrast(image.convert("L").filter(ImageFilter.MedianFilter(size=3)))


def adaptive_threshold_ocr_image(image: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np

        arr = np.array(image.convert("L"))
        binary = cv2.adaptiveThreshold(
            arr,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        return Image.fromarray(binary)
    except Exception:
        return ImageOps.autocontrast(image.convert("L")).point(lambda pixel: 255 if pixel > 155 else 0).convert("L")


def pick_best_ocr_result(results: list[tuple[str, str]]) -> tuple[str, str]:
    def score(text: str) -> tuple[int, int]:
        alnum = sum(char.isalnum() for char in text)
        words = len([token for token in text.split() if len(token) > 2])
        return (alnum, words)

    best_strategy = "none"
    best_text = ""
    best_score = (-1, -1)
    for strategy, text in results:
        current_score = score(text)
        if current_score > best_score:
            best_strategy = strategy
            best_text = text
            best_score = current_score
    return best_strategy, best_text


def get_paddle_ocr_engine():
    global _PADDLE_OCR_ENGINE
    if _PADDLE_OCR_ENGINE is None:
        try:
            _PADDLE_OCR_ENGINE = PaddleOCR(
                lang=OCR_LANG,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            _PADDLE_OCR_ENGINE = PaddleOCR(lang=OCR_LANG, use_angle_cls=False)
    return _PADDLE_OCR_ENGINE


def flatten_paddle_texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        texts: list[str] = []
        for key in ("rec_texts", "text", "texts"):
            item = value.get(key)
            if isinstance(item, list):
                texts.extend(str(part) for part in item if str(part or "").strip())
            elif isinstance(item, str) and item.strip():
                texts.append(item)
        if texts:
            return texts
        for item in value.values():
            texts.extend(flatten_paddle_texts(item))
        return texts
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1] and isinstance(value[1][0], str):
            return [str(value[1][0])]
        texts: list[str] = []
        for item in value:
            texts.extend(flatten_paddle_texts(item))
        return texts
    if hasattr(value, "json"):
        try:
            return flatten_paddle_texts(value.json)
        except Exception:
            pass
    if hasattr(value, "res"):
        try:
            return flatten_paddle_texts(value.res)
        except Exception:
            pass
    return []


def paddle_ocr_text(image: Image.Image) -> str:
    engine = get_paddle_ocr_engine()
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        image.convert("RGB").save(tmp.name, format="PNG")
        if hasattr(engine, "predict"):
            result = engine.predict(tmp.name)
        else:
            result = engine.ocr(tmp.name, cls=False)
    return sanitize_text("\n".join(flatten_paddle_texts(result)))


def run_ocr_on_image(image: Image.Image) -> tuple[str, str]:
    attempts: list[tuple[str, str]] = []
    for strategy, prepared, _config in preprocess_variants_for_ocr(image):
        text = paddle_ocr_text(prepared)
        attempts.append((strategy, text))
    return pick_best_ocr_result(attempts)


def image_to_markdown(path: Path, source_url: str, title: str) -> tuple[str, bool, str]:
    image = Image.open(path)
    strategy, text = run_ocr_on_image(image)
    chunks = [f"# {title}", f"Fuente: {source_url}"]
    if text:
        chunks.append(text)
    return "\n\n".join(chunks).strip(), True, strategy


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        page_text = sanitize_text(page.extract_text() or "")
        if page_text:
            chunks.append(page_text)
    return "\n\n".join(chunks).strip()


def ocr_pdf(path: Path) -> tuple[str, int, str]:
    images = convert_from_path(str(path), dpi=220, first_page=1, last_page=OCR_PAGE_LIMIT)
    chunks: list[str] = []
    strategies: dict[str, int] = {}
    for index, image in enumerate(images, start=1):
        strategy, text = run_ocr_on_image(image)
        if text:
            chunks.append(f"## Pagina {index}\n{text}")
        strategies[strategy] = strategies.get(strategy, 0) + 1
    dominant_strategy = max(strategies, key=strategies.get) if strategies else "none"
    return "\n\n".join(chunks).strip(), len(images), dominant_strategy


def pdf_to_markdown(path: Path, source_url: str, title: str) -> tuple[str, bool, int, str]:
    direct_text = extract_pdf_text(path)
    used_ocr = False
    ocr_pages = 0
    ocr_strategy = "direct"

    if len(direct_text) < MIN_DIRECT_PDF_TEXT:
        ocr_text, ocr_pages, ocr_strategy = ocr_pdf(path)
        if len(ocr_text) > len(direct_text):
            direct_text = ocr_text
            used_ocr = True

    chunks = [f"# {title}", f"Fuente: {source_url}"]
    if direct_text:
        chunks.append(direct_text)
    return "\n\n".join(chunks).strip(), used_ocr, ocr_pages, ocr_strategy


def request_source(client: httpx.Client, entry: SourceEntry) -> httpx.Response:
    try:
        response = client.get(entry.url, follow_redirects=True, timeout=60.0)
        response.raise_for_status()
        return response
    except httpx.ConnectError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        fallback = httpx.get(
            entry.url,
            headers={"User-Agent": "NOVA-Offline-Feeder/1.0"},
            follow_redirects=True,
            timeout=60.0,
            verify=False,
        )
        fallback.raise_for_status()
        return fallback


def snapshot_source(client: httpx.Client, entry: SourceEntry) -> SnapshotResult:
    target_dir = RAW_DIR / entry.slug
    target_dir.mkdir(parents=True, exist_ok=True)

    response = request_source(client, entry)
    content_type = response.headers.get("content-type", "").lower()
    source_url = str(response.url)

    if entry.source_type == "pdf" or "application/pdf" in content_type:
        binary_path = target_dir / "source.pdf"
        binary_path.write_bytes(response.content)
        markdown, used_ocr, ocr_pages, ocr_strategy = pdf_to_markdown(binary_path, source_url, entry.title)
        return SnapshotResult(
            raw_path=str(binary_path),
            markdown=markdown,
            source_url=source_url,
            source_type="pdf",
            content_type=content_type,
            used_ocr=used_ocr,
            ocr_pages=ocr_pages,
            ocr_strategy=ocr_strategy,
        )

    if entry.source_type in {"image", "tiff"} or "image/" in content_type:
        suffix = ".tiff" if "tiff" in content_type or entry.source_type == "tiff" else ".png"
        image_path = target_dir / f"source{suffix}"
        image_path.write_bytes(response.content)
        markdown, used_ocr, ocr_strategy = image_to_markdown(image_path, source_url, entry.title)
        return SnapshotResult(
            raw_path=str(image_path),
            markdown=markdown,
            source_url=source_url,
            source_type="image" if suffix != ".tiff" else "tiff",
            content_type=content_type,
            used_ocr=used_ocr,
            ocr_pages=1,
            ocr_strategy=ocr_strategy,
        )

    html_path = target_dir / "source.html"
    html_path.write_text(response.text, encoding="utf-8")
    markdown = html_to_markdown(response.text, source_url)
    return SnapshotResult(
        raw_path=str(html_path),
        markdown=markdown,
        source_url=source_url,
        source_type="html",
        content_type=content_type,
        used_ocr=False,
        ocr_pages=0,
        ocr_strategy="none",
    )


def write_knowledge(entry: SourceEntry, markdown: str) -> Path:
    filename = f"cliente-colmena-{entry.slug}.md"
    output_path = KNOWLEDGE_DIR / filename
    output_path.write_text(markdown + "\n", encoding="utf-8")
    return output_path


def update_catalog(entry: SourceEntry, knowledge_path: Path, result: SnapshotResult) -> None:
    catalog = load_catalog()
    catalog[knowledge_path.name] = {
        "topic": entry.topic,
        "document_type": entry.document_type,
        "audience": entry.audience,
        "source_url": result.source_url,
        "owner": "colmena_seguros" if "colmena" in entry.slug else "normativa_oficial",
        "source_type": result.source_type,
        "ocr": result.used_ocr,
        "ocr_strategy": result.ocr_strategy,
    }
    save_catalog(catalog)


def run(
    limit: int | None = None,
    selected_slugs: list[str] | None = None,
    skip_existing: bool = False,
) -> None:
    entries = load_registry()
    if selected_slugs:
        wanted = set(selected_slugs)
        entries = [entry for entry in entries if entry.slug in wanted]
    if limit is not None:
        entries = entries[:limit]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    processed = 0
    failed = 0
    report: list[dict[str, Any]] = []

    total = len(entries)
    with httpx.Client(headers={"User-Agent": "NOVA-Offline-Feeder/1.0"}) as client:
        for index, entry in enumerate(entries, start=1):
            row = asdict(entry)
            knowledge_name = f"cliente-colmena-{entry.slug}.md"
            knowledge_path = KNOWLEDGE_DIR / knowledge_name
            if skip_existing and knowledge_path.exists():
                row.update(
                    {
                        "status": "skipped",
                        "knowledge_file": knowledge_name,
                        "reason": "already_exists",
                    }
                )
                report.append(row)
                print(f"[skip] {index}/{total} {entry.slug} -> {knowledge_name}")
                continue
            try:
                result = snapshot_source(client, entry)
                knowledge_path = write_knowledge(entry, result.markdown)
                update_catalog(entry, knowledge_path, result)
                processed += 1
                row.update(
                    {
                        "status": "ok",
                        "knowledge_file": knowledge_path.name,
                        "raw_path": result.raw_path,
                        "resolved_url": result.source_url,
                        "resolved_source_type": result.source_type,
                        "content_type": result.content_type,
                        "used_ocr": result.used_ocr,
                        "ocr_pages": result.ocr_pages,
                        "ocr_strategy": result.ocr_strategy,
                    }
                )
                print(
                    f"[ok] {index}/{total} {entry.slug} -> {knowledge_path.name} "
                    f"(ocr={result.used_ocr} paginas_ocr={result.ocr_pages} estrategia={result.ocr_strategy})"
                )
            except Exception as exc:
                failed += 1
                row.update({"status": "error", "error": str(exc)})
                print(f"[error] {index}/{total} {entry.slug}: {exc}")
            report.append(row)

    save_feed_report(report)
    print(f"[summary] procesadas={processed} fallidas={failed}")
    print(f"[summary] reporte={FEED_REPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Captura fuentes web y normativas para modo offline.")
    parser.add_argument("--limit", type=int, default=None, help="Procesar solo las primeras N fuentes")
    parser.add_argument("--slug", action="append", default=None, help="Procesar solo fuentes especificas por slug")
    parser.add_argument("--skip-existing", action="store_true", help="Saltar fuentes ya capturadas en data/knowledge")
    args = parser.parse_args()
    run(limit=args.limit, selected_slugs=args.slug, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
