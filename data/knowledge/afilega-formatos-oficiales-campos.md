# Formatos oficiales AFILEGA - estructura campo por campo

Fuente local revisada:

- `2_Formulario_Independientes_ARL_bc76e199a3.pdf`
- `2_Formulario_Independientes_ARL_bc76e199a3 (1).pdf`
- `2_Formulario_de_Afiliacion_Empresa_721d722e1f (1).pdf`
- `Resolucion-No-196-de-2026-1.pdf`
- `PLANTILLA_CARGUE_MASIVO_NUEVOS_AFILIADOS_ARL_9296e5e58d.xlsx`

Regla para el RAG: estos archivos son formatos patrón. Cuando una consulta pregunte qué es un formato, qué campos contiene, cómo validarlo o cómo comparar un documento cargado contra el formato esperado, debe usar esta referencia campo por campo.

## Diccionario de búsqueda para recuperación RAG

Este documento debe recuperarse como fuente principal para consultas como:

- "campos de la plantilla de cargue masivo nuevos afiliados ARL"
- "PLANTILLA_CARGUE_MASIVO_NUEVOS_AFILIADOS_ARL"
- "hoja PLANTILLA columnas A a BE"
- "qué significa No. de Afiliación, Número de sucursal, Código Actividades a ejecutar"
- "Formulario Independientes ARL campos contratante contratista IBC 40"
- "Formulario de Afiliación Empresa campos empleador representante legal"
- "Resolución 196 de 2026 formulario único de afiliación campos 1 a 71"
- "autorizaciones 64 65 66 firmas 67 68 anexos 69 70 71"

Resumen rápido para recuperación:

- Plantilla XLSX de cargue masivo: hoja `PLANTILLA`, campos A-BE, 57 columnas, filas de captura 5 a 52, documento operativo `Relación de ingreso de trabajadores`.
- Formulario independientes/contratistas: se reconoce por trabajador/contratista, contratante, contrato, centro de trabajo, resumen de pago de cotización, IBC 40%, firmas de contratante y trabajador.
- Formulario empresa/empleador: se reconoce por empleador, representante legal, trabajadores dependientes, clase de afiliación, contactos de pagos, contacto de salud ocupacional, firma y sello.
- Resolución 000196 de 2026: se reconoce por formulario nuevo con campos numerados 1 a 71, capítulos de trámite, responsable, afiliado, sitio de trabajo, condiciones pactadas, novedades, autorizaciones, firmas y anexos.

## Formulario único para trabajadores independientes y contratistas

Archivo patrón: `2_Formulario_Independientes_ARL_bc76e199a3.pdf`. El archivo duplicado con sufijo `(1)` contiene la misma estructura. Nombre documental AFILEGA recomendado: `Formulario de Afiliación` cuando está diligenciado y firmado por contratante y trabajador.

### Encabezado

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Fecha de radicación | Fecha en que se recibe el trámite en la ARL. | Formato AAAA/MM/DD o día, mes y año equivalente. |
| Fecha inicio de cobertura | Fecha desde la cual inicia la cobertura. | Debe ser posterior a la afiliación, normalmente el día siguiente a la radicación. |
| NIT ARL | Identificación de la ARL del formulario. | Debe aparecer en el encabezado del formato. |

### I. Tipo de trámite

| Campo | Qué significa | Opciones o contenido |
| --- | --- | --- |
| Tipo de trámite | Define si el documento afilia o reporta una novedad. | Afiliación, Novedad. |
| Tipo de novedad | Motivo específico cuando el trámite no es afiliación inicial. | Corrección nombres o apellidos, cambio/corrección identificación, suspensión contrato, cambio de datos personales, modificación de IBC, adición contrato, cambio de actividad económica, retiro, prórroga contrato, traslado de ARL, cesión contrato, terminación anticipada, terminación contrato, nuevo contrato, otro. |
| Número de contrato de la novedad | Contratos afectados por la novedad. | Puede registrar hasta 5 contratos. |
| Fecha de novedad | Fecha desde la cual aplica la novedad. | AAAA/MM/DD. |

