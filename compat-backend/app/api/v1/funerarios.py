from __future__ import annotations
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.db import get_engine
from app.repositories.funerarios_repository import FunerariosRepository
from app.schemas.funerarios import (
    AsignarSolicitudIn,
    CambiarEstadoIn,
    GuardarPagosReclamantesIn,
)
from app.services.funerarios_service import FunerariosService
from app.services.state_machine import StateMachineService

router = APIRouter()
engine = get_engine()
state_machine = StateMachineService(engine)
repository = FunerariosRepository(engine)
service = FunerariosService(repository, state_machine)
logger = logging.getLogger(__name__)

LEGACY_OPC_SOPORTADOS = {
    "asignar",
    "modEstado",
    "modEstadoAdm",
    "buscaReclamantes",
    "cargaReclamantes",
    "guardaBen",
    "actualizaDatosPago",
    "listarValores",
    "tipo_cuenta",
    "listarBancos",
    "muestraDatosPago",
    "muestraDatosPagoAjustar",
    "muestraDatosPagoFid",
    "muestraDatosPagoAsu",
    "muestraDatosPagoRech",
    "actualizaReclamante",
    "verificaReclamante",
    "modificaReclamante",
    "eliminatramite",
    "modificatramite",
    "cierraPensionado",
    "cierraFiducia",
    "cierraAsulado",
    "cierraOrigenFondos",
    "rechazaDatosPago",
    "rechazaDatosPagoAsu",
    "rechazaDatosPagoFid",
    "marcaAprPagos",
    "marcaDev",
    "marcaLla",
    "finaliza",
    "finalizaPen",
    "gestionaBen",
    "guardaExe",
    "gestionaRec",
    "guardaGesCheque",
    "guardaGesTrans",
    "guardarBanco",
    "actualizarBanco",
    "cargaPagosAuf",
    "cargaPagosAufFid",
    "cargaPagosAufAsu",
    "cargaPagosAufPen",
    "pantallaR",
    "validaTrans",
    "actRechazo",
    "editaReclamante",
    "informarCheque",
    "guardaRechazo",
    "cargaModalBancos",
    "reporte",
    "estadistico",
    "pagosFunerariosDetalle",
    "pagosFunerariosDetalleMes",
    "bancos",
    "gestionar",
    "guardarRespuesta",
    "rechManualOptima",
    "finoficinacheque",
    "50 Semanas y Accidente de Trabajo",
    "50 Semanas y Fidelidad",
    "Accidente de Trabajo",
    "Afiliado a Otro Regimen",
    "Fidelidad Menor a 20 A&ntilde;os",
    "No Cotizante 26 Semanas",
    "Pendiente Origen de Muerte",
    "Preexequial",
    "Reclamante No Procede",
    "adjuntar",
    "cargarRes",
    "carguetxtbanco",
    "cierreMasivo",
    "cierreMasivoAsulado",
    "clasificaImg",
    "cppOptimaMasivo",
    "crearTerceros",
    "enviaContabilizacion",
    "enviaContabilizacionAsulado",
    "enviaContabilizacionOptima",
    "guardarAvanceTercero",
    "reversionMasivo",
    "sincronizar",
    "CargarExcelMasivo",
    "CargarExcelMasivoAsulado",
}


def _req_str(payload: dict, *keys: str) -> str:
    for key in keys:
        if key in payload and str(payload.get(key, "")).strip():
            return str(payload[key]).strip()
    raise HTTPException(status_code=400, detail=f"Campo requerido faltante: {'/'.join(keys)}")


