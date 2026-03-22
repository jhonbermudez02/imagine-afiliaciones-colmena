from __future__ import annotations
import re
import zipfile
import json
import os
import uuid
from datetime import date
from io import BytesIO
from xml.etree import ElementTree as ET

from app.repositories.funerarios_repository import FunerariosRepository
from app.services.state_machine import StateMachineService


class FunerariosService:
    def __init__(self, repository: FunerariosRepository, state_machine: StateMachineService) -> None:
        self.repository = repository
        self.state_machine = state_machine
        self._months_en = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

    @staticmethod
    def _slice(raw: str, start: int, length: int) -> str:
        return (raw[start : start + length] if raw else "").strip()

    @staticmethod
    def _to_int(raw: str) -> int:
        value = (raw or "").strip()
        if not value:
            return 0
        try:
            return int(float(value))
        except ValueError:
            return 0

    @staticmethod
    def _excel_col_to_index(ref: str) -> int:
        col = 0
        for ch in ref:
            if "A" <= ch <= "Z":
                col = col * 26 + (ord(ch) - ord("A") + 1)
        return col

    def _parse_xlsx_rows(self, content: bytes) -> tuple[int, list[list[str]]]:
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        with zipfile.ZipFile(BytesIO(content)) as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root_ss.findall(".//s:si", ns):
                    parts = [t.text or "" for t in si.findall(".//s:t", ns)]
                    shared.append("".join(parts))

            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            first_sheet = workbook.find(".//s:sheets/s:sheet", ns)
            if first_sheet is None:
                return 0, []
            rid = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            target = "worksheets/sheet1.xml"
            for rel in rels.findall(".//r:Relationship", rel_ns):
                if rel.attrib.get("Id") == rid:
                    target = rel.attrib.get("Target", target)
                    break
            sheet_path = f"xl/{target}" if not target.startswith("xl/") else target
            sheet = ET.fromstring(zf.read(sheet_path))

            parsed_rows: list[dict[int, str]] = []
            max_col = 0
            for row in sheet.findall(".//s:sheetData/s:row", ns):
                values: dict[int, str] = {}
                for cell in row.findall("s:c", ns):
                    ref = cell.attrib.get("r", "")
                    col_ref = re.sub(r"[^A-Z]", "", ref)
                    col_idx = self._excel_col_to_index(col_ref)
                    if col_idx <= 0:
                        continue
                    max_col = max(max_col, col_idx)
                    ctype = cell.attrib.get("t", "")
                    value = ""
                    if ctype == "s":
                        node = cell.find("s:v", ns)
                        if node is not None and (node.text or "").strip().isdigit():
                            s_idx = int((node.text or "0").strip())
                            value = shared[s_idx] if 0 <= s_idx < len(shared) else ""
                    elif ctype == "inlineStr":
                        node = cell.find("s:is/s:t", ns)
                        value = (node.text or "") if node is not None else ""
                    else:
                        node = cell.find("s:v", ns)
                        value = (node.text or "") if node is not None else ""
                    values[col_idx] = value.strip()
                parsed_rows.append(values)

            matrix: list[list[str]] = []
            for row in parsed_rows:
                matrix.append([row.get(i, "").strip() for i in range(1, max_col + 1)])
            return max_col, matrix

    def asignar_solicitud(self, tramite: str, usuario: str) -> dict:
        affected = self.repository.assign_solicitud(tramite)
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "asignar",
            {"usuario": usuario, "new_estado": "Asignado", "affected": affected},
        )
        return {"ok": True, "tramite": tramite, "affected": affected}

    def cambiar_estado_solicitud(
        self, tramite: str, usuario: str, new_estado: str, estado_actual: str | None
    ) -> dict:
        affected = self.repository.change_estado_solicitud(tramite, new_estado)
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "cambiar_estado",
            {
                "usuario": usuario,
                "estado_actual": estado_actual,
                "new_estado": new_estado,
                "affected": affected,
            },
        )
        return {"ok": True, "tramite": tramite, "new_estado": new_estado, "affected": affected}

    def listar_reclamantes(self, tramite: str) -> dict:
        items = self.repository.list_reclamantes(tramite)
        return {"tramite": tramite, "items": items, "count": len(items)}

    def guardar_pagos_reclamantes(self, tramite: str, usuario: str, items: list[dict]) -> dict:
        result = self.repository.upsert_pagos_reclamantes(tramite, items)
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "guardar_pagos_reclamantes",
            {"usuario": usuario, **result},
        )
        return {"ok": True, "tramite": tramite, **result}

    def listar_auditoria(self, tramite: str, limit: int) -> dict:
        items = self.repository.list_auditoria(tramite=tramite, limit=limit)
        return {"ok": True, "tramite": tramite, "count": len(items), "items": items}

    def listar_valores(self, tipo: str) -> dict:
        if tipo == "bancos":
            items = self.repository.list_bancos_catalog()
            return {"ok": True, "tipo": tipo, "count": len(items), "items": items}
        if tipo == "tipo_cuenta":
            items = [{"tipo_cuenta": "Ahorros"}, {"tipo_cuenta": "Corriente"}]
            return {"ok": True, "tipo": tipo, "count": len(items), "items": items}
        return {"ok": False, "tipo": tipo, "count": 0, "items": []}

    def listar_bancos(
        self,
        *,
        page: int,
        rp: int,
        sortname: str,
        sortorder: str,
        query: str | None,
        qtype: str | None,
    ) -> dict:
        data = self.repository.list_bancos_grid(
            page=page,
            rp=rp,
            sortname=sortname,
            sortorder=sortorder,
            query=query,
            qtype=qtype,
        )
        return {"ok": True, **data}

    def mostrar_datos_pago(
        self, *, tramite: str | None, ccreclamante: str | None, idben: str | None, opc: str
    ) -> dict:
        item = self.repository.get_pago_reclamante(
            tramite=tramite,
            id_ben=idben,
            identificacion=ccreclamante,
        )
        return {"ok": item is not None, "opc": opc, "item": item}

    def actualizar_reclamante(
        self, *, id_ben: str, tipoid: str, cedula: str, nombre: str, telefono: str, direccion: str, usuario: str
    ) -> dict:
        affected = self.repository.update_reclamante(
            id_ben=id_ben,
            tipoid=tipoid,
            cedula=cedula,
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            id_ben,
            "actualiza_reclamante",
            {"usuario": usuario, "cedula": cedula, "affected": affected},
        )
        return {"ok": affected > 0, "affected": affected}

    def verificar_reclamante(self, identificacion: str) -> dict:
        exists = self.repository.count_reclamante_exists(identificacion)
        if exists == 0:
            return {"ok": False, "exists": False, "can_delete": False, "message": "El reclamante ingresado no existe."}
        mod_count = self.repository.count_reclamante_modificable(identificacion)
        if mod_count > 0:
            return {"ok": True, "exists": True, "can_delete": True, "message": "Reclamante elegible para eliminar."}
        return {"ok": False, "exists": True, "can_delete": False, "message": "El reclamante ingresado no se puede eliminar."}

    def modificar_reclamante(self, *, tramite: str, id_ben: str, identificacion: str, usuario: str) -> dict:
        affected = self.repository.mark_reclamante_eliminado(id_ben=id_ben)
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "modifica_reclamante",
            {"usuario": usuario, "id_ben": id_ben, "identificacion": identificacion, "affected": affected},
        )
        return {"ok": affected > 0, "affected": affected}

    def eliminar_tramite(self, *, tramite: str, accion: int) -> dict:
        estado = self.repository.get_tramite_estado(tramite)
        if estado is None:
            return {"ok": False, "can_execute": False, "message": "El tramite ingresado no existe"}
        if estado in {"APROBADO", "Aprobado"}:
            return {
                "ok": False,
                "can_execute": False,
                "message": "El tramite ingresado no se puede procesar, puesto que ya fue aprobado.",
            }
        if estado == "Eliminado":
            return {"ok": False, "can_execute": False, "message": "El tramite ingresado fue eliminado."}
        tramitados = self.repository.count_reclamantes_tramitados(tramite)
        if tramitados > 0:
            return {
                "ok": False,
                "can_execute": False,
                "message": "El tramite ingresado no se puede procesar, puesto los reclamantes ya fueron tramitados.",
            }
        return {"ok": True, "can_execute": True, "tramite": tramite, "accion": accion}

    def modificar_tramite(self, *, tramite: str, accion: int, usuario: str) -> dict:
        affected = self.repository.modificar_tramite(tramite=tramite, accion=accion)
        accion_desc = "eliminar" if accion == 1 else "inicializar" if accion == 2 else "desconocida"
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "modifica_tramite",
            {"usuario": usuario, "accion": accion, "accion_desc": accion_desc, "affected": affected},
        )
        return {"ok": affected > 0, "tramite": tramite, "accion": accion, "affected": affected}

    def cerrar_tramite_origen(
        self,
        *,
        opc: str,
        tramite: str,
        identificacion: str,
        estado: str,
        observacion: str,
        usuario: str,
    ) -> dict:
        if estado == "DEVUELTO":
            has_rel = self.repository.has_tramite_solicitud_relation(tramite)
            if not has_rel:
                return {
                    "ok": False,
                    "status": "Error",
                    "tramite": tramite,
                    "identificacion": identificacion,
                    "message": "No se puede devolver el caso por falta de relacion historica en fun_tramite_solicitud.",
                }
            self.repository.insert_devolucion_analisis(
                tramite=tramite,
                reclamante=identificacion,
                observacion=observacion,
                usuario=usuario,
            )
            estado_devuelto = "DEVUELTO A GESTION OPERATIVA" if opc in {"cierraFiducia", "cierraAsulado"} else "DEVUELTO A ANALISIS"
            affected = self.repository.update_estado_reclamante_identificacion(
                tramite=tramite,
                identificacion=identificacion,
                estado=estado_devuelto,
            )
            self.state_machine.register_event(
                "fun_reclamante",
                tramite,
                "cierre_origen_devuelto",
                {
                    "opc": opc,
                    "usuario": usuario,
                    "identificacion": identificacion,
                    "estado_reclamante": estado_devuelto,
                    "affected": affected,
                },
            )
            return {
                "ok": affected > 0,
                "status": "OK",
                "tramite": tramite,
                "identificacion": identificacion,
                "estado_reclamante": estado_devuelto,
                "affected": affected,
            }

        if opc == "cierraPensionado":
            forma_pago = self.repository.get_forma_pago_reclamante(tramite=tramite, identificacion=identificacion)
            nuevo_estado = "Interfaz Generada" if forma_pago == "Cheque" else "Transferencia Generada"
        elif opc == "cierraFiducia":
            nuevo_estado = "Aprueba Pago Fiducia Jefe"
        elif opc == "cierraAsulado":
            nuevo_estado = "Aprueba Pago Asulado Jefe"
        else:
            nuevo_estado = "Aprueba Pago Jefe"

        affected = self.repository.update_estado_reclamante_identificacion(
            tramite=tramite,
            identificacion=identificacion,
            estado=nuevo_estado,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "cierre_origen_aprobacion",
            {
                "opc": opc,
                "usuario": usuario,
                "identificacion": identificacion,
                "estado_reclamante": nuevo_estado,
                "affected": affected,
            },
        )
        return {
            "ok": affected > 0,
            "status": "OK",
            "tramite": tramite,
            "identificacion": identificacion,
            "estado_reclamante": nuevo_estado,
            "affected": affected,
        }

    def rechazar_datos_pago(
        self,
        *,
        opc: str,
        tramite: str,
        identificacion: str,
        observacion: str,
        usuario: str,
    ) -> dict:
        inserted = self.repository.insert_rechazo_pago(
            tramite=tramite,
            beneficiario=identificacion,
            usuario=usuario,
            observacion=observacion,
        )
        affected = self.repository.update_estado_reclamante_identificacion(
            tramite=tramite,
            identificacion=identificacion,
            estado="AUXILIO NO APROBADO",
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "rechaza_datos_pago",
            {
                "opc": opc,
                "usuario": usuario,
                "identificacion": identificacion,
                "inserted_rechazo": inserted,
                "affected": affected,
            },
        )
        return {
            "ok": affected > 0,
            "tramite": tramite,
            "identificacion": identificacion,
            "inserted_rechazo": inserted,
            "affected": affected,
            "estado_reclamante": "AUXILIO NO APROBADO",
        }

    def marcar_aprueba_pagos(self, *, tramites: list[str], usuario: str) -> dict:
        affected = self.repository.mark_aprueba_pago_jefe(tramites)
        self.state_machine.register_event(
            "fun_reclamante",
            "masivo",
            "marca_aprueba_pagos",
            {"usuario": usuario, "tramites": tramites, "affected": affected},
        )
        return {"ok": True, "tramites": tramites, "affected": affected}

    def marcar_devuelto(self, *, tramite: str, usuario: str) -> dict:
        affected = self.repository.update_estado_solicitud(tramite=tramite, estado_flujo="Documentos Pendientes")
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "marca_devuelto",
            {"usuario": usuario, "estado_flujo": "Documentos Pendientes", "affected": affected},
        )
        return {"ok": affected > 0, "tramite": tramite, "estado_flujo": "Documentos Pendientes", "affected": affected}

    def marcar_llamar_funeraria(self, *, tramite: str, usuario: str, info: list[str] | None) -> dict:
        pagos_ajustados = 0
        for item in info or []:
            parts = item.split("|")
            if len(parts) >= 3 and parts[1] == "Transferencia" and parts[2] == "N":
                pagos_ajustados += self.repository.update_forma_pago_by_id_ben(
                    tramite=tramite,
                    id_ben=parts[0],
                    forma_pago="Cheque",
                )
        affected = self.repository.update_estado_solicitud(tramite=tramite, estado_flujo="Llamar Funeraria")
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "marca_llamar_funeraria",
            {
                "usuario": usuario,
                "estado_flujo": "Llamar Funeraria",
                "affected": affected,
                "pagos_ajustados": pagos_ajustados,
            },
        )
        return {
            "ok": affected > 0,
            "tramite": tramite,
            "estado_flujo": "Llamar Funeraria",
            "affected": affected,
            "pagos_ajustados": pagos_ajustados,
        }

    def finalizar_reclamante_aseguradora(self, *, tramite: str, identificacion: str, estado: str, usuario: str) -> dict:
        nuevo_estado = "PAGO COBRADO Y PAGADO ASEGURADORA" if estado == "Paga" else "CASO MAL RECONOCIDO ASEGURADORA NO PAGA"
        affected = self.repository.update_estado_reclamante_identificacion(
            tramite=tramite,
            identificacion=identificacion,
            estado=nuevo_estado,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "finaliza_aseguradora",
            {
                "usuario": usuario,
                "identificacion": identificacion,
                "estado_reclamante": nuevo_estado,
                "affected": affected,
            },
        )
        return {"ok": affected > 0, "tramite": tramite, "identificacion": identificacion, "estado_reclamante": nuevo_estado, "affected": affected}

    def finalizar_reclamante_pensionado(self, *, tramite: str, identificacion: str, estado: str, usuario: str) -> dict:
        if estado != "ok":
            return {"ok": True, "tramite": tramite, "identificacion": identificacion, "affected": 0, "skipped": True}
        forma_pago = self.repository.get_forma_pago_reclamante(tramite=tramite, identificacion=identificacion)
        nuevo_estado = "Interfaz Generada" if forma_pago == "Cheque" else "Transferencia Generada"
        affected = self.repository.update_estado_reclamante_identificacion(
            tramite=tramite,
            identificacion=identificacion,
            estado=nuevo_estado,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "finaliza_pensionado",
            {
                "usuario": usuario,
                "identificacion": identificacion,
                "estado_reclamante": nuevo_estado,
                "affected": affected,
            },
        )
        return {"ok": affected > 0, "tramite": tramite, "identificacion": identificacion, "estado_reclamante": nuevo_estado, "affected": affected}

    def gestionar_beneficiario(
        self,
        *,
        tramite: str,
        beneficiario: str,
        usuario: str,
        estado: str,
        contacto: str,
        observacion: str,
        reclama: str,
        poder: str,
        pagado_por: str,
        plan_exequial: str,
        numero_plan: str,
        titular_fallecido: str,
        nombre_funeraria: str,
    ) -> dict:
        inserted = self.repository.insert_gestion_funeraria(
            id_reclamante=beneficiario,
            tramite=tramite,
            estado=estado,
            contacto_gestion=contacto,
            observacion=observacion,
            reclama_paga=reclama,
            poder=poder,
            pagado_por=pagado_por,
            usuario_gestion=usuario,
            plan_exequial=plan_exequial,
            numero_plan=numero_plan,
            titular_fallecido=titular_fallecido,
            nombre_funeraria=nombre_funeraria,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "gestiona_ben",
            {"usuario": usuario, "beneficiario": beneficiario, "inserted": inserted, "estado": estado},
        )
        return {"ok": inserted > 0, "tramite": tramite, "beneficiario": beneficiario, "inserted": inserted}

    def guardar_exequial(
        self,
        *,
        tramite: str,
        plan_exequial: str,
        numero_plan: str,
        titular_fallecido: str,
        nombre_funeraria: str,
        usuario: str,
    ) -> dict:
        inserted = self.repository.insert_exequial_tramite(
            tramite=tramite,
            plan_exequial=plan_exequial,
            numero_plan=numero_plan.upper(),
            titular_fallecido=titular_fallecido,
            nombre_funeraria=nombre_funeraria.upper(),
        )
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "guarda_exequial",
            {"usuario": usuario, "inserted": inserted},
        )
        return {"ok": inserted > 0, "tramite": tramite, "inserted": inserted}

    def gestionar_reclamante(
        self,
        *,
        tramite: str,
        id_ben: str,
        estado: str,
        usuario: str,
        observacion: str,
    ) -> dict:
        modificar_fpago = estado == "Modificar Fpago"
        inserted = self.repository.insert_gestion_reclamante(
            tramite=tramite,
            id_reclamante=id_ben,
            estado=estado,
            usuario=usuario,
            observacion=observacion,
            modificar_fpago=modificar_fpago,
        )
        updated_pago = 0
        if modificar_fpago:
            updated_pago = self.repository.update_forma_pago_by_id_ben(
                tramite=tramite,
                id_ben=id_ben,
                forma_pago="Cheque",
            )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "gestiona_rec",
            {
                "usuario": usuario,
                "id_ben": id_ben,
                "estado": estado,
                "inserted": inserted,
                "updated_pago": updated_pago,
            },
        )
        return {
            "ok": inserted > 0,
            "tramite": tramite,
            "id_ben": id_ben,
            "estado": estado,
            "inserted": inserted,
            "updated_pago": updated_pago,
        }

    def gestionar_origen_fondos(self, *, tramite: str, usuario: str) -> dict:
        reclamantes = self.repository.list_reclamantes_origen_fondos(tramite=tramite)
        respuestas = self.repository.list_respuestas_llamada()
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "gestionar_origen_fondos",
            {"usuario": usuario, "count_reclamantes": len(reclamantes), "count_respuestas": len(respuestas)},
        )
        return {
            "ok": True,
            "tramite": tramite,
            "count": len(reclamantes),
            "reclamantes": reclamantes,
            "respuestas": respuestas,
            "message": "" if reclamantes else "No se encontraron Reclamantes aprobados",
        }

    def guardar_respuesta_origen_fondos(
        self,
        *,
        tramite: str,
        id_reclamante: str,
        id_respuesta: str,
        observacion: str,
        usuario: str,
    ) -> dict:
        inserted = self.repository.insert_llamada_cheque(
            tramite=tramite,
            id_reclamante=id_reclamante,
            id_respuesta=id_respuesta,
            observacion=observacion,
            usuario=usuario,
        )
        response_norm = (id_respuesta or "").strip().lower()
        confirmed = response_norm in {"1", "confirmado", "si", "sí"}
        updated_pago = (
            self.repository.confirmar_pago_reclamante_origen_fondos(tramite=tramite, id_reclamante=id_reclamante)
            if confirmed
            else 0
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "guardar_respuesta_origen_fondos",
            {
                "usuario": usuario,
                "id_reclamante": id_reclamante,
                "id_respuesta": id_respuesta,
                "inserted": inserted,
                "updated_pago": updated_pago,
            },
        )
        return {
            "ok": inserted > 0,
            "tramite": tramite,
            "id_reclamante": id_reclamante,
            "id_respuesta": id_respuesta,
            "inserted": inserted,
            "updated_pago": updated_pago,
        }

    def guardar_gestion_cheque(
        self, *, tramite: str, id_ben: str, estado: str, observacion: str, usuario: str
    ) -> dict:
        inserted = self.repository.insert_llamada_cheque(
            tramite=tramite,
            id_reclamante=id_ben,
            id_respuesta=estado,
            observacion=observacion,
            usuario=usuario,
        )
        affected = 0
        if estado == "1":
            affected = self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado="Cheque Informado")
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "guarda_gestion_cheque",
            {
                "usuario": usuario,
                "id_ben": id_ben,
                "estado": estado,
                "inserted": inserted,
                "affected": affected,
            },
        )
        return {"ok": inserted > 0, "tramite": tramite, "id_ben": id_ben, "inserted": inserted, "affected": affected}

    def guardar_gestion_transferencia(
        self, *, tramite: str, id_ben: str, estado: str, observacion: str, usuario: str
    ) -> dict:
        inserted = self.repository.insert_llamada_transferencia(
            tramite=tramite,
            id_reclamante=id_ben,
            estado=estado,
            observacion=observacion,
            usuario=usuario,
        )
        affected = 0
        updated_pago = 0
        if estado == "Nueva Cuenta":
            affected = self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado="Pte Dtos Nueva Cuenta")
        elif estado == "Pago Cheque":
            affected = self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado="Interfaz Generada")
            updated_pago = self.repository.update_forma_pago_by_id_ben(
                tramite=tramite,
                id_ben=id_ben,
                forma_pago="Cheque",
            )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "guarda_gestion_transferencia",
            {
                "usuario": usuario,
                "id_ben": id_ben,
                "estado": estado,
                "inserted": inserted,
                "affected": affected,
                "updated_pago": updated_pago,
            },
        )
        return {
            "ok": inserted > 0,
            "tramite": tramite,
            "id_ben": id_ben,
            "inserted": inserted,
            "affected": affected,
            "updated_pago": updated_pago,
        }

    def guardar_banco(self, *, codigo: str, banco: str, usuario: str) -> dict:
        exists = self.repository.exists_banco_codigo(codigo)
        if exists:
            return {"ok": False, "status": "exists", "codigo": codigo}
        inserted = self.repository.insert_banco(codigo=codigo, banco=banco)
        self.state_machine.register_event(
            "fun_catalogo",
            "bancos",
            "guardar_banco",
            {"usuario": usuario, "codigo": codigo, "inserted": inserted},
        )
        return {"ok": inserted > 0, "status": "ok", "codigo": codigo, "inserted": inserted}

    def actualizar_banco(self, *, codigo: str, banco: str, usuario: str) -> dict:
        affected = self.repository.update_banco_nombre(codigo=codigo, banco=banco)
        self.state_machine.register_event(
            "fun_catalogo",
            "bancos",
            "actualizar_banco",
            {"usuario": usuario, "codigo": codigo, "affected": affected},
        )
        return {"ok": affected > 0, "codigo": codigo, "affected": affected}

    def actualizar_rechazo_pago(
        self,
        *,
        id_ben: str,
        id_pago: str,
        nrocuenta: str,
        nrocuentaold: str,
        banco: str,
        bancoold: str,
        tipocta: str,
        tipoctaold: str,
        usuario: str,
    ) -> dict:
        affected = self.repository.update_pago_rechazo(
            id_pago=id_pago,
            numero_cuenta=nrocuenta,
            banco=banco,
            tipo_cuenta=tipocta,
        )
        log_inserted = self.repository.insert_actualiza_rechazo_log(
            id_ben=id_ben,
            id_pago=id_pago,
            cuenta_old=nrocuentaold,
            cuenta_new=nrocuenta,
            banco_old=bancoold,
            banco_new=banco,
            tipo_cta_old=tipoctaold,
            tipo_cta_new=tipocta,
            usuario=usuario,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            id_ben,
            "act_rechazo",
            {"usuario": usuario, "id_pago": id_pago, "affected": affected, "log_inserted": log_inserted},
        )
        return {"ok": affected > 0, "id_ben": id_ben, "id_pago": id_pago, "affected": affected, "log_inserted": log_inserted}

    def editar_reclamante(self, *, id_ben: str, usuario: str) -> dict:
        item = self.repository.get_reclamante_by_id_ben(id_ben)
        self.state_machine.register_event(
            "fun_reclamante",
            id_ben,
            "edita_reclamante",
            {"usuario": usuario, "found": item is not None},
        )
        return {"ok": item is not None, "id_ben": id_ben, "item": item}

    def guardar_rechazo(
        self, *, tramite: str, semanas: str, fidelidad: str, fecha_muerte: str, usuario: str
    ) -> dict:
        if self.repository.exists_rechazo_datos(tramite):
            return {
                "ok": False,
                "tramite": tramite,
                "inserted": 0,
                "message": "Ya ha sido almacenada la informacion del rechazo.",
            }
        inserted = self.repository.insert_rechazo_datos(
            tramite=tramite,
            semanas=semanas,
            fidelidad=fidelidad,
            fecha_muerte=fecha_muerte,
            usuario=usuario,
        )
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "guarda_rechazo",
            {"usuario": usuario, "inserted": inserted},
        )
        return {"ok": inserted > 0, "tramite": tramite, "inserted": inserted}

    def cargar_modal_bancos(self, *, operacion: str, codigo: str | None, usuario: str) -> dict:
        item = self.repository.get_banco_by_codigo(codigo) if operacion == "editar" and codigo else None
        self.state_machine.register_event(
            "fun_catalogo",
            "bancos",
            "carga_modal_bancos",
            {"usuario": usuario, "operacion": operacion, "codigo": codigo or "", "found": item is not None},
        )
        return {
            "ok": True,
            "operacion": operacion,
            "title": "Editar Bancos" if operacion == "editar" else "Registro Bancos",
            "item": item,
        }

    def reporte_pagos(self, *, year: int, entidad: str | None, usuario: str) -> dict:
        items = self.repository.get_reporte_mensual(year=year, entidad=entidad)
        self.state_machine.register_event(
            "fun_reporte",
            str(year),
            "reporte_pagos",
            {"usuario": usuario, "entidad": entidad or "", "count": len(items)},
        )
        return {"ok": True, "year": year, "entidad": entidad, "count": len(items), "items": items}

    def estadistico_pagos(self, *, year: int, entidad: str | None, usuario: str) -> dict:
        items = self.repository.get_reporte_mensual(year=year, entidad=entidad)
        by_entity: dict[str, list[dict]] = {}
        for item in items:
            by_entity.setdefault(item["entidad"], []).append(item)
        self.state_machine.register_event(
            "fun_reporte",
            str(year),
            "estadistico_pagos",
            {"usuario": usuario, "entidad": entidad or "", "series": len(by_entity)},
        )
        return {"ok": True, "year": year, "entidad": entidad, "series": by_entity}

    def detalle_pagos_mes(self, *, year: int, month_label: str, usuario: str) -> dict:
        month_num = self._months_en.get(month_label.lower())
        if not month_num:
            return {"ok": False, "year": year, "month_label": month_label, "items": []}
        items: list[dict] = []
        for entidad in (
            "FIDUCIA",
            "COMPANIA DE SEGUROS BOLIVAR S A",
            "SEGUROS DE VIDA SURAMERICANA S.A.",
        ):
            rows = self.repository.get_reporte_detalle_mes(year=year, month_num=month_num, entidad=entidad)
            total_valor = sum(r["suma_de_valor"] for r in rows)
            total_count = sum(r["cuenta_id"] for r in rows)
            items.append(
                {
                    "entidad": entidad,
                    "month_num": month_num,
                    "month_label": month_label,
                    "total_valor": total_valor,
                    "total_count": total_count,
                }
            )
        self.state_machine.register_event(
            "fun_reporte",
            f"{year}-{month_num}",
            "pagos_detalle_mes",
            {"usuario": usuario, "month_label": month_label},
        )
        return {"ok": True, "year": year, "month_num": month_num, "month_label": month_label, "items": items}

    def detalle_diario_entidad(
        self, *, year: int, month: str, entidad: str, mes_label: str | None, usuario: str
    ) -> dict:
        month_num = self._months_en.get(month.lower())
        if not month_num and month.isdigit():
            month_num = int(month)
        if not month_num:
            return {"ok": False, "year": year, "month": month, "entidad": entidad, "items": []}
        items = self.repository.get_reporte_detalle_mes(year=year, month_num=month_num, entidad=entidad)
        self.state_machine.register_event(
            "fun_reporte",
            f"{year}-{month_num}-{entidad}",
            "pagos_detalle_diario_entidad",
            {"usuario": usuario, "entidad": entidad},
        )
        return {
            "ok": True,
            "year": year,
            "month_num": month_num,
            "month_label": mes_label or month,
            "entidad": entidad,
            "count": len(items),
            "items": items,
        }

    def rechazo_manual_optima(
        self, *, tramite: str, identificacion: str, causal: str, origen: str, usuario: str
    ) -> dict:
        id_ben = self.repository.get_id_ben_for_rechazo(
            tramite=tramite,
            identificacion=identificacion,
            origen=origen,
        )
        if not id_ben:
            return {"ok": False, "status": "Error", "msg": "El reclamante no existe para el tramite enviado"}

        rechazo = self.repository.get_respuesta_banco_cargado(
            identificacion=identificacion,
            causal=causal,
        )
        if not rechazo:
            return {
                "ok": False,
                "status": "Error",
                "msg": "No se evidencia un registro de rechazo cargado.",
            }

        na = int(rechazo["na"])
        self.repository.update_respuesta_banco_estado(na=na, estado=f"Cruzado - {id_ben}")
        affected = self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado="PAGO RECHAZADO")
        self.repository.insert_causal_rechazo(id_reclamante=id_ben, cod_respuesta=causal, id_archivo=na)
        self.repository.insert_log_activacion_rechazos(
            tramite=tramite,
            reclamante=id_ben,
            causal=causal,
            archivo=na,
            usuario=usuario,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "rech_manual_optima",
            {
                "usuario": usuario,
                "identificacion": identificacion,
                "id_ben": id_ben,
                "causal": causal,
                "archivo": na,
                "affected": affected,
            },
        )
        return {"ok": True, "status": "OK", "msg": "Tramite rechazado exitosamente", "affected": affected}

    def cargar_txt_banco(self, *, nombre_archivo: str, lineas: list[str], usuario: str) -> dict:
        if self.repository.exists_respuesta_banco_nombre_archivo(nombre_archivo):
            return {
                "ok": False,
                "status": "Error",
                "msg": "EL ARCHIVO QUE INTENTA CARGAR YA EXISTE EN EL SISTEMA, POR FAVOR REVISE",
            }

        cargados = 0
        for line in lineas:
            registro = line.rstrip("\r\n")
            nit_pagadora = self._to_int(self._slice(registro, 0, 13))
            fecha_transmision = self._slice(registro, 13, 8)
            secuencia_pago = self._slice(registro, 21, 1)
            tipo_registro = self._slice(registro, 22, 1)
            nit_reclamante = self._to_int(self._slice(registro, 23, 15))
            nit_txt = str(nit_reclamante)
            if len(nit_txt) == 10 and not nit_txt.startswith("1"):
                nit_reclamante = self._to_int(nit_txt[:9])
            nombre_reclamante = self._slice(registro, 38, 18)
            codigo_banco = self._to_int(self._slice(registro, 56, 9))
            cuenta_reclamante = self._to_int(self._slice(registro, 65, 17))
            cuenta_local = self._slice(registro, 82, 1)
            tipo_transaccion = self._slice(registro, 83, 2)
            valor_raw = self._slice(registro, 85, 18)
            valor = self._to_int(valor_raw.split(".")[0])
            concepto = self._slice(registro, 103, 22)
            codigo_respuesta = self._slice(registro, 125, 3)
            numero_cheque = self._slice(registro, 128, 8)
            fecha_aplicacion = self._slice(registro, 136, 8)
            self.repository.insert_respuesta_banco(
                row={
                    "nit_pagadora": nit_pagadora,
                    "fecha_transmision": fecha_transmision,
                    "secuencia_pago": secuencia_pago,
                    "tipo_registro": tipo_registro,
                    "nit_reclamante": nit_reclamante,
                    "nombre_reclamante": nombre_reclamante,
                    "codigo_banco": codigo_banco,
                    "cuenta_reclamante": cuenta_reclamante,
                    "cuenta_local": cuenta_local,
                    "tipo_transaccion": tipo_transaccion,
                    "valor": valor,
                    "concepto": concepto,
                    "codigo_respuesta": codigo_respuesta,
                    "numero_cheque": numero_cheque,
                    "fecha_aplicacion": fecha_aplicacion,
                    "nombre_archivo": nombre_archivo,
                    "usuario_carga": usuario,
                    "estado": "Cargado",
                }
            )
            cargados += 1

        cruzados = 0
        con_error = 0
        pendientes = self.repository.list_respuesta_banco_pendientes_cruce()
        for row in pendientes:
            identificacion = str(row.get("nit_reclamante") or "").strip()
            if not identificacion:
                continue
            reclamantes = self.repository.list_reclamantes_by_identificacion_y_estado(
                identificacion=identificacion,
                estados=["Interfaz Fiducia Generada", "Interfaz Asulado Generada"],
            )
            if not reclamantes:
                continue

            estado_flujo = str(row.get("estado_flujo") or "").strip().upper()
            na_txt = int(row["na"])
            codigo_respuesta = str(row.get("codigo_respuesta") or "").strip()
            ultimo_id_ben = ""

            if estado_flujo == "APROBADO":
                for recl in reclamantes:
                    id_ben = str(recl["id_ben"])
                    ultimo_id_ben = id_ben
                    origen = self.repository.get_origen_pago(
                        tramite=str(recl["tramite"]),
                        identificacion=str(recl["identificacion"]),
                    )
                    estado_pago = (
                        "AUXILIO ASULADO PAGADO"
                        if str(origen or "").strip() == "Asulado"
                        else "AUXILIO DE FIDUCIA PAGADO"
                    )
                    self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado=estado_pago)
                if ultimo_id_ben:
                    self.repository.update_respuesta_banco_estado(na=na_txt, estado=f"Cruzado - {ultimo_id_ben}")
                cruzados += 1
            else:
                for recl in reclamantes:
                    id_ben = str(recl["id_ben"])
                    ultimo_id_ben = id_ben
                    self.repository.update_estado_reclamante_by_id_ben(id_ben=id_ben, estado="PAGO RECHAZADO")
                    self.repository.insert_causal_rechazo(
                        id_reclamante=id_ben,
                        cod_respuesta=codigo_respuesta,
                        id_archivo=na_txt,
                    )
                if ultimo_id_ben:
                    self.repository.update_respuesta_banco_estado(na=na_txt, estado=f"Cruzado - {ultimo_id_ben}")
                con_error += 1

        self.state_machine.register_event(
            "fun_respuesta_banco",
            nombre_archivo,
            "cargue_txt_banco",
            {"usuario": usuario, "cargados": cargados, "cruzados": cruzados, "rechazados": con_error},
        )
        return {
            "ok": True,
            "status": "OK",
            "nombre_archivo": nombre_archivo,
            "cargados": cargados,
            "cruzados": cruzados,
            "rechazados": con_error,
            "msg": (
                f"ARCHIVO CARGADO EXITOSAMENTE, SE HAN CARGADO {cargados} REGISTROS. "
                f"SE HAN FINALIZADO {cruzados} PAGOS. SE HAN RECHAZADO {con_error} PAGOS."
            ),
        }

    def finalizar_oficina_cheque(self, *, tramite: str, identificacion: str, usuario: str) -> dict:
        cedula = self.repository.get_afiliado_by_tramite(tramite)
        if not cedula:
            return {"ok": False, "respuesta": "No se encuentra afiliado para el tramite"}
        if not self.repository.has_soporte_egreso_hoy(cedula):
            return {
                "ok": False,
                "respuesta": "NO SE PUEDE MODIFICAR EL ESTADO DE LA SOLICITUD, NO HA ADJUNTADO EL SOPORTE DE EGRESO",
            }

        origen = self.repository.get_origen_pago(tramite=tramite, identificacion=identificacion)
        estado = "AUXILIO APROBADO CON SOPORTE OK" if origen == "Cuenta" else "AUXILIO APROBADO CON SOPORTE OK ADMINISTRADORA"
        affected = self.repository.update_estado_reclamante_identificacion(
            tramite=tramite,
            identificacion=identificacion,
            estado=estado,
        )
        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "fin_oficina_cheque",
            {
                "usuario": usuario,
                "identificacion": identificacion,
                "estado_reclamante": estado,
                "affected": affected,
            },
        )
        return {"ok": True, "respuesta": "GESTION REALIZADA EXITOSAMENTE", "affected": affected, "estado_reclamante": estado}

    def cierre_masivo_operador(self, *, usuario: str, asulado: bool) -> dict:
        if asulado:
            estado_origen = "APROBADO ASULADO"
            estado_destino = "Aprueba Pago Asulado Jefe"
            estado_log_actual = "APROBADO ASULADO"
            evento = "cierre_masivo_asulado_operador"
        else:
            estado_origen = "APROBADO FIDUCIA"
            estado_destino = "Aprueba Pago Fiducia Jefe"
            estado_log_actual = "APROBADO FIDUCIA"
            evento = "cierre_masivo_operador"
        try:
            result = self.repository.ejecutar_cierre_masivo_operador(
                usuario=usuario,
                estado_origen=estado_origen,
                estado_destino=estado_destino,
                estado_log_actual=estado_log_actual,
            )
            self.state_machine.register_event(
                "fun_log_cierre_masivo",
                usuario,
                evento,
                {"usuario": usuario, "asulado": asulado, **result},
            )
            return {
                "ok": True,
                "status": "OK",
                "msg": "Proceso Operador Finalizado Exitosamente",
                **result,
            }
        except Exception:
            regresados = self.repository.regresa_estados_masivo(
                usuario=usuario,
                estado_regreso=estado_origen,
            )
            self.state_machine.register_event(
                "fun_log_cierre_masivo",
                usuario,
                f"{evento}_error",
                {"usuario": usuario, "asulado": asulado, "regresados": regresados},
            )
            return {
                "ok": False,
                "status": "Error Operador",
                "msg": "Error al finalizar los casos en la bandeja del operador",
                "regresados": regresados,
            }

    def cargar_excel_masivo(self, *, nombre_archivo: str, content: bytes, usuario: str, asulado: bool) -> dict:
        self.repository.delete_log_cierre_masivo_en_validacion_usuario(usuario)
        self.repository.delete_log_cierre_masivo_en_validacion_anteriores()
        if "." not in nombre_archivo or nombre_archivo.rsplit(".", 1)[1].lower() != "xlsx":
            return {"ok": False, "status": "Error", "archivo": nombre_archivo, "msg": "La extensión del archivo no es válida"}

        try:
            highest_col, rows = self._parse_xlsx_rows(content)
        except Exception:
            return {"ok": False, "status": "Error", "archivo": nombre_archivo, "msg": "No fue posible procesar el archivo xlsx"}

        if highest_col != 7:
            return {"ok": False, "status": "Error", "archivo": nombre_archivo, "msg": "El numero de columnas del excel no es válido"}

        sw_error = False
        list_error: list[dict] = []
        for i, row in enumerate(rows, start=1):
            if i == 1:
                continue
            if len(row) < 7:
                row = row + [""] * (7 - len(row))
            tramite = str(row[0]).strip()
            id_afiliado = str(row[1]).strip()
            id_reclamante = str(row[2]).strip()
            valor = str(row[3]).strip()
            banco = str(row[4]).strip()
            tipo_cta = str(row[5]).strip().capitalize()
            cta = str(row[6]).strip()

            if not any([tramite, id_afiliado, id_reclamante, valor, banco, tipo_cta, cta]):
                continue

            err = self.repository.validate_masivo_row(
                tramite=tramite,
                id_afiliado=id_afiliado,
                id_reclamante=id_reclamante,
                valor=valor,
                banco=banco,
                tipo_cta=tipo_cta,
                cta=cta,
                asulado=asulado,
            )
            if err:
                sw_error = True
                list_error.append({"fila": i, "msg": err})

            if self.repository.exists_log_cierre_masivo_duplicado(
                tramite=tramite,
                id_reclamante=id_reclamante,
                usuario=usuario,
            ):
                sw_error = True
                list_error.append({"fila": i, "msg": "Cedula de reclamante repetida en el excel"})
            else:
                self.repository.insert_log_cierre_masivo_en_validacion(
                    tramite=tramite,
                    id_reclamante=id_reclamante,
                    valor=valor,
                    cod_banco=banco,
                    tipo_cta=tipo_cta,
                    cuenta=cta,
                    usuario=usuario,
                )

        if sw_error:
            self.repository.delete_log_cierre_masivo_en_validacion_usuario(usuario)
            self.state_machine.register_event(
                "fun_log_cierre_masivo",
                nombre_archivo,
                "cargar_excel_masivo_error",
                {"usuario": usuario, "asulado": asulado, "errores": len(list_error)},
            )
            return {
                "ok": False,
                "status": "Error Data",
                "archivo": nombre_archivo,
                "msg": "Se encontraron errores de validacion",
                "errores": list_error,
            }

        validados = self.repository.mark_log_cierre_masivo_validado_hoy(usuario)
        self.state_machine.register_event(
            "fun_log_cierre_masivo",
            nombre_archivo,
            "cargar_excel_masivo",
            {"usuario": usuario, "asulado": asulado, "validados": validados},
        )
        return {"ok": True, "status": "OK", "archivo": nombre_archivo, "msg": "Archivo Cargado Exitosamente", "validados": validados}

    def cpp_optima_masivo(self, *, tramites: list[str], sw_origen: str, usuario: str) -> dict:
        asulado = sw_origen.strip().lower() == "asulado"
        estado_flujo = "AUXILIO ASULADO PAGADO" if asulado else "AUXILIO FIDUCIA PAGADO"
        estado_reclamante = "Interfaz Asulado Generada" if asulado else "Interfaz Fiducia Generada"
        items: list[dict] = []
        procesados = 0
        errores = 0
        tramites_afectados: set[str] = set()

        for raw in tramites:
            token = str(raw or "").strip()
            if not token:
                continue
            if "_" not in token:
                items.append({"token": token, "status": "error", "detail": "Formato invalido, esperado tramite_reclamante"})
                errores += 1
                continue
            tramite, identificacion = token.split("_", 1)
            pago = self.repository.get_pago_para_cpp(tramite=tramite, identificacion=identificacion)
            if not pago:
                items.append({"tramite": tramite, "identificacion": identificacion, "status": "error", "detail": "No se encontro pago"})
                errores += 1
                continue

            # Compatibilidad temporal: el consumo externo generaCPP/CPP se simula como exitoso.
            updated = self.repository.update_estado_reclamante_by_tramite_identificacion(
                tramite=tramite,
                identificacion=identificacion,
                estado=estado_reclamante,
            )
            if updated <= 0:
                items.append({"tramite": tramite, "identificacion": identificacion, "status": "error", "detail": "No fue posible actualizar estado"})
                errores += 1
                continue
            procesados += 1
            tramites_afectados.add(tramite)
            items.append({"tramite": tramite, "identificacion": identificacion, "status": "ok"})

        cerrados = 0
        for tramite in tramites_afectados:
            total = self.repository.count_reclamantes_by_tramite(tramite)
            total_estado = self.repository.count_reclamantes_by_tramite_estado(tramite=tramite, estado=estado_reclamante)
            if total > 0 and total == total_estado:
                self.repository.change_estado_solicitud(tramite=tramite, new_estado=estado_flujo)
                cerrados += 1

        status = "OK" if errores == 0 else "Error"
        msg = "INTERFAZ GENERADA EXITOSAMEMTE" if errores == 0 else "Se presento un error al consumir las cuentas de los reclamantes"
        self.state_machine.register_event(
            "fun_cpp",
            ",".join(sorted(tramites_afectados)) if tramites_afectados else "sin_tramites",
            "cpp_optima_masivo",
            {
                "usuario": usuario,
                "origen": sw_origen,
                "procesados": procesados,
                "errores": errores,
                "cerrados": cerrados,
                "cpp_externo": "simulado",
            },
        )
        return {
            "ok": errores == 0,
            "status": status,
            "msg": msg,
            "origen": sw_origen,
            "estado_reclamante": estado_reclamante,
            "estado_flujo": estado_flujo,
            "procesados": procesados,
            "errores": errores,
            "tramites_cerrados": cerrados,
            "items": items,
            "nota": "Consumo CPP externo pendiente; en esta fase se simula exito para mantener flujo funcional local.",
        }

    def reversion_masivo(self, *, id_benes: list[str], usuario: str) -> dict:
        estado_reclamante = "AUXILIO DE FIDUCIA PAGADO"
        estado_flujo = "AUXILIO FIDUCIA PAGADO"
        items: list[dict] = []
        procesados = 0
        errores = 0
        tramites_afectados: set[str] = set()

        for raw in id_benes:
            id_ben = str(raw or "").strip()
            if not id_ben:
                continue
            rec = self.repository.get_reclamante_by_id_ben(id_ben)
            if not rec:
                items.append({"id_ben": id_ben, "status": "error", "detail": "Reclamante no encontrado"})
                errores += 1
                continue
            tramite = str(rec["tramite"])
            identificacion = str(rec["identificacion"])
            pago = self.repository.get_pago_para_cpp(tramite=tramite, identificacion=identificacion)
            if not pago:
                items.append({"id_ben": id_ben, "tramite": tramite, "identificacion": identificacion, "status": "error", "detail": "No se encontro pago"})
                errores += 1
                continue

            # Compatibilidad temporal: consumo externo generaCPP/CPP simulado.
            updated = self.repository.update_estado_reclamante_by_tramite_identificacion(
                tramite=tramite,
                identificacion=identificacion,
                estado=estado_reclamante,
            )
            if updated <= 0:
                items.append({"id_ben": id_ben, "tramite": tramite, "identificacion": identificacion, "status": "error", "detail": "No fue posible actualizar estado"})
                errores += 1
                continue
            procesados += 1
            tramites_afectados.add(tramite)
            items.append({"id_ben": id_ben, "tramite": tramite, "identificacion": identificacion, "status": "ok"})

        cerrados = 0
        for tramite in tramites_afectados:
            total = self.repository.count_reclamantes_by_tramite(tramite)
            total_estado = self.repository.count_reclamantes_by_tramite_estado(tramite=tramite, estado=estado_reclamante)
            if total > 0 and total == total_estado:
                self.repository.change_estado_solicitud(tramite=tramite, new_estado=estado_flujo)
                cerrados += 1

        status = "OK" if errores == 0 else "Error"
        msg = "PAGO REVERSADO EXITOSAMEMTE" if errores == 0 else "Se presento un error al consumir las cuentas de los reclamantes"
        self.state_machine.register_event(
            "fun_cpp",
            ",".join(sorted(tramites_afectados)) if tramites_afectados else "sin_tramites",
            "reversion_masivo",
            {
                "usuario": usuario,
                "procesados": procesados,
                "errores": errores,
                "cerrados": cerrados,
                "cpp_externo": "simulado",
            },
        )
        return {
            "ok": errores == 0,
            "status": status,
            "msg": msg,
            "estado_reclamante": estado_reclamante,
            "estado_flujo": estado_flujo,
            "procesados": procesados,
            "errores": errores,
            "tramites_cerrados": cerrados,
            "items": items,
            "nota": "Consumo CPP externo pendiente; en esta fase se simula exito para mantener flujo funcional local.",
        }

    def _cerrar_solicitud_si_aplica(self, *, tramite: str, estado_reclamante: str, estado_flujo: str) -> bool:
        total = self.repository.count_reclamantes_by_tramite(tramite)
        total_estado = self.repository.count_reclamantes_by_tramite_estado(tramite=tramite, estado=estado_reclamante)
        if total > 0 and total == total_estado:
            ok_ws, _ = self._pension_actualiza_estado_solicitud(
                tramite=tramite,
                estado_as="PAG",
                estado_flujo=estado_flujo,
                usuario="IMAGINE",
            )
            if not ok_ws:
                self.repository.change_estado_solicitud(tramite=tramite, new_estado=estado_flujo)
            return True
        return False

    def _pension_actualiza_estado_solicitud(
        self, *, tramite: str, estado_as: str, estado_flujo: str, usuario: str
    ) -> tuple[bool, str]:
        mode = os.getenv("PENSION_ACTUALIZA_MODE", "local").strip().lower()
        if mode != "real":
            return False, "local_mode"
        wsdl = os.getenv("WSDL_PENSION", "").strip()
        endpoint = os.getenv("ENDPOINTURI_PENSION", "").strip()
        if not wsdl:
            return False, "missing_wsdl_pension"
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
            result = client.service.estadoSolicitudActualizacion(
                estadoSolicitudActualizacionEntrada={
                    "Cabecera": "",
                    "idSolicitud": str(tramite),
                    "tipoSolicitud": "AUF",
                    "estado": estado_as,
                    "usuario": usuario or "IMAGINE",
                }
            )
            payload = json.loads(json.dumps(result, default=str))
            serialized = json.dumps(payload, ensure_ascii=False)
            ok = ('"Codigo": "0"' in serialized) or ('"Codigo":"0"' in serialized)
            if ok:
                self.repository.change_estado_solicitud(tramite=tramite, new_estado=estado_flujo)
                return True, "ws_ok"
            return False, "ws_codigo_no_ok"
        except Exception as exc:
            return False, str(exc)

    def envia_contabilizacion_optima(self, *, tramite: str, idrecla: str, usuario: str, asulado: bool) -> dict:
        pago = self.repository.get_pago_para_cpp(tramite=tramite, identificacion=idrecla)
        if not pago:
            return {"ok": False, "status": "Error", "msg": "No se encontró información de pago para el reclamante."}

        # Compatibilidad temporal: se simula resultado OK de generaCPP para flujo local.
        estado_reclamante = "Interfaz Asulado Generada" if asulado else "Interfaz Fiducia Generada"
        estado_flujo = "AUXILIO ASULADO PAGADO" if asulado else "AUXILIO FIDUCIA PAGADO"
        affected = self.repository.update_estado_reclamante_by_tramite_identificacion(
            tramite=tramite,
            identificacion=idrecla,
            estado=estado_reclamante,
        )
        cerrado = self._cerrar_solicitud_si_aplica(
            tramite=tramite,
            estado_reclamante=estado_reclamante,
            estado_flujo=estado_flujo,
        )
        self.state_machine.register_event(
            "fun_cpp",
            f"{tramite}_{idrecla}",
            "envia_contabilizacion_optima",
            {
                "usuario": usuario,
                "asulado": asulado,
                "affected": affected,
                "cerrado": cerrado,
                "cpp_externo": "simulado",
            },
        )
        if affected <= 0:
            return {"ok": False, "status": "Error", "msg": "Se presento un error al generar la interfaz contable, por favor intente nuevamente"}
        return {
            "ok": True,
            "status": "OK",
            "msg": "Interfaces generadas exitosamente",
            "affected": affected,
            "tramite_cerrado": cerrado,
            "nota": "Consumo CPP externo pendiente; en esta fase se simula exito para mantener flujo funcional local.",
        }

    def _sap_send(self, payload: dict) -> tuple[bool, str]:
        mode = os.getenv("SAP_CONTABILIDAD_MODE", "stub_success").strip().lower()
        if mode == "stub_error":
            return False, "Modo stub_error configurado"
        if mode != "real":
            return True, "Modo stub_success"
        wsdl = os.getenv("WSDL_SAP_CONTABILIDAD", os.getenv("SAP_CONTABILIDAD_WSDL", "")).strip()
        endpoint = os.getenv("ENDPOINTURI_SAP_CONTABILIDAD", os.getenv("SAP_CONTABILIDAD_ENDPOINT", "")).strip()
        if not wsdl:
            return False, "WSDL_SAP_CONTABILIDAD no configurado"
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
            result = client.service.ContabilidadSAP_solicitarRegistro(payload)
            salida = getattr(result, "DocumentoContableRegistroSalida", None)
            ok = bool(getattr(salida, "entregaExitosa", False))
            return ok, "SOAP OK" if ok else "SOAP respuesta negativa"
        except Exception as exc:
            return False, str(exc)

    def _build_parametros_sap(self, *, guid: str, pago: dict, usuario: str) -> dict:
        valor = float(pago.get("valor_reconocido") or 0)
        forma_pago = str(pago.get("forma_pago") or "")
        banco = str(pago.get("entidad_bancaria") or "") if forma_pago == "Transferencia" else ""
        cuenta = str(pago.get("numero_cuenta") or "") if forma_pago == "Transferencia" else ""
        documento_referencia = self.repository.next_interfaz_sequence() or 0
        ip = os.getenv("SERVICES_IP", os.getenv("SERVICE_IP", "")).strip()
        terceros = {
            "Tercero": [
                {
                    "Identificacion": {
                        "tipoId": str(pago.get("tipoid_beneficiario") or ""),
                        "identificacion": str(pago.get("identificacion") or ""),
                    },
                    "nombre": str(pago.get("nombre_beneficiario") or ""),
                    "formaPago": forma_pago,
                    "monedaPago": "COP",
                    "Cuentas": [
                        {
                            "codigo": "2501080030",
                            "centroCostos": "CO02VO0144",
                            "valorCredito": valor,
                            "valorDebito": 0,
                            "descripcion": "AUXILIOS FUNERARIOS",
                            "CuentaBancaria": {
                                "codigoBanco": banco,
                                "cuentaBancaria": cuenta,
                            },
                        }
                    ],
                },
                {
                    "Identificacion": {
                        "tipoId": "NIT",
                        "identificacion": str(pago.get("nit_aseguradora") or ""),
                    },
                    "nombre": str(pago.get("nombre_aseguradora") or ""),
                    "formaPago": "",
                    "monedaPago": "",
                    "Cuentas": [
                        {
                            "codigo": "1605040106",
                            "centroCostos": "CO02VO0144",
                            "valorCredito": 0,
                            "valorDebito": valor,
                            "descripcion": "AUXILIOS FUNERARIOS",
                            "CuentaBancaria": {
                                "codigoBanco": "",
                                "cuentaBancaria": "",
                            },
                        }
                    ],
                },
            ]
        }
        return {
            "DocumentoContableRegistroEntrada": {
                "idAplicacion": "151",
                "uuidTransaccion": guid,
                "numeroRegistros": "1",
                "valorTotalCreditos": valor,
                "valorTotalDebitos": valor,
                "descripcion": "AUXILIOS FUNERARIOS",
                "fechaTransaccion": date.today().isoformat(),
                "usuario": usuario,
                "direccionIP": ip,
                "Transacciones": {
                    "Transaccion": {
                        "documentoReferencia": documento_referencia,
                        "Terceros": terceros,
                    }
                },
            }
        }

    def envia_contabilizacion(self, *, tramites: list[str], usuario: str) -> dict:
        items: list[dict] = []
        enviados = 0
        for raw in tramites:
            token = str(raw or "").strip()
            if not token:
                continue
            if "_" not in token:
                items.append({"token": token, "status": "error", "detail": "Formato invalido, esperado tramite_reclamante"})
                continue
            tramite, idrecla = token.split("_", 1)
            pago = self.repository.get_pago_para_sap(tramite=tramite, identificacion=idrecla)
            if not pago:
                items.append({"tramite": tramite, "reclamante": idrecla, "status": "error", "detail": "No se encontro informacion de pago"})
                continue

            guid = str(uuid.uuid4()).lower()
            payload = self._build_parametros_sap(guid=guid, pago=pago, usuario=usuario)
            ok, detail = self._sap_send(payload)
            if ok:
                self.repository.insert_transaccion_sap(
                    uuid=guid,
                    tramite=tramite,
                    reclamante=idrecla,
                    tipo_proceso="Contabilizacion",
                    estado="Enviado",
                    parametros_json=json.dumps(payload, ensure_ascii=False),
                )
                self.repository.update_estado_reclamante_by_tramite_identificacion(
                    tramite=tramite,
                    identificacion=idrecla,
                    estado="En Espera Respuesta Generica",
                )
                enviados += 1
                items.append({"tramite": tramite, "reclamante": idrecla, "status": "ok", "uid": guid, "detail": detail})
            else:
                items.append({"tramite": tramite, "reclamante": idrecla, "status": "error", "uid": "", "detail": detail})

        self.state_machine.register_event(
            "fun_sap",
            "contabilizacion_masiva",
            "envia_contabilizacion",
            {"usuario": usuario, "total": len(tramites), "enviados": enviados},
        )
        return {
            "ok": True,
            "status": "OK",
            "total": len(tramites),
            "enviados": enviados,
            "items": items,
            "mode": os.getenv("SAP_CONTABILIDAD_MODE", "stub_success"),
        }

    def _sync_fetch_beneficiarios(
        self, *, cedula: str, tramite: str, tipo_id: str, payload: dict
    ) -> tuple[list[dict], str]:
        if isinstance(payload.get("beneficiarios"), list):
            return list(payload.get("beneficiarios") or []), "payload"
        mode = os.getenv("SYNC_BENEFICIARIOS_MODE", "stub_empty").strip().lower()
        if mode != "real":
            return [], mode
        wsdl = os.getenv("WSDL_PENSION", os.getenv("WS_PENSION_WSDL", "")).strip()
        endpoint = os.getenv("ENDPOINTURI_PENSION", os.getenv("WS_PENSION_ENDPOINT", "")).strip()
        if not wsdl:
            return [], "real_missing_wsdl"
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
            result = client.service.solicitudAfiliadoConsulta(
                solicitudAfiliadoConsultaEntrada={
                    "Cabecera": "",
                    "identificacionAfiliado": {"tipoId": (tipo_id or "CC"), "id": cedula},
                    "tipoSolicitud": "AUF",
                }
            )
            salida = getattr(result, "solicitudAfiliadoConsultaSalida", None)
            lista = getattr(salida, "listaSolicitud", None)
            tram = str(getattr(lista, "idSolicitud", "") or "")
            if tram != tramite:
                return [], "real_tramite_no_match"
            benef_raw = getattr(lista, "listaBeneficiario", None) or []
            if isinstance(benef_raw, dict):
                benef_raw = [benef_raw]
            parsed: list[dict] = []
            for b in benef_raw:
                ident = getattr(b, "identificacion", None)
                parsed.append(
                    {
                        "tipoid_beneficiario": str(getattr(ident, "tipoId", "") or ""),
                        "identificacion": str(getattr(ident, "id", "") or ""),
                        "nombre_beneficiario": str(getattr(b, "nombreCompleto", "") or ""),
                        "direccion": str(getattr(b, "direccion", "") or ""),
                        "telefono_beneficiario": str(getattr(b, "telefono", "") or ""),
                    }
                )
            return parsed, "real"
        except Exception:
            return [], "real_error"

    def sincronizar_reclamantes(self, *, tramite: str, cedula: str, usuario: str, payload: dict) -> dict:
        if not self.repository.exists_solicitud_sincronizable(cedula):
            return {
                "ok": False,
                "status": "Error",
                "msg": "El caso se encuentra en un estado en el cual no es posible hacer la sincronización, deben cargar el nuevo reclamante en un trámite nuevo",
            }

        beneficiarios, source = self._sync_fetch_beneficiarios(
            cedula=cedula,
            tramite=tramite,
            tipo_id="CC",
            payload=payload,
        )
        nuevos = 0
        for b in beneficiarios:
            ident = str(b.get("identificacion", "")).strip()
            if not ident:
                continue
            if self.repository.exists_reclamante_tramite_ident(tramite=tramite, identificacion=ident):
                continue
            self.repository.insert_reclamante_basico(
                tramite=tramite,
                tipoid_beneficiario=str(b.get("tipoid_beneficiario", "")).strip() or "CC",
                identificacion=ident,
                nombre_beneficiario=str(b.get("nombre_beneficiario", "")).strip(),
                direccion=str(b.get("direccion", "")).strip(),
                telefono_beneficiario=str(b.get("telefono_beneficiario", "")).strip(),
                usuario=usuario,
            )
            nuevos += 1

        self.state_machine.register_event(
            "fun_reclamante",
            tramite,
            "sincronizar",
            {"usuario": usuario, "cedula": cedula, "nuevos": nuevos, "source": source},
        )
        return {
            "ok": True,
            "status": "OK",
            "msg": f"Sincronización exitosa, se han agregado {nuevos} reclamantes",
            "nuevos": nuevos,
            "source": source,
        }

    def _tercero_existe_consulta(self, lista_terceros: list[dict]) -> tuple[list[str], str]:
        mode = os.getenv("TERCERO_EXISTE_MODE", "local_all").strip().lower()
        if mode != "real":
            return [str(x.get("id", "")) for x in lista_terceros if str(x.get("id", "")).strip()], mode
        wsdl = os.getenv("WSDL_SAP_TERCERO", os.getenv("WSDL_CONTABILIDAD", "")).strip()
        endpoint = os.getenv("ENDPOINTURI_SAP_TERCERO", os.getenv("ENDPOINTURI_CONTABILIDAD", "")).strip()
        if not wsdl:
            return [], "real_missing_wsdl"
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
            result = client.service.terceroExisteConsulta(
                terceroExisteConsultaEntrada={
                    "Cabecera": "",
                    "listaTercero": lista_terceros,
                    "fondo": "AFP",
                }
            )
            payload = json.loads(json.dumps(result, default=str))
            raw = json.dumps(payload, ensure_ascii=False)
            ids = re.findall(r'"id"\s*:\s*"([^"]+)"', raw)
            return ids, "real"
        except Exception:
            return [], "real_error"

    def _tercero_crear(self, *, directorio: dict, datos: dict, cuenta_corriente: dict) -> tuple[bool, str]:
        mode = os.getenv("TERCERO_CREAR_MODE", "stub_success").strip().lower()
        if mode == "stub_error":
            return False, "stub_error"
        if mode != "real":
            return True, "stub_success"
        wsdl = os.getenv("WSDL_SAP_TERCERO", os.getenv("WSDL_CONTABILIDAD", "")).strip()
        endpoint = os.getenv("ENDPOINTURI_SAP_TERCERO", os.getenv("ENDPOINTURI_CONTABILIDAD", "")).strip()
        if not wsdl:
            return False, "real_missing_wsdl"
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
            result = client.service.terceroCrear(
                terceroCrearEntrada={
                    "Cabecera": "",
                    "directorio": directorio,
                    "datos": datos,
                    "cuentaCorriente": cuenta_corriente,
                    "fondo": "AFP",
                    "usuarioCreacion": "AMONSALV",
                }
            )
            payload = json.loads(json.dumps(result, default=str))
            raw = json.dumps(payload, ensure_ascii=False)
            ok = ('"Codigo": "0"' in raw) or ('"Codigo":"0"' in raw)
            return ok, "real_ok" if ok else "real_codigo_no_ok"
        except Exception as exc:
            return False, str(exc)

    def _valida_nuevo_reclamante_crear_tercero(
        self, *, cc_afiliado: str, tramite: str, tipoid_afiliado: str, usuario: str
    ) -> bool:
        beneficiarios, _ = self._sync_fetch_beneficiarios(
            cedula=cc_afiliado,
            tramite=tramite,
            tipo_id=tipoid_afiliado or "CC",
            payload={},
        )
        nuevo = False
        for ben in beneficiarios:
            id_reclamante = str(ben.get("identificacion", "")).strip()
            if not id_reclamante:
                continue
            if self.repository.exists_reclamante_tramite_ident(tramite=tramite, identificacion=id_reclamante):
                continue
            if self.repository.exists_solicitud_by_afiliado_tramite(afiliado=id_reclamante, tramite=tramite):
                continue
            self.repository.insert_reclamante_basico(
                tramite=tramite,
                tipoid_beneficiario=str(ben.get("tipoid_beneficiario", "")).strip() or "CC",
                identificacion=id_reclamante,
                nombre_beneficiario=str(ben.get("nombre_beneficiario", "")).strip(),
                direccion=str(ben.get("direccion", "")).strip(),
                telefono_beneficiario=str(ben.get("telefono_beneficiario", "")).strip(),
                usuario=usuario,
            )
            nuevo = True
        if nuevo:
            self.repository.change_estado_solicitud(tramite=tramite, new_estado="Reasignar Valores")
            return False
        return True

    def crear_terceros(self, *, usuario: str) -> dict:
        rows = self.repository.list_reclamantes_aprobados_para_terceros()
        if not rows:
            return {"ok": True, "respuesta": "No existen registros para procesar", "count": 0}

        lista_tercero: list[dict] = []
        tramites_por_reclamante: dict[str, str] = {}
        for rw in rows:
            cc = str(rw.get("id_afiliado") or "").strip()
            tramite = str(rw.get("tramite") or "").strip()
            tipoid_afi = str(rw.get("tipoid_afiliado") or "CC").strip()
            puede = self._valida_nuevo_reclamante_crear_tercero(
                cc_afiliado=cc,
                tramite=tramite,
                tipoid_afiliado=tipoid_afi,
                usuario=usuario,
            )
            if not puede:
                continue
            ccrec = str(rw.get("identificacion") or "").strip()
            tpidrec = str(rw.get("tipoid_beneficiario") or "CC").strip()
            if not ccrec:
                continue
            lista_tercero.append({"id": ccrec, "tipoId": tpidrec})
            tramites_por_reclamante[ccrec] = tramite

        if not lista_tercero:
            return {"ok": True, "respuesta": "No existen registros para procesar", "count": 0}

        validas, mode_exists = self._tercero_existe_consulta(lista_tercero)
        creados = 0
        errores = 0
        detalle: list[dict] = []
        for ccr in validas:
            tramiter = tramites_por_reclamante.get(ccr, "")
            if not tramiter:
                continue
            rec = self.repository.get_reclamante_core(tramite=tramiter, identificacion=ccr)
            if not rec:
                errores += 1
                detalle.append({"reclamante": ccr, "status": "error", "detail": "Reclamante no encontrado"})
                continue
            nombre = str(rec.get("nombre_beneficiario") or "").strip()
            nombres = [n for n in re.split(r"\s+", nombre) if n]
            while len(nombres) < 4:
                nombres.append("")
            tipoid = str(rec.get("tipoid_beneficiario") or "CC").strip()
            clase = "SIM" if tipoid == "NIT" else "COM"
            directorio = {
                "identificacionTercero": {"id": ccr, "tipoId": tipoid},
                "digitoChequeo": "",
                "direccion": str(rec.get("direccion") or ""),
                "telefono": str(rec.get("telefono_beneficiario") or ""),
                "claseTercero": clase,
            }
            datos = {
                "primerNombre": nombres[0],
                "segundoNombre": nombres[1],
                "primerApellido": nombres[2],
                "segundoApellido": nombres[3],
                "razonSocial": nombres,
                "codigoArea": "0",
                "idPais": "169",
                "idDepartamento": "05",
                "idCiudad": "05001",
                "ciudad": "MEDELLIN",
                "tipoContribuyente": "",
                "estado": "A",
                "representante": nombres,
                "tipoRegimen": "0",
                "fax": str(rec.get("telefono_beneficiario") or ""),
                "email": "",
                "icaCompras": "0",
                "icaServicios": "0",
                "rteCompras": "0",
                "rteServicios": "0",
                "idActividad": "",
                "origen": "",
            }
            cuenta_corriente = {
                "idBanco": "0",
                "cuentaContable": "",
                "tipoCuenta": "",
                "numeroCuenta": "",
                "bancoCuenta": "",
                "ciudadCuenta": "",
            }
            ok, detail = self._tercero_crear(
                directorio=directorio,
                datos=datos,
                cuenta_corriente=cuenta_corriente,
            )
            if ok:
                creados += 1
                detalle.append({"reclamante": ccr, "status": "ok", "detail": detail})
            else:
                errores += 1
                detalle.append({"reclamante": ccr, "status": "error", "detail": detail})

        for item in lista_tercero:
            rid = str(item.get("id") or "").strip()
            sol = tramites_por_reclamante.get(rid, "")
            if not rid or not sol:
                continue
            self.repository.update_estado_reclamante_by_tramite_identificacion(
                tramite=sol,
                identificacion=rid,
                estado="Crear CPP",
            )

        self.state_machine.register_event(
            "fun_terceros",
            "crear_terceros",
            "crear_terceros",
            {
                "usuario": usuario,
                "candidatos": len(lista_tercero),
                "creados": creados,
                "errores": errores,
                "mode_exists": mode_exists,
                "mode_crear": os.getenv("TERCERO_CREAR_MODE", "stub_success"),
            },
        )
        return {
            "ok": True,
            "respuesta": "Ha finalizado el proceso de creacion de terceros Exitosamente",
            "candidatos": len(lista_tercero),
            "creados": creados,
            "errores": errores,
            "detalle": detalle,
        }

    def cargar_respuesta_transferencia(self, *, usuario: str) -> dict:
        self.state_machine.register_event(
            "fun_ui",
            "cargar_respuesta_transferencia",
            "cargar_respuesta_transferencia",
            {"usuario": usuario},
        )
        return {
            "ok": True,
            "status": "OK",
            "view": "cargarRespuestaTrans",
            "message": "Vista legacy convertida a respuesta estructurada para frontend React.",
        }

    def adjuntar_soportes(self, *, usuario: str) -> dict:
        self.state_machine.register_event(
            "fun_ui",
            "adjuntar_soportes",
            "adjuntar_soportes",
            {"usuario": usuario},
        )
        return {
            "ok": True,
            "status": "OK",
            "view": "adjuntarSoportes",
            "message": "Vista legacy convertida a respuesta estructurada para frontend React.",
        }

    def clasifica_imagenes(self, *, tramite: str, usuario: str) -> dict:
        solicitud = self.repository.get_solicitud_funeraria(tramite)
        if not solicitud:
            return {"ok": False, "status": "Error", "msg": "Tramite no encontrado"}
        reclamantes = self.repository.list_reclamantes_para_clasificacion(tramite)
        imagenes = self.repository.list_imagenes_afiliado(str(solicitud.get("id_afiliado") or ""))
        items = []
        for row in reclamantes:
            fpago = str(row.get("forma_pago") or "")
            items.append(
                {
                    "id_ben": row.get("id_ben"),
                    "identificacion": str(row.get("identificacion") or "").strip(),
                    "tipoid_beneficiario": str(row.get("tipoid_beneficiario") or "").strip(),
                    "nombre_beneficiario": str(row.get("nombre_beneficiario") or "").strip(),
                    "telefono_beneficiario": str(row.get("telefono_beneficiario") or "").strip(),
                    "direccion": str(row.get("direccion") or "").strip(),
                    "forma_pago": fpago,
                    "numero_cuenta": str(row.get("numero_cuenta") or "").strip(),
                    "entidad_bancaria": str(row.get("entidad_bancaria") or "").strip(),
                    "tipo_cuenta": str(row.get("tipo_cuenta") or "").strip(),
                    "analisis_documental_default": {
                        "soporte_factura": "N",
                        "soporte_cuenta": "N" if fpago == "Transferencia" else None,
                    },
                }
            )
        self.state_machine.register_event(
            "fun_ui",
            tramite,
            "clasifica_imagenes",
            {"usuario": usuario, "reclamantes": len(items), "imagenes": len(imagenes)},
        )
        return {
            "ok": True,
            "status": "OK",
            "tramite": tramite,
            "afiliado": solicitud,
            "reclamantes": items,
            "imagenes": imagenes,
            "count_reclamantes": len(items),
            "count_imagenes": len(imagenes),
        }

    def registrar_causal_rechazo(self, *, tramite: str, causal: str, usuario: str) -> dict:
        ws_ok, ws_detail = self._pension_actualiza_estado_solicitud(
            tramite=tramite,
            estado_as="RCH",
            estado_flujo="Rechazado",
            usuario=usuario or "IMAGINE",
        )
        affected = self.repository.update_solicitud_rechazada(tramite=tramite, sub_estado=causal)
        actividad = self.repository.insert_actividad(
            tramite=tramite,
            usuario=usuario,
            descripcion=f"RECHAZO DE SOLICITUDES AS400 - {causal}",
        )
        self.state_machine.register_event(
            "fun_solicitud",
            tramite,
            "registrar_causal_rechazo",
            {
                "usuario": usuario,
                "causal": causal,
                "affected": affected,
                "actividad": actividad,
                "ws_ok": ws_ok,
                "ws_detail": ws_detail,
            },
        )
        return {
            "ok": affected > 0,
            "status": "OK" if affected > 0 else "Error",
            "tramite": tramite,
            "causal": causal,
            "affected": affected,
            "ws_ok": ws_ok,
            "ws_detail": ws_detail,
            "msg": "Causal de rechazo registrada",
        }

    def guardar_avance_tercero(self, *, tramite: str, cc: str, payload: dict, usuario: str) -> dict:
        prefix_fields = [
            "tratamiento",
            "abreviatura",
            "region",
            "poblacion",
            "movil",
            "fax",
            "email",
            "ct_cod_banco",
            "ct_cuenta_bancaria",
            "ct_titular",
            "ct_tipo_cuenta",
            "ct_referencia",
            "ct_swift",
            "ct_iban",
            "ct_aba",
            "dc_documento1",
            "dc_documento2",
            "dc_documento3",
            "dc_tipo_doc",
            "dc_clase_impuesto",
            "dc_ciiu",
            "s_codigo",
            "s_cuenta_asociada",
            "s_grupo_tesoreria",
            "ct_condicion_pago",
            "ct_via_pago",
            "ct_bloqueado",
            "ir_tipo_retencion",
            "ir_indicador_retencion",
            "ir_indicador_sujeto",
            "ir_categoria_retencion",
        ]

        def _field(name: str) -> str:
            return str(payload.get(f"{name}_{cc}", payload.get(name, "")) or "").strip()

        data = {k: _field(k) for k in prefix_fields}
        rec = self.repository.get_reclamante_core(tramite=tramite, identificacion=cc)
        if not rec:
            return {"ok": False, "status": "Error", "msg": "Reclamante no encontrado para el tramite"}

        tipo_id = str(rec.get("tipoid_beneficiario") or "").strip()
        direccion = str(rec.get("direccion") or "").strip()
        telefono = str(rec.get("telefono_beneficiario") or "").strip()
        nombre = str(rec.get("nombre_beneficiario") or "").strip()
        nombres = [n for n in nombre.split(" ") if n]
        tercero_id = self.repository.get_tercero_id_by_identificacion(cc)
        if tercero_id is None:
            tercero_id = self.repository.next_tercero_id()

        result = self.repository.upsert_avance_tercero(
            tercero_id=tercero_id,
            identificacion=cc,
            tipo_id=tipo_id,
            nombres=nombres,
            direccion=direccion,
            telefono=telefono,
            data=data,
        )
        self.state_machine.register_event(
            "fun_terceros",
            cc,
            "guardar_avance_tercero",
            {"usuario": usuario, "tramite": tramite, "tercero_id": tercero_id},
        )
        return {"ok": True, "status": "OK", "msg": "OK", **result}