### II. Datos del trabajador y/o contratista

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Tipo de documento | Tipo de identificación del trabajador/contratista. | NIT, CC, CE, PA, RC, TI. |
| Número de documento | Identificación del trabajador/contratista. | Debe coincidir con cédula/RUT/soporte del afiliado. |
| Primer apellido | Primer apellido del afiliado. | Obligatorio. |
| Segundo apellido | Segundo apellido del afiliado. | Opcional si no aplica. |
| Primer nombre | Primer nombre del afiliado. | Obligatorio. |
| Segundo nombre | Segundo nombre del afiliado. | Opcional si no aplica. |
| Dirección | Dirección del afiliado. | Debe estar diligenciada para contacto/residencia. |
| Ciudad | Ciudad del afiliado. | Debe ser consistente con dirección. |
| Teléfono | Teléfono fijo del afiliado. | Numérico cuando exista. |
| Celular | Celular del afiliado. | Recomendado, usualmente obligatorio en operación. |
| Correo electrónico | Correo del afiliado. | Debe contener `@` cuando esté diligenciado. |
| Fecha de nacimiento | Fecha de nacimiento del afiliado. | AAAA/MM/DD. |
| Género | Sexo/género del afiliado en el formato antiguo. | F o M. |
| Código EPS | Código de la EPS. | Debe corresponder a la EPS informada. |
| Nombre EPS | EPS actual del afiliado. | Debe ser coherente con certificación EPS activa. |
| Código ARL | Código de ARL actual si aplica. | Solo aplica en ciertos casos o traslados. |
| Nombre ARL | ARL actual si aplica. | Usar para detectar traslado o ARL anterior. |
| Código AFP | Código de fondo de pensiones. | Debe corresponder a AFP informada. |
| Nombre AFP | AFP actual del afiliado. | Debe ser coherente con certificación AFP. |

### III. Información del contrato

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Número de contrato | Identificador del contrato entre contratista y contratante. | Debe coincidir con contrato soporte si existe. |
| Tipo de cotizante | Condición del afiliado. | Dependiente, independiente, pensionado, madres comunitarias, estudiantes relación docencia-servicio, aprendices SENA etapa lectiva/productiva, otro. |
| Subtipo de cotizante | Clasificación adicional del cotizante. | Pensionado supera/no supera 25 SMLMV, conductor taxi, conductor taxi pensionado, independiente con contrato de prestación de servicios. |
| Tipo de aportante | Quién aporta al sistema. | Empleador, independiente, convenio docencia-servicio. |
| Modalidad | Forma de ejecución del trabajo. | Teletrabajador, voluntario, otro. |
| Datos conductor taxi | Bloque especial para conductores. | Operador de transporte, documento, dirección, teléfono, fax, correo. |
| Tipo de documento contratante | Identificación del contratante. | NIT, CC, CE, PA, RC, TI. |
| Número de documento contratante | Número de identificación del contratante. | Debe coincidir con RUT/cámara/contrato del contratante. |
| Nombre o razón social contratante | Nombre legal del contratante. | Debe coincidir con contrato y Cámara de Comercio/RUT. |
| Dirección sede principal | Dirección principal del contratante. | Debe ser consistente con RUT o cámara. |
| Departamento sede principal | Departamento de la sede. | Debe existir. |
| Municipio sede principal | Municipio de la sede. | Debe existir. |
| Teléfono contratante | Teléfono del contratante. | Numérico cuando aplique. |
| Fax contratante | Fax del contratante. | Opcional. |
| Correo electrónico contratante | Correo del contratante. | Debe contener `@` si se diligencia. |
| Código actividad económica contratante | Código según Decreto 1607/2002 en el formato antiguo. | Incluye clase de riesgo, CIIU y dígitos adicionales. |
| Actividad económica principal | Descripción de la actividad económica del contratante. | Debe ser coherente con código. |
| Tipo de contrato | Naturaleza del contrato. | Civil, comercial o administrativo. |
| Naturaleza jurídica de la empresa | Tipo de entidad contratante. | Pública, privada o mixta. |
| Suministro de transporte | Indica si el empleador suministra transporte. | Sí o No. |
| Fecha de inicio del contrato | Inicio de ejecución contractual. | AAAA/MM/DD; debe coincidir con contrato. |
| Fecha de terminación del contrato | Final de ejecución contractual. | AAAA/MM/DD; debe ser posterior al inicio. |
| Número de meses del contrato | Duración contractual. | Debe ser consistente con fechas. |
| Días de ejecución | Días de la semana de ejecución. | Lunes a domingo marcados según actividad. |
| Horario de ejecución | Horas de ejecución de actividades. | Horario de 1 a 24 según formato. |
| Valor total del contrato | Valor global pactado. | Numérico; debe coincidir con contrato. |
| Valor mensual del contrato | Valor mensual pactado o calculado. | Numérico; usualmente valor total / meses. |
| Ingreso Base de Cotización (IBC) | Base para cotización a riesgos laborales. | En contratistas suele corresponder al 40% del ingreso/honorarios, sin superar topes. |
| Actividad a ejecutar | Labor contratada. | Debe coincidir con objeto contractual. |
| Código actividad a ejecutar | Código CIIU/actividad de la labor. | Coherente con actividad y riesgo. |
| Clase de riesgo centro de trabajo | Riesgo de la actividad/centro. | I, II, III, IV o V. |
| Dirección centro de trabajo | Lugar donde se ejecuta la actividad. | Obligatorio para centro de trabajo. |
| Departamento centro de trabajo | Departamento del centro. | Debe existir. |
| Municipio centro de trabajo | Municipio del centro. | Debe existir. |
| Teléfono centro de trabajo | Teléfono del centro. | Numérico si aplica. |
| Fax centro de trabajo | Fax del centro. | Opcional. |
| Correo centro de trabajo | Correo del centro. | Debe contener `@` si se diligencia. |

