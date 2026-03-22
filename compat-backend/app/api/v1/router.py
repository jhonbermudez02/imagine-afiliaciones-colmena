import os

from fastapi import APIRouter

from app.api.v1 import afiliaciones, ai, funerarios, notificaciones, nova

api_router = APIRouter()

profile = os.getenv("APP_PROFILE", "full").strip().lower()

# IA/NOVA se mantienen activos para todos los perfiles operativos.
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(nova.router, prefix="/nova", tags=["nova"])

if profile in {"full", "all", "afiliaciones", "afiliaciones_only"}:
    api_router.include_router(afiliaciones.router, prefix="/afiliaciones", tags=["afiliaciones"])

if profile in {"full", "all", "funerarios", "funerarios_only"}:
    api_router.include_router(funerarios.router, prefix="/funerarios", tags=["funerarios"])

if profile in {"full", "all", "notificaciones", "notificaciones_only"}:
    api_router.include_router(notificaciones.router, prefix="/notificaciones", tags=["notificaciones"])
