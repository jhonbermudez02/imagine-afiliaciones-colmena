from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.db import get_engine
from app.repositories.notificaciones_repository import NotificacionesRepository
from app.schemas.notificaciones import (
    ActualizarCategoriaIn,
    ActualizarCategoriaNewIn,
    BloqueoCreateIn,
    CambiarEstadoNotIn,
    ConsultarImagenesIn,
    ConsultarAfiliadoIn,
    EliminarImagenExistenteIn,
    FinalizarTramiteIn,
    GuardarPostEstadoIn,
    GuardarPostGestionIn,
    NotificarSolicitudIn,
    RechazarTramiteIn,
    TraerImagenesValidarIn,
    TraerGestionPostPrestacionIn,
    ValidarImagenIn,
    ValidarTramiteIn,
)
from app.services.notificaciones_service import NotificacionesService
from app.services.state_machine import StateMachineService

router = APIRouter()
engine = get_engine()
state_machine = StateMachineService(engine)
repository = NotificacionesRepository(engine)
service = NotificacionesService(repository, state_machine)
logger = logging.getLogger(__name__)

LEGACY_OPC_SOPORTADOS = {
    "consultaAfil",
    "notificarIns",
    "validarTramite",
    "rechazarTramite",
    "finalizarTramite",
    "guardarPostEstado",
    "guardarPostGestion",
    "traerGestionPostPrestacion",
    "verReclamantes",
    "cargaReclamantes",
    "traerImagenesAValidar",
    "validarImagen",
    "consultarImagenes",
    "eliminarImagenExistente",
    "actualizarCategoria",
    "actualizarCategoriaNew",
    "modEstado",
    "eliminarImagenExistenteNew",
    "elimImgNoIndex",
    "mostrarDocumentos",
    "mostrarDocumentosNew",
    "indexaImagenes",
    "indexaImagenesNew",
    "asignallamada",
    "cargaDocumentosCaso",
    "cargaPlugInImages",
    "execValCloseImgNot",
    "AdicionarImgCaso",
    "bloqueoEstado",
    "bloqueoCreate",
}


def _req_str(payload: dict, *keys: str) -> str:
    for key in keys:
        if key in payload and str(payload.get(key, "")).strip():
            return str(payload[key]).strip()
    raise HTTPException(status_code=400, detail=f"Campo requerido faltante: {'/'.join(keys)}")


def _req_int(payload: dict, *keys: str) -> int:
    raw = _req_str(payload, *keys)
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Campo entero invalido: {'/'.join(keys)}") from exc
    return value


