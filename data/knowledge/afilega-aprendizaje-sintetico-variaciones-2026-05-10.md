# AFILEGA - aprendizaje sintetico por variaciones controladas

Fecha de carga: 2026-05-10.
Proyecto: AFILEGA_FA_IMA_LA_V2.
Origen: variaciones sinteticas derivadas de los paquetes reales `case-colima-849c7f2999` y `case-colima-6104b466ae`.

Este documento no agrega nuevos datos reales. Usa los mismos patrones observados en empresa y contratista para entrenar reglas operativas, regresion de OCR, prellenado de Digitacion y decision previa al archivo 926.

## Escenarios sinteticos creados

### case-afilega-syn-empresa-completo-001 - Empresa multipdf completo aprobable

- Tipo de entrada: `empresa`.
- Decision esperada: `aprobable`.
- Documentos: Camara de Comercio de la empresa contratante original menor a 90 dias, Cedula de representante legal de la empresa contratante, Centros de trabajo, Copia RUT del Contratista, Formulario de Afiliacion. (firmado por ambas partes), Relacion de ingreso de trabajadores.
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=colectiva`, `razon_social=AFILEGA EMPRESA COMPLETA SAS`, `nit=901880001`, `sede_nombre=Principal`, `sede_codigo=1`, `sede_direccion=Calle 72 10 20`, `documento_afiliado=101880101`.
- Regla aprendida: El orden de paginas no importa si todos los soportes obligatorios se clasifican.
- Regla aprendida: Empresa completa debe proponer tipo_afiliacion colectiva.

### case-afilega-syn-empresa-desorden-002 - Empresa paginas desordenadas y autorizacion duplicada

- Tipo de entrada: `empresa`.
- Decision esperada: `aprobable`.
- Documentos: Autorizacion Uso Datos Personales, Camara de Comercio de la empresa contratante original menor a 90 dias, Formulario de Afiliacion. (firmado por ambas partes), Relacion de ingreso de trabajadores.
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=colectiva`, `razon_social=AFILEGA DESORDEN SAS`, `nit=901880002`, `sede_nombre=Principal`, `sede_codigo=1`.
- Regla aprendida: Las paginas desordenadas no deben afectar el resultado.
- Regla aprendida: Documentos duplicados se cuentan como evidencia repetida y no deben crear campos duplicados.

### case-afilega-syn-empresa-sin-camara-003 - Empresa sin Camara de Comercio

- Tipo de entrada: `empresa`.
- Decision esperada: `observado`.
- Documentos: Centros de trabajo, Copia RUT del Contratista, Formulario de Afiliacion. (firmado por ambas partes).
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=colectiva`, `razon_social=AFILEGA SIN CAMARA SAS`, `nit=901880003`, `sede_nombre=Principal`, `sede_codigo=1`.
- Bloqueos esperados: Falta Camara de Comercio de la empresa contratante menor a 90 dias..
- Regla aprendida: Si falta Camara de Comercio, no aprobar aunque formulario y RUT existan.
- Regla aprendida: RAG debe pedir soporte o reclasificacion manual si la camara esta en paginas no clasificadas.

### case-afilega-syn-empresa-ocr-ruido-004 - Empresa con OCR ruidoso en datos alfa y email

- Tipo de entrada: `empresa`.
- Decision esperada: `observado`.
- Documentos: Camara de Comercio de la empresa contratante original menor a 90 dias, Formulario de Afiliacion. (firmado por ambas partes).
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=colectiva`, `razon_social=AFILEGA 77 SAS Tipo de documento`, `correo_empresa=ofuala@gmal.communicipio`, `nit=901880004`, `eps=menor a 30 dias de expedicion`.
- Bloqueos esperados: Campos OCR ruidosos no deben pasar validacion alfa, email ni catalogo EPS..
- Regla aprendida: Campos alfa no aceptan numeros mezclados ni etiquetas de formulario.
- Regla aprendida: Correos con municipio/comuna o dominios mal leidos deben rechazarse.
- Regla aprendida: Frases normativas no son EPS/AFP validas.

### case-afilega-syn-contratista-completo-005 - Contratista multipdf completo aprobable

