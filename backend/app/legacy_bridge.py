from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict

import httpx

from .config import settings


def _load_legacy_engine_class():
    root_value = str(settings.legacy_project_root or "").strip()
    if not root_value:
        return None, "legacy_project_root no configurado."
    root = Path(root_value).expanduser()
    engine_path = root / "backend" / "app" / "services" / "legacy_compat_engine.py"
    if not engine_path.exists():
        return None, f"No existe legacy_compat_engine.py en {engine_path}."
    spec = importlib.util.spec_from_file_location("nova_legacy_compat_engine", engine_path)
    if spec is None or spec.loader is None:
        return None, "No pude cargar el spec del engine legacy."
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine_class = getattr(module, "LegacyCompatEngine", None)
    if engine_class is None:
        return None, "LegacyCompatEngine no está disponible en el módulo legacy."
    return engine_class, ""


def generate_legacy_flatfile_926(lote: str = "") -> Dict[str, Any]:
    engine_class, error = _load_legacy_engine_class()
    if engine_class is None:
        return {"available": False, "ok": False, "error": error}

    state_value = str(settings.legacy_state_path or "").strip()
    if not state_value:
        return {"available": False, "ok": False, "error": "legacy_state_path no configurado."}
    state_path = Path(state_value).expanduser()
    if not state_path.exists():
        return {"available": False, "ok": False, "error": f"No existe legacy_state_path en {state_path}."}

    try:
        engine = engine_class(state_path=state_path)
        content = engine.generate_flatfile_926(lote=lote)
        text = content.decode("latin-1", errors="replace")
        return {
            "available": True,
            "ok": True,
            "filename": f"legacy_926_{lote or 'caso'}.txt",
            "content": text,
            "source": str(state_path),
        }
    except Exception as exc:
        return {"available": True, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def generate_legacy_flatfile_926_http(lote: str, base: str = "ybr", strict_validate: bool = False) -> Dict[str, Any]:
    configured_url = str(settings.legacy_backend_url or "").strip().rstrip("/")
    if not configured_url:
        return {"available": False, "ok": False, "error": "legacy_backend_url no configurado."}
    if not lote:
        return {"available": False, "ok": False, "error": "Se requiere lote para generar 926 por HTTP."}

    candidate_urls = _compat_candidate_urls(configured_url)

    last_error = ""
    for backend_url in candidate_urls:
        try:
            response = httpx.get(
                f"{backend_url}/legacy/flatfile/build",
                params={
                    "lote": lote,
                    "from_db": "true",
                    "base": base,
                    "strict_validate": "true" if strict_validate else "false",
                },
                timeout=120.0,
            )
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                continue
            content = response.text
            return {
                "available": True,
                "ok": True,
                "filename": f"legacy_http_926_{lote}.txt",
                "content": content,
                "source": backend_url,
                "headers": dict(response.headers),
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

    return {"available": True, "ok": False, "error": last_error or "No pude conectar con el backend legacy."}


def _compat_candidate_urls(configured_url: str = "") -> list[str]:
    """URLs a intentar contra el compat-backend, en orden.

    Dentro de docker el nombre del servicio resuelve solo; cuando el backend corre fuera
    del compose (desarrollo en el host) la url configurada apunta a 127.0.0.1/localhost,
    que desde un contenedor no es el host. Por eso se prueba tambien
    host.docker.internal como alternativa, sin cambiar configuracion.
    """
    base = str(configured_url or settings.legacy_backend_url or "").strip().rstrip("/")
    if not base:
        return []
    urls = [base]
    for local in ("127.0.0.1", "localhost"):
        if local in base:
            urls.append(base.replace(local, "host.docker.internal"))
    return urls


def _compat_get(path: str, timeout: float = 60.0) -> httpx.Response:
    """GET contra el compat-backend probando las urls candidatas.

    Devuelve la primera respuesta con codigo 200. Un 4xx del compat es una respuesta
    legitima del servicio -no un fallo de conectividad-, asi que se propaga tal cual en
    vez de seguir intentando con la siguiente url.
    """
    candidatos = _compat_candidate_urls()
    if not candidatos:
        raise RuntimeError("legacy_backend_url no configurado.")
    ultimo_error = ""
    for base in candidatos:
        try:
            respuesta = httpx.get(f"{base}{path}", timeout=timeout)
        except Exception as exc:
            ultimo_error = f"{type(exc).__name__}: {exc}"
            continue
        if respuesta.status_code == 200 or 400 <= respuesta.status_code < 500:
            return respuesta
        ultimo_error = f"HTTP {respuesta.status_code}: {respuesta.text[:300]}"
    raise RuntimeError(ultimo_error or "No pude conectar con el compat-backend.")


def pqr_pendientes() -> Dict[str, Any]:
    """Bandeja de afiliaciones pendientes (view pqr.afa_pendientes) con sus adjuntos."""
    respuesta = _compat_get("/legacy/pqr/pendientes")
    if respuesta.status_code != 200:
        raise RuntimeError(_compat_detalle(respuesta))
    return respuesta.json()


def pqr_adjuntos(id_radicacion: int) -> Dict[str, Any]:
    """Inventario de adjuntos de una radicacion."""
    respuesta = _compat_get(f"/legacy/pqr/pendientes/{int(id_radicacion)}/adjuntos")
    if respuesta.status_code != 200:
        raise RuntimeError(_compat_detalle(respuesta))
    return respuesta.json()


def pqr_adjunto_bytes(id_radicacion: int, id_adjunto: int) -> bytes:
    """Contenido de un adjunto del repositorio legacy."""
    respuesta = _compat_get(
        f"/legacy/pqr/pendientes/{int(id_radicacion)}/adjuntos/{int(id_adjunto)}",
        timeout=120.0,
    )
    if respuesta.status_code != 200:
        raise RuntimeError(_compat_detalle(respuesta))
    return respuesta.content


def pqr_adjuntos_zip(id_radicacion: int) -> bytes:
    """Todos los adjuntos de la radicacion, comprimidos por el compat."""
    respuesta = _compat_get(f"/legacy/pqr/pendientes/{int(id_radicacion)}/zip", timeout=180.0)
    if respuesta.status_code != 200:
        raise RuntimeError(_compat_detalle(respuesta))
    return respuesta.content


def _compat_detalle(respuesta: httpx.Response) -> str:
    """Mensaje de error del compat, prefiriendo su campo `detail` sobre el cuerpo crudo."""
    try:
        cuerpo = respuesta.json()
        if isinstance(cuerpo, dict) and cuerpo.get("detail"):
            return str(cuerpo["detail"])
    except Exception:
        pass
    return f"HTTP {respuesta.status_code}: {respuesta.text[:300]}"