def _opt_int(payload: dict, *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in payload and str(payload.get(key, "")).strip():
            try:
                return int(str(payload[key]).strip())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Campo entero invalido: {key}") from exc
    return default


def _req_bool(payload: dict, *keys: str) -> bool:
    raw = _req_str(payload, *keys).lower()
    if raw in {"1", "true", "t", "si", "s", "yes", "y"}:
        return True
    if raw in {"0", "false", "f", "no", "n"}:
        return False
    raise HTTPException(status_code=400, detail=f"Campo booleano invalido: {'/'.join(keys)}")


@router.post("/afiliado/consultar")
def consultar_afiliado(payload: ConsultarAfiliadoIn) -> dict:
    return service.consultar_afiliado(
        tipo_id=payload.tipo_id,
        identificacion=payload.id,
        tipo_solicitud=payload.tipo_solicitud,
    )


@router.post("/solicitudes/notificar")
def notificar_solicitud(payload: NotificarSolicitudIn) -> dict:
    return service.notificar_solicitud(payload.model_dump())


@router.post("/solicitudes/{solicitud_id}/documentos/validar")
def validar_tramite(solicitud_id: int, payload: ValidarTramiteIn) -> dict:
    return service.validar_tramite(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        id_prestacion=payload.id_prestacion,
        usuario=payload.usuario,
    )


@router.post("/solicitudes/{solicitud_id}/documentos/rechazar")
def rechazar_tramite(solicitud_id: int, payload: RechazarTramiteIn) -> dict:
    return service.rechazar_tramite(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        id_prestacion=payload.id_prestacion,
        razon_rechazo=payload.razon_rechazo,
        usuario=payload.usuario,
    )


@router.post("/solicitudes/{solicitud_id}/estado")
def cambiar_estado_notificacion(solicitud_id: int, payload: CambiarEstadoNotIn) -> dict:
    return service.cambiar_estado_solicitud(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        usuario=payload.usuario,
        new_estado=payload.new_estado,
    )


@router.post("/solicitudes/{solicitud_id}/finalizar")
def finalizar_tramite(solicitud_id: int, payload: FinalizarTramiteIn) -> dict:
    return service.finalizar_tramite(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        usuario=payload.usuario,
    )


@router.post("/solicitudes/{solicitud_id}/post-estados")
def guardar_post_estado(solicitud_id: int, payload: GuardarPostEstadoIn) -> dict:
    return service.guardar_post_estado(
        solicitud_id=solicitud_id,
        id_estado_post=payload.id_estado_post,
        marca=payload.marca,
        usuario=payload.usuario,
    )


@router.post("/solicitudes/{solicitud_id}/post-gestiones")
def guardar_post_gestion(solicitud_id: int, payload: GuardarPostGestionIn) -> dict:
    return service.guardar_post_gestion(
        solicitud_id=solicitud_id,
        tipo_gestion=payload.tipo_gestion,
        usuario=payload.usuario,
        observacion_g=payload.observacion_g,
    )


@router.get("/solicitudes/{solicitud_id}/reclamantes")
def listar_reclamantes(solicitud_id: int, tramite: Optional[str] = None) -> dict:
    return service.listar_reclamantes(solicitud_id=solicitud_id, tramite=tramite)


@router.post("/solicitudes/{solicitud_id}/imagenes/validar/lista")
def traer_imagenes_a_validar(solicitud_id: int, payload: TraerImagenesValidarIn) -> dict:
    return service.traer_imagenes_a_validar(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        id_prestacion=payload.id_prestacion,
        tipo_solicitud=payload.tipo_solicitud,
    )


@router.post("/solicitudes/{solicitud_id}/imagenes/marca")
def validar_imagen(solicitud_id: int, payload: ValidarImagenIn) -> dict:
    return service.validar_imagen(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        pn=payload.pn,
        ax=payload.ax,
        valor=payload.valor,
    )


@router.post("/solicitudes/{solicitud_id}/imagenes/consulta")
def consultar_imagenes(solicitud_id: int, payload: ConsultarImagenesIn) -> dict:
    return service.consultar_imagenes(
        solicitud_id=solicitud_id,
        tramite=payload.tramite,
        id_prestacion=payload.id_prestacion,
        tipo_solicitud=payload.tipo_solicitud,
    )


@router.post("/imagenes/eliminar-existente")
def eliminar_imagen_existente(payload: EliminarImagenExistenteIn) -> dict:
    return service.eliminar_imagen_existente(payload.pn)


@router.post("/imagenes/categoria")
def actualizar_categoria(payload: ActualizarCategoriaIn) -> dict:
    return service.actualizar_categoria(pn=payload.pn, val=payload.val)


@router.post("/imagenes/categoria/new")
def actualizar_categoria_new(payload: ActualizarCategoriaNewIn) -> dict:
    return service.actualizar_categoria_new(key=payload.pn, val=payload.val, indexado=payload.indexado)


@router.post("/solicitudes/{solicitud_id}/post-gestiones/contexto")
def traer_gestion_post_prestacion(solicitud_id: int, payload: TraerGestionPostPrestacionIn) -> dict:
    return service.traer_gestion_post_prestacion(
        solicitud_id=solicitud_id,
        tipo_gestion=payload.tipo_gestion,
        usuario=payload.usuario,
    )


@router.get("/catalogos/post-estados")
def listar_post_estados_activos() -> dict:
    return service.listar_post_estados_activos()


@router.get("/auditoria")
def listar_auditoria(solicitud_id: int, limit: int = 100) -> dict:
    safe_limit = max(1, min(limit, 500))
    return service.listar_auditoria(solicitud_id=solicitud_id, limit=safe_limit)


@router.get("/bloqueo/estado")
def obtener_estado_bloqueo() -> dict:
    return service.obtener_estado_bloqueo()


@router.post("/bloqueo/estado")
def crear_estado_bloqueo(payload: BloqueoCreateIn) -> dict:
    return service.crear_estado_bloqueo(estado=payload.estado, usuario=payload.usuario)


@router.get("/legacy/opc/soportados")
def legacy_opc_soportados() -> dict:
    return {"ok": True, "count": len(LEGACY_OPC_SOPORTADOS), "items": sorted(LEGACY_OPC_SOPORTADOS)}


def _legacy_opc_dispatch_impl(payload: dict) -> dict:
    opc = str(payload.get("opc", "")).strip()
    if not opc:
        raise HTTPException(status_code=400, detail="Campo 'opc' es obligatorio.")

    # Compatibilidad con legacy notificaciones/funciones.php
    if opc == "consultaAfil":
        return service.consultar_afiliado(
            tipo_id=_req_str(payload, "ti", "tipo_id"),
            identificacion=_req_str(payload, "cc", "id"),
            tipo_solicitud=_req_str(payload, "ts", "tipo_solicitud"),
        )
    if opc == "notificarIns":
        if "beneficiarios" not in payload:
            raise HTTPException(
                status_code=400,
                detail=(
                    "notificarIns en Python requiere payload normalizado "
                    "(tramite/tipo_solicitud/.../beneficiarios)."
                ),
            )
        return service.notificar_solicitud(payload)
    if opc == "validarTramite":
        return service.validar_tramite(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "id_prestacion"),
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc == "rechazarTramite":
        return service.rechazar_tramite(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "id_prestacion"),
            razon_rechazo=_req_str(payload, "razon_rechazo"),
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc == "finalizarTramite":
        return service.finalizar_tramite(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc == "guardarPostEstado":
        return service.guardar_post_estado(
            solicitud_id=_req_int(payload, "solicitud_id"),
            id_estado_post=_req_int(payload, "id_estado_post"),
            marca=_req_bool(payload, "marca"),
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc == "guardarPostGestion":
        return service.guardar_post_gestion(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tipo_gestion=_req_int(payload, "tipo_gestion"),
            usuario=_req_str(payload, "user", "usuario"),
            observacion_g=_req_str(payload, "observacion_g"),
        )
    if opc == "traerGestionPostPrestacion":
        return service.traer_gestion_post_prestacion(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tipo_gestion=_req_int(payload, "tipo_gestion"),
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc in {"verReclamantes", "cargaReclamantes"}:
        tramite = payload.get("tramite")
        return service.listar_reclamantes(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=str(tramite) if tramite is not None else None,
        )
    if opc == "traerImagenesAValidar":
        return service.traer_imagenes_a_validar(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "id_prestacion"),
            tipo_solicitud=_req_str(payload, "tipo_solicitud"),
        )
    if opc == "validarImagen":
        return service.validar_imagen(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            pn=_req_int(payload, "pn"),
            ax=_req_str(payload, "ax"),
            valor=_opt_int(payload, "valor", default=0),
        )
    if opc == "consultarImagenes":
        return service.consultar_imagenes(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "id_prestacion"),
            tipo_solicitud=_req_str(payload, "tipo_solicitud"),
        )
    if opc == "eliminarImagenExistente":
        return service.eliminar_imagen_existente(_req_int(payload, "pn"))
    if opc in {"eliminarImagenExistenteNew", "elimImgNoIndex"}:
        return service.eliminar_imagen_existente(_req_int(payload, "pn", "key"))
    if opc == "actualizarCategoria":
        return service.actualizar_categoria(
            pn=_req_int(payload, "pn"),
            val=_req_int(payload, "val"),
        )
    if opc == "actualizarCategoriaNew":
        return service.actualizar_categoria_new(
            key=_req_str(payload, "pn"),
            val=_req_str(payload, "val"),
            indexado=_req_str(payload, "indexado"),
        )
    if opc in {"indexaImagenes", "indexaImagenesNew"}:
        if payload.get("indexado") is not None:
            return service.actualizar_categoria_new(
                key=_req_str(payload, "pn", "key"),
                val=_req_str(payload, "val"),
                indexado=_req_str(payload, "indexado"),
            )
        return service.actualizar_categoria(
            pn=_req_int(payload, "pn"),
            val=_req_int(payload, "val"),
        )
    if opc in {"mostrarDocumentos", "mostrarDocumentosNew"}:
        return service.consultar_imagenes(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "id_prestacion"),
            tipo_solicitud=_req_str(payload, "tipo_solicitud"),
        )
    if opc == "asignallamada":
        return {
            "ok": True,
            "opc": opc,
            "tramite": _req_str(payload, "tramite"),
            "usuario": _req_str(payload, "usuario", "user"),
            "ui": {"accion": "llamada", "modulo": "notificaciones"},
        }
    if opc in {"cargaDocumentosCaso", "cargaPlugInImages"}:
        return service.consultar_imagenes(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            id_prestacion=_req_int(payload, "prestacion", "id_prestacion"),
            tipo_solicitud=_req_str(payload, "tiposol", "tipo_solicitud"),
        )
    if opc == "execValCloseImgNot":
        return service.cambiar_estado_solicitud(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "user", "usuario"),
            new_estado="Pendiente Validacion",
        )
    if opc == "AdicionarImgCaso":
        import base64

        nombre_archivo = _req_str(payload, "nombre_archivo")
        archivo_base64 = _req_str(payload, "archivo_base64")
        try:
            content = base64.b64decode(archivo_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="archivo_base64 invalido") from exc
        return service.adicionar_img_caso(
            tramite=_req_str(payload, "tramite"),
            solicitud_id=_req_int(payload, "solicitud_id"),
            prestacion=_req_int(payload, "prestacion", "id_prestacion"),
            nombre_archivo=nombre_archivo,
            content=content,
            usuario=_req_str(payload, "user", "usuario"),
        )
    if opc == "modEstado":
        return service.cambiar_estado_solicitud(
            solicitud_id=_req_int(payload, "solicitud_id"),
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "user", "usuario"),
            new_estado=_req_str(payload, "new_estado", "estado"),
        )
    if opc == "bloqueoEstado":
        return service.obtener_estado_bloqueo()
    if opc == "bloqueoCreate":
        return service.crear_estado_bloqueo(
            estado=_req_int(payload, "estado"),
            usuario=_req_str(payload, "user", "usuario"),
        )

    raise HTTPException(status_code=501, detail=f"OPC legacy no implementado: {opc}")


@router.post("/legacy/opc")
def legacy_opc_dispatch(payload: dict) -> dict:
    try:
        return _legacy_opc_dispatch_impl(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("legacy_opc_notificaciones_error opc=%s error=%s", payload.get("opc"), exc)
        return {
            "ok": False,
            "status": "Error",
            "opc": str(payload.get("opc", "")),
            "msg": "Error interno controlado en adapter legacy",
            "detail": str(exc.__class__.__name__),
        }


@router.post("/legacy/adicionarimgcaso")
async def adicionar_img_caso(
    file: UploadFile = File(...),
    tramite: str = Form(...),
    solicitud_id: int = Form(...),
    prestacion: int = Form(...),
    usuario: str = Form(...),
) -> dict:
    content = await file.read()
    return service.adicionar_img_caso(
        tramite=tramite,
        solicitud_id=solicitud_id,
        prestacion=prestacion,
        nombre_archivo=file.filename or "archivo.bin",
        content=content,
        usuario=usuario,
    )