- Tipo de entrada: `contratista`.
- Decision esperada: `aprobable`.
- Documentos: Carta de presentacion del trabajador por parte del Contratante, Cedula de trabajador independiente / contratista, Certificacion de afiliacion del trabajador a la AFP, Certificacion de afiliacion del trabajador a la EPS, Contrato entre el contratista y el contratante, Formulario de Afiliacion. (firmado por ambas partes).
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=individual`, `nit=102880005`, `tipo_documento_afiliado=CC`, `documento_afiliado=102880005`, `eps=EPS SANITAS`, `afp=PROTECCION`, `sede_nombre=Principal`, `sede_codigo=1`.
- Regla aprendida: Contratista completo debe proponer tipo_afiliacion individual.
- Regla aprendida: EPS y AFP validas deben mapear contra catalogos.

### case-afilega-syn-contratista-sin-cedula-006 - Contratista con documento en contrato pero sin cedula

- Tipo de entrada: `contratista`.
- Decision esperada: `observado`.
- Documentos: Carta de presentacion del trabajador por parte del Contratante, Certificacion de afiliacion del trabajador a la EPS, Contrato entre el contratista y el contratante.
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=individual`, `nit=102880006`, `tipo_documento_afiliado=CC`, `documento_afiliado=102880006`.
- Bloqueos esperados: Falta soporte clasificado como Cedula de trabajador independiente / contratista..
- Regla aprendida: El numero de documento en carta o contrato no reemplaza la cedula.
- Regla aprendida: RAG debe sugerir buscar la cedula en paginas no clasificadas o pedir el soporte.

### case-afilega-syn-contratista-eps-afp-frase-007 - Contratista con EPS/AFP leidas como frases del formato

- Tipo de entrada: `contratista`.
- Decision esperada: `observado`.
- Documentos: Cedula de trabajador independiente / contratista, Certificacion de afiliacion del trabajador a la AFP, Certificacion de afiliacion del trabajador a la EPS, Formulario de Afiliacion. (firmado por ambas partes).
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=individual`, `documento_afiliado=102880007`, `eps=menor a 30 dias de expedicion`, `afp=para pensionado adjuntar resolucion de pension`.
- Bloqueos esperados: EPS y AFP no son entidades homologables; son instrucciones del formato..
- Regla aprendida: Frases del formato deben bloquear prellenado EPS/AFP.
- Regla aprendida: La certificacion puede existir pero aun requerir lectura manual de entidad.

### case-afilega-syn-contratista-duplicados-008 - Contratista con pagos y contrato duplicados

- Tipo de entrada: `contratista`.
- Decision esperada: `aprobable`.
- Documentos: Cedula de trabajador independiente / contratista, Contrato entre el contratista y el contratante, Formulario de Afiliacion. (firmado por ambas partes), Pagos seguridad social.
- Campos esperados de Digitacion: `tipo_tramite=afiliacion`, `tipo_afiliacion=individual`, `documento_afiliado=102880008`, `nit=102880008`, `sede_nombre=Principal`, `sede_codigo=1`.
- Regla aprendida: Duplicados no deben bloquear si existe al menos un soporte valido por tipo requerido.
- Regla aprendida: El resumen debe mostrar cantidad para auditoria.

## Reglas reforzadas

1. Repetir los mismos paquetes reales no agrega datos nuevos, pero si permite probar estabilidad, duplicados, orden de paginas y ruido OCR.
2. Las variaciones sinteticas deben marcarse como sinteticas y no mezclarse con evidencia real.
3. Para `empresa`, `tipo_afiliacion` esperado es `colectiva`; para `contratista`, `individual`.
4. Paginas desordenadas o duplicadas no deben cambiar la decision si los soportes obligatorios estan presentes.
5. Faltantes documentales como Camara de Comercio o Cedula deben dejar el caso observado aunque otros documentos mencionen la informacion.
6. Campos OCR ruidosos, correos mal leidos y frases normativas usadas como EPS/AFP deben bloquear prellenado automatico y pedir revision manual.
7. Un caso aprobable puede generar archivo 926; un caso observado debe detenerse antes de generar plano definitivo.
