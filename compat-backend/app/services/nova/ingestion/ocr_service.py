from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except Exception:  # pragma: no cover - fallback if PIL missing at runtime
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageFilter = None
    ImageFont = None
try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional import
    fitz = None

class OcrService:
    def __init__(self) -> None:
        self.engine = os.getenv("AI_OCR_ENGINE", "tesseract").strip().lower()
        self.lang = os.getenv("AI_OCR_LANG", "spa+eng").strip() or "spa+eng"
        self.pdf_max_pages = max(1, min(int(os.getenv("AI_OCR_PDF_MAX_PAGES", "5")), 30))

    def _fallback_text(self, text: str) -> dict[str, Any]:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return {
            "ok": True,
            "engine": "fallback-text",
            "text": normalized,
            "chars": len(normalized),
            "lines": len(normalized.splitlines()) if normalized else 0,
        }

    @staticmethod
    def _looks_like_afiliacion_empleador(text: str) -> bool:
        n = OcrService._norm(text)
        if not n:
            return False
        keys = [
            "razon social",
            "representante legal",
            "direccion",
            "ciudad",
            "nit",
            "afiliacion",
            "empleador",
        ]
        hits = sum(1 for k in keys if k in n)
        return hits >= 2

    @staticmethod
    def _looks_like_identidad(text: str) -> bool:
        n = OcrService._norm(text)
        if not n:
            return False
        keys = [
            "cedula de ciudadania",
            "identificacion personal",
            "lugar de nacimiento",
            "fecha de nacimiento",
            "fecha y lugar de expedicion",
        ]
        hits = sum(1 for k in keys if k in n)
        return hits >= 2

    @staticmethod
    def _norm(value: str) -> str:
        s = str(value or "")
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        s = s.lower()
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _to_iso_date(raw: str) -> str | None:
        txt = OcrService._norm(raw)
        m_num = re.search(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b", txt)
        if m_num:
            d, m, y = m_num.groups()
            yy = int(y)
            if yy < 100:
                yy += 2000
            return f"{yy:04d}-{int(m):02d}-{int(d):02d}"
        months = {
            "ene": 1, "enero": 1,
            "feb": 2, "febrero": 2,
            "mar": 3, "marzo": 3,
            "abr": 4, "abril": 4,
            "may": 5, "mayo": 5,
            "jun": 6, "junio": 6,
            "jul": 7, "julio": 7,
            "ago": 8, "agosto": 8,
            "sep": 9, "sept": 9, "septiembre": 9,
            "oct": 10, "octubre": 10,
            "nov": 11, "noviembre": 11,
            "dic": 12, "diciembre": 12,
        }
        m_mix = re.search(r"\b(\d{1,2})[\/\-.]([a-z]{3,10})[\/\-.](\d{2,4})\b", txt)
        if m_mix:
            d, m_name, y = m_mix.groups()
            m_key = m_name[:3] if m_name[:3] in months else m_name
            m_val = months.get(m_key)
            if m_val:
                yy = int(y)
                if yy < 100:
                    yy += 2000
                return f"{yy:04d}-{m_val:02d}-{int(d):02d}"
        m_txt = re.search(r"\b(\d{1,2})\s*(?:de)?\s*([a-z]{3,10})\s*(?:de)?\s*(\d{2,4})\b", txt)
        if not m_txt:
            return None
        d, m_name, y = m_txt.groups()
        m_key = m_name[:3] if m_name[:3] in months else m_name
        m_val = months.get(m_key)
        if not m_val:
            return None
        yy = int(y)
        if yy < 100:
            yy += 2000
        return f"{yy:04d}-{m_val:02d}-{int(d):02d}"

    @staticmethod
    def _extract_incapacidad_fields(text: str) -> dict[str, dict[str, Any]]:
        raw = str(text or "")
        n = OcrService._norm(raw)

        def status(conf: float) -> str:
            if conf >= 0.9:
                return "CONFIDENT"
            if conf >= 0.6:
                return "REVIEW_RECOMMENDED"
            return "UNRELIABLE"

        def mk(value: Any, conf: float) -> dict[str, Any]:
            v = None if value in ("", None) else value
            return {
                "value": v,
                "confidence": conf if v is not None else 0.0,
                "status": status(conf if v is not None else 0.0),
            }

        ced = None
        m_ced = re.search(r"(?:cedula|cc|identificacion)[^0-9]{0,12}([0-9][0-9\.\-]{5,20})", n)
        if m_ced:
            ced = re.sub(r"\D", "", m_ced.group(1))

        dias = None
        m_dias = re.search(r"\b(\d{1,3})\s*(?:dias|dia)\b", n)
        if m_dias:
            dias = int(m_dias.group(1))

        evento = None
        if "accidente de trabajo" in n:
            evento = "Accidente de Trabajo"
        elif "enfermedad laboral" in n:
            evento = "Enfermedad Laboral"
        elif "accidente comun" in n or "accidente comun" in n:
            evento = "Accidente Común"

        entidad = None
        if "colmena" in n:
            entidad = "Colmena Riesgos Profesionales"
        elif "arl" in n:
            entidad = "ARL"

        fecha_inicio = None
        fecha_fin = None
        m_rango = re.search(r"(?:desde|inicio)\s*[:\-]?\s*([^\n,;]{6,24}).{0,20}(?:hasta|fin)\s*[:\-]?\s*([^\n,;]{6,24})", n)
        if m_rango:
            fecha_inicio = OcrService._to_iso_date(m_rango.group(1))
            fecha_fin = OcrService._to_iso_date(m_rango.group(2))

        if not fecha_inicio:
            m_fi = re.search(r"(?:fecha inicio|inicio)\s*[:\-]?\s*([^\n,;]{6,24})", n)
            if m_fi:
                fecha_inicio = OcrService._to_iso_date(m_fi.group(1))
        if not fecha_fin:
            m_ff = re.search(r"(?:fecha fin|hasta|fin)\s*[:\-]?\s*([^\n,;]{6,24})", n)
            if m_ff:
                fecha_fin = OcrService._to_iso_date(m_ff.group(1))

        medico_cargo = "Médico General" if "medico general" in n else None
        medico_nombre = None
        m_med = re.search(r"(?:medico|medica)\s*(?:tratante)?\s*[:\-]?\s*([a-z\s]{8,70})", n)
        if m_med:
            candidato = " ".join(w.capitalize() for w in m_med.group(1).split())
            medico_nombre = candidato if len(candidato.split()) >= 2 else None

        return {
            "paciente_nombre": mk(None, 0.0),
            "paciente_cedula": mk(ced, 0.58 if ced else 0.0),
            "entidad": mk(entidad, 0.9 if entidad else 0.0),
            "tipo_evento": mk(evento, 0.92 if evento else 0.0),
            "dias_incapacidad": mk(dias, 0.94 if dias is not None else 0.0),
            "fecha_inicio": mk(fecha_inicio, 0.88 if fecha_inicio else 0.0),
            "fecha_fin": mk(fecha_fin, 0.88 if fecha_fin else 0.0),
            "medico_nombre": mk(medico_nombre, 0.7 if medico_nombre else 0.0),
            "medico_cargo": mk(medico_cargo, 0.9 if medico_cargo else 0.0),
        }

    @staticmethod
    def _extract_identidad_fields(text: str) -> dict[str, dict[str, Any]]:
        raw = str(text or "")
        n = OcrService._norm(raw)

        def status(conf: float) -> str:
            if conf >= 0.9:
                return "CONFIDENT"
            if conf >= 0.6:
                return "REVIEW_RECOMMENDED"
            return "UNRELIABLE"

        def mk(value: Any, conf: float) -> dict[str, Any]:
            v = None if value in ("", None) else value
            return {
                "value": v,
                "confidence": conf if v is not None else 0.0,
                "status": status(conf if v is not None else 0.0),
            }

        doc_type = None
        if "cedula de ciudadania" in n or "cedula de ciudadania" in n:
            doc_type = "CC"
        elif "tarjeta de identidad" in n:
            doc_type = "TI"
        elif "cedula de extranjeria" in n:
            doc_type = "CE"

        doc_number = None
        m_num = re.search(r"(?:numero|n[. ]?o|identificacion|identificacion personal)[^0-9]{0,12}([0-9][0-9\.\- ]{4,18})", n)
        if not m_num:
            m_num = re.search(r"\b([0-9][0-9\.\- ]{6,18})\b", n)
        if m_num:
            digits = re.sub(r"\D", "", m_num.group(1))
            if 5 <= len(digits) <= 12:
                doc_number = digits

        last_names = None
        first_names = None
        m_ap = re.search(r"apellidos?\s*[:\-]?\s*([a-z ]{3,90}?)(?=\s+nombres?\b|\s+fecha\b|\s+lugar\b|$)", n)
        if m_ap:
            last_names = " ".join(w.upper() for w in m_ap.group(1).split()[:6])
        m_no = re.search(r"nombres?\s*[:\-]?\s*([a-z ]{3,90}?)(?=\s+fecha\b|\s+lugar\b|$)", n)
        if m_no:
            first_names = " ".join(w.upper() for w in m_no.group(1).split()[:6])

        full_name = " ".join(v for v in [last_names, first_names] if v).strip() or None
        birth_date = None
        issue_date = None
        birth_place = None
        issue_place = None

        m_fn = re.search(r"fecha de nacimiento\s*[:\-]?\s*([^\n,;]{5,25})", n)
        if m_fn:
            birth_date = OcrService._to_iso_date(m_fn.group(1))
        m_fe = re.search(r"fecha y lugar de expedicion\s*[:\-]?\s*([^\n,;]{5,32})", n)
        if m_fe:
            guess = m_fe.group(1)
            issue_date = OcrService._to_iso_date(guess)
        if not issue_date:
            m_fe2 = re.search(r"expedicion\s*[:\-]?\s*([^\n,;]{5,25})", n)
            if m_fe2:
                issue_date = OcrService._to_iso_date(m_fe2.group(1))

        m_ln = re.search(r"lugar de nacimiento\s*[:\-]?\s*([a-z ]{3,60}?)(?=\s+fecha\b|\s+lugar\b|$)", n)
        if m_ln:
            birth_place = " ".join(w.upper() for w in m_ln.group(1).split()[:8])
        m_le = re.search(r"lugar de expedicion\s*[:\-]?\s*([a-z ]{3,60})", n)
        if m_le:
            issue_place = " ".join(w.upper() for w in m_le.group(1).split()[:8])

        return {
            "document_type": mk(doc_type, 0.92 if doc_type else 0.0),
            "document_number": mk(doc_number, 0.72 if doc_number else 0.0),
            "last_names": mk(last_names, 0.68 if last_names else 0.0),
            "first_names": mk(first_names, 0.68 if first_names else 0.0),
            "full_name": mk(full_name, 0.75 if full_name else 0.0),
            "birth_date": mk(birth_date, 0.78 if birth_date else 0.0),
            "birth_place": mk(birth_place, 0.63 if birth_place else 0.0),
            "issue_date": mk(issue_date, 0.78 if issue_date else 0.0),
            "issue_place": mk(issue_place, 0.63 if issue_place else 0.0),
        }

    def _build_incapacidad_rag_payload(
        self,
        *,
        filename: str,
        mime_type: str,
        text: str,
        has_text_layer: bool,
        pages_total: int,
        pages_processed: int,
        quality_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fields = self._extract_incapacidad_fields(text)
        requires_review = any(v.get("status") != "CONFIDENT" for v in fields.values())
        q = quality_hint or {}
        retrieval_summary = (
            "Documento de incapacidad médica. "
            f"Evento: {fields['tipo_evento']['value'] or 'No identificado'}. "
            f"Días: {fields['dias_incapacidad']['value'] if fields['dias_incapacidad']['value'] is not None else 'No identificado'}. "
            f"Inicio: {fields['fecha_inicio']['value'] or 'No identificado'}. "
            f"Fin: {fields['fecha_fin']['value'] or 'No identificado'}. "
            f"Entidad: {fields['entidad']['value'] or 'No identificada'}."
        )
        return {
            "document_type": "incapacidad_medica",
            "source_type": "digital_pdf_text_layer" if has_text_layer else "scanned_pdf_image_based",
            "has_text_layer": bool(has_text_layer),
            "requires_ocr": not bool(has_text_layer),
            "pages_total": int(pages_total),
            "pages_processed": int(pages_processed),
            "ocr_clean_text": text,
            "structured_fields": fields,
            "quality_report": {
                "overall_quality_score": q.get("overall_quality_score", 0.7 if has_text_layer else 0.62),
                "low_contrast": q.get("low_contrast", not has_text_layer),
                "skew_detected": q.get("skew_detected", not has_text_layer),
                "small_text_regions": q.get("small_text_regions", True),
                "table_layout_detected": q.get("table_layout_detected", True),
            },
            "retrieval_text": retrieval_summary,
            "needs_human_review": requires_review,
            "meta": {"filename": filename, "mime_type": mime_type},
        }

    def _build_identidad_rag_payload(
        self,
        *,
        filename: str,
        mime_type: str,
        text: str,
        has_text_layer: bool,
        pages_total: int,
        pages_processed: int,
    ) -> dict[str, Any]:
        fields = self._extract_identidad_fields(text)
        requires_review = any(v.get("status") != "CONFIDENT" for v in fields.values())
        retrieval_summary = (
            "Documento de identificación OCR. "
            f"Tipo: {fields['document_type']['value'] or 'No identificado'}. "
            f"Número: {fields['document_number']['value'] or 'No identificado'}. "
            f"Nombre: {fields['full_name']['value'] or 'No identificado'}. "
            f"Nacimiento: {fields['birth_date']['value'] or 'No identificado'}."
        )
        return {
            "document_type": "identificacion_personal",
            "source_type": "digital_pdf_text_layer" if has_text_layer else "scanned_pdf_image_based",
            "has_text_layer": bool(has_text_layer),
            "requires_ocr": not bool(has_text_layer),
            "pages_total": int(pages_total),
            "pages_processed": int(pages_processed),
            "ocr_clean_text": text,
            "structured_fields": fields,
            "quality_report": {
                "overall_quality_score": 0.7 if has_text_layer else 0.6,
                "small_text_regions": True,
                "needs_visual_evidence": True,
            },
            "retrieval_text": retrieval_summary,
            "needs_human_review": requires_review,
            "meta": {"filename": filename, "mime_type": mime_type},
        }

    @staticmethod
    def _extract_afiliacion_empleador_fields(text: str) -> dict[str, dict[str, Any]]:
        raw = str(text or "")
        n = OcrService._norm(raw)

        def status(conf: float) -> str:
            if conf >= 0.9:
                return "CONFIDENT"
            if conf >= 0.6:
                return "REVIEW_RECOMMENDED"
            return "UNRELIABLE"

        def mk(value: Any, conf: float) -> dict[str, Any]:
            v = None if value in ("", None) else value
            return {
                "value": v,
                "confidence": conf if v is not None else 0.0,
                "status": status(conf if v is not None else 0.0),
            }

        nit = None
        m_nit = re.search(r"\bnit\b[^0-9]{0,12}([0-9][0-9\.\- ]{6,16})", n)
        if m_nit:
            nit = re.sub(r"\D", "", m_nit.group(1))
        if not nit:
            m_doc = re.search(r"(?:documento empleador|numero de documento|identificacion empleador)[^0-9]{0,12}([0-9][0-9\.\- ]{6,16})", n)
            if m_doc:
                nit = re.sub(r"\D", "", m_doc.group(1))

        razon_social = None
        m_rs = re.search(r"(?:razon social|nombre empresa|empleador)\s*[:\-]?\s*([a-z0-9 .,&\\-]{6,120}?)(?=\s+(?:nit|direccion|ciudad|representante)\b|$)", n)
        if m_rs:
            razon_social = " ".join(w.upper() for w in m_rs.group(1).split()[:14])

        representante = None
        m_rep = re.search(r"representante legal\s*[:\-]?\s*([a-z ]{6,90}?)(?=\s+(?:documento|cedula|direccion|ciudad)\b|$)", n)
        if m_rep:
            representante = " ".join(w.upper() for w in m_rep.group(1).split()[:10])

        direccion = None
        m_dir = re.search(r"direccion(?: empresa| empleador| sede)?\s*[:\-]?\s*([a-z0-9 #\\-\\.]{5,80}?)(?=\s+(?:ciudad|telefono|correo|representante)\b|$)", n)
        if m_dir:
            direccion = " ".join(w.upper() for w in m_dir.group(1).split()[:12])

        ciudad = None
        m_ciu = re.search(r"ciudad(?: empresa| empleador| sede)?\s*[:\-]?\s*([a-z ]{3,40}?)(?=\s+(?:zona|departamento|telefono|correo|representante)\b|$)", n)
        if m_ciu:
            ciudad = " ".join(w.upper() for w in m_ciu.group(1).split()[:6])

        return {
            "nit_empleador": mk(nit, 0.82 if nit else 0.0),
            "razon_social": mk(razon_social, 0.76 if razon_social else 0.0),
            "representante_legal": mk(representante, 0.74 if representante else 0.0),
            "direccion": mk(direccion, 0.72 if direccion else 0.0),
            "ciudad": mk(ciudad, 0.72 if ciudad else 0.0),
        }

    def _build_afiliacion_empleador_rag_payload(
        self,
        *,
        filename: str,
        mime_type: str,
        text: str,
        has_text_layer: bool,
        pages_total: int,
        pages_processed: int,
    ) -> dict[str, Any]:
        fields = self._extract_afiliacion_empleador_fields(text)
        requires_review = any(v.get("status") != "CONFIDENT" for v in fields.values())
        retrieval_summary = (
            "Documento de afiliación/soporte empleador OCR. "
            f"NIT: {fields['nit_empleador']['value'] or 'No identificado'}. "
            f"Razón social: {fields['razon_social']['value'] or 'No identificada'}. "
            f"Representante legal: {fields['representante_legal']['value'] or 'No identificado'}. "
            f"Dirección: {fields['direccion']['value'] or 'No identificada'}. "
            f"Ciudad: {fields['ciudad']['value'] or 'No identificada'}."
        )
        return {
            "document_type": "afiliacion_empleador",
            "source_type": "digital_pdf_text_layer" if has_text_layer else "scanned_pdf_image_based",
            "has_text_layer": bool(has_text_layer),
            "requires_ocr": not bool(has_text_layer),
            "pages_total": int(pages_total),
            "pages_processed": int(pages_processed),
            "ocr_clean_text": text,
            "structured_fields": fields,
            "quality_report": {
                "overall_quality_score": 0.72 if has_text_layer else 0.62,
                "small_text_regions": True,
                "needs_visual_evidence": True,
            },
            "retrieval_text": retrieval_summary,
            "needs_human_review": requires_review,
            "meta": {"filename": filename, "mime_type": mime_type},
        }

    def _run_tesseract(self, file_path: Path) -> dict[str, Any]:
        if not shutil.which("tesseract"):
            return {
                "ok": False,
                "engine": "tesseract",
                "message": "tesseract no está instalado en este servidor.",
            }
        try:
            proc = subprocess.run(
                ["tesseract", str(file_path), "stdout", "-l", self.lang, "--oem", "1", "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "engine": "tesseract",
                    "message": f"OCR error: {proc.stderr.strip() or 'error desconocido'}",
                }
            txt = proc.stdout.strip()
            return {
                "ok": True,
                "engine": "tesseract",
                "text": txt,
                "chars": len(txt),
                "lines": len(txt.splitlines()) if txt else 0,
            }
        except Exception as exc:
            return {"ok": False, "engine": "tesseract", "message": f"Fallo OCR: {type(exc).__name__}: {exc}"}

    def _preprocess_scanned_page(self, image_path: Path) -> Path:
        # Improve OCR on scanned PDFs (image-only pages): denoise + contrast + binarize.
        if Image is None or ImageEnhance is None:
            return image_path
        try:
            img = Image.open(image_path).convert("L")
            img = ImageEnhance.Contrast(img).enhance(1.8)
            if ImageFilter is not None:
                img = img.filter(ImageFilter.MedianFilter(size=3))
            # Simple threshold to emphasize text strokes.
            img = img.point(lambda p: 255 if p > 155 else 0)
            out = image_path.with_name(f"{image_path.stem}_pre{image_path.suffix}")
            img.save(out)
            return out
        except Exception:
            return image_path

    def extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_text = str(payload.get("text", "")).strip()
        hinted_filename = str(payload.get("filename", "")).strip().lower()
        document_type = str(payload.get("document_type", "")).strip().lower()
        is_incapacidad = document_type == "incapacidad_medica" or ("incapac" in hinted_filename)
        is_identidad = (
            document_type in {"identificacion_personal", "cedula", "documento_identidad"}
            or any(x in hinted_filename for x in ["cedula", "cc_", "documento", "identidad"])
        )
        is_afiliacion_empleador = (
            document_type in {"afiliacion_empleador", "afiliacion_empresa", "contrato_afiliacion"}
            or any(x in hinted_filename for x in ["contrato", "camara", "comercio", "afiliacion", "formulario"])
        )
        max_pages_raw = payload.get("max_pages", 0)
        max_pages_override: int | None = None
        try:
            max_pages_num = int(max_pages_raw or 0)
            if max_pages_num > 0:
                max_pages_override = max(1, min(max_pages_num, 30))
        except Exception:
            max_pages_override = None
        if raw_text:
            out = self._fallback_text(raw_text)
            if is_incapacidad:
                out["rag_ingest_template"] = self._build_incapacidad_rag_payload(
                    filename=str(payload.get("filename", "") or "inline_text"),
                    mime_type=str(payload.get("mime_type", "") or "text/plain"),
                    text=str(out.get("text") or ""),
                    has_text_layer=True,
                    pages_total=1,
                    pages_processed=1,
                )
            elif is_identidad:
                out["rag_ingest_template"] = self._build_identidad_rag_payload(
                    filename=str(payload.get("filename", "") or "inline_text"),
                    mime_type=str(payload.get("mime_type", "") or "text/plain"),
                    text=str(out.get("text") or ""),
                    has_text_layer=True,
                    pages_total=1,
                    pages_processed=1,
                )
            elif self._looks_like_identidad(str(out.get("text") or "")):
                out["rag_ingest_template"] = self._build_identidad_rag_payload(
                    filename=str(payload.get("filename", "") or "inline_text"),
                    mime_type=str(payload.get("mime_type", "") or "text/plain"),
                    text=str(out.get("text") or ""),
                    has_text_layer=True,
                    pages_total=1,
                    pages_processed=1,
                )
            elif is_afiliacion_empleador:
                out["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                    filename=str(payload.get("filename", "") or "inline_text"),
                    mime_type=str(payload.get("mime_type", "") or "text/plain"),
                    text=str(out.get("text") or ""),
                    has_text_layer=True,
                    pages_total=1,
                    pages_processed=1,
                )
            elif self._looks_like_afiliacion_empleador(str(out.get("text") or "")):
                out["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                    filename=str(payload.get("filename", "") or "inline_text"),
                    mime_type=str(payload.get("mime_type", "") or "text/plain"),
                    text=str(out.get("text") or ""),
                    has_text_layer=True,
                    pages_total=1,
                    pages_processed=1,
                )
            return out

        file_b64 = str(payload.get("file_base64", "")).strip()
        if not file_b64:
            return {"ok": False, "message": "Debes enviar `text` o `file_base64`."}

        filename = str(payload.get("filename", "")).strip() or "ocr_input.bin"
        ext = Path(filename).suffix.lower() or ".bin"

        try:
            raw = base64.b64decode(file_b64, validate=False)
        except Exception as exc:
            return {"ok": False, "message": f"file_base64 invalido: {type(exc).__name__}: {exc}"}

        if ext == ".pdf":
            out_pdf = self._extract_pdf(raw, max_pages=max_pages_override)
            if is_incapacidad and bool(out_pdf.get("ok")):
                out_pdf["rag_ingest_template"] = self._build_incapacidad_rag_payload(
                    filename=filename,
                    mime_type="application/pdf",
                    text=str(out_pdf.get("text") or ""),
                    has_text_layer=bool(out_pdf.get("has_text_layer")),
                    pages_total=int(out_pdf.get("pages_total") or 0),
                    pages_processed=int(out_pdf.get("pages_processed") or 0),
                )
            elif is_identidad and bool(out_pdf.get("ok")):
                out_pdf["rag_ingest_template"] = self._build_identidad_rag_payload(
                    filename=filename,
                    mime_type="application/pdf",
                    text=str(out_pdf.get("text") or ""),
                    has_text_layer=bool(out_pdf.get("has_text_layer")),
                    pages_total=int(out_pdf.get("pages_total") or 0),
                    pages_processed=int(out_pdf.get("pages_processed") or 0),
                )
            elif bool(out_pdf.get("ok")) and self._looks_like_identidad(str(out_pdf.get("text") or "")):
                out_pdf["rag_ingest_template"] = self._build_identidad_rag_payload(
                    filename=filename,
                    mime_type="application/pdf",
                    text=str(out_pdf.get("text") or ""),
                    has_text_layer=bool(out_pdf.get("has_text_layer")),
                    pages_total=int(out_pdf.get("pages_total") or 0),
                    pages_processed=int(out_pdf.get("pages_processed") or 0),
                )
            elif is_afiliacion_empleador and bool(out_pdf.get("ok")):
                out_pdf["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                    filename=filename,
                    mime_type="application/pdf",
                    text=str(out_pdf.get("text") or ""),
                    has_text_layer=bool(out_pdf.get("has_text_layer")),
                    pages_total=int(out_pdf.get("pages_total") or 0),
                    pages_processed=int(out_pdf.get("pages_processed") or 0),
                )
            elif bool(out_pdf.get("ok")) and self._looks_like_afiliacion_empleador(str(out_pdf.get("text") or "")):
                out_pdf["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                    filename=filename,
                    mime_type="application/pdf",
                    text=str(out_pdf.get("text") or ""),
                    has_text_layer=bool(out_pdf.get("has_text_layer")),
                    pages_total=int(out_pdf.get("pages_total") or 0),
                    pages_processed=int(out_pdf.get("pages_processed") or 0),
                )
            return out_pdf

        with tempfile.TemporaryDirectory(prefix="nova_ocr_") as td:
            file_path = Path(td) / f"input{ext}"
            file_path.write_bytes(raw)
            if self.engine == "tesseract":
                out_img = self._run_tesseract(file_path)
                if is_incapacidad and bool(out_img.get("ok")):
                    out_img["rag_ingest_template"] = self._build_incapacidad_rag_payload(
                        filename=filename,
                        mime_type=str(payload.get("mime_type", "") or "image/*"),
                        text=str(out_img.get("text") or ""),
                        has_text_layer=False,
                        pages_total=1,
                        pages_processed=1,
                    )
                elif is_identidad and bool(out_img.get("ok")):
                    out_img["rag_ingest_template"] = self._build_identidad_rag_payload(
                        filename=filename,
                        mime_type=str(payload.get("mime_type", "") or "image/*"),
                        text=str(out_img.get("text") or ""),
                        has_text_layer=False,
                        pages_total=1,
                        pages_processed=1,
                    )
                elif bool(out_img.get("ok")) and self._looks_like_identidad(str(out_img.get("text") or "")):
                    out_img["rag_ingest_template"] = self._build_identidad_rag_payload(
                        filename=filename,
                        mime_type=str(payload.get("mime_type", "") or "image/*"),
                        text=str(out_img.get("text") or ""),
                        has_text_layer=False,
                        pages_total=1,
                        pages_processed=1,
                    )
                elif is_afiliacion_empleador and bool(out_img.get("ok")):
                    out_img["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                        filename=filename,
                        mime_type=str(payload.get("mime_type", "") or "image/*"),
                        text=str(out_img.get("text") or ""),
                        has_text_layer=False,
                        pages_total=1,
                        pages_processed=1,
                    )
                elif bool(out_img.get("ok")) and self._looks_like_afiliacion_empleador(str(out_img.get("text") or "")):
                    out_img["rag_ingest_template"] = self._build_afiliacion_empleador_rag_payload(
                        filename=filename,
                        mime_type=str(payload.get("mime_type", "") or "image/*"),
                        text=str(out_img.get("text") or ""),
                        has_text_layer=False,
                        pages_total=1,
                        pages_processed=1,
                    )
                return out_img

        return {"ok": False, "message": f"Engine OCR no soportado: {self.engine}"}

    def _extract_pdf(self, pdf_bytes: bytes, max_pages: int | None = None) -> dict[str, Any]:
        if fitz is None:
            return {"ok": False, "engine": self.engine, "message": "OCR PDF no disponible: falta dependencia PyMuPDF."}
        if self.engine != "tesseract":
            return {"ok": False, "engine": self.engine, "message": "OCR PDF soportado solo con engine tesseract."}
        if not shutil.which("tesseract"):
            return {"ok": False, "engine": self.engine, "message": "tesseract no está instalado en este servidor."}
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            return {"ok": False, "engine": self.engine, "message": f"PDF inválido: {type(exc).__name__}: {exc}"}
        pages_total = len(doc)
        effective_max_pages = max_pages if max_pages is not None else self.pdf_max_pages
        pages_to_process = min(pages_total, max(1, min(int(effective_max_pages), 30)))
        page_texts: list[str] = []
        page_details: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="nova_ocr_pdf_") as td:
            tmp_dir = Path(td)
            for i in range(pages_to_process):
                page = doc[i]
                text_layer = (page.get_text("text") or "").strip()
                has_text_layer = len(text_layer) >= 20

                # 3x zoom for better OCR quality on scanned pages.
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                page_img = tmp_dir / f"page_{i+1}.png"
                pix.save(str(page_img))

                if has_text_layer:
                    txt = text_layer
                    ocr = {"ok": True, "engine": "pdf-text-layer", "chars": len(txt)}
                    source_mode = "pdf_text_layer"
                else:
                    pre_img = self._preprocess_scanned_page(page_img)
                    ocr = self._run_tesseract(pre_img)
                    txt = str(ocr.get("text") or "").strip()
                    source_mode = "ocr_image_page"

                if txt:
                    page_texts.append(txt)
                page_details.append(
                    {
                        "page": i + 1,
                        "ok": bool(ocr.get("ok")),
                        "chars": int(ocr.get("chars") or 0),
                        "source_mode": source_mode,
                        "text_layer": has_text_layer,
                        "text_preview": txt[:180],
                    }
                )
        full_text = "\n\n".join(page_texts).strip()
        has_text_layer = any(bool(p.get("text_layer")) for p in page_details)
        scanned_pages = sum(1 for p in page_details if str(p.get("source_mode")) == "ocr_image_page")
        text_layer_pages = sum(1 for p in page_details if str(p.get("source_mode")) == "pdf_text_layer")
        return {
            "ok": True,
            "engine": self.engine,
            "mime": "application/pdf",
            "pages_total": pages_total,
            "pages_processed": pages_to_process,
            "pdf_max_pages": effective_max_pages,
            "has_text_layer": has_text_layer,
            "source_type": "scanned_pdf_image_based" if not has_text_layer else "digital_pdf_text_layer",
            "scanned_pages": scanned_pages,
            "text_layer_pages": text_layer_pages,
            "text": full_text,
            "chars": len(full_text),
            "lines": len(full_text.splitlines()) if full_text else 0,
            "pages": page_details,
        }

    def build_synthetic_ocr_docs(self, rows: list[dict[str, Any]], out_dir: str = "/tmp/nova_ocr_synthetic") -> dict[str, Any]:
        if Image is None or ImageDraw is None:
            return {"ok": False, "message": "Pillow no está instalado. No se pueden generar imágenes sintéticas."}
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        docs: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            idtramite = str(row.get("idtramite") or "").strip()
            if not idtramite:
                continue
            text = "\n".join(
                [
                    "RUTA INCLUSION - DOCUMENTO SINTETICO",
                    f"IDTRAMITE: {idtramite}",
                    f"CODIGO_UNICO_OCR: OCRSIM-{idtramite}",
                    "CLAVE_OCR_NOVA: NOVAOCRSINTETICO",
                    f"ESTADO: {str(row.get('estado') or '')}",
                    f"TRABAJADOR: {str(row.get('trabajador') or '')}",
                    f"DOCUMENTO: {str(row.get('numerodocumento') or '')}",
                    f"EMPLEADOR: {str(row.get('razonsocialempleador') or '')}",
                    f"NIT: {str(row.get('numerodocumentoempleador') or '')}",
                ]
            )
            filename = f"ocr_sintetico_{idtramite}_{idx}.png"
            file_path = target / filename
            image = Image.new("RGB", (1600, 900), color=(255, 255, 255))
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default()
            draw.multiline_text((40, 40), text, fill=(0, 0, 0), font=font, spacing=10)
            image.save(file_path, format="PNG")
            ocr = self._run_tesseract(file_path) if self.engine == "tesseract" else self._fallback_text(text)
            ocr_text = str(ocr.get("text") or "").strip()
            if not ocr_text:
                ocr_text = text
            docs.append(
                {
                    "doc_id": f"ocr-sintetico-{idtramite}",
                    "source": "ocr-sintetico",
                    "text": ocr_text,
                    "metadata": {
                        "idtramite": idtramite,
                        "estado": str(row.get("estado") or ""),
                        "tipo": "imagen_sintetica",
                        "path": str(file_path),
                    },
                }
            )
            images.append(
                {
                    "idtramite": idtramite,
                    "path": str(file_path),
                    "filename": filename,
                    "ocr_text": ocr_text,
                    "ocr_chars": len(ocr_text),
                    "ocr_ok": bool(ocr.get("ok")),
                }
            )
        manifest = {
            "ok": True,
            "engine": self.engine,
            "output_dir": str(target),
            "images_generated": len(images),
            "images": images,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "engine": self.engine,
            "output_dir": str(target),
            "images_generated": len(images),
            "images": images,
            "documents": docs,
        }

    def list_synthetic_images(self, out_dir: str = "/tmp/nova_ocr_synthetic") -> dict[str, Any]:
        target = Path(out_dir)
        if not target.exists():
            return {"ok": True, "output_dir": str(target), "images_generated": 0, "images": []}
        manifest_path = target / "manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                images = data.get("images", []) if isinstance(data, dict) else []
                return {
                    "ok": True,
                    "output_dir": str(target),
                    "images_generated": len(images),
                    "images": images,
                }
            except Exception:
                pass
        images: list[dict[str, Any]] = []
        for p in sorted(target.glob("ocr_sintetico_*.png")):
            images.append({"filename": p.name, "path": str(p)})
        return {"ok": True, "output_dir": str(target), "images_generated": len(images), "images": images}

    def resolve_synthetic_image_path(self, filename: str, out_dir: str = "/tmp/nova_ocr_synthetic") -> Path | None:
        clean = Path(filename).name
        if clean != filename or not clean.lower().endswith(".png"):
            return None
        p = Path(out_dir) / clean
        if not p.exists() or not p.is_file():
            return None
        return p
