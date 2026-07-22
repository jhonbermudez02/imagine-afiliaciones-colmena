import os
from functools import lru_cache
from typing import Any, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


DEFAULT_LEGACY_ALIASES = [
    "temporal",
    "wimg004",
    "ybr",
    "SR03EPSDB",
]


def _norm_alias(alias: str) -> str:
    return "".join(ch for ch in alias.strip() if ch.isalnum() or ch == "_").upper()


def _env_key_for_alias(alias: str) -> str:
    return f"DB_ALIAS_{_norm_alias(alias)}_URL"


def _alias_url(alias: str) -> str:
    alias_clean = alias.strip()
    if not alias_clean:
        return ""

    by_alias_env = os.getenv(_env_key_for_alias(alias_clean), "").strip()
    if by_alias_env:
        return by_alias_env

    simple_env = os.getenv(f"{_norm_alias(alias_clean)}_DATABASE_URL", "").strip()
    if simple_env:
        return simple_env

    if alias_clean.lower() == "temporal":
        return os.getenv("DATABASE_URL", "").strip()
    return ""


@lru_cache(maxsize=64)
def get_engine_by_alias(alias: str) -> Engine:
    database_url = _alias_url(alias)
    if not database_url:
        raise ValueError(
            f"No hay URL configurada para alias '{alias}'. "
            f"Define {_env_key_for_alias(alias)} o {_norm_alias(alias)}_DATABASE_URL."
        )
    return create_engine(database_url, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:pass@localhost:5432/db")
    return create_engine(database_url, pool_pre_ping=True, future=True)


def list_alias_status() -> list[dict[str, Any]]:
    aliases: dict[str, str] = {a.lower(): a for a in DEFAULT_LEGACY_ALIASES}
    for key in os.environ.keys():
        if key.startswith("DB_ALIAS_") and key.endswith("_URL"):
            alias = key[len("DB_ALIAS_") : -len("_URL")]
            if alias:
                low = alias.lower()
                if low not in aliases:
                    aliases[low] = alias

    out: list[dict[str, Any]] = []
    for alias in sorted(aliases.values(), key=lambda a: a.lower()):
        url = _alias_url(alias)
        out.append(
            {
                "alias": alias,
                "env_key": _env_key_for_alias(alias),
                "configured": bool(url),
                "driver": (url.split("://", 1)[0] if "://" in url else ""),
            }
        )
    return out


def ping_alias(alias: str) -> dict[str, Any]:
    try:
        engine = get_engine_by_alias(alias)
    except Exception as exc:
        return {"ok": False, "alias": alias, "error": f"{type(exc).__name__}: {exc}"}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "alias": alias}
    except SQLAlchemyError as exc:
        return {"ok": False, "alias": alias, "error": f"{type(exc).__name__}: {exc}"}


def fetch_all_by_alias(alias: str, sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    engine = get_engine_by_alias(alias)
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]


def execute_by_alias(alias: str, sql: str, params: Optional[dict[str, Any]] = None) -> int:
    engine = get_engine_by_alias(alias)
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return int(result.rowcount or 0)


def execute_many_by_alias(alias: str, sql: str, params_list: list[dict[str, Any]]) -> int:
    """Como execute_by_alias, pero para insertar/actualizar muchas filas con el mismo
    SQL en una sola transaccion (un commit) en vez de una llamada -y un commit- por
    fila. params_list vacia es un no-op (0 filas afectadas)."""
    if not params_list:
        return 0
    engine = get_engine_by_alias(alias)
    with engine.begin() as conn:
        result = conn.execute(text(sql), params_list)
        return int(result.rowcount or 0)


def get_table_columns_by_alias(alias: str, table: str, schema: Optional[str] = None) -> list[str]:
    engine = get_engine_by_alias(alias)
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name=table, schema=schema)
    return [str(col.get("name")) for col in columns if col.get("name")]