### IV. Resumen información pago cotización

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Número de contrato | Contrato por el cual se paga. | Puede repetirse hasta cinco filas. |
| Valor mensual del contrato | Valor mensual por contrato. | Numérico. |
| Fecha inicio del contrato | Inicio del contrato relacionado. | AAAA/MM/DD. |
| Fecha terminación del contrato | Terminación del contrato relacionado. | AAAA/MM/DD. |
| Clase de riesgo | Clase asociada al contrato. | I, II, III, IV o V. |
| IBC 40% | Base de cotización calculada. | No debe superar 25 SMLMV; si varios contratos, priorizar reglas de mayor riesgo y orden cronológico. |

### Firmas

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Firma del contratante | Aceptación del responsable/contratante. | Debe estar presente para formulario firmado por ambas partes. |
| Firma del trabajador | Aceptación del afiliado/contratista. | Debe estar presente para formulario firmado por ambas partes. |
| Firma funcionario ARL | Constancia de recepción/gestión ARL. | Deseable o requerida según operación. |

## Formulario de afiliación empresa

Archivo patrón: `2_Formulario_de_Afiliacion_Empresa_721d722e1f (1).pdf`. Nombre documental AFILEGA recomendado: `Solicitud Afiliación Empleador` o `Formulario de Afiliación` según el trámite y firma.

### A. Entidad administradora de riesgos laborales

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| ARL | Entidad administradora. | Debe identificar a Seguros de Vida Alfa S.A. en este patrón. |
| NIT ARL | Identificación tributaria de la ARL. | Debe estar en encabezado. |
| Fecha de radicación | Fecha de recepción. | AAAA/MM/DD. |
| Fecha de solicitud de afiliación o traslado | Fecha de solicitud. | AAAA/MM/DD. |
| Resolución de autorización | Referencia de autorización de la ARL. | Aparece como antecedente operativo del formato. |

### B. Empleador

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Tipo de documento | Tipo de identificación del empleador. | NIT, CC o CE. |
| Número de identificación | Identificación del empleador. | Debe coincidir con RUT/Cámara. |
| Dígito de verificación | DV del NIT si aplica. | Numérico, coherente con NIT. |
| Nombre o razón social | Nombre legal del empleador. | Debe coincidir con Cámara de Comercio/RUT. |
| Número de sucursales | Cantidad de sucursales del empleador. | Numérico. |
| Número de centros de trabajo | Cantidad de centros registrados. | Numérico; debe soportarse con documento de centros de trabajo si existe. |
| Dirección sede principal | Dirección principal. | Obligatoria. |
| Municipio sede principal | Municipio de sede. | Debe existir. |
| Departamento sede principal | Departamento de sede. | Debe existir. |
| Teléfono | Teléfono del empleador. | Numérico cuando aplique. |
| Fax | Fax del empleador. | Opcional. |
| Código actividad económica | Código según actividad económica. | Debe corresponder a actividad principal. |
| Actividad económica principal | Descripción de la actividad. | Coherente con código y Cámara/RUT. |

### B1. Representante legal

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Tipo de documento | Tipo de identificación del representante. | NIT, CC o CE. |
| Número de identificación | Documento del representante legal. | Debe coincidir con cédula soporte y Cámara. |
| Nombres y apellidos | Nombre completo del representante. | Debe coincidir con Cámara. |
| Cargo | Cargo del representante. | Representante legal u otro cargo autorizado. |
| Correo electrónico | Correo del representante. | Debe contener `@`. |

### C. Trabajadores dependientes

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Número inicial de trabajadores incluidos en anexo | Cantidad de trabajadores relacionados para ingreso. | Debe coincidir con anexo/relación de ingreso de trabajadores o plantilla masiva. |
| Anexo de trabajadores | Relación de dependientes cubiertos por la afiliación. | Debe contener datos de identificación y novedades de ingreso. |

