# AFILEGA - aprendizaje RAG con dos paquetes reales de afiliacion

Fecha de carga: 2026-05-10.
Proyecto: AFILEGA_FA_IMA_LA_V2.
Origen: bandeja de entrada local, paquetes multipdf separados y OCR por pagina.

Este documento alimenta el RAG con lo observado en dos contratos reales cargados en la bandeja: una entrada de tipo empresa y una entrada de tipo contratista. El objetivo es que el asistente conozca como se comportan los paquetes multipdf reales, que documentos se detectaron, que campos se pudieron prellenar y que alertas debe sugerir al operador.

## Regla aprendida de entrada

La bandeja de entrada de afiliaciones trabaja con dos tipos:

- Empresa: entrada para contratante, sedes, centros de trabajo y trabajadores asociados. El prellenado de Digitacion debe marcar `tipo_afiliacion=colectiva`.
- Contratista: entrada para trabajador independiente o contratista. El prellenado de Digitacion debe marcar `tipo_afiliacion=individual`.

Ambas entradas pueden traer un PDF multipagina. El sistema debe explotar el PDF en paginas individuales, OCR por cada pagina y clasificar cada pagina como documento independiente cuando aplique. Lo que se lea en OCR se lleva a `analysis.digitacion_prefill.values`, con trazabilidad en `analysis.digitacion_prefill.sources`.

Los valores OCR de baja calidad, textos cortados o cadenas con ruido no deben aceptarse automaticamente como definitivos. Deben aparecer como prellenado operativo y el operador debe confirmar contra la imagen/documento antes de generar archivo 926.

## Caso real: paquete Empresa

Case ID: `case-colima-849c7f2999`.
Label: `afi-1778444541186`.
Tipo de entrada: `empresa`.
Estado: `analyzed`.
Creado: `2026-05-10T20:22:21.284915+00:00`.
Actualizado: `2026-05-10T20:22:53.689234+00:00`.

El paquete `EMPRESA` se exploto en 29 paginas PDF: `EMPRESA__p001.pdf` a `EMPRESA__p029.pdf`. Todas las paginas tuvieron OCR (`ocr_documents_ok=29`).

Documentos clasificados en el paquete Empresa:

| Tipo documental | Cantidad | Archivos |
| --- | ---: | --- |
| Autorizacion Uso Datos Personales | 4 | `EMPRESA__p017.pdf`, `EMPRESA__p022.pdf`, `EMPRESA__p025.pdf`, `EMPRESA__p028.pdf` |
| Camara de Comercio de la empresa contratante | 1 | `EMPRESA__p026.pdf` |
| Cedula de representante legal o trabajador independiente | 1 | `EMPRESA__p013.pdf` |
| Centros de trabajo | 5 | `EMPRESA__p002.pdf`, `EMPRESA__p019.pdf`, `EMPRESA__p020.pdf`, `EMPRESA__p021.pdf`, `EMPRESA__p027.pdf` |
| Formulario de Afiliacion firmado | 3 | `EMPRESA__p008.pdf`, `EMPRESA__p018.pdf`, `EMPRESA__p023.pdf` |
| Relacion de ingreso de trabajadores | 1 | `EMPRESA__p029.pdf` |
| Copia RUT del Contratista | 2 | `EMPRESA__p011.pdf`, `EMPRESA__p012.pdf` |
| Pagos seguridad social | 1 | `EMPRESA__p007.pdf` |
| Paginas no clasificadas / imagen generica | 11 | `EMPRESA__p001.pdf`, `EMPRESA__p003.pdf`, `EMPRESA__p004.pdf`, `EMPRESA__p005.pdf`, `EMPRESA__p006.pdf`, `EMPRESA__p009.pdf`, `EMPRESA__p010.pdf`, `EMPRESA__p014.pdf`, `EMPRESA__p015.pdf`, `EMPRESA__p016.pdf`, `EMPRESA__p024.pdf` |

Prellenado OCR generado para Digitacion en el caso Empresa:

| Campo Digitacion | Valor leido | Fuente | Confianza |
| --- | --- | --- | ---: |
| `tipo_tramite` | `afiliacion` | regla de entrada | 0.99 |
| `tipo_afiliacion` | `colectiva` | regla de entrada | 0.99 |
| `razon_social` | `W IRISTA 4 CiAS AS 2. Tipo de documento` | perfil/OCR de empleador | 0.78 |
| `nit` | `830119224` | perfil/OCR de empleador | 0.80 |
| `direccion_empresa` | `seccional Sb in dectonico 830119 2 2 4` | formulario/OCR sede principal | 0.72 |
| `sede_nombre` | `W IRISTA 4 CiAS AS 2. Tipo de documento` | formulario sede principal | 0.72 |
| `sede_codigo` | `1` | formulario sede principal | 0.72 |
| `sede_direccion` | `seccional Sb in dectonico 830119 2 2 4` | formulario sede principal | 0.72 |
| `tipo_documento_afiliado` | `CC` | OCR/documento de identidad | 0.70 |
| `documento_afiliado` | `330149223` | OCR/documento de identidad | 0.78 |
| `eps` | `Poe - Li 165` | certificacion EPS/OCR | 0.62 |
| `afp` | `RESENTATIVE DE CAPITAL. DB` | certificacion AFP/OCR | 0.62 |

Decision documental del caso Empresa:

- Estado recomendado: observado.
- Motivo principal: no se pudo leer la razon social en Camara de Comercio para comparar contra Excel/Formulario.
- Aprendizaje: cuando Camara de Comercio existe pero el OCR no logra extraer razon social confiable, el sistema debe pedir validacion manual de razon social antes de aprobar o generar archivo 926.
- Aprendizaje: EPS/AFP con texto ruidoso en prellenado no debe pasar validacion de catalogo; se debe confirmar desde certificacion real o catalogos EPS/AFP.

## Caso real: paquete Contratista

Case ID: `case-colima-6104b466ae`.
Label: `afi-1778444594468`.
Tipo de entrada: `contratista`.
Estado: `analyzed`.
Creado: `2026-05-10T20:23:14.558573+00:00`.
Actualizado: `2026-05-10T20:23:59.162517+00:00`.

El paquete `CONTRATRISTA` se exploto en 32 paginas PDF: `CONTRATRISTA__p001.pdf` a `CONTRATRISTA__p032.pdf`. Todas las paginas tuvieron OCR (`ocr_documents_ok=32`). Nota: el nombre de archivo venia con la grafia `CONTRATRISTA`; el sistema debe tratarlo como paquete de entrada `contratista` por el selector de bandeja, no por el nombre del archivo.

Documentos clasificados en el paquete Contratista:

| Tipo documental | Cantidad | Archivos |
| --- | ---: | --- |
| Carta de presentacion del trabajador por parte del Contratante | 2 | `CONTRATRISTA__p001.pdf`, `CONTRATRISTA__p002.pdf` |
| Autorizacion Uso Datos Personales | 2 | `CONTRATRISTA__p008.pdf`, `CONTRATRISTA__p030.pdf` |
| Camara de Comercio de la empresa contratante | 1 | `CONTRATRISTA__p016.pdf` |
| Certificacion de afiliacion del trabajador a la AFP | 1 | `CONTRATRISTA__p024.pdf` |
| Contrato entre contratista y contratante | 5 | `CONTRATRISTA__p004.pdf`, `CONTRATRISTA__p005.pdf`, `CONTRATRISTA__p006.pdf`, `CONTRATRISTA__p025.pdf`, `CONTRATRISTA__p026.pdf` |
| Copia RUT del Contratista | 4 | `CONTRATRISTA__p020.pdf`, `CONTRATRISTA__p021.pdf`, `CONTRATRISTA__p022.pdf`, `CONTRATRISTA__p023.pdf` |
| Pagos seguridad social | 2 | `CONTRATRISTA__p027.pdf`, `CONTRATRISTA__p029.pdf` |
| Paginas no clasificadas / imagen generica | 15 | `CONTRATRISTA__p003.pdf`, `CONTRATRISTA__p007.pdf`, `CONTRATRISTA__p009.pdf`, `CONTRATRISTA__p010.pdf`, `CONTRATRISTA__p011.pdf`, `CONTRATRISTA__p012.pdf`, `CONTRATRISTA__p013.pdf`, `CONTRATRISTA__p014.pdf`, `CONTRATRISTA__p015.pdf`, `CONTRATRISTA__p017.pdf`, `CONTRATRISTA__p018.pdf`, `CONTRATRISTA__p019.pdf`, `CONTRATRISTA__p028.pdf`, `CONTRATRISTA__p031.pdf`, `CONTRATRISTA__p032.pdf` |

