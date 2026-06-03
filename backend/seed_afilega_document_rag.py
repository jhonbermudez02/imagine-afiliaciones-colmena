from __future__ import annotations

import uuid

from qdrant_client import QdrantClient, models

from app.cases import DOC_TYPE_TO_PRIMARY_CODE
from app.embeddings import embed_text, get_embed_dims


COLLECTION = "afi_doc_clasificaciones"

EXAMPLES = [
    ("carta_presentacion_trabajador", "Carta de presentacion del trabajador por parte del contratante. El contratante presenta al trabajador independiente para afiliacion ARL."),
    ("formulario_afiliacion", "Formulario de Afiliacion firmado por contratista y contratante. Incluye datos del empleador, trabajador, riesgo y firmas de ambas partes."),
    ("rut_contratista", "Registro Unico Tributario RUT del contratista expedido por la DIAN con NIT, actividad economica y responsabilidades tributarias."),
    ("autorizacion_uso_datos_personales", "Formato de autorizacion de uso y tratamiento de datos personales. Habeas data, autorizacion para recolectar y consultar informacion."),
    ("anexo_sedes", "SEDES. Sede principal, centros de trabajo, direccion, telefono, actividad economica y responsable del centro de trabajo."),
    ("solicitud_afiliacion_empleador", "Solicitud Afiliacion Empleador. Formato operativo para crear empleador y continuar radicacion de afiliacion."),
    ("solicitud_usuario_pagina_web", "Solicitud Usuario Pagina WEB. Creacion o habilitacion de usuario para portal web de afiliaciones."),
    ("camara_comercio_contratante", "Certificado de existencia y representacion legal de Camara de Comercio de la empresa contratante, expedicion menor a 90 dias."),
    ("contrato_contratista_contratante", "Contrato entre el contratista y el contratante. Objeto del contrato, valor, fecha inicial, fecha final y obligaciones."),
    ("cedula_representante_legal_contratante", "Cedula de ciudadania del representante legal de la empresa contratante. Documento de identificacion del firmante."),
    ("cedula_trabajador_independiente", "Cedula de trabajador independiente o contratista. Documento de identidad del afiliado independiente."),
    ("certificacion_afiliacion_eps", "Certificacion de afiliacion del trabajador a la EPS. Estado activo, fecha de expedicion menor a 30 dias."),
    ("certificacion_afiliacion_afp", "Certificacion de afiliacion del trabajador a la AFP o fondo de pensiones. Expedicion menor a 30 dias."),
    ("cedula_trabajadores", "Cedula de los trabajadores. Soportes de identidad de trabajadores relacionados para ingreso."),
    ("pagos_seguridad_social", "Pagos seguridad social. Planilla PILA, IBC, aportes, resumen general de pago y periodo de cotizacion."),
    ("paz_salvo_arl_anterior", "Paz y salvo con la anterior ARL. Certifica ausencia de deuda o novedades pendientes con ARL anterior."),
    ("carta_traslado_arl_anterior", "Carta Solicitud de traslado de la ARL anterior. Solicitud formal de traslado o desafiliacion por cambio de ARL."),
    ("contrato_trabajo_remoto", "Para trabajo remoto contrato con el trabajador. Acuerdo de trabajo remoto, funciones, lugar y condiciones."),
    ("relacion_ingreso_trabajadores", "Relacion de ingreso de trabajadores. Listado de trabajadores a ingresar con documento, nombres, cargo y salario."),
]


def main() -> None:
    client = QdrantClient(host="imagine_qdrant", port=6333)
    collections = {item.name for item in client.get_collections().collections}
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(size=get_embed_dims(), distance=models.Distance.COSINE),
        )
    points = []
    for document_type, text in EXAMPLES:
        vector = embed_text(text)
        points.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "case_id": "afilega-document-catalog",
                    "filename": f"{document_type}.txt",
                    "document_type": document_type,
                    "legacy_code": DOC_TYPE_TO_PRIMARY_CODE.get(document_type, 99),
                    "source": "afilega_catalog_seed",
                    "ocr_preview": text[:200],
                },
            )
        )
    client.upsert(collection_name=COLLECTION, points=points, wait=True)
    print(f"OK collection={COLLECTION} examples={len(points)}")


if __name__ == "__main__":
    main()