### D. Clase de afiliación

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Primera vez / Traslado | Tipo de afiliación del empleador. | Marcar una opción. |
| Tipo de aportante | Naturaleza del aportante. | Empleador, agremiación, cooperativa, asociación, servicio doméstico u otra. |
| Clase de aportante | Tamaño/tipo operativo del aportante. | Gran aportante o pequeño aportante. |
| ARL de la cual se desafilia | ARL anterior cuando es traslado. | Obligatorio si marca traslado. |
| Adjunta copia de carta de desvinculación | Soporte de traslado. | Marcar si se adjunta. |
| Adjunta constancia ARL anterior | Soporte de afiliación previa. | Marcar si se adjunta. |
| Adjunta recibos de pago del trimestre anterior | Soporte de pagos previos. | Marcar si se adjunta. |
| Clase de riesgo principal | Riesgo principal de la empresa. | Mínimo 1, Bajo 2, Medio 3, Alto 4, Máximo 5. |
| Requiere reclasificación | Indica si la ARL debe reclasificar riesgo. | Sí o No. |

### Datos de contacto pagos

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Nombres y apellidos | Contacto responsable de pagos. | Obligatorio para gestión de cartera/aportes. |
| Cargo | Cargo del contacto de pagos. | Debe estar diligenciado. |
| Correo electrónico | Correo del contacto. | Debe contener `@`. |
| Dirección | Dirección de contacto. | Debe estar diligenciada. |
| Ciudad | Ciudad de contacto. | Debe existir. |
| Teléfono/extensión | Teléfono de contacto. | Numérico cuando aplique. |
| Celular | Celular de contacto. | Numérico. |

### Datos de contacto salud ocupacional

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Nombres y apellidos | Contacto de SST/salud ocupacional. | Debe estar diligenciado. |
| Cargo | Cargo del contacto SST. | Debe estar diligenciado. |
| Correo electrónico | Correo del contacto SST. | Debe contener `@`. |
| Dirección | Dirección del contacto SST. | Debe estar diligenciada. |
| Ciudad | Ciudad del contacto SST. | Debe existir. |
| Teléfono/extensión | Teléfono del contacto SST. | Numérico cuando aplique. |
| Celular | Celular del contacto SST. | Numérico. |

### Datos de la administradora y firmas

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Fecha de iniciación de vigencia | Fecha en que inicia la afiliación. | AAAA/MM/DD. |
| Lugar, fecha y hora de recepción | Evidencia de recepción por ARL. | Debe estar diligenciado en trámite recibido. |
| Persona que recibe | Funcionario receptor. | Nombre completo. |
| Cargo | Cargo del funcionario receptor. | Debe estar diligenciado. |
| Firma y sello empleador o representante legal | Aceptación del empleador. | Debe estar firmada. |
| Nombre completo y CC del firmante | Identificación del firmante. | Debe coincidir con representante legal/autorizado. |
| Firma administradora de riesgos laborales | Firma de la ARL. | Debe estar presente cuando aplica recepción formal. |

## Resolución 000196 de 2026 - formulario nuevo SGRL

Archivo patrón: `Resolucion-No-196-de-2026-1.pdf`. Es norma de referencia y anexo técnico. Nombre documental AFILEGA recomendado: referencia normativa para `Formulario de afiliación` y validación de campos nuevos. La resolución modifica el Formulario Único de Afiliación y Reporte de Novedades al Sistema General de Riesgos Laborales de la Resolución 413 de 2025, con efectos desde el 1 de febrero de 2026.

### Encabezado

| Campo | Qué significa | Validación esperada |
| --- | --- | --- |
| Logo ARL | Espacio para la ARL. | Identifica la administradora. |
| Número de radicación | Consecutivo asignado por ARL. | Debe existir en trámite recibido. |
| Fecha de radicación | Fecha de recepción por ARL. | Fecha real de recepción. |
| Fecha inicio de cobertura | Inicio de cobertura. | Día calendario siguiente a la afiliación/radicación. |

### Campos numerados 1 a 71