def _opt_int(payload: dict, *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in payload and str(payload.get(key, "")).strip():
            try:
                return int(str(payload[key]).strip())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Campo entero invalido: {key}") from exc
    return default


def _req_int(payload: dict, *keys: str) -> int:
    raw = _req_str(payload, *keys)
    try:
        return int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Campo entero invalido: {'/'.join(keys)}") from exc


def _parse_tramites(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    cleaned = raw.strip().rstrip(",")
    if not cleaned:
        return []
    parts = [p.strip().strip("'").strip('"') for p in cleaned.split(",")]
    return [p for p in parts if p]


@router.post("/solicitudes/{tramite}/asignar")
def asignar_solicitud(tramite: str, payload: AsignarSolicitudIn) -> dict:
    return service.asignar_solicitud(tramite, payload.usuario)


@router.post("/solicitudes/{tramite}/estado")
def cambiar_estado_solicitud(tramite: str, payload: CambiarEstadoIn) -> dict:
    return service.cambiar_estado_solicitud(
        tramite,
        usuario=payload.usuario,
        new_estado=payload.new_estado,
        estado_actual=payload.estado_actual,
    )


@router.get("/solicitudes/{tramite}/reclamantes")
def listar_reclamantes(tramite: str) -> dict:
    return service.listar_reclamantes(tramite)


@router.post("/solicitudes/{tramite}/reclamantes/pagos")
def guardar_pagos_reclamantes(tramite: str, payload: GuardarPagosReclamantesIn) -> dict:
    return service.guardar_pagos_reclamantes(
        tramite,
        usuario=payload.usuario,
        items=[i.model_dump() for i in payload.items],
    )


@router.get("/auditoria")
def listar_auditoria(tramite: str, limit: int = 100) -> dict:
    safe_limit = max(1, min(limit, 500))
    return service.listar_auditoria(tramite=tramite, limit=safe_limit)


@router.get("/legacy/opc/soportados")
def legacy_opc_soportados() -> dict:
    return {"ok": True, "count": len(LEGACY_OPC_SOPORTADOS), "items": sorted(LEGACY_OPC_SOPORTADOS)}


def _legacy_opc_dispatch_impl(payload: dict) -> dict:
    opc = str(payload.get("opc", "")).strip()
    if not opc:
        raise HTTPException(status_code=400, detail="Campo 'opc' es obligatorio.")

    # Compatibilidad con legacy funerarios/funciones.php (subset migrado)
    if opc == "asignar":
        return service.asignar_solicitud(
            _req_str(payload, "tramite"),
            _req_str(payload, "usuario", "user"),
        )
    if opc in {"modEstado", "modEstadoAdm"}:
        return service.cambiar_estado_solicitud(
            _req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
            new_estado=_req_str(payload, "new_estado", "estado"),
            estado_actual=str(payload.get("estado_actual")) if payload.get("estado_actual") is not None else None,
        )
    if opc in {"buscaReclamantes", "cargaReclamantes"}:
        return service.listar_reclamantes(_req_str(payload, "tramite"))
    if opc in {"guardaBen", "actualizaDatosPago"}:
        items = payload.get("items")
        if not isinstance(items, list):
            raise HTTPException(
                status_code=400,
                detail="guardaBen en Python requiere payload normalizado con lista 'items'.",
            )
        return service.guardar_pagos_reclamantes(
            _req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
            items=items,
        )
    if opc == "listarValores":
        return service.listar_valores(_req_str(payload, "tipo"))
    if opc == "tipo_cuenta":
        return service.listar_valores("tipo_cuenta")
    if opc == "listarBancos":
        return service.listar_bancos(
            page=_opt_int(payload, "page", default=1),
            rp=_opt_int(payload, "rp", default=10),
            sortname=str(payload.get("sortname", "id")),
            sortorder=str(payload.get("sortorder", "ASC")),
            query=str(payload.get("query")).strip() if payload.get("query") is not None else None,
            qtype=str(payload.get("qtype")).strip() if payload.get("qtype") is not None else None,
        )
    if opc in {
        "muestraDatosPago",
        "muestraDatosPagoAjustar",
        "muestraDatosPagoFid",
        "muestraDatosPagoAsu",
        "muestraDatosPagoRech",
    }:
        return service.mostrar_datos_pago(
            tramite=str(payload.get("tramite")).strip() if payload.get("tramite") is not None else None,
            ccreclamante=(
                str(payload.get("ccreclamante")).strip() if payload.get("ccreclamante") is not None else None
            ),
            idben=str(payload.get("idben")).strip() if payload.get("idben") is not None else None,
            opc=opc,
        )
    if opc == "actualizaReclamante":
        return service.actualizar_reclamante(
            id_ben=_req_str(payload, "idBen", "id_ben"),
            tipoid=_req_str(payload, "tipoid"),
            cedula=_req_str(payload, "cedula"),
            nombre=_req_str(payload, "nombre"),
            telefono=_req_str(payload, "telefono"),
            direccion=_req_str(payload, "direccion"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "verificaReclamante":
        return service.verificar_reclamante(_req_str(payload, "identificacion"))
    if opc == "modificaReclamante":
        return service.modificar_reclamante(
            tramite=_req_str(payload, "tramite"),
            id_ben=_req_str(payload, "id_ben", "id_benef", "idBen", "id_ben_reclamante"),
            identificacion=_req_str(payload, "identificacion"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "eliminatramite":
        return service.eliminar_tramite(
            tramite=_req_str(payload, "tramite"),
            accion=_opt_int(payload, "accion", default=1),
        )
    if opc == "modificatramite":
        return service.modificar_tramite(
            tramite=_req_str(payload, "tramite"),
            accion=_opt_int(payload, "accion", default=1),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc in {"cierraPensionado", "cierraFiducia", "cierraAsulado", "cierraOrigenFondos"}:
        return service.cerrar_tramite_origen(
            opc=opc,
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "ccben", "idrecla", "identificacion"),
            estado=_req_str(payload, "estado"),
            observacion=str(payload.get("obs", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc in {"rechazaDatosPago", "rechazaDatosPagoAsu", "rechazaDatosPagoFid"}:
        return service.rechazar_datos_pago(
            opc=opc,
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "idrecla", "ccben", "identificacion"),
            observacion=_req_str(payload, "obsrechazo"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "marcaAprPagos":
        tramites = _parse_tramites(str(payload.get("tramite", "")))
        if not tramites:
            raise HTTPException(status_code=400, detail="Campo 'tramite' no contiene tramites validos para marcaAprPagos.")
        return service.marcar_aprueba_pagos(
            tramites=tramites,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "marcaDev":
        return service.marcar_devuelto(
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "marcaLla":
        info_raw = payload.get("info")
        info = info_raw if isinstance(info_raw, list) else []
        return service.marcar_llamar_funeraria(
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
            info=[str(x) for x in info],
        )
    if opc == "finaliza":
        return service.finalizar_reclamante_aseguradora(
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "recla", "ccben", "idrecla", "identificacion"),
            estado=_req_str(payload, "estado"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "finalizaPen":
        return service.finalizar_reclamante_pensionado(
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "recla", "ccben", "idrecla", "identificacion"),
            estado=_req_str(payload, "estado"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "gestionaBen":
        return service.gestionar_beneficiario(
            tramite=_req_str(payload, "tramite"),
            beneficiario=_req_str(payload, "bene", "idben", "id_ben"),
            usuario=_req_str(payload, "usuario", "user"),
            estado=_req_str(payload, "estado"),
            contacto=str(payload.get("contacto", "")),
            observacion=str(payload.get("obs", "")),
            reclama=str(payload.get("reclama", "")),
            poder=str(payload.get("poder", "")),
            pagado_por=str(payload.get("pagadopor", "")),
            plan_exequial=str(payload.get("plexe", "")),
            numero_plan=str(payload.get("numplan", "")),
            titular_fallecido=str(payload.get("titfall", "")),
            nombre_funeraria=str(payload.get("nomfune", "")),
        )
    if opc == "guardaExe":
        return service.guardar_exequial(
            tramite=_req_str(payload, "tramite"),
            plan_exequial=str(payload.get("planexe", "")),
            numero_plan=str(payload.get("numplan", "")),
            titular_fallecido=str(payload.get("titular", "")),
            nombre_funeraria=str(payload.get("nomfune", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "gestionaRec":
        return service.gestionar_reclamante(
            tramite=_req_str(payload, "tramite"),
            id_ben=_req_str(payload, "idben", "id_ben"),
            estado=_req_str(payload, "estado"),
            usuario=_req_str(payload, "usuario", "user"),
            observacion=str(payload.get("obs", "")),
        )
    if opc == "guardaGesCheque":
        return service.guardar_gestion_cheque(
            tramite=_req_str(payload, "tramite"),
            id_ben=_req_str(payload, "llave", "idben", "id_ben"),
            estado=_req_str(payload, "estado"),
            observacion=str(payload.get("obs", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "guardaGesTrans":
        return service.guardar_gestion_transferencia(
            tramite=_req_str(payload, "tramite"),
            id_ben=_req_str(payload, "llave", "idben", "id_ben"),
            estado=_req_str(payload, "estado"),
            observacion=str(payload.get("obs", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "guardarBanco":
        return service.guardar_banco(
            codigo=_req_str(payload, "codigo"),
            banco=_req_str(payload, "banco"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "actualizarBanco":
        return service.actualizar_banco(
            codigo=_req_str(payload, "cod", "codigo"),
            banco=_req_str(payload, "banco"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc in {"cargaPagosAuf", "cargaPagosAufFid", "cargaPagosAufAsu", "cargaPagosAufPen", "pantallaR", "validaTrans"}:
        return service.mostrar_datos_pago(
            tramite=str(payload.get("tramite", payload.get("caso", ""))).strip() or None,
            ccreclamante=str(payload.get("idrecl", payload.get("ccreclamante", ""))).strip() or None,
            idben=str(payload.get("idben", payload.get("llave", ""))).strip() or None,
            opc=opc,
        )
    if opc == "informarCheque":
        return service.mostrar_datos_pago(
            tramite=str(payload.get("tramite", "")).strip() or None,
            ccreclamante=str(payload.get("ccben", payload.get("idrecl", ""))).strip() or None,
            idben=str(payload.get("idben", payload.get("llave", ""))).strip() or None,
            opc=opc,
        )
    if opc == "actRechazo":
        return service.actualizar_rechazo_pago(
            id_ben=_req_str(payload, "idben"),
            id_pago=_req_str(payload, "idpago"),
            nrocuenta=_req_str(payload, "nrocuenta"),
            nrocuentaold=str(payload.get("nrocuentaold", "")),
            banco=_req_str(payload, "banco"),
            bancoold=str(payload.get("bancoold", "")),
            tipocta=_req_str(payload, "tipocta"),
            tipoctaold=str(payload.get("tipoctaold", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "editaReclamante":
        return service.editar_reclamante(
            id_ben=_req_str(payload, "id"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "guardaRechazo":
        return service.guardar_rechazo(
            tramite=_req_str(payload, "tramite"),
            semanas=str(payload.get("semanas", "")),
            fidelidad=str(payload.get("fidelidad", "")),
            fecha_muerte=str(payload.get("fmuerte", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "cargaModalBancos":
        return service.cargar_modal_bancos(
            operacion=str(payload.get("operacion", "")),
            codigo=str(payload.get("cod", payload.get("codigo", ""))).strip() or None,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "reporte":
        return service.reporte_pagos(
            year=_req_int(payload, "date", "year"),
            entidad=str(payload.get("entidad", "")).strip() or None,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "estadistico":
        return service.estadistico_pagos(
            year=_req_int(payload, "date", "year"),
            entidad=str(payload.get("entidad", "")).strip() or None,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "pagosFunerariosDetalle":
        return service.detalle_pagos_mes(
            year=_req_int(payload, "date", "year"),
            month_label=_req_str(payload, "category"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "pagosFunerariosDetalleMes":
        return service.detalle_diario_entidad(
            year=_req_int(payload, "year"),
            month=_req_str(payload, "month"),
            entidad=_req_str(payload, "entity", "entidad"),
            mes_label=str(payload.get("mes", "")),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "bancos":
        return service.listar_valores("bancos")
    if opc == "gestionar":
        return service.gestionar_origen_fondos(
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "guardarRespuesta":
        return service.guardar_respuesta_origen_fondos(
            tramite=_req_str(payload, "tramite"),
            id_reclamante=_req_str(payload, "id_reclamante", "llave", "idben", "id_ben"),
            id_respuesta=_req_str(payload, "id_respuesta", "estado"),
            observacion=str(payload.get("observacion_respuesta", payload.get("obs", payload.get("observacion", "")))),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "rechManualOptima":
        return service.rechazo_manual_optima(
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "idrecl", "ccben", "identificacion"),
            causal=_req_str(payload, "causal"),
            origen=_req_str(payload, "origen"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "finoficinacheque":
        return service.finalizar_oficina_cheque(
            tramite=_req_str(payload, "tramite"),
            identificacion=_req_str(payload, "ccben", "idrecl", "identificacion"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "carguetxtbanco":
        nombre_archivo = _req_str(payload, "nombre_archivo")
        archivo_texto = _req_str(payload, "archivo_texto")
        return service.cargar_txt_banco(
            nombre_archivo=nombre_archivo,
            lineas=archivo_texto.splitlines(),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "cierreMasivo":
        return service.cierre_masivo_operador(
            usuario=_req_str(payload, "usuario", "user"),
            asulado=False,
        )
    if opc == "cierreMasivoAsulado":
        return service.cierre_masivo_operador(
            usuario=_req_str(payload, "usuario", "user"),
            asulado=True,
        )
    if opc == "CargarExcelMasivo":
        nombre_archivo = _req_str(payload, "nombre_archivo")
        archivo_base64 = _req_str(payload, "archivo_base64")
        import base64

        try:
            content = base64.b64decode(archivo_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="archivo_base64 invalido") from exc
        return service.cargar_excel_masivo(
            nombre_archivo=nombre_archivo,
            content=content,
            usuario=_req_str(payload, "usuario", "user"),
            asulado=False,
        )
    if opc == "CargarExcelMasivoAsulado":
        nombre_archivo = _req_str(payload, "nombre_archivo")
        archivo_base64 = _req_str(payload, "archivo_base64")
        import base64

        try:
            content = base64.b64decode(archivo_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="archivo_base64 invalido") from exc
        return service.cargar_excel_masivo(
            nombre_archivo=nombre_archivo,
            content=content,
            usuario=_req_str(payload, "usuario", "user"),
            asulado=True,
        )
    if opc == "cppOptimaMasivo":
        raw = payload.get("tramites")
        tramites: list[str]
        if isinstance(raw, list):
            tramites = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str):
            tramites = _parse_tramites(raw)
        else:
            tramites = []
        return service.cpp_optima_masivo(
            tramites=tramites,
            sw_origen=_req_str(payload, "swOrigen", "sworigen"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "reversionMasivo":
        raw = payload.get("tramites")
        id_benes: list[str]
        if isinstance(raw, list):
            id_benes = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str):
            id_benes = _parse_tramites(raw)
        else:
            id_benes = []
        return service.reversion_masivo(
            id_benes=id_benes,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "enviaContabilizacionOptima":
        return service.envia_contabilizacion_optima(
            tramite=_req_str(payload, "tramite"),
            idrecla=_req_str(payload, "idrecla", "idrecl"),
            usuario=_req_str(payload, "usuario", "user"),
            asulado=False,
        )
    if opc == "enviaContabilizacionAsulado":
        return service.envia_contabilizacion_optima(
            tramite=_req_str(payload, "tramite"),
            idrecla=_req_str(payload, "idrecla", "idrecl"),
            usuario=_req_str(payload, "usuario", "user"),
            asulado=True,
        )
    if opc == "enviaContabilizacion":
        raw = payload.get("tramites")
        tramites: list[str]
        if isinstance(raw, list):
            tramites = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str):
            tramites = _parse_tramites(raw)
        else:
            tramites = []
        return service.envia_contabilizacion(
            tramites=tramites,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "sincronizar":
        return service.sincronizar_reclamantes(
            tramite=_req_str(payload, "tramite"),
            cedula=_req_str(payload, "cedula"),
            usuario=_req_str(payload, "usuario", "user"),
            payload=payload,
        )
    if opc == "guardarAvanceTercero":
        return service.guardar_avance_tercero(
            tramite=_req_str(payload, "tramite"),
            cc=_req_str(payload, "cc"),
            payload=payload,
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "crearTerceros":
        return service.crear_terceros(
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "cargarRes":
        return service.cargar_respuesta_transferencia(
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "adjuntar":
        return service.adjuntar_soportes(
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc == "clasificaImg":
        return service.clasifica_imagenes(
            tramite=_req_str(payload, "tramite"),
            usuario=_req_str(payload, "usuario", "user"),
        )
    if opc in {
        "50 Semanas y Accidente de Trabajo",
        "50 Semanas y Fidelidad",
        "Accidente de Trabajo",
        "Afiliado a Otro Regimen",
        "Fidelidad Menor a 20 A&ntilde;os",
        "No Cotizante 26 Semanas",
        "Pendiente Origen de Muerte",
        "Preexequial",
        "Reclamante No Procede",
    }:
        return service.registrar_causal_rechazo(
            tramite=_req_str(payload, "tramite"),
            causal=opc,
            usuario=_req_str(payload, "usuario", "user"),
        )

    raise HTTPException(status_code=501, detail=f"OPC legacy no implementado: {opc}")


@router.post("/legacy/opc")
def legacy_opc_dispatch(payload: dict) -> dict:
    try:
        return _legacy_opc_dispatch_impl(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("legacy_opc_funerarios_error opc=%s error=%s", payload.get("opc"), exc)
        return {
            "ok": False,
            "status": "Error",
            "opc": str(payload.get("opc", "")),
            "msg": "Error interno controlado en adapter legacy",
            "detail": str(exc.__class__.__name__),
        }


@router.post("/legacy/carguetxtbanco")
async def cargar_txt_banco(archivobanco: UploadFile = File(...), usuario: str = Form(...)) -> dict:
    raw = await archivobanco.read()
    try:
        contenido = raw.decode("utf-8")
    except UnicodeDecodeError:
        contenido = raw.decode("latin-1", errors="ignore")
    return service.cargar_txt_banco(
        nombre_archivo=archivobanco.filename or "sin_nombre.txt",
        lineas=contenido.splitlines(),
        usuario=usuario,
    )


@router.post("/legacy/cargarexcelmasivo")
async def cargar_excel_masivo(file: UploadFile = File(...), usuario: str = Form(...)) -> dict:
    content = await file.read()
    return service.cargar_excel_masivo(
        nombre_archivo=file.filename or "sin_nombre.xlsx",
        content=content,
        usuario=usuario,
        asulado=False,
    )


@router.post("/legacy/cargarexcelmasivoasulado")
async def cargar_excel_masivo_asulado(file: UploadFile = File(...), usuario: str = Form(...)) -> dict:
    content = await file.read()
    return service.cargar_excel_masivo(
        nombre_archivo=file.filename or "sin_nombre.xlsx",
        content=content,
        usuario=usuario,
        asulado=True,
    )
