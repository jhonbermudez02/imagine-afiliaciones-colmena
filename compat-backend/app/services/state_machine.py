from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class StateMachineService:
    """Maquina de estados base con auditoria best-effort.

    Todavia no valida transiciones, pero persiste trazas operativas:
    - not_* -> auxilios.not_log
    - fun_* -> auxilios.fun_actividades
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine

    def register_event(self, aggregate: str, aggregate_id: str, event: str, payload: dict) -> None:
        if not self.engine:
            return
        try:
            if aggregate.startswith("not_"):
                self._audit_notificaciones(aggregate_id, event, payload)
            elif aggregate.startswith("fun_"):
                self._audit_funerarios(aggregate_id, event, payload)
        except SQLAlchemyError:
            # Auditoria no debe romper el flujo transaccional principal.
            return

    def _audit_notificaciones(self, aggregate_id: str, event: str, payload: dict) -> None:
        try:
            solicitud_id = int(aggregate_id)
        except (TypeError, ValueError):
            return

        usuario = str(payload.get("usuario", "")).strip() or "SYSTEM"
        estado_anterior = str(payload.get("estado_actual", "") or "")
        estado_actual = str(payload.get("new_estado", "") or event)
        observacion = str(payload.get("observacion_g", payload.get("razon_rechazo", "")) or "")

        sql = text(
            """
            INSERT INTO auxilios.not_log
            (solicitud_id, usuario, estado_anterior, estado_actual, observacion)
            VALUES
            (:solicitud_id, :usuario, :estado_anterior, :estado_actual, :observacion)
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "solicitud_id": solicitud_id,
                    "usuario": usuario,
                    "estado_anterior": estado_anterior,
                    "estado_actual": estado_actual,
                    "observacion": observacion,
                },
            )

    def _audit_funerarios(self, aggregate_id: str, event: str, payload: dict) -> None:
        tramite = str(payload.get("tramite", aggregate_id)).strip() or str(aggregate_id)
        usuario = str(payload.get("usuario", "")).strip() or "SYSTEM"
        new_estado = str(payload.get("new_estado", "")).strip()
        descripcion = f"{event}" if not new_estado else f"{event} -> {new_estado}"

        sql = text(
            """
            INSERT INTO auxilios.fun_actividades
            (descripcion_actividad, usuario_ejecuta, proceso, tramite)
            VALUES
            (:descripcion_actividad, :usuario_ejecuta, 'FUNERARIOS AUXILIOS', :tramite)
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "descripcion_actividad": descripcion,
                    "usuario_ejecuta": usuario,
                    "tramite": tramite,
                },
            )
