"""Ingreso desde el portal Yii 1.1 (Active Directory) por token firmado.

El portal ya autenticó al usuario contra el directorio activo. Esta app no repite esa
autenticación: recibe un traspaso firmado y abre su propia sesión.

    Yii (AD)                         esta app
       │ clic en el submenú
       │ token = base64(payload) + "." + HMAC-SHA256(payload, secreto)
       ├──── GET /sso/yii?token=… ──────►│ valida firma, exp, jti sin usar
       │                                  │ Set-Cookie de sesión (HttpOnly)
       │◄──── 302 a /  (ya sin token) ────┤
       │                                  │
       │ el front arranca → GET /api/session → {usuario, perfil} → bandeja correcta

Por qué un token y no la cookie de sesión de Yii: la sesión de Yii 1.1 es PHP
serializado en su propio almacén; leerla desde Python ataría esta app al formato interno
de PHP y obligaría a compartir el storage. El token firmado no tiene estado compartido y
funciona aunque el portal y la app vivan en hosts distintos.

Por qué el token NO es la sesión: viajando en la URL queda en el historial del navegador,
en los logs de nginx y en la cabecera Referer. Se canjea una sola vez por una cookie
HttpOnly y el redirect deja la URL limpia.

El perfil (imagine/colmena) lo fija el enlace del menú, no el directorio activo: son dos
entradas distintas en Yii, cada una con su perfil. Queda registrado que el perfil es una
elección del portal y no un atributo de la identidad del usuario.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

PERFILES_VALIDOS = {"imagine", "colmena"}

# jti ya canjeados, con el instante en que dejan de importar (su propio exp). Basta con
# memoria del proceso: el token vive 90 s, así que un reinicio solo puede "olvidar" los
# de la última ventana, y esos ya expiraron o están por expirar. Un store persistente
# (Redis/tabla) solo haría falta con varios workers, ver nota en README.
_jti_usados: Dict[str, float] = {}
_jti_lock = threading.Lock()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _firmar(payload_b64: str, secreto: str) -> str:
    mac = hmac.new(secreto.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256)
    return _b64url_encode(mac.digest())


def firmar_payload(payload: Dict[str, Any], secreto: str) -> str:
    """Arma un token `payload.firma`. Lo usa Yii en PHP y el script de pruebas local."""
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload_b64}.{_firmar(payload_b64, secreto)}"


def _purgar_jti(ahora: float) -> None:
    vencidos = [jti for jti, expira in _jti_usados.items() if expira <= ahora]
    for jti in vencidos:
        _jti_usados.pop(jti, None)


def _consumir_jti(jti: str, expira_en: float) -> bool:
    """Marca el jti como usado. Devuelve False si ya se había usado (replay)."""
    ahora = time.time()
    with _jti_lock:
        _purgar_jti(ahora)
        if jti in _jti_usados:
            return False
        _jti_usados[jti] = expira_en
        return True


def validar_token(token: str, secreto: str, ttl_seconds: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """Valida el token de traspaso. Devuelve (payload, "") o (None, motivo).

    El motivo es para el log del servidor, NO para la respuesta al navegador: decirle a
    quien prueba tokens si falló la firma, el vencimiento o el replay le sirve para
    afinar el ataque. Al cliente se le responde siempre lo mismo.
    """
    if not secreto:
        return None, "sso_shared_secret sin configurar"
    token = str(token or "").strip()
    if not token or token.count(".") != 1:
        return None, "formato de token invalido"

    payload_b64, firma = token.split(".", 1)
    esperada = _firmar(payload_b64, secreto)
    # compare_digest: la comparación normal de strings corta en el primer byte distinto y
    # filtra por tiempo cuántos bytes de la firma se acertaron.
    if not hmac.compare_digest(firma, esperada):
        return None, "firma invalida"

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        return None, f"payload ilegible: {type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "payload no es un objeto"

    ahora = time.time()
    try:
        iat = float(payload.get("iat") or 0)
    except (TypeError, ValueError):
        return None, "iat invalido"
    if iat <= 0:
        return None, "falta iat"
    # 60 s de tolerancia por desfase de reloj entre el server de Yii y este.
    if iat > ahora + 60:
        return None, "iat en el futuro"
    expira_en = iat + max(1, int(ttl_seconds))
    if ahora > expira_en:
        return None, f"token vencido (iat hace {int(ahora - iat)}s, ttl {ttl_seconds}s)"

    perfil = str(payload.get("perfil") or "").strip().lower()
    if perfil not in PERFILES_VALIDOS:
        return None, f"perfil invalido: {perfil!r}"
    usuario = str(payload.get("usuario") or "").strip()
    if not usuario:
        return None, "falta usuario"

    jti = str(payload.get("jti") or "").strip()
    if not jti:
        return None, "falta jti"
    if not _consumir_jti(jti, expira_en):
        return None, f"jti ya usado: {jti}"

    return payload, ""


def crear_sesion(payload: Dict[str, Any], secreto: str, ttl_seconds: int) -> str:
    """Valor de la cookie de sesión: mismo esquema firmado, con su propio vencimiento."""
    ahora = int(time.time())
    datos = {
        "usuario": str(payload.get("usuario") or "").strip(),
        "nombre": str(payload.get("nombre") or payload.get("usuario") or "").strip(),
        # La identidad del operador es el "usuario" del token (portal/AD). El correo ya no
        # se usa en ninguna parte del flujo: lo que se guarda como operador es el usuario.
        "perfil": str(payload.get("perfil") or "").strip().lower(),
        "origen": "yii",
        "iat": ahora,
        "exp": ahora + max(60, int(ttl_seconds)),
    }
    return firmar_payload(datos, secreto)


def leer_sesion(cookie_value: str, secreto: str) -> Optional[Dict[str, Any]]:
    """Sesión válida desde la cookie, o None. No consume jti: la cookie se reusa."""
    if not secreto or not cookie_value or str(cookie_value).count(".") != 1:
        return None
    payload_b64, firma = str(cookie_value).split(".", 1)
    if not hmac.compare_digest(firma, _firmar(payload_b64, secreto)):
        return None
    try:
        datos = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(datos, dict):
        return None
    try:
        if float(datos.get("exp") or 0) <= time.time():
            return None
    except (TypeError, ValueError):
        return None
    if str(datos.get("perfil") or "") not in PERFILES_VALIDOS:
        return None
    return datos
