import time
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.observability import (
    get_logger,
    get_or_create_request_id,
    request_id_ctx,
    request_log_payload,
    setup_logging,
)


def _load_runtime_env() -> None:
    # Carga explícita de archivos .env para evitar depender de export al shell.
    cwd = Path.cwd()
    here = Path(__file__).resolve().parents[2]  # .../backend
    candidates = [
        cwd / ".env",
        cwd / ".env.real",
        here / ".env",
        here / ".env.real",
        Path("/srv/www/.env"),
    ]
    for env_file in candidates:
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=False)


_load_runtime_env()

from app.api.v1.router import api_router

setup_logging()
logger = get_logger("app.api")

app = FastAPI(title="Flujos Migracion API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    started_at = time.time()
    request_id = get_or_create_request_id(request)
    token = request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(request_log_payload(request, response.status_code, started_at))
        return response
    finally:
        request_id_ctx.reset(token)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = request_id_ctx.get("-")
    logger.warning(request_log_payload(request, exc.status_code, time.time()))
    safe_detail = jsonable_encoder(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {"type": "http_error", "detail": safe_detail},
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request_id_ctx.get("-")
    logger.exception(f'unhandled_error method="{request.method}" path="{request.url.path}" error="{exc}"')
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {"type": "internal_error", "detail": "Unhandled server error"},
            "request_id": request_id,
        },
    )