| No. | Campo | Qué debe saber el RAG |
| --- | --- | --- |
| 1 | Tipo de trámite | Afiliación o reporte de novedades. Obligatorio. |
| 2 | Tipo de afiliación | Individual o colectiva. Obligatorio. |
| 3 | Tipo de aportante | Código PILA del aportante: empleador, independiente, agremiación, cooperativa, misión diplomática, pagador concejales, contratante, pagador promotor del servicio social para la paz, entre otros. |
| 4 | Tipo de afiliado | Condición del cotizante: dependiente, dependiente tiempo parcial, independiente, independiente voluntario, trabajador penitenciario, estudiante, voluntario primera respuesta, servicio de utilidad pública, promotor servicio social para la paz o ley de segundas oportunidades. Debe incluir código. |
| 5 | Subtipo de afiliado | Pensionado, conductor servicio público u otro subtipo. Debe incluir código cuando aplique. |
| 6 | Nombre o razón social del responsable | Identifica a quien realiza la afiliación. Obligatorio. |
| 7 | Tipo de documento del responsable | Código de documento del responsable de afiliación. |
| 8 | Número de documento del responsable | Número exacto del documento de identificación. |
| 9 | Ubicación/sede principal del responsable | Dirección, teléfono, celular, correo, municipio/distrito, zona, localidad/comuna y departamento. |
| 10 | Código de actividad económica del responsable | Código de actividad económica según Decreto 768 de 2022 o norma vigente. |
| 11 | Clase de riesgo del responsable | Clase I, II, III, IV o V. |
| 12 | Apellidos y nombres del afiliado | Primer apellido, segundo apellido si aplica, primer nombre y segundo nombre si aplica; deben coincidir con documento. |
| 13 | Tipo de documento del afiliado | RC, TI, CC, CE, PA, CD, SC, PT u otro código permitido. |
| 14 | Número de documento del afiliado | Número exacto del documento. |
| 15 | Sexo identificación | F, M, T, NB u O; si O, especificar cuál. |
| 16 | Fecha de nacimiento | Fecha del documento de identificación. |
| 17 | EPS | Entidad Promotora de Salud del afiliado. |
| 18 | AFP | Administradora de Pensiones del afiliado. |
| 19 | Ingreso Base de Cotización - IBC | Valor mensual sobre el cual cotiza. Debe estar entre 1 y 25 SMLMV según tipo de afiliado; para prestación de servicios suele ser 40% de honorarios mensuales. |
| 20 | Residencia | Dirección, teléfono fijo, celular, correo, municipio/distrito, zona urbana/rural, localidad/comuna y departamento. |
| 21 | Modalidad | Presencial, teletrabajo, trabajo en casa o trabajo remoto. |
| 22 | Sitio de trabajo, práctica o actividad | Sede principal o centro de trabajo; para trabajo en casa/remoto corresponde centro de trabajo, para teletrabajo sede principal. |
| 23 | Código de actividad económica del sitio | Código SGRL según Decreto 768 de 2022, salvo excepciones como voluntario primera respuesta. |
| 24 | Clase de riesgo del afiliado/sitio | Clase I a V. |
| 25 | Código de ocupación u oficio | Código según tabla de ocupaciones/oficios SGRL. |
| 26 | Ubicación sitio de trabajo | Dirección, teléfono, celular, correo, municipio/distrito, zona, localidad/comuna y departamento. |
| 27 | Cargo trabajador dependiente | Denominación del cargo o empleo. |
| 28 | Cargo trabajador dependiente tiempo parcial | Denominación del cargo o empleo para tiempo parcial con varios empleadores. |
| 29 | Tipo de contrato | Para independiente con prestación de servicios superior a un mes: A civil, B administrativo, C comercial. |
| 30 | Fecha inicial contrato | Inicio del contrato de prestación de servicios. |
| 31 | Fecha final contrato | Terminación del contrato. |
| 32 | Valor total honorarios | Valor total pactado dentro del contrato. |
| 33 | Valor mensual honorarios | Valor mensual pagado durante la ejecución. |
| 34 | Fecha inicial independiente voluntario | Inicio de ocupación u oficio. |
| 35 | Fecha final independiente voluntario | Fin de ocupación u oficio. |
| 36 | Fecha inicial trabajador penitenciario | Inicio de actividad. |
| 37 | Fecha final trabajador penitenciario | Fin de actividad. |
| 38 | Actividad principal trabajador penitenciario | Actividad que realiza el trabajador penitenciario. |
| 39 | Fecha inicial estudiante | Inicio de práctica formativa. |
| 40 | Fecha final estudiante | Fin de práctica formativa. |
| 41 | Actividad principal estudiante | Actividad principal de la práctica. |
| 42 | Actividad secundaria estudiante | Segunda actividad de la práctica. |
| 43 | Fecha inicial voluntario primera respuesta | Inicio de convocatoria/actividad. |
| 44 | Fecha final voluntario primera respuesta | Fin de convocatoria/actividad. |
| 45 | Fecha inicial servicio utilidad pública | Inicio de prestación del servicio. |
| 46 | Fecha final servicio utilidad pública | Fin de prestación del servicio. |
| 47 | Actividad de apoyo servicio utilidad pública | Actividad de apoyo conforme a reglamentación: espacio público, víctimas, protección animal, comunidades vulnerables, ambiente, cultura, ocio, proyectos comunitarios, defensa civil/bomberos, convivencia vial, gestión pública, obras públicas, transporte u otras análogas. |
| 48 | Fecha inicial promotor servicio social para la paz | Inicio del servicio social para la paz. |
| 49 | Fecha final promotor servicio social para la paz | Fin del servicio social para la paz. |
| 50 | Actividad de apoyo promotor servicio social para la paz | Modalidad de apoyo: alfabetización digital, víctimas, acuerdos de paz, política de paz, ambiente, paz étnica/cultural, discapacidad/personas mayores, reforma rural, patrimonio cultural, damnificados, gestión de riesgo/cambio climático. |
| 51 | Fecha inicial trabajador ley segundas oportunidades | Inicio del trabajador bajo Ley de Segundas Oportunidades. |
| 52 | Fecha final trabajador ley segundas oportunidades | Fin del periodo reportado. |
| 53 | Fecha inicial interno de medicina | Inicio de actividades del interno de medicina. |
| 54 | Fecha final interno de medicina | Final de actividades del interno de medicina. |
| 55 | Remuneración interno de medicina | Remuneración mensual de apoyo del estudiante interno de medicina; referencia normativa Ley 2466 de 2025. |
| 56 | Jornada establecida | Jornada única, turnos o rotativa. Aplica a dependientes y estudiantes. |
| 57 | Tipo de novedad | Ingreso, retiro, retiro por muerte, incapacidades, vacaciones/licencia remunerada, suspensión, licencia maternidad/paternidad, modificaciones de datos, modificación IBC, variación centro, cambio ocupación, traslado ARL, licencia parental flexible u otras licencias/permisos. |
| 58 | Identificación de quien registra novedad | Datos básicos de identificación del afiliado o responsable después de la modificación. |
| 59 | Datos complementarios de novedad | EPS, AFP, IBC y residencia cuando se actualizan datos complementarios del afiliado. |
| 60 | Novedades relacionadas con fechas | Fecha inicial y fecha final de la novedad; para ingreso, retiro o muerte solo fecha inicial. |
| 61 | ARL anterior | Nombre de la ARL anterior en traslado. |
| 62 | Licencia parental flexible | Hora inicio y hora final en formato HH:mm:ss. |
| 63 | Cambio de sitio de trabajo/práctica/actividad | Sede principal o centro de trabajo, código actividad económica, clase de riesgo, sitio de trabajo y código de ocupación cuando aplique. |
| 64 | Autorización reporte información | Autoriza reporte a base de datos de afiliados y entidades públicas competentes. |
| 65 | Autorización tratamiento datos personales | Autoriza manejo de datos personales según Ley 1581 de 2012 y Decreto 1377 de 2013. |
| 66 | Autorización envío de información | Autoriza envío al correo o celular por mensajes de texto. |
| 67 | Firma responsable/afiliado | Firma de quien suscribe; declara veracidad de información y autorizaciones. |
| 68 | Nombre y firma funcionario ARL | Identificación y firma del funcionario de la ARL. |
| 69 | Anexo documento de identidad | Documento de identidad para afiliación de trabajador independiente. |
| 70 | Anexo identificación de peligros | Formato diligenciado de identificación de peligros. |
| 71 | Anexo examen pre-ocupacional | Certificado de resultados del examen pre-ocupacional. |

