from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.notificaciones_repository import NotificacionesRepository
from app.services.state_machine import StateMachineService


class NotificacionesService:
    def __init__(self, repository: NotificacionesRepository, state_machine: StateMachineService) -> None:
        self.repository = repository
        self.state_machine = state_machine
        self._bloqueo_fallback: dict | None = None
        self._post_estados_fallback: list[dict] = [
            {"estado_post_id": 1, "estado_post": "Pendiente Validacion"},
            {"estado_post_id": 2, "estado_post": "Pendiente Prestacion"},
            {"estado_post_id": 3, "estado_post": "Prestacion Generada"},
            {"estado_post_id": 4, "estado_post": "Rechazada"},
        ]

    def consultar_afiliado(self, tipo_id: str, identificacion: str, tipo_solicitud: str) -> dict:
        mode = os.getenv("NOT_CONSULTA_AFIL_MODE", "stub").strip().lower()
        result_items: list[dict] = []
        source = "soap_stub"
        if mode == "real":
            wsdl = os.getenv("WSDL_PENSION", "").strip()
            endpoint = os.getenv("ENDPOINTURI_PENSION", "").strip()
            if wsdl:
                try:
                    from zeep import Client, Settings
                    from zeep.transports import Transport

                    client = Client(
                        wsdl=wsdl,
                        transport=Transport(timeout=180),
                        settings=Settings(strict=False),
                    )
                    if endpoint:
                        try:
                            client.service._binding_options["address"] = endpoint
                        except Exception:
                            pass
                    response = client.service.solicitudAfiliadoConsulta(
                        solicitudAfiliadoConsultaEntrada={
                            "Cabecera": "",
                            "identificacionAfiliado": {"tipoId": tipo_id, "id": identificacion},
                            "tipoSolicitud": tipo_solicitud,
                        }
                    )
                    payload = json.loads(json.dumps(response, default=str))
                    salida = payload.get("solicitudAfiliadoConsultaSalida", {})
                    lista = salida.get("listaSolicitud", [])
                    if isinstance(lista, dict):
                        lista = [lista]
                    for item in lista:
                        result_items.append(
                            {
                                "idSolicitud": str(item.get("idSolicitud", "")),
                                "tipoSolicitud": str(item.get("tipoSolicitud", "")),
                                "estadoSolicitud": str(item.get("estadoSolicitud", "")),
                                "fechaSolicitud": str(item.get("fechaSolicitud", "")),
                            }
                        )
                    source = "soap_real"
                except Exception:
                    source = "soap_real_error"
            else:
                source = "soap_real_missing_wsdl"
        self.state_machine.register_event(
            "not_solicitud",
            identificacion,
            "consulta_afiliado",
            {"tipo_id": tipo_id, "tipo_solicitud": tipo_solicitud, "source": source},
        )
        return {
            "ok": True,
            "tipo_id": tipo_id,
            "id": identificacion,
            "tipo_solicitud": tipo_solicitud,
            "result": result_items,
            "source": source,
        }

    def notificar_solicitud(self, payload: dict) -> dict:
        solicitud_id = self.repository.insert_notificacion(payload)
        inserted_beneficiarios = self.repository.insert_beneficiarios(
            payload["tramite"],
            payload["usuario"],
            payload["beneficiarios"],
        )
        self.state_machine.register_event(
            "not_solicitud",
            payload["tramite"],
            "notificar",
            {
                "solicitud_id": solicitud_id,
                "inserted_beneficiarios": inserted_beneficiarios,
                "usuario": payload["usuario"],
            },
        )
        return {
            "ok": True,
            "tramite": payload["tramite"],
            "solicitud_id": solicitud_id,
            "inserted_beneficiarios": inserted_beneficiarios,
        }

    def validar_tramite(self, solicitud_id: int, tramite: str, id_prestacion: int, usuario: str) -> dict:
        # Regla base tomada del legacy:
        # prestacion 1 => PENDIENTE GENERAR PRESTACION, resto => PENDIENTE LLAMADA.
        new_estado = "PENDIENTE GENERAR PRESTACION" if id_prestacion == 1 else "PENDIENTE LLAMADA"
        affected = self.repository.change_estado_solicitud(solicitud_id, tramite, new_estado)
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "validar_tramite",
            {
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "usuario": usuario,
                "new_estado": new_estado,
                "affected": affected,
            },
        )
        return {
            "ok": affected > 0,
            "solicitud_id": solicitud_id,
            "tramite": tramite,
            "new_estado": new_estado,
            "affected": affected,
        }

    def rechazar_tramite(
        self,
        solicitud_id: int,
        tramite: str,
        id_prestacion: int,
        razon_rechazo: str,
        usuario: str,
    ) -> dict:
        self.repository.add_log_transition(
            solicitud_id=solicitud_id,
            usuario=usuario,
            estado_proximo="Solicitud Rechazada",
            observacion=razon_rechazo,
        )
        new_estado = "DOCUMENTACION PENDIENTE"
        affected = self.repository.change_estado_solicitud(solicitud_id, tramite, new_estado)
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "rechazar_tramite",
            {
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "usuario": usuario,
                "razon_rechazo": razon_rechazo,
                "new_estado": new_estado,
                "affected": affected,
            },
        )
        return {
            "ok": affected > 0,
            "solicitud_id": solicitud_id,
            "tramite": tramite,
            "new_estado": new_estado,
            "affected": affected,
        }

    def cambiar_estado_solicitud(self, solicitud_id: int, tramite: str, usuario: str, new_estado: str) -> dict:
        affected = self.repository.change_estado_solicitud(solicitud_id, tramite, new_estado)
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "cambiar_estado",
            {"tramite": tramite, "usuario": usuario, "new_estado": new_estado, "affected": affected},
        )
        return {
            "ok": affected > 0,
            "solicitud_id": solicitud_id,
            "tramite": tramite,
            "new_estado": new_estado,
            "affected": affected,
        }

    def finalizar_tramite(self, solicitud_id: int, tramite: str, usuario: str) -> dict:
        self.repository.add_log_transition(
            solicitud_id=solicitud_id,
            usuario=usuario,
            estado_proximo="Prestacion Generada",
            observacion="",
        )
        affected = self.repository.finalize_tramite(solicitud_id, tramite)
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "finalizar_tramite",
            {"tramite": tramite, "usuario": usuario, "new_estado": "FINALIZADO", "affected": affected},
        )
        return {
            "ok": affected > 0,
            "solicitud_id": solicitud_id,
            "tramite": tramite,
            "new_estado": "FINALIZADO",
            "affected": affected,
        }

    def guardar_post_estado(
        self, solicitud_id: int, id_estado_post: int, marca: bool, usuario: str
    ) -> dict:
        result = self.repository.upsert_post_estado(solicitud_id, id_estado_post, marca, usuario)
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "guardar_post_estado",
            {
                "id_estado_post": id_estado_post,
                "marca": marca,
                "usuario": usuario,
                **result,
            },
        )
        return {"ok": (result["inserted"] + result["updated"]) > 0, "solicitud_id": solicitud_id, **result}

    def guardar_post_gestion(
        self, solicitud_id: int, tipo_gestion: int, usuario: str, observacion_g: str | None
    ) -> dict:
        result = self.repository.guardar_post_gestion(
            solicitud_id=solicitud_id,
            tipo_gestion=tipo_gestion,
            usuario=usuario,
            observacion_g=observacion_g,
        )
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "guardar_post_gestion",
            {
                "tipo_gestion": tipo_gestion,
                "usuario": usuario,
                "observacion_g": observacion_g or "",
                **result,
            },
        )
        return {"ok": (result["inserted"] + result["updated"]) > 0, "solicitud_id": solicitud_id, **result}

    def listar_reclamantes(self, solicitud_id: int, tramite: str | None) -> dict:
        items = self.repository.list_reclamantes(solicitud_id=solicitud_id, tramite=tramite)
        return {"ok": True, "solicitud_id": solicitud_id, "count": len(items), "items": items}

    def traer_imagenes_a_validar(
        self, solicitud_id: int, tramite: str, id_prestacion: int, tipo_solicitud: str
    ) -> dict:
        items = self.repository.list_imagenes_validacion(
            solicitud_id=solicitud_id,
            tramite=tramite,
            id_prestacion=id_prestacion,
            tipo_solicitud=tipo_solicitud,
        )
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "traer_imagenes_a_validar",
            {
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "tipo_solicitud": tipo_solicitud,
                "count": len(items),
            },
        )
        return {"ok": True, "solicitud_id": solicitud_id, "count": len(items), "items": items}

    def validar_imagen(self, solicitud_id: int, tramite: str, pn: int, ax: str, valor: int) -> dict:
        result = self.repository.upsert_marca_imagen(
            solicitud_id=solicitud_id,
            tramite=tramite,
            pn=pn,
            ax=ax,
            valor=valor,
        )
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "validar_imagen",
            {"tramite": tramite, "pn": pn, "ax": ax, "valor": valor, **result},
        )
        return {"ok": (result["inserted"] + result["updated"]) > 0, "solicitud_id": solicitud_id, **result}

    def consultar_imagenes(
        self, solicitud_id: int, tramite: str, id_prestacion: int, tipo_solicitud: str
    ) -> dict:
        items = self.repository.list_imagenes_consulta(
            solicitud_id=solicitud_id,
            tramite=tramite,
            id_prestacion=id_prestacion,
            tipo_solicitud=tipo_solicitud,
        )
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "consultar_imagenes",
            {
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "tipo_solicitud": tipo_solicitud,
                "count": len(items),
            },
        )
        return {"ok": True, "solicitud_id": solicitud_id, "count": len(items), "items": items}

    def eliminar_imagen_existente(self, pn: int) -> dict:
        result = self.repository.eliminar_imagen_existente(pn)
        self.state_machine.register_event("not_documento", str(pn), "eliminar_imagen_existente", result)
        return {"ok": True, "pn": pn, **result}

    def actualizar_categoria(self, pn: int, val: int) -> dict:
        affected = self.repository.actualizar_categoria(pn=pn, val=val)
        self.state_machine.register_event(
            "not_documento",
            str(pn),
            "actualizar_categoria",
            {"pn": pn, "val": val, "affected": affected},
        )
        return {"ok": affected > 0, "pn": pn, "val": val, "affected": affected}

    def actualizar_categoria_new(self, key: str, val: str, indexado: str) -> dict:
        affected = self.repository.actualizar_categoria_new(key=key, val=val, indexado=indexado)
        self.state_machine.register_event(
            "not_documento",
            key,
            "actualizar_categoria_new",
            {"key": key, "val": val, "indexado": indexado, "affected": affected},
        )
        return {"ok": affected > 0, "key": key, "val": val, "indexado": indexado, "affected": affected}

    def traer_gestion_post_prestacion(self, solicitud_id: int, tipo_gestion: int, usuario: str) -> dict:
        source = "db"
        try:
            context = self.repository.get_post_gestion_context(
                solicitud_id=solicitud_id, tipo_gestion=tipo_gestion
            )
        except SQLAlchemyError:
            source = "fallback_memory"
            estado_meta = next(
                (e for e in self._post_estados_fallback if int(e.get("estado_post_id", 0)) == int(tipo_gestion)),
                None,
            )
            context = {
                "tipo_gestion_meta": estado_meta,
                "ultima_gestion": None,
            }
        self.state_machine.register_event(
            "not_solicitud",
            str(solicitud_id),
            "traer_gestion_post_prestacion",
            {"tipo_gestion": tipo_gestion, "usuario": usuario, "source": source},
        )
        return {
            "ok": True,
            "source": source,
            "solicitud_id": solicitud_id,
            "tipo_gestion": tipo_gestion,
            "usuario": usuario,
            "ui": {
                "titulo": "Gestion post prestacion",
                "label_observacion": "Observacion de la gestion",
                "require_observacion": True,
                "accion": "guardarPostGestion",
            },
            **context,
        }

    def listar_post_estados_activos(self) -> dict:
        source = "db"
        try:
            items = self.repository.list_post_estados_activos()
        except SQLAlchemyError:
            source = "fallback_memory"
            items = list(self._post_estados_fallback)
        return {"ok": True, "source": source, "count": len(items), "items": items}

    def listar_auditoria(self, solicitud_id: int, limit: int) -> dict:
        items = self.repository.list_auditoria(solicitud_id=solicitud_id, limit=limit)
        return {"ok": True, "solicitud_id": solicitud_id, "count": len(items), "items": items}

    def adicionar_img_caso(
        self,
        *,
        tramite: str,
        solicitud_id: int,
        prestacion: int,
        nombre_archivo: str,
        content: bytes,
        usuario: str,
    ) -> dict:
        day = datetime.now().strftime("%Y%m%d")
        ext = Path(nombre_archivo).suffix or ".bin"
        unique = f"{day}_{uuid4().hex[:12]}{ext}"
        folder = f"{tramite}_{solicitud_id}"
        base_path = os.getenv("RUTASERVER", os.getenv("IMG_RUTASERVER", "/tmp"))
        base_url = os.getenv("PREFIJO", os.getenv("IMG_PREFIX", "http://localhost/"))
        destino = Path(base_path) / "pia" / day / "notificaciones" / folder
        destino.mkdir(parents=True, exist_ok=True)
        ruta_final = destino / unique
        with open(ruta_final, "wb") as f:
            f.write(content)
        rel = f"pia/{day}/notificaciones/{folder}/{unique}"
        url = base_url.rstrip("/") + "/" + rel
        na = self.repository.insert_imagen_temporal(
            tramite=tramite,
            id_solicitud=solicitud_id,
            id_prestacion=prestacion,
            path=url,
            nombre_real=nombre_archivo,
        )
        self.state_machine.register_event(
            "not_documento",
            str(na),
            "adicionar_img_caso",
            {
                "usuario": usuario,
                "tramite": tramite,
                "solicitud_id": solicitud_id,
                "prestacion": prestacion,
                "archivo": nombre_archivo,
            },
        )
        return {
            "ok": True,
            "status": "OK",
            "na": na,
            "path": url,
            "nombre_real": nombre_archivo,
            "archivo": unique,
            "msg": "Archivo Cargado Correctamente",
        }

    def obtener_estado_bloqueo(self) -> dict:
        # Fallback en memoria para ambientes que no tienen auxilios.not_bloqueo.
        source = "db"
        try:
            row = self.repository.get_bloqueo_ultimo_registro()
        except SQLAlchemyError:
            row = self._bloqueo_fallback
            source = "fallback_memory"

        row = row or {}
        estado = row.get("estado")
        estado_label = ""
        if estado == 0:
            estado_label = "Inactivo"
        elif estado == 1:
            estado_label = "Activo"

        return {
            "ok": True,
            "source": source,
            "item": {
                "na": row.get("na"),
                "estado": estado,
                "estado_label": estado_label,
                "usuario": row.get("usuario", ""),
                "fecha_bloqueo": row.get("fecha_bloqueo"),
            },
        }

    def crear_estado_bloqueo(self, estado: int, usuario: str) -> dict:
        source = "db"
        try:
            row = self.repository.create_bloqueo_registro(estado=estado, usuario=usuario)
        except SQLAlchemyError:
            source = "fallback_memory"
            row = {
                "na": 1 if not self._bloqueo_fallback else int(self._bloqueo_fallback.get("na") or 0) + 1,
                "estado": estado,
                "usuario": usuario,
                "fecha_bloqueo": datetime.now().isoformat(sep=" ", timespec="seconds"),
            }
            self._bloqueo_fallback = row

        self.state_machine.register_event(
            "not_bloqueo",
            str(row.get("na") or "0"),
            "crear_estado",
            {"estado": estado, "usuario": usuario, "source": source},
        )
        return {
            "ok": True,
            "source": source,
            "mensaje": "El registro se creo correctamente.",
            "item": row,
        }
