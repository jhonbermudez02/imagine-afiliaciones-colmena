#!/usr/bin/env bash
# ============================================================================
#  Levanta una pagina local que imita el submenu de Yii 1.1: dos enlaces, uno
#  por perfil, cada uno con su token recien firmado.
#
#  Uso:
#    SSO_SHARED_SECRET='...' ./scripts/sso_yii_demo.sh      # sirve en :8199
#
#  Los tokens se generan al abrir la pagina; como vencen en ~90s y son de un
#  solo uso, la pagina se auto-recarga para tener enlaces frescos.
# ============================================================================
set -euo pipefail

PORT="${PORT:-8199}"
BASE_URL="${BASE_URL:-http://localhost:8105}"
SECRET="${SSO_SHARED_SECRET:-}"
[[ -n "$SECRET" ]] || { echo "ERROR: falta SSO_SHARED_SECRET" >&2; exit 1; }

echo "Menu falso de Yii en http://localhost:$PORT  (Ctrl+C para salir)"
echo "Apunta a la app en $BASE_URL"

SECRET="$SECRET" BASE_URL="$BASE_URL" PORT="$PORT" python3 - <<'PY'
import base64, hashlib, hmac, json, os, time, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = os.environ["SECRET"]; BASE = os.environ["BASE_URL"]

def token(perfil, usuario, nombre):
    p = {"usuario": usuario, "nombre": nombre, "email": f"{usuario}@colmena.com",
         "perfil": perfil, "iat": int(time.time()), "jti": uuid.uuid4().hex}
    b64 = base64.urlsafe_b64encode(
        json.dumps(p, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
    mac = hmac.new(SECRET.encode(), b64.encode(), hashlib.sha256).digest()
    return f"{b64}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        links = "".join(
            f'<a class="mi" href="{BASE}/sso/yii?token={token(perfil, usuario, nombre)}">'
            f'<b>Afiliaciones ARL</b><span>Perfil {perfil}</span></a>'
            for perfil, usuario, nombre in [
                ("imagine", "jbermudez", "Jhon Bermudez"),
                ("colmena", "operador.colmena", "Operador Colmena"),
            ])
        html = f"""<!doctype html><meta charset="utf-8"><title>Portal (simulado)</title>
<meta http-equiv="refresh" content="60">
<style>
 body{{font:14px system-ui;background:#1f2933;color:#e5e7eb;margin:0;padding:40px}}
 .box{{max-width:520px;margin:auto;background:#111827;border-radius:10px;padding:26px}}
 h1{{font-size:16px;margin:0 0 4px}} p{{color:#9ca3af;font-size:12px;margin:0 0 20px}}
 .mi{{display:flex;flex-direction:column;gap:2px;padding:13px 16px;margin-bottom:10px;
   background:#1f2937;border-left:3px solid #3b82f6;border-radius:6px;
   color:#e5e7eb;text-decoration:none}}
 .mi:hover{{background:#374151}} .mi span{{font-size:11px;color:#9ca3af}}
 code{{background:#0b1220;padding:2px 6px;border-radius:4px;font-size:11px}}
</style>
<div class="box"><h1>Portal Colmena · menú (simulado)</h1>
<p>Cada enlace lleva su propio token firmado. Vencen en ~90 s y son de un solo uso:
la página se recarga sola cada 60 s.</p>
{links}
<p style="margin-top:20px">Destino: <code>{BASE}</code></p></div>"""
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("0.0.0.0", int(os.environ["PORT"])), H).serve_forever()
PY