## Plantilla de cargue masivo nuevos afiliados ARL

Archivo patrón: `PLANTILLA_CARGUE_MASIVO_NUEVOS_AFILIADOS_ARL_9296e5e58d.xlsx`. Hoja principal: `PLANTILLA`. Hojas de soporte: `ANEXOS` y `Listas`. Nombre documental AFILEGA recomendado: `Relación de ingreso de trabajadores` cuando se use como anexo masivo de ingreso.

La plantilla registra hasta 48 trabajadores en filas 5 a 52. Los encabezados están en la fila 4 y los campos operativos van de A a BE, 57 columnas. La hoja contiene listas y validaciones para tipo de cotizante, subtipo, sexo, departamentos, municipios, estado civil, EPS, AFP, zona, modalidad, jornada, sitio de trabajo, tipo de contrato, teletrabajo, discapacidad, trabajo en altura y códigos.

### Campos de la hoja PLANTILLA

| No. | Columna | Campo | Qué significa / validación esperada |
| --- | --- | --- | --- |
| 1 | A | No. de Afiliación | Número asignado por la ARL o póliza; longitud esperada 1 a 5 caracteres. |
| 2 | B | Número de sucursal | Código asignado por el empleador a la sede; longitud 1 a 5. |
| 3 | C | Número del centro de trabajo | Código del centro de trabajo en la ARL; longitud 1 a 5. |
| 4 | D | Fecha de Radicación | Fecha en que se radica el documento en la ARL; formato aaaa/mm/dd. |
| 5 | E | Fecha de Ingreso Empresa | Fecha de ingreso del dependiente a la empresa; formato aaaa/mm/dd. |
| 6 | F | Fecha Inicio de Cobertura | Inicio de cobertura en riesgos laborales; normalmente día siguiente a radicación. |
| 7 | G | Tipo de Afiliación | Tipo de afiliación seleccionado según lista del formato. |
| 8 | H | Tipo de Cotizante | Lista `Cotizante`; ejemplo: dependiente, independiente, estudiante, voluntario primera respuesta. |
| 9 | I | Código Tipo de Cotizante | Código dependiente del tipo seleccionado en H. |
| 10 | J | Subtipo de cotizante | Lista `Subtipos`: pensionado, conductor servicio público u otro subtipo. |
| 11 | K | Código Subtipo de Cotizante | Código dependiente del subtipo seleccionado en J. |
| 12 | L | Tipo de Identificación | Abreviatura del documento del afiliado. |
| 13 | M | No. de identificación | Documento del afiliado; alfanumérico, máximo 16 caracteres. |
| 14 | N | Primer Apellido | Obligatorio; longitud 1 a 60. |
| 15 | O | Segundo Apellido | Opcional si no aplica. |
| 16 | P | Primer Nombre | Obligatorio; longitud 1 a 60. |
| 17 | Q | Segundo Nombre | Opcional si no aplica. |
| 18 | R | Género | Lista `SEXO`; en esta plantilla M=Mujer, H=Hombre. |
| 19 | S | Fecha de nacimiento | Fecha como aparece en el documento; formato aaaa/mm/dd. |
| 20 | T | Departamento Nacimiento | Lista `Departamento`; dato opcional según DIVIPOLA. |
| 21 | U | Municipio/Distrito Nacimiento | Lista dependiente del departamento de nacimiento. |
| 22 | V | Estado civil | Lista `Estado_civil`; dato obligatorio. |
| 23 | W | Entidad Promotora de Salud-EPS | Lista `Administradora_EPS`; debe coincidir con certificación EPS. |
| 24 | X | Administradora de Pensiones AFP | Lista `Administradora_AFP`; debe coincidir con certificación AFP. |
| 25 | Y | Ingreso Base de Cotización - IBC | Valor entero; validación aproximada entre 1.000.000 y 25.000.000 en la plantilla. |
| 26 | Z | Denominación del cargo o del empleo | Cargo contratado; obligatorio, longitud 5 a 100. |
| 27 | AA | Dirección Residencia del Trabajador | Dirección de contacto/residencia; longitud 5 a 100. |
| 28 | AB | Teléfono Fijo | Indicativo + número sin espacios; longitud 10 a 15 si no hay celular. |
| 29 | AC | Teléfono Celular | Obligatorio según ayuda de celda; longitud 10 a 15. |
| 30 | AD | Correo electrónico | Obligatorio; debe contener `@`; longitud 4 a 100. |
| 31 | AE | Departamento de Residencia | Lista `Departamento`; obligatorio según DIVIPOLA. |
| 32 | AF | Municipio/Distrito | Lista dependiente del departamento. |
| 33 | AG | Zona de Residencia | Lista `Zona`: urbana o rural. |
| 34 | AH | Localidad/Comuna | Localidad o comuna si existe en la ciudad. |
| 35 | AI | Estrato Socio económico | Lista `Estrato`; opcional. |
| 36 | AJ | Modalidad Laboral | Lista `Modalidad`: presencial, teletrabajo, trabajo en casa o trabajo remoto. |
| 37 | AK | Jornada establecida | Lista `Jornada`: jornada única, turnos o rotativa. |
| 38 | AL | Fecha Inicio Modalidad Laboral | Fecha de inicio de la modalidad laboral; longitud 10. |
| 39 | AM | Fecha Terminación Modalidad Laboral | Fecha final de la modalidad laboral; longitud 10. |
| 40 | AN | Sitio de trabajo | Lista `Sitio_de_trabajo`: sede principal o centro de trabajo. |
| 41 | AO | Trabajo en altura | Lista `Altura`; Sí/No según corresponda. |
| 42 | AP | Código Ocupación | Código de la Clasificación Única de Ocupaciones para Colombia - CUOC. |
| 43 | AQ | Tipo de Contrato | Lista `Contrato`; aplica a independiente. |
| 44 | AR | Valor Total Honorarios | Valor total pactado; entero entre 100.000 y 1.000.000.000. |
| 45 | AS | Valor Mensual Honorarios | Valor mensual de honorarios; entero entre 100.000 y 1.000.000.000. |
| 46 | AT | Fecha inicial | Inicio de contrato u ocupación; longitud 10. |
| 47 | AU | Fecha final | Fin de contrato u ocupación; longitud 10. |
| 48 | AV | Código Actividad Principal | Actividad principal; aplica a independiente, trabajador penitenciario, estudiante o voluntario primera respuesta según ayuda de celda. |
| 49 | AW | Código Actividad Secundaria | Actividad secundaria; aplica a estudiante. |
| 50 | AX | Código Actividad Principal | Actividad para independiente voluntario a riesgos laborales. |
| 51 | AY | Modalidad para Teletrabajo | Lista `TELETRABAJO`; aplica al tipo teletrabajo. |
| 52 | AZ | Cargo del Teletrabajo | Lista `Cargo_Teletrabajo`; aplica a teletrabajo. |
| 53 | BA | Persona con discapacidad | Lista `Discapacidad`; Sí/No para todos los tipos de cotizante. |
| 54 | BB | Departamento Desempeño Laboral | Departamento donde desempeña labores; especialmente teletrabajo/remoto. |
| 55 | BC | Municipio/Distrito Laboral | Municipio o distrito de desempeño laboral. |
| 56 | BD | Dirección Desempeño de Labores | Dirección donde ejecuta actividades en teletrabajo o trabajo remoto. |
| 57 | BE | Código Actividades a ejecutar | Código de actividades a ejecutar; ayuda de celda lo asocia a trabajador remoto. |

