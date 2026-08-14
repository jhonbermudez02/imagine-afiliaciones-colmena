#!/usr/bin/env bash
# ============================================================================
#  Genera un token de traspaso firmado y arma la URL de ingreso, igual que lo
#  hara el submenu de Yii 1.1. Sirve para probar el SSO sin tener PHP local.
#
#  Uso:
#    ./scripts/sso_token.sh                          # perfil imagine
#    ./scripts/sso_token.sh colmena                  # perfil colmena
#    PERFIL=colmena USUARIO=jbermudez ./scripts/sso_token.sh
#
#  Variables:
#    SSO_SHARED_SECRET  secreto compartido (debe ser el MISMO del backend)
#    BASE_URL           default http://localhost:8105
#    USUARIO / NOMBRE / EMAIL
#
#  El token dura lo que diga SSO_TOKEN_TTL_SECONDS en el backend (90s por
#  defecto) y es de un solo uso: para reintentar hay que generar otro.
# ============================================================================
set -euo pipefail

PERFIL="${1:-${PERFIL:-imagine}}"
BASE_URL="${BASE_URL:-http://localhost:8105}"
SECRET="${SSO_SHARED_SECRET:-}"
USUARIO="${USUARIO:-jbermudez}"
NOMBRE="${NOMBRE:-Jhon Bermudez}"
EMAIL="${EMAIL:-jhonbermudezpa98@gmail.com}"

if [[ -z "$SECRET" ]]; then
  echo "ERROR: falta SSO_SHARED_SECRET (debe coincidir con el del backend)." >&2
  echo "  export SSO_SHARED_SECRET='...'   # el mismo del .env / compose" >&2
  exit 1
fi
if [[ "$PERFIL" != "imagine" && "$PERFIL" != "colmena" ]]; then
  echo "ERROR: perfil debe ser 'imagine' o 'colmena' (recibi: $PERFIL)" >&2
  exit 1
fi

URL="$(SECRET="$SECRET" PERFIL="$PERFIL" USUARIO="$USUARIO" NOMBRE="$NOMBRE" EMAIL="$EMAIL" \
       BASE_URL="$BASE_URL" python3 - <<'PY'
import base64, hashlib, hmac, json, os, time, uuid

payload = {
    "usuario": os.environ["USUARIO"],
    "nombre":  os.environ["NOMBRE"],
    "email":   os.environ["EMAIL"],
    "perfil":  os.environ["PERFIL"],
    "iat":     int(time.time()),
    "jti":     uuid.uuid4().hex,
}
raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
mac = hmac.new(os.environ["SECRET"].encode(), b64.encode(), hashlib.sha256).digest()
firma = base64.urlsafe_b64encode(mac).decode().rstrip("=")
print(f"{os.environ['BASE_URL']}/sso/yii?token={b64}.{firma}")
PY
)"

echo "Perfil : $PERFIL"
echo "Usuario: $USUARIO"
echo
echo "$URL"
echo
echo "Abrela en el navegador (vence en ~90s y es de un solo uso)."