Prellenado OCR generado para Digitacion en el caso Contratista:

| Campo Digitacion | Valor leido | Fuente | Confianza |
| --- | --- | --- | ---: |
| `tipo_tramite` | `afiliacion` | regla de entrada | 0.99 |
| `tipo_afiliacion` | `individual` | regla de entrada | 0.99 |
| `razon_social` | `de PRINCEX 00 DOMBACIALTEROCRA SAS. e SPIO FABRICA UE CABLES ESPECIALES SAS. Por Acta Mo` | perfil/OCR de empleador | 0.78 |
| `nit` | `900313622` | perfil/OCR de empleador | 0.80 |
| `direccion_empresa` | `Estrategica` | formulario/OCR sede principal | 0.72 |
| `correo_empresa` | `ofuala@gmal.communicipio` | formulario/OCR | 0.76 |
| `sede_nombre` | `de PRINCEX 00 DOMBACIALTEROCRA SAS. e SPIO FABRICA UE CABLES ESPECIALES SAS. Por Acta Mo` | formulario sede principal | 0.72 |
| `sede_codigo` | `1` | formulario sede principal | 0.72 |
| `sede_direccion` | `Estrategica` | formulario sede principal | 0.72 |
| `sede_correo` | `ofuala@gmal.communicipio` | formulario sede principal | 0.72 |
| `tipo_documento_afiliado` | `CC` | OCR/documento de identidad | 0.70 |
| `documento_afiliado` | `1073157358` | OCR/documento de identidad | 0.78 |
| `eps` | `menor a 30 dias de expedicion` | certificacion EPS/OCR | 0.62 |
| `afp` | `menor a 30 dias de expedicion Para pensionado debe adjuntar copia de resolucion de pensi` | certificacion AFP/OCR | 0.62 |

Decision documental del caso Contratista:

- Estado recomendado: observado.
- Motivo principal: falta soporte obligatorio de Cedula de representante legal o trabajador independiente.
- Aprendizaje: aunque el OCR encontro `documento_afiliado=1073157358` en carta/contrato/autorizacion, el paquete no quedo satisfecho si no existe documento clasificado como Cedula. El RAG debe recomendar pedir o reclasificar manualmente la cedula si esta dentro de paginas no clasificadas.
- Aprendizaje: el selector de entrada `contratista` debe prevalecer sobre nombres de archivo con errores tipograficos.
- Aprendizaje: valores de EPS/AFP que son frases normativas o instrucciones del formato no son entidades validas; deben fallar contra catalogo EPS/AFP.

## Reglas operativas aprendidas para el RAG

1. Si una entrada es `empresa`, Digitacion debe iniciar con `tipo_afiliacion=colectiva`; si es `contratista`, debe iniciar con `tipo_afiliacion=individual`.
2. Un PDF multipagina debe explotarse por pagina y cada pagina debe tener OCR y clasificacion documental independiente.
3. El RAG debe explicar que el prellenado OCR es una ayuda de digitacion, no una aprobacion automatica.
4. Si un campo de prellenado tiene texto ruidoso, truncado, mezclado con etiquetas o no pasa catalogo, debe recomendar verificacion manual contra la imagen y no generar 926.
5. Para empresa, la Camara de Comercio debe permitir validar razon social; si el OCR no lee razon social, el caso queda observado aunque exista archivo de Camara.
6. Para contratista, la presencia de numero de documento en otros soportes no reemplaza el soporte clasificado como Cedula; si falta cedula, el caso queda observado.
7. Las certificaciones EPS/AFP deben aportar nombre de entidad o codigo homologable al catalogo. Frases como "menor a 30 dias de expedicion" no son EPS/AFP validas.
8. La tabla de documentos recibidos debe usarse como evidencia para checklist: `received_summary` agrupa por tipo documental, etiqueta, cantidad, codigos legados y archivos.
9. Cuando existan paginas `pdf` o `imagen` sin clasificacion, el operador debe revisar si alguna corresponde a un documento faltante y aplicar reclasificacion manual.
10. El RAG debe responder consultas de estos paquetes citando los case IDs y los archivos/paginas relevantes.

## Rutas locales de evidencia

- Empresa: `/data/cases/case-colima-849c7f2999/case.json`
- Contratista: `/data/cases/case-colima-6104b466ae/case.json`