### Hojas de soporte del XLSX

| Hoja | Qué contiene | Uso para validación |
| --- | --- | --- |
| PLANTILLA | Campos de captura del cargue masivo. | Es la hoja que debe leerse para extraer trabajadores. |
| ANEXOS | Tablas de consulta y fórmulas de búsqueda para ocupaciones, actividades económicas, tipos de cotizante, subtipos y documentos. | Sirve para explicar códigos y validar catálogos. |
| Listas | Rangos nombrados para validaciones. | Contiene EPS, AFP, departamentos, municipios, sexo, estado civil, zona, modalidad, jornada, sitio de trabajo, contrato, teletrabajo, discapacidad, trabajo en altura, CIIU y CUOC. |

### Rangos y listas importantes del XLSX

| Lista / rango | Uso |
| --- | --- |
| `Cotizante` | Opciones de tipo de cotizante. |
| `Dependiente`, `Independiente`, `Estudiante`, `Voluntario_en_primera_respuesta_aporte_solo_riesgos_laborales` | Códigos dependientes del tipo de cotizante. |
| `Subtipos`, `Pensionado`, `Conductor_del_servicio_público`, `Otro_Subtipo` | Subtipos y códigos. |
| `DOCUMENTO_ID` | Tipos de documento. |
| `SEXO` | Valores permitidos de género en la plantilla. |
| `Administradora_EPS` | Lista de EPS. |
| `Administradora_AFP` | Lista de AFP. |
| `Departamento` y rangos por departamento | Departamentos y municipios DIVIPOLA. |
| `Zona` | Urbana/Rural. |
| `Modalidad` | Modalidad laboral. |
| `Jornada` | Jornada establecida. |
| `Sitio_de_trabajo` | Sede principal o centro de trabajo. |
| `Contrato` | Tipo de contrato. |
| `TELETRABAJO` | Modalidades de teletrabajo. |
| `Discapacidad` | Sí/No sobre discapacidad. |
| `Altura` | Sí/No sobre trabajo en altura. |
| `ANEXO_I_DECRETO_768_DE_2022`, `DECRETO_768_DE_2022`, `CÓDIGO_SGSS`, `CLASE_DE_RIESGO_DEC_768_2022`, `DÍG._ADIC_DEC_768_2022` | Validación de actividades económicas, códigos SGSS, clase de riesgo y dígitos adicionales. |
| `Independiente_voluntario_a_riesgos_laborales` y `CÓDIGO_SGSS_VOL` | Actividades y códigos para independiente voluntario. |
| `ActividadesCUOC` | Ocupaciones/oficios. |

## Reglas operativas para respuestas del RAG

- Si preguntan por el paquete sin XLSX, el RAG debe decir que puede clasificar por documentos PDF/imágenes y que el XLSX solo es obligatorio para cargues masivos cuando la operación lo exija.
- Si preguntan por `Formulario de Afiliación`, distinguir entre el formulario de empresa y el formulario de trabajador independiente/contratista.
- Si un formulario está firmado por ambas partes, debe asociarse con `Formulario de Afiliación. (firmado por ambas partes)`.
- Si el documento trae campos de empleador, representante legal, contactos de pago y salud ocupacional, corresponde al formato de afiliación de empresa/empleador.
- Si el documento trae contratante, contratista, contrato, IBC 40%, centro de trabajo y firmas de contratante/trabajador, corresponde al formulario de independiente/contratista.
- Si el documento trae campos numerados 1 a 71, autorizaciones 64 a 66, firmas 67 y 68, anexos 69 a 71, corresponde al formulario nuevo definido por Resolución 000196 de 2026.
- Si el documento es una hoja de cálculo con columnas A a BE y hoja `PLANTILLA`, corresponde a `Relación de ingreso de trabajadores` o plantilla de cargue masivo de nuevos afiliados.
