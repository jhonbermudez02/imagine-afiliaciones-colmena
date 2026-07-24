# Documento de validaciones de afiliaciones AFILEGA_FA_IMA_LA_V2

Fecha de referencia: 2026-05-24  
Sistema: AFILEGA_FA_IMA_LA_V2  
Fuente funcional principal: Afiliaciones.mdb v5.2, reglas 926, catálogos Alfa/Imagine y reglas acordadas en validación con usuario.

## 1. Tipos de afiliación soportados

El sistema debe manejar tres clases de afiliación:

1. Primera vez.
2. Traslado.
3. Independiente - Contratista.

La clase de afiliación gobierna obligatoriedad, cálculo de fechas, exigencia de ARL traslado y exigencia de trabajadores.

## 2. Reglas generales para todos los tipos

### 2.1 Obligatoriedad

Todo campo marcado con asterisco es obligatorio. El sistema debe mostrar el error en el campo exacto, indicando:

- Pantalla o pestaña.
- Nombre del campo.
- Validación incumplida.

No se debe permitir guardar como completo ni generar 926 si existen errores obligatorios.

### 2.2 Formato de texto

Los campos de texto digitados deben guardarse y mostrarse en mayúscula, excepto campos técnicos donde aplique código, fecha, número o correo.

Campos solo alfabéticos:

- Nombres.
- Apellidos.
- Cargos de contacto.
- Contacto de sede.
- Representante legal.
- ARL anterior cuando sea texto.

Regla: solo letras, espacios y caracteres normales de nombre. No deben aceptar números.

Campos alfanuméricos:

- Razón social.
- Nombre centro de trabajo.
- Dirección.
- Observaciones.
- Nombre de sede cuando aplique.

Regla: letras, números y caracteres comunes de dirección/razón social. No deben permitir caracteres extraños o scripts.

### 2.3 Números

Los campos numéricos solo deben aceptar dígitos.

Aplica a:

- NIT o número de identificación.
- Dígito de verificación.
- Códigos de actividad.
- Código centro de trabajo.
- Teléfonos.
- Celulares.
- Salario / IBC.
- Conteos de trabajadores.
- Tipo aportante, clase aportante, vinculador laboral y códigos legacy.
- EPS, AFP, cargo y tipo cotizante cuando se usan por código.

### 2.4 Fechas

Las fechas deben ser válidas y no aceptar fechas imposibles.

Reglas generales:

- Fecha radicación Alfa no puede ser mayor a la fecha actual.
- Fecha recibido Imagine no puede ser menor que Fecha radicación Alfa.
- Fecha recibido Imagine no puede ser mayor a la fecha actual.
- Fecha inicio cobertura no puede ser anterior a Fecha radicación Alfa.
- Fecha de nacimiento debe ser anterior a la fecha actual.
- Fecha de constitución en Cámara de Comercio no puede ser mayor a la fecha actual.
- Fecha fin de contrato no puede ser menor que fecha inicio contrato cuando esos campos existan.
- Fecha fin de novedad no puede ser menor que fecha inicio de novedad.

Formato especial:

- Fecha nacimiento trabajador debe capturarse como DDMMAAAA.

### 2.5 Correos

Todo correo debe tener formato válido:

- Debe contener `@`.
- Debe contener dominio.
- Debe tener extensión de dominio válida.

Ejemplo válido: `CONTACTO@EMPRESA.COM`

### 2.6 Teléfonos y celulares

Regla actual del sistema:

- Teléfono: numérico de 10 dígitos.
- Celular: numérico de 10 dígitos.
- Extensión: solo dígitos, máximo 6.

Nota: aunque el requerimiento inicial hablaba de mínimo 7 para teléfono, la implementación actual quedó más estricta con 10 dígitos.

### 2.7 Catálogos obligatorios

Los campos desplegables deben validar contra catálogo. No basta con mostrar una opción en pantalla; el valor guardado debe existir en la tabla fuente.

Catálogos usados:

- Tipo documento.
- Clase afiliación.
- Sucursales ARL.
- Departamentos y municipios.
- Actividad económica ARP/926.
- Actividad Cámara de Comercio.
- Tipo aportante.
- Vinculador laboral.
- Tipo cotizante trabajadores.
- Cargo trabajadores.
- EPS.
- AFP.
- ARL traslado.
- Riesgos y tarifas.

## 3. Radicación / Nuevo contrato

La radicación es el primer paso del flujo. Debe ejecutarse antes de clasificación, OCR y digitación.

### 3.1 Campos obligatorios de radicación

- Consecutivo radicación.
- Clase afiliación.
- Fecha radicación Alfa.
- Fecha inicio vigencia.
- Fecha recibido Imagine.
- Tipo documento.
- No. de identificación.
- Razón social.
- Sucursal ARL.

### 3.2 Consecutivo radicación

Reglas:

- Lo asigna Imagine.
- Debe generarse automáticamente por secuenciador.
- Debe tener formato `IMG` + año + consecutivo.
- No debe ser editable en Nuevo contrato.
- El secuenciador solo debe avanzar cuando el consecutivo anterior fue usado efectivamente en una radicación.
- Debe existir opción administrativa/paramétrica para ajustar el último consecutivo.

### 3.3 Clase afiliación

Valores permitidos:

- Primera vez.
- Traslado.
- Independiente - Contratista.

La primera opción del combo debe ser `Selecciona...`; no debe quedar una clase preseleccionada si el usuario no la eligió.

### 3.4 Fecha radicación Alfa

Validaciones:

- Obligatoria.
- Fecha válida.
- Menor o igual a fecha actual.

### 3.5 Fecha recibido Imagine

Validaciones:

- Obligatoria.
- Fecha válida.
- Mayor o igual a Fecha radicación Alfa.
- Menor o igual a fecha actual.

### 3.6 Fecha inicio vigencia

Validaciones:

- Obligatoria.
- Fecha válida.
- Si Clase afiliación es Traslado, se calcula automáticamente como el primer día del mes subsiguiente a la Fecha radicación Alfa.
- Si no es traslado, debe conservar la regla funcional definida para el tipo de afiliación.

### 3.7 ARL traslado

Reglas:

- Campo desplegable alimentado con tabla ARL riesgos.
- Solo se habilita cuando Clase afiliación es Traslado.
- Es obligatorio cuando Clase afiliación es Traslado.
- Si la clase no es Traslado, debe quedar deshabilitado o vacío.

### 3.8 Tipo documento y número identificación

Tipo documento:

- Valores de catálogo legacy: CC, NIT, SC, PT, PE, CE, TI y equivalentes permitidos.
- Para empresa normalmente debe ser NIT.

Número identificación:

- Solo numérico.
- Si Tipo documento es NIT: longitud exacta 9.
- Si Tipo documento es CC: longitud 7, 8 o 10. No se permite longitud 9.
- Para otros tipos: entre 5 y 15 dígitos, salvo regla específica del tipo.

### 3.9 Razón social

Validaciones:

- Obligatoria.
- Alfanumérica.
- Mínimo 2 caracteres.
- Debe guardarse en mayúscula.

### 3.10 Sucursal ARL

Valores permitidos:

- Barranquilla.
- Cali.
- Dirección General.
- Medellín.

Debe ser obligatoria.

### 3.11 Estado inicial

Al radicar un contrato, el estado inicial debe ser Pendiente o Radicada, según el tablero operativo definido. No debe quedar automáticamente en devolución si no se ha ejecutado una validación que lo justifique.

## 4. Digitación - Afiliación

La pestaña Afiliación contiene la información de la empresa, contratante o independiente y los datos requeridos para el 926.

### 4.1 Campos base obligatorios

- Tipo Id.
- Nro NIT / No. identificación.
- Razón social.
- Dígito verificación.
- Código actividad económica.
- Actividad principal.
- Riesgo.
- Dirección sede principal.
- Departamento.
- Municipio.
- Correo electrónico.
- Teléfono.
- Tipo persona.
- Tipo aportante.
- Clase aportante.
- Vinculador laboral.

### 4.2 Tipo Id

Reglas:

- Desplegable de catálogo legacy.
- Debe coincidir con Cámara de Comercio cuando exista OCR confiable.
- En Digitación, algunos casos lo muestran solo lectura si viene de radicación.

### 4.3 NIT / número identificación

Reglas:

- Solo numérico.
- Si Tipo Id es NIT: longitud exacta 9.
- Si Tipo Id es CC: longitud 7, 8 o 10. No se permite longitud 9.
- Debe coincidir con Cámara de Comercio y RUT cuando exista lectura OCR confiable.

### 4.4 Dígito de verificación

Reglas:

- Obligatorio.
- Un solo dígito.
- Debe coincidir con el cálculo del MDB AFILEGA v5.2 para el NIT digitado.
- Debe coincidir con RUT si existe lectura OCR confiable.

### 4.5 Razón social

Reglas:

- Obligatoria.
- Alfanumérica.
- Mínimo 2 caracteres.
- Guardar en mayúscula.
- Debe coincidir con Cámara de Comercio cuando exista lectura OCR confiable.

### 4.6 Código actividad económica ARP/926

Reglas:

- Obligatorio.
- Numérico.
- Debe tener 7 dígitos para el catálogo ARP/926.
- Debe existir en el catálogo de actividad económica usado para generación 926.
- Al seleccionarlo debe traer automáticamente Actividad principal y Clase/Riesgo.

### 4.7 Actividad principal

Reglas:

- Se llena automáticamente desde el código de actividad económica.
- Debe quedar dentro del límite legacy de longitud.
- Si excede el límite, debe truncarse o mostrar error antes de guardar.

### 4.8 Riesgo / clase de riesgo empresa

Reglas:

- Obligatorio.
- Valores 1 a 5 o equivalente romano I a V.
- Debe coincidir con la clase del catálogo de actividad económica.

### 4.9 Departamento y municipio

Reglas:

- Ambos obligatorios.
- Departamento debe existir en tabla Colombia.
- Municipio debe pertenecer al departamento.
- Si el usuario selecciona municipio, el sistema debe inferir el departamento cuando sea único.

### 4.10 Tipo aportante

Reglas:

- Desplegable.
- Debe alimentarse de la tabla `gar_tipos_aportantes`.
- Debe guardar código.
- Al seleccionar tipo aportante debe traer clase aportante y vinculador laboral cuando aplique.

### 4.11 Clase aportante

Reglas:

- Obligatoria.
- Código numérico máximo 3 dígitos.
- Se deriva del tipo aportante cuando exista regla en catálogo.

### 4.12 Vinculador laboral

Reglas:

- Obligatorio.
- Desplegable alimentado por tabla de vinculador laboral.
- Debe guardar código válido del catálogo.

### 4.13 Representante legal

Campos obligatorios:

- Nombre completo.
- Tipo documento.
- Número documento.
- Cargo.
- Correo representante.

Validaciones:

- Nombre y cargo solo letras y espacios.
- Tipo documento debe existir en catálogo legacy.
- Número documento solo numérico, entre 5 y 15 dígitos.
- Correo válido.
- Debe cruzarse contra Cámara de Comercio y cédula del representante cuando exista OCR confiable.

### 4.14 Cámara de Comercio

Campos obligatorios:

- Fecha constitución.
- Régimen.
- Código actividad.
- Actividad principal.
- OLCSA / PYME.
- Naturaleza.
- Clase sociedad.
- Tamaño.

Validaciones:

- Fecha constitución debe ser válida.
- Fecha constitución no puede ser mayor a fecha actual.
- Código actividad Cámara debe ser numérico de 4 a 7 dígitos.
- Código actividad Cámara debe existir en la tabla de actividad de Cámara de Comercio.
- Actividad principal debe corresponder al código seleccionado.
- Régimen, naturaleza, clase sociedad y tamaño deben existir en sus catálogos.
- Cámara de Comercio como documento soporte debe tener fecha de expedición no mayor a 90 días calendario.

Cruces contra OCR:

- NIT.
- Razón social.
- Representante legal.
- Fecha constitución.
- Naturaleza.
- Clase sociedad.
- Tamaño.
- Régimen.
- Actividad.

Cuando el OCR no sea confiable, el campo puede quedar para edición y validación manual.

### 4.15 Contacto pagos y contacto SST

Campos obligatorios para cada bloque:

- Nombre.
- Cargo.
- Correo electrónico.
- Dirección.
- Departamento.
- Ciudad.
- Teléfono.
- Celular.

Validaciones:

- Nombre y cargo solo letras.
- Correo válido.
- Departamento y ciudad por catálogo.
- Teléfono y celular de 10 dígitos.
- Guardar en mayúscula donde aplique.

## 5. Digitación - Sede

La pestaña Sede debe permitir una sede principal y múltiples centros de trabajo.

### 5.1 Sede / centro de trabajo principal

Campos:

- Sede.
- Sucursal.
- Código centro de trabajo.
- Nombre centro de trabajo.
- Dirección centro de trabajo.
- Departamento.
- Municipio.
- Zona.
- Código actividad.
- Clase de riesgo.
- Nro trabajadores.
- Teléfono.
- Celular.
- Transporte.
- Contacto.
- Cargo contacto.
- Correo.
- Grado de riesgo.
- Tarifa.

### 5.2 Nombre centro de trabajo

Validaciones:

- Obligatorio.
- Alfanumérico.
- Máximo 60 caracteres.
- Debe ubicarse después de Código centro de trabajo.

### 5.3 Código centro de trabajo

Validaciones:

- Obligatorio.
- Numérico.
- Máximo 6 dígitos para centro principal.
- En centros adicionales puede aceptar código alfanumérico controlado de máximo 20 caracteres.
- No debe repetirse entre centros.

### 5.4 Dirección

Validaciones:

- Obligatoria.
- Mínimo 5 caracteres.

### 5.5 Departamento y municipio

Validaciones:

- Obligatorios.
- Departamento debe existir en catálogo.
- Municipio debe pertenecer al departamento.

### 5.6 Zona

Valores:

- Urbana / U.
- Rural / R.

Debe ser obligatoria.

### 5.7 Código actividad sede

Validaciones:

- Obligatorio.
- Numérico.
- Debe existir en catálogo ARP/926.
- Al seleccionarlo debe traer automáticamente clase de riesgo.

### 5.8 Clase de riesgo

Validaciones:

- Obligatoria.
- Valores 1 a 5.
- Debe coincidir con el catálogo de actividad económica.

### 5.9 Grado de riesgo

Validaciones:

- Obligatorio.
- Valores 1 a 5.
- El primer número del grado debe coincidir con el primer número del código de actividad económica.

### 5.10 Tarifa

Debe calcularse automáticamente según grado:

| Grado | Tarifa |
| --- | --- |
| 1 | 0.522 |
| 2 | 1.044 |
| 3 | 2.436 |
| 4 | 4.360 |
| 5 | 6.960 |

No debe permitirse una tarifa diferente a la esperada para el grado.

### 5.11 Nro trabajadores

Validaciones:

- Obligatorio.
- Numérico.
- Debe coincidir con la cantidad de trabajadores asociados a ese centro en la pestaña Trabajadores.

### 5.12 Transporte

Validaciones:

- Obligatorio.
- Valores permitidos: S o N.

### 5.13 Centros de trabajo adicionales

Reglas:

- El cuadro de centro adicional solo se muestra al dar clic en Agregar centro.
- Al agregar un centro se deben pedir los mismos campos obligatorios del centro de trabajo.
- Debe mostrar claramente errores campo por campo.
- Debe permitir editar y eliminar centros.
- Al crear varios centros, todos deben aparecer disponibles en la pestaña Trabajadores.
- El trabajador debe quedar amarrado a uno de los centros registrados.

## 6. Digitación - Trabajadores

Esta pestaña aplica para afiliaciones de empresa. Para Independiente - Contratista no debe exigirse ni permitirse registro de trabajadores.

### 6.1 Campos de trabajador

Campos obligatorios:

- Centro de trabajo.
- Tipoid.
- Numero_id.
- Primer_apellido.
- Primer_nombre.
- Fecha_nacimiento.
- Sexo.
- Afi tipo.
- Salario / IBC.
- Cargo.
- EPS.
- AFP.

Campos opcionales:

- Segundo_apellido.
- Segundo_nombre.
- Edad, calculada automáticamente.

### 6.2 Centro de trabajo

Validaciones:

- Obligatorio.
- Debe existir en la lista de centros registrados en Sede.
- La cantidad de trabajadores por centro debe coincidir con Nro trabajadores digitado en ese centro.

### 6.3 Tipo documento trabajador

Valores permitidos:

- CC.
- TI.
- PE.
- PT.
- CE.

### 6.4 Número documento trabajador

Validaciones:

- Obligatorio.
- Solo numérico.
- Si tipo CC: longitud 7, 8 o 10. No se permite longitud 9.
- Si tipo TI: longitud 7, 8 o 10. No se permite longitud 9.
- Si tipo CE: menos de 6 dígitos.
- Para PE/PT y otros permitidos: entre 5 y 15 dígitos, salvo regla específica.
- No puede ser igual al número de identificación de la empresa.
- No se permite registrar más de un trabajador con el mismo tipo y número de documento.

### 6.5 Nombres y apellidos

Validaciones:

- Primer apellido obligatorio.
- Primer nombre obligatorio.
- Segundo apellido opcional.
- Segundo nombre opcional.
- Solo letras y espacios.
- Guardar en mayúscula.

### 6.6 Fecha nacimiento y edad

Validaciones:

- Fecha nacimiento obligatoria.
- Formato DDMMAAAA.
- Debe ser fecha válida.
- Debe ser anterior a la fecha actual.
- Edad se calcula automáticamente desde fecha nacimiento.

### 6.7 Sexo / género

Valores:

- M.
- F.

Debe ser obligatorio.

### 6.8 Afi tipo / tipo cotizante

Reglas:

- Obligatorio.
- Desplegable alimentado por `tabla tipo cotizante - trabajadores.csv`.
- Debe permitir seleccionar cualquier código válido del catálogo, no solo 1.
- Debe guardarse como código.

Regla especial:

- Si tipo cotizante es 51, se permite salario inferior al SMMLV por condición de cotizante tiempo parcial.

### 6.9 Salario / IBC

Validaciones:

- Obligatorio.
- Numérico.
- Mayor que 0.
- No inferior al SMMLV vigente del año de radicación.
- No superior a 25 SMMLV.
- Excepción: tipo cotizante 51 permite salario inferior al SMMLV.

SMMLV configurado actualmente:

- 2025: 1.423.500.
- 2026: 1.750.905.

### 6.10 Cargo

Reglas:

- Obligatorio.
- Desplegable alimentado por tabla cargo trabajadores.
- En pantalla debe mostrar descripción.
- En base de datos y salida debe guardar código.
- Debe permitir búsqueda por código o por nombre.
- Al modificar un trabajador no debe borrarse el cargo.

### 6.11 EPS

Reglas:

- Obligatorio.
- Debe existir en catálogo EPS.
- Debe guardar código estandarizado.
- Debe permitir búsqueda por código o nombre.

### 6.12 AFP

Reglas:

- Obligatorio.
- Debe existir en catálogo AFP.
- Debe guardar código estandarizado.
- Debe permitir búsqueda por código o nombre.

### 6.13 Agregar, modificar y eliminar trabajadores

Reglas:

- Debe permitir agregar múltiples trabajadores.
- Debe permitir modificar trabajador registrado.
- Debe permitir eliminar trabajador.
- Al modificar debe cargar los datos existentes sin perder cargo, EPS, AFP o centro.
- Debe validar duplicados antes de guardar.

### 6.14 Cargue masivo de trabajadores

Debe aceptar Excel con los mismos campos del formulario de trabajadores.

Columnas esperadas:

- TI.
- Documento.
- PrimerApellido.
- SegundoApellido.
- PrimerNombre.
- SegundoNombre.
- EDAD.
- FECHADENACIMIENTO.
- Sexo.
- Codigo E.P.S.
- Codigo AFP.
- SALARIO.
- CODIGO CENTRO TRABAJO.
- CODIGO CARGO.
- FECHA DE INGRESO.
- FECHA DE RECEPCION.
- sucursal.
- riesgo.
- tipo de cotizante.

Reglas:

- Cargo, EPS y AFP deben registrarse por código, no por nombre.
- El sistema puede mostrar descripción, pero debe guardar código.
- Cada fila debe validarse contra los mismos catálogos y reglas del formulario manual.
- Si una fila falla, debe indicar fila, campo y error.

## 7. Reglas específicas por tipo de afiliación

### 7.1 Primera vez

Debe cumplir:

- Radicación completa.
- Datos de empresa completos.
- Cámara de Comercio vigente, máximo 90 días calendario desde expedición.
- RUT cuando aplique.
- Representante legal identificado y cruzado contra Cámara/cédula si existe OCR.
- Sedes y centros de trabajo completos.
- Trabajadores obligatorios para empresa.
- Conteo de trabajadores por centro debe coincidir.
- Fecha inicio cobertura debe ser exactamente un día después de Fecha radicación Alfa.
- No requiere ARL traslado.

Documentos esperados principales:

- Formulario de Afiliación firmado.
- Cámara de Comercio menor o igual a 90 días.
- RUT.
- Cédula representante legal.
- Centros de trabajo / sedes.
- Relación de ingreso de trabajadores.
- Cédulas trabajadores.
- Certificados EPS/AFP de trabajadores cuando aplique.

### 7.2 Traslado

Debe cumplir todas las reglas de Primera vez y adicionalmente:

- Clase afiliación = Traslado.
- ARL traslado obligatorio.
- Fecha inicio vigencia calculada al mes subsiguiente de Fecha radicación Alfa.
- Fecha inicio cobertura debe coincidir con Fecha inicio vigencia.
- Debe existir carta solicitud de traslado de la ARL anterior cuando aplique.
- Debe existir paz y salvo con la anterior ARL cuando aplique.
- Estado cuenta empleador debe estar dentro de valores legacy permitidos:
  - Al día.
  - En mora.
  - Acuerdo de pago.
  - Incumplimiento de acuerdo de pago.

Documentos esperados adicionales:

- Paz y salvo con anterior ARL.
- Carta solicitud de traslado de la ARL anterior.
- Soporte de ARL anterior / ARL traslado.

### 7.3 Independiente - Contratista

Debe cumplir:

- Radicación completa.
- Clase afiliación = Independiente - Contratista.
- Datos del contratista/independiente completos.
- RUT del contratista.
- Formulario de afiliación firmado por ambas partes.
- Autorización de uso de datos personales.
- Contrato entre contratista y contratante.
- Cédula del trabajador independiente / contratista.
- Certificación EPS activa menor a 30 días.
- Certificación AFP menor a 30 días.
- Si es trabajo remoto, contrato/acuerdo correspondiente.

Regla clave:

- No debe exigir ni permitir trabajadores en la pestaña Trabajadores.

Campos de trabajador individual/contratista:

- Tipo documento.
- Número documento.
- Primer apellido.
- Segundo apellido.
- Primer nombre.
- Segundo nombre.
- Fecha nacimiento.
- Sexo/género.
- EPS.
- AFP.
- Salario/IBC.
- Cargo.
- Afi tipo.

Validaciones:

- Mismas reglas de documento, fecha nacimiento, EPS, AFP, salario, cargo y tipo cotizante.
- La cédula del contratista no puede confundirse con el NIT de la empresa contratante.

## 8. Validación documental y OCR

### 8.1 Clasificación documental

Todo documento cargado debe quedar tipificado. Si el OCR o clasificador no lo identifica con confianza, debe quedar en estado Validar, no Observado.

Los documentos deben organizarse según la clasificación manual previa.

Cuando el usuario reclasifique un documento, el sistema debe:

- Guardar la reclasificación.
- Reaprender para ese contrato.
- Usar esa corrección en reprocesos del mismo paquete.
- Aplicar la corrección como señal para paquetes futuros cuando corresponda.

### 8.2 Documentos esperados

Catálogo documental de referencia:

- Carta de presentación del trabajador por parte del Contratante.
- Formulario de Afiliación firmado por ambas partes.
- Copia RUT del Contratista.
- Formato de autorización de uso de datos personales.
- Centros de trabajo.
- Solicitud Afiliación Empleador.
- Solicitud Usuario Página WEB.
- Autorización Uso Datos Personales.
- Cámara de Comercio de la empresa contratante original menor a 90 días.
- Contrato entre el contratista y el contratante.
- Cédula de representante legal de la empresa contratante.
- Cédula de trabajador independiente / contratista.
- Certificación de afiliación del trabajador a la EPS menor a 30 días y activa.
- Certificación de afiliación del trabajador a la AFP menor a 30 días.
- Cédula de los trabajadores.
- Pagos seguridad social.
- Paz y salvo con la anterior ARL.
- Carta solicitud de traslado de la ARL anterior.
- Para trabajo remoto, contrato con el trabajador.
- Relación de ingreso de trabajadores.
- Listado documentos entregados.
- SEDES.
- RUT.

Documentos retirados o no usados como tipo principal:

- NIT.
- Anexo.
- Planilla de pago como nombre principal.

### 8.3 Vigencia documental

Validaciones por documento:

- Cámara de Comercio: expedición menor o igual a 90 días calendario.
- Certificación EPS trabajador: menor o igual a 30 días y estado activo.
- Certificación AFP trabajador: menor o igual a 30 días.

### 8.4 Cruces obligatorios por OCR

Cuando exista OCR confiable, se debe cruzar:

- NIT formulario vs Cámara vs RUT.
- Razón social formulario vs Cámara.
- Dígito verificación formulario vs RUT.
- Representante legal formulario vs Cámara vs cédula.
- Fecha constitución Cámara vs RUT.
- Actividad económica formulario vs Cámara/RUT cuando aplique.
- Trabajadores reportados vs cédulas, EPS y AFP.
- Cantidad trabajadores en sede vs trabajadores digitados.

Si no existe OCR confiable, el sistema debe dejar el campo editable y marcarlo para validación manual.

## 9. Reglas de generación 926 / legacy MDB

Antes de generar 926 se debe validar:

- Campos obligatorios de radicación, afiliación, sede y trabajadores según tipo de afiliación.
- Límites máximos de longitud heredados del MDB.
- Catálogos MDB y catálogos externos.
- Homologación de departamentos y municipios a códigos MDB.
- Homologación de tipo documento NIT a código legacy cuando aplique.
- Dígito de verificación NIT calculado.
- Actividad económica válida.
- Clase de riesgo coherente con actividad.
- Trabajadores completos y sin duplicados.
- EPS, AFP, cargo y tipo cotizante por código.
- IBC dentro de rango SMMLV.
- Centros de trabajo con conteo coherente.

Si hay errores, el sistema debe impedir la generación y mostrar los campos corregibles.

## 10. Estados operativos esperados

Tarjetas de Bandeja de entrada:

- Radicadas.
- En Proceso.
- Por Entregar.
- En Devolución.

Reglas:

- Recién radicado: Radicada/Pendiente.
- Con digitación parcial: En Proceso.
- Con validación completa y listo para entrega: Por Entregar.
- Con rechazo real o devolución justificada: En Devolución.

No todas las afiliaciones deben quedar en devolución por defecto.

## 11. Reglas de seguridad de carga documental

El sistema debe proteger la carga de paquetes:

- Solo aceptar extensiones permitidas.
- Rechazar ZIP corruptos.
- Rechazar ZIP con archivos internos no permitidos.
- Limitar tamaño individual de archivo.
- Limitar tamaño total del paquete.
- Limitar cantidad de archivos dentro de ZIP.
- Limitar expansión máxima de ZIP.
- Limitar cantidad de páginas PDF a explotar.

## 12. Criterio de aceptación funcional

Una afiliación se considera lista si:

1. Tiene radicación válida.
2. Tiene documentos clasificados.
3. Tiene OCR ejecutado o validación manual cuando OCR no sea suficiente.
4. Cumple campos obligatorios según tipo de afiliación.
5. Cumple catálogos y formatos.
6. Cumple cruces documentales.
7. Cumple validación legacy MDB.
8. Genera 926 sin errores.
9. Queda en estado operativo correcto.

## 13. Diccionario de campos por solicitud

Esta sección describe campo por campo qué debe capturarse, cuándo aplica, tipo de dato, longitud/formato, obligatoriedad y valores de combo.

Convenciones:

- Obligatorio = Sí: siempre requerido para el tipo de solicitud indicado.
- Obligatorio = Condicional: depende de la clase de afiliación o de otra selección.
- Solo lectura: el usuario no debe editarlo en esa pantalla.
- Catálogo: el valor debe existir en la tabla indicada.

## 14. Solicitud: Nuevo contrato / Radicación

Aplica a: Primera vez, Traslado e Independiente - Contratista.

| Campo | Aplica a | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Consecutivo Radicación | Todas | Sí | Input solo lectura | Alfanumérico | Formato IMG + año + consecutivo. Ej: IMG202625 | Secuenciador Imagine | Se genera automáticamente. No editable. Solo avanza cuando se usa el consecutivo anterior. |
| Clase afiliación | Todas | Sí | Combo | Catálogo | N/A | Selecciona..., Primera vez, Traslado, Independiente - Contratista | Debe seleccionarse un valor válido. La primera opción debe ser Selecciona... |
| Fecha radicación Alfa | Todas | Sí | Fecha | Fecha | AAAA-MM-DD en control date | N/A | Fecha válida. No puede ser mayor a la fecha actual. |
| Fecha inicio vigencia | Todas | Sí | Fecha | Fecha | AAAA-MM-DD en control date | N/A | En Traslado se calcula como primer día del mes subsiguiente a Fecha radicación Alfa. |
| Fecha recibido Imagine | Todas | Sí | Fecha | Fecha | AAAA-MM-DD en control date | N/A | Fecha válida. Debe ser mayor o igual a Fecha radicación Alfa y menor o igual a fecha actual. |
| ARL traslado | Traslado | Condicional | Combo | Catálogo | N/A | Tabla ARL traslado / arl riesgos.xlsx | Obligatorio solo cuando Clase afiliación = Traslado. En otros casos queda vacío/deshabilitado. |
| Tipo documento | Todas | Sí | Combo | Catálogo | Máximo 3 caracteres legacy | NIT, CC, CE, TI, PE, PT | Debe existir en catálogo. Para empresa normalmente NIT. |
| No. de identificación | Todas | Sí | Input | Numérico | NIT = 9 dígitos. CC = 7, 8 o 10 dígitos. General = 5 a 15 dígitos | N/A | Solo números. Si NIT longitud exacta 9. Si CC no puede tener longitud 9. |
| Razón social | Todas | Sí | Input | Alfanumérico | 2 a 200 caracteres | N/A | Guarda en mayúscula. Solo letras, números y caracteres comunes de razón social. |
| Sucursal ARL | Todas | Sí | Combo | Catálogo | N/A | Selecciona..., Barranquilla, Cali, Dirección General, Medellin | Debe seleccionarse valor válido. |
| Tipo entrada | Todas | Sí | Selector | Catálogo operativo | N/A | Empresa, Contratista | Define si el paquete se trata como afiliación empresa o contratista independiente. |
| Documentos del paquete | Todas | Sí | Cargue archivo | Archivo | PDF, imagen, ZIP, XLS/XLSX/XLSM, TXT | Extensiones permitidas por backend | Valida tamaño, extensión, ZIP seguro y cantidad. Debe crear un solo contrato por paquete cargado. |

## 15. Solicitud: Digitación - Afiliación empresa

Aplica a: Primera vez y Traslado.  
No aplica como bloque completo a Independiente - Contratista, salvo campos comunes de identificación del contratista.

### 15.1 Contratante / responsable de afiliación

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Clase afiliación | Sí | Combo solo lectura | Catálogo | N/A | Primera vez, Traslado, Independiente - Contratista | Viene desde Radicación. No editable en Digitación. |
| Tipo Id | Sí | Combo solo lectura | Catálogo | Máximo 3 caracteres | Selecciona..., CC, NIT, SC, PT, PE | Viene desde Radicación. Debe coincidir con Cámara/RUT si hay OCR. |
| Nro NIT | Sí | Input solo lectura | Numérico | Si NIT = 9 dígitos. Si CC = 7, 8 o 10 dígitos | N/A | Viene desde Radicación. Solo números. No editable. |
| Razón social | Sí | Input | Alfanumérico | 2 a 200 caracteres | N/A | Guarda en mayúscula. Debe coincidir con Cámara si hay OCR confiable. |
| Dígito verificación | Sí | Input | Numérico | 1 dígito | N/A | Debe coincidir con cálculo MDB AFILEGA v5.2 y con RUT si existe OCR. |
| Código actividad económica | Sí | Input con búsqueda | Numérico | 7 dígitos | Catálogo actividad económica ARP/926 | Debe existir en catálogo. Al seleccionar, trae Actividad principal y Riesgo. |
| Actividad principal | Sí | Input automático | Texto | Límite legacy MDB | Catálogo actividad económica ARP/926 | Se llena desde código actividad. No debe exceder límite legacy. |
| Riesgo | Sí | Combo | Catálogo | 1 carácter | Selecciona..., I, II, III, IV, V. Guarda 1 a 5 | Debe coincidir con clase del código actividad económica. |
| Dirección sede principal | Sí | Input | Alfanumérico | Mínimo 5 caracteres, límite legacy | N/A | Guarda en mayúscula. |
| Departamento | Sí | Combo | Catálogo | Nombre departamento | Tabla departamentos Colombia | Debe existir en tabla. |
| Municipio / distrito | Sí | Combo dependiente | Catálogo | Nombre municipio | Municipios según departamento | Debe pertenecer al departamento. Si se selecciona municipio, debe inferir departamento cuando sea posible. |
| Correo electrónico | Sí | Input | Email | Formato correo | N/A | Debe contener @ y dominio válido. |
| Teléfono | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. Longitud exacta 10. |
| Tipo persona | Condicional | Combo | Catálogo | N/A | Selecciona..., Jurídica, Natural | Debe seleccionarse cuando el formulario lo requiera. |
| Tipo aportante | Sí | Combo | Catálogo | Código numérico | gar_tipos_aportantes.xlsx | Debe guardar código válido. Debe traer clase aportante/vinculador si el catálogo lo define. |
| Clase aportante | Sí | Input | Numérico | Máximo 3 dígitos | Derivado de tipo aportante / MDB | Debe ser código numérico válido. |
| Vinculador laboral | Sí | Combo | Catálogo | Código numérico | tabla Vinculador laboral - Contratante.csv | Debe existir en catálogo. |

### 15.2 Representante legal

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Nombre completo | Sí | Input | Letras | 2 a 80 caracteres legacy | N/A | Solo letras y espacios. Debe cruzar con Cámara y cédula si hay OCR. |
| Tipo documento | Sí | Combo | Catálogo | Máximo 3 caracteres | Selecciona..., CC, CE, TI, PE, PT, CD, RC, SC | Debe existir en catálogo legacy. |
| Número documento | Sí | Input | Numérico | 5 a 15 dígitos | N/A | Solo números. Debe cruzar con Cámara/cédula si hay OCR. |
| Correo representante | Sí | Input | Email | Formato correo | N/A | Debe contener @ y dominio válido. |
| Cargo | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |

### 15.3 Cámara de Comercio

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Fecha constitución | Sí | Fecha | Fecha | AAAA-MM-DD | N/A | Fecha válida. No puede ser mayor a fecha actual. Debe cruzar con RUT si hay OCR. |
| Régimen | Sí | Combo | Catálogo | N/A | Selecciona..., Simple, Común, Especial | Debe seleccionarse valor válido. |
| Código actividad | Sí | Input con búsqueda | Numérico | 4 a 7 dígitos | tabla Código actividad - Cámara de Comercio.xlsx | Debe existir en catálogo Cámara. |
| Actividad principal | Sí | Input automático/editable | Texto | Máximo legacy, recomendado <= 250 | Catálogo Cámara de Comercio | Debe corresponder al código seleccionado. |
| OLCSA / PYME | Sí | Combo | Catálogo | N/A | Selecciona..., OLCSA, PYME | Debe seleccionarse una opción. |
| Naturaleza | Sí | Combo | Catálogo | N/A | Selecciona..., Privada, Pública | Debe seleccionarse valor válido. |
| Clase sociedad | Sí | Combo | Catálogo | N/A | Selecciona..., SA, SAS, LTDA | Debe seleccionarse valor válido. |
| Tamaño | Sí | Combo | Catálogo | N/A | Selecciona..., Pequeña, Mediana, Grande | Debe seleccionarse valor válido. |
| Grupo empresarial | No / Legacy | Input | Alfanumérico/código | Límite legacy | MDB / OCR | Se trae por defecto cuando exista. |
| Tipo localización | No / Legacy | Input | Numérico/código | Máximo 3 dígitos si se codifica | MDB | Se trae por defecto cuando exista. |
| Zona localización | No / Legacy | Combo | Catálogo | 1 carácter | Selecciona..., U Urbana, R Rural | Si se diligencia debe ser U o R. |

Documento soporte:

- Cámara de Comercio debe tener expedición menor o igual a 90 días calendario.
- Se deben cruzar NIT, razón social, representante legal, fecha constitución, naturaleza, clase sociedad, tamaño, régimen y actividad contra lo digitado cuando el OCR sea confiable.

### 15.4 Datos contacto pagos

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Nombre | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. Guarda mayúscula. |
| Cargo | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Correo electrónico | Sí | Input | Email | Formato correo | N/A | Debe contener @ y dominio válido. |
| Dirección | Sí | Input | Alfanumérico | Mínimo 5 caracteres | N/A | Guarda mayúscula. |
| Departamento | Sí | Combo | Catálogo | Nombre departamento | Tabla departamentos Colombia | Debe existir en tabla. |
| Ciudad | Sí | Combo dependiente | Catálogo | Nombre municipio | Municipios del departamento | Debe pertenecer al departamento. |
| Teléfono | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |
| Celular | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |

### 15.5 Datos contacto SST

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Nombre | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. Guarda mayúscula. |
| Cargo | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Correo electrónico | Sí | Input | Email | Formato correo | N/A | Debe contener @ y dominio válido. |
| Dirección | Sí | Input | Alfanumérico | Mínimo 5 caracteres | N/A | Guarda mayúscula. |
| Departamento | Sí | Combo | Catálogo | Nombre departamento | Tabla departamentos Colombia | Debe existir en tabla. |
| Ciudad | Sí | Combo dependiente | Catálogo | Nombre municipio | Municipios del departamento | Debe pertenecer al departamento. |
| Teléfono | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |
| Celular | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |

## 16. Solicitud: Digitación - Sede / centros de trabajo

Aplica a: Primera vez y Traslado.  
Para Independiente - Contratista solo aplica si el proceso exige centro asociado al contratista; no debe exigir trabajadores.

### 16.1 Sede principal

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Sede | Sí | Input | Alfanumérico | Límite legacy, recomendado <= 80 | N/A | Guarda mayúscula. |
| Sucursal | Sí | Combo | Catálogo | N/A | Selecciona..., Barranquilla, Cali, Dirección General, Medellin | Debe seleccionarse valor válido. |

### 16.2 Centro de trabajo principal

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Código centro de trabajo | Sí | Input | Numérico | 1 a 6 dígitos | N/A | No debe repetirse con otros centros. |
| Nombre centro de trabajo | Sí | Input | Alfanumérico | Máximo 60 caracteres | N/A | Debe estar después del código centro. Guarda mayúscula. |
| Dirección centro de trabajo | Sí | Input | Alfanumérico | Mínimo 5 caracteres | N/A | Guarda mayúscula. |
| Departamento | Sí | Combo | Catálogo | Nombre departamento | Tabla departamentos Colombia | Debe existir. |
| Municipio | Sí | Combo dependiente | Catálogo | Nombre municipio | Municipios del departamento | Debe pertenecer al departamento. |
| Zona | Sí | Combo | Catálogo | N/A | Selecciona..., Urbana, Rural | Guarda como U/R para legacy cuando aplique. |
| Teléfono | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |
| Celular | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |
| Fax | No | Input | Numérico | Máximo 10 dígitos legacy | N/A | Solo números si se diligencia. |
| Correo | No | Input | Email | Formato correo | N/A | Debe ser válido si se diligencia. |
| Código actividad económica | Sí | Input con búsqueda | Numérico | 7 dígitos | Catálogo actividad económica ARP/926 | Debe existir. Trae clase riesgo. |
| Clase de riesgo centro | Sí | Combo | Catálogo | 1 carácter | Selecciona..., 1, 2, 3, 4, 5 | Debe coincidir con actividad económica. |
| Nro trabajadores | Sí | Input | Numérico | 1 a 6 dígitos | N/A | Debe coincidir con cantidad de trabajadores asociados al centro. |
| Transporte | Sí | Combo | Catálogo | 1 carácter | Selecciona..., S, N | Obligatorio. |
| Grado riesgo | Sí | Combo | Catálogo | 1 carácter | Selecciona..., 1, 2, 3, 4, 5 | Debe coincidir con primer dígito del código actividad económica. |
| Tarifa | Sí | Input solo lectura | Decimal | 0.000 | Calculada por grado | Grado 1=0.522, 2=1.044, 3=2.436, 4=4.360, 5=6.960. |
| Tipo localización | Condicional legacy | Input | Numérico | Máximo 3 dígitos | MDB | Si se diligencia debe ser código numérico. |
| Contacto centro | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Cargo contacto | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Responsable sede | Condicional legacy | Input | Letras | 2 a 80 caracteres legacy | N/A | Solo letras y espacios. |
| Tipo doc responsable | Condicional legacy | Combo | Catálogo | Máximo 3 caracteres | Selecciona..., CC, CE, TI, PE, PT | Debe existir en catálogo. |
| Doc responsable | Condicional legacy | Input | Numérico | 5 a 15 dígitos | N/A | Solo números. |

### 16.3 Centros de trabajo adicionales

El editor aparece solo al presionar Agregar centro.

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Código centro | Sí | Input | Código | 1 a 20 caracteres, números/letras/punto/guion | N/A | No se puede repetir. |
| Nombre centro | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Sucursal | Sí | Combo | Catálogo | N/A | Barranquilla, Cali, Dirección General, Medellin | Debe seleccionarse. |
| Dirección | Sí | Input | Alfanumérico | Mínimo 5 caracteres | N/A | Guarda mayúscula. |
| Departamento | Sí | Combo | Catálogo | Nombre departamento | Tabla departamentos Colombia | Debe existir. |
| Municipio | Sí | Combo dependiente | Catálogo | Nombre municipio | Municipios del departamento | Debe pertenecer al departamento. |
| Zona | Sí | Combo | Catálogo | N/A | Urbana, Rural | Obligatoria. |
| Teléfono | Sí | Input | Numérico | 10 dígitos | N/A | Solo números. |
| Celular | No | Input | Numérico | 10 dígitos | N/A | Solo números si se diligencia. |
| Fax | No | Input | Numérico | Máximo 10 dígitos | N/A | Solo números si se diligencia. |
| Correo | No | Input | Email | Formato correo | N/A | Debe ser válido si se diligencia. |
| Código actividad económica | Sí | Input con búsqueda | Numérico | 7 dígitos | Catálogo actividad económica ARP/926 | Debe existir. |
| Clase riesgo | Sí | Combo | Catálogo | 1 carácter | 1, 2, 3, 4, 5 | Debe estar entre 1 y 5. |
| Nro trabajadores | Sí | Input | Numérico | 1 a 6 dígitos | N/A | Debe coincidir con trabajadores asociados. |
| Transporte | Sí | Combo | Catálogo | 1 carácter | S, N | Obligatorio. |
| Grado riesgo | Sí | Combo | Catálogo | 1 carácter | 1, 2, 3, 4, 5 | Debe coincidir con primer dígito del código actividad. |
| Tarifa | Sí | Input solo lectura | Decimal | 0.000 | Calculada por grado | 1=0.522, 2=1.044, 3=2.436, 4=4.360, 5=6.960. |
| Tipo localización | No | Input | Numérico | Máximo 3 dígitos | MDB | Si se diligencia debe ser numérico. |
| Contacto centro | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |
| Cargo contacto | Sí | Input | Letras | 2 a 150 caracteres | N/A | Solo letras y espacios. |

## 17. Solicitud: Digitación - Trabajadores empresa

Aplica a: Primera vez y Traslado.  
No aplica a: Independiente - Contratista.

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Centro de trabajo | Sí | Combo | Catálogo dinámico | Código centro | Centros registrados en Sede | Debe corresponder a un centro existente. |
| Tipoid | Sí | Combo | Catálogo | 2 caracteres | Selecciona..., CC, TI, PE, PT, CE | Debe seleccionarse valor válido. |
| Numero_id | Sí | Input | Numérico | CC/TI = 7, 8 o 10. CE = menos de 6. Otros = 5 a 15 | N/A | No puede ser igual al número de la empresa. No puede duplicarse con otro trabajador del mismo tipo. |
| Primer_apellido | Sí | Input | Letras | 2 a 80 caracteres legacy | N/A | Solo letras y espacios. Guarda mayúscula. |
| Segundo_apellido | No | Input | Letras | 2 a 80 caracteres legacy si se diligencia | N/A | Solo letras y espacios si se diligencia. |
| primer_nombre | Sí | Input | Letras | 2 a 80 caracteres legacy | N/A | Solo letras y espacios. Guarda mayúscula. |
| segundo_nombre | No | Input | Letras | 2 a 80 caracteres legacy si se diligencia | N/A | Solo letras y espacios si se diligencia. |
| fecha_nacimiento | Sí | Input | Fecha numérica | DDMMAAAA, 8 dígitos | N/A | Debe ser fecha válida y anterior a hoy. |
| edad | Automático | Input solo lectura | Numérico | 1 a 3 dígitos | Calculada | Se calcula desde fecha_nacimiento. |
| sexo | Sí | Combo | Catálogo | 1 carácter | Selecciona..., M, F | Debe ser M o F. |
| afi_tipo | Sí | Combo | Catálogo | Código numérico | tabla tipo cotizante - trabajadores.csv | Debe permitir cualquier código válido. Si es 51 permite salario inferior a SMMLV. |
| salario | Sí | Input | Numérico | Valor entero | N/A | Mayor que 0. Entre 1 y 25 SMMLV, salvo afi_tipo 51. |
| cargo | Sí | Input con búsqueda/lista | Código catálogo | Código cargo | tabla cargo - trabajadores.csv | En pantalla muestra descripción; guarda código. Búsqueda por código o nombre. |
| eps | Sí | Input con búsqueda/lista | Código catálogo | Código EPS | tabla_eps.csv | Debe guardar código EPS válido. Búsqueda por código o nombre. |
| afp | Sí | Input con búsqueda/lista | Código catálogo | Código AFP | tabla_afp.csv | Debe guardar código AFP válido. Búsqueda por código o nombre. |

Reglas adicionales:

- Debe permitir agregar varios trabajadores.
- Debe permitir modificar trabajador registrado.
- Debe permitir eliminar trabajador.
- Al modificar no debe borrar cargo, EPS, AFP ni centro.
- Debe validar duplicados por Tipoid + Numero_id.
- La cantidad por centro debe cuadrar contra Nro trabajadores de cada centro.

## 18. Solicitud: Independiente - Contratista

La solicitud Independiente - Contratista usa radicación y datos del contratista, pero no debe exigir trabajadores.

### 18.1 Campos de radicación

Debe llenar todos los campos de Nuevo contrato:

- Consecutivo Radicación.
- Clase afiliación = Independiente - Contratista.
- Fecha radicación Alfa.
- Fecha inicio vigencia.
- Fecha recibido Imagine.
- Tipo documento.
- No. de identificación.
- Razón social / nombre del contratista.
- Sucursal ARL.
- Tipo entrada = Contratista.
- Documentos del paquete.

### 18.2 Campos de contratista / afiliado

| Campo | Obligatorio | Tipo de control | Tipo de dato | Longitud / formato | Valores de combo / catálogo | Validación |
| --- | --- | --- | --- | --- | --- | --- |
| Tipo documento | Sí | Combo | Catálogo | 2 a 3 caracteres | CC, TI, PE, PT, CE | Debe existir en catálogo. |
| Número documento | Sí | Input | Numérico | CC/TI = 7, 8 o 10. CE = menos de 6. Otros = 5 a 15 | N/A | Solo números. No debe confundirse con NIT de contratante. |
| Primer apellido | Sí | Input | Letras | 2 a 80 caracteres | N/A | Solo letras y espacios. |
| Segundo apellido | No | Input | Letras | 2 a 80 caracteres | N/A | Solo letras y espacios si se diligencia. |
| Primer nombre | Sí | Input | Letras | 2 a 80 caracteres | N/A | Solo letras y espacios. |
| Segundo nombre | No | Input | Letras | 2 a 80 caracteres | N/A | Solo letras y espacios si se diligencia. |
| Fecha nacimiento | Sí | Input | Fecha numérica | DDMMAAAA | N/A | Fecha válida y anterior a hoy. |
| Sexo / género | Sí | Combo | Catálogo | 1 carácter | M, F | Debe ser M o F. |
| EPS | Sí | Input con búsqueda/lista | Código catálogo | Código EPS | tabla_eps.csv | Debe guardar código válido. |
| AFP | Sí | Input con búsqueda/lista | Código catálogo | Código AFP | tabla_afp.csv | Debe guardar código válido. |
| Salario / IBC | Sí | Input | Numérico | Valor entero | N/A | Mayor que 0. Entre 1 y 25 SMMLV, salvo tipo cotizante 51. |
| Cargo | Sí | Input con búsqueda/lista | Código catálogo | Código cargo | tabla cargo - trabajadores.csv | Muestra descripción y guarda código. |
| Afi tipo | Sí | Combo | Catálogo | Código numérico | tabla tipo cotizante - trabajadores.csv | Debe existir. Si es 51 permite salario inferior al SMMLV. |

### 18.3 Reglas especiales contratista

- La pestaña Trabajadores debe ocultarse o no exigirse.
- Si existen trabajadores capturados por error, la validación debe rechazarlos.
- Deben existir soportes de RUT contratista, formulario firmado, autorización de datos, contrato contratante-contratista, cédula contratista, EPS activa y AFP vigente.
- EPS debe estar activa y con expedición menor o igual a 30 días cuando el soporte lo permita.
- AFP debe tener expedición menor o igual a 30 días cuando el soporte lo permita.

## 19. Solicitud: Traslado

La solicitud Traslado usa los mismos campos de empresa, sede y trabajadores, con reglas adicionales:

| Campo | Obligatorio | Tipo de control | Tipo de dato | Valores / catálogo | Validación |
| --- | --- | --- | --- | --- | --- |
| Clase afiliación | Sí | Combo | Catálogo | Traslado | Debe venir desde radicación. |
| ARL traslado | Sí | Combo | Catálogo | Tabla ARL traslado | Obligatorio en radicación si clase = Traslado. |
| Fecha inicio vigencia | Sí | Fecha | Fecha | N/A | Primer día del mes subsiguiente a Fecha radicación Alfa. |
| Fecha inicio cobertura | Sí | Automático | Fecha | N/A | Debe coincidir con Fecha inicio vigencia. |
| Estado cuenta empleador | Condicional legacy | Combo / texto controlado | Catálogo | Al día, En mora, Acuerdo de pago, Incumplimiento de acuerdo de pago | Debe estar en valores legacy permitidos si se usa traslado. |

Documentos adicionales:

- Paz y salvo con anterior ARL.
- Carta solicitud de traslado de ARL anterior.
- Soporte de ARL anterior cuando exista.

## 20. Cargue masivo de trabajadores

Aplica a: Primera vez y Traslado.  
No aplica a: Independiente - Contratista.

| Columna Excel | Obligatorio | Tipo | Formato / longitud | Catálogo | Validación |
| --- | --- | --- | --- | --- | --- |
| TI | Sí | Catálogo | CC, TI, PE, PT, CE | Tipo documento trabajador | Debe ser válido. |
| Documento | Sí | Numérico | Según tipo documento | N/A | Solo números. No duplicado. No igual a NIT empresa. |
| PrimerApellido | Sí | Letras | 2 a 80 | N/A | Solo letras. |
| SegundoApellido | No | Letras | 2 a 80 | N/A | Solo letras si viene. |
| PrimerNombre | Sí | Letras | 2 a 80 | N/A | Solo letras. |
| SegundoNombre | No | Letras | 2 a 80 | N/A | Solo letras si viene. |
| EDAD | No | Numérico | 1 a 3 | Calculada | Puede recalcularse desde fecha nacimiento. |
| FECHADENACIMIENTO | Sí | Fecha | DD/MM/AAAA o DDMMAAAA | N/A | Fecha válida y anterior a hoy. |
| Sexo | Sí | Catálogo | M/F | N/A | Debe ser M o F. |
| Codigo E.P.S | Sí | Código | Numérico/código EPS | tabla_eps.csv | Debe existir. No usar nombre libre. |
| Codigo AFP | Sí | Código | Numérico/código AFP | tabla_afp.csv | Debe existir. No usar nombre libre. |
| SALARIO | Sí | Numérico | Entero mayor a 0 | SMMLV | Entre 1 y 25 SMMLV, salvo tipo cotizante 51. |
| CODIGO CENTRO TRABAJO | Sí | Código | Centro existente | Centros digitados | Debe existir en Sede. |
| CODIGO CARGO | Sí | Código | Código cargo | tabla cargo - trabajadores.csv | Debe existir. No usar nombre libre. |
| FECHA DE INGRESO | Condicional | Fecha | DD/MM/AAAA | N/A | Fecha válida si viene. |
| FECHA DE RECEPCION | Condicional | Fecha | DD/MM/AAAA | N/A | Fecha válida si viene. |
| sucursal | Condicional | Código/catálogo | 1 o nombre sucursal | Sucursales ARL | Debe homologarse. |
| riesgo | Condicional | Numérico | 1 a 5 | Clase riesgo | Debe estar entre 1 y 5. |
| tipo de cotizante | Sí | Código | Numérico | tabla tipo cotizante - trabajadores.csv | Debe existir. |

## 21. Combos y fuentes de valores

| Combo | Valores fijos o fuente |
| --- | --- |
| Clase afiliación | Primera vez, Traslado, Independiente - Contratista |
| Tipo entrada | Empresa, Contratista |
| Tipo documento radicación | NIT, CC, CE, TI, PE, PT |
| Tipo Id digitación | CC, NIT, SC, PT, PE |
| Tipo documento representante | CC, CE, TI, PE, PT, CD, RC, SC |
| Tipo documento responsable sede | CC, CE, TI, PE, PT |
| Tipo documento trabajador | CC, TI, PE, PT, CE |
| Sucursal ARL | Barranquilla, Cali, Dirección General, Medellin |
| Riesgo empresa | I, II, III, IV, V; guarda 1, 2, 3, 4, 5 |
| Clase riesgo centro | 1, 2, 3, 4, 5 |
| Grado riesgo | 1, 2, 3, 4, 5 |
| Tarifa | Calculada: 1=0.522, 2=1.044, 3=2.436, 4=4.360, 5=6.960 |
| Zona | Urbana/Rural o U/R para legacy |
| Transporte | S, N |
| Tipo persona | Jurídica, Natural |
| Régimen Cámara | Simple, Común, Especial |
| OLCSA / PYME | OLCSA, PYME |
| Naturaleza | Privada, Pública |
| Clase sociedad | SA, SAS, LTDA |
| Tamaño | Pequeña, Mediana, Grande |
| Zona localización | U Urbana, R Rural |
| Departamento | Tabla Colombia locations |
| Municipio | Tabla Colombia locations, dependiente de departamento |
| Código actividad económica ARP/926 | `ACTIVITY_RISK_CATALOG` |
| Código actividad Cámara | `CAMARA_COMERCIO_ACTIVITY_CATALOG` desde tabla Código actividad - Cámara de Comercio.xlsx |
| Tipo aportante | `gar_tipos_aportantes.xlsx` |
| Vinculador laboral | `tabla Vinculador laboral - Contratante.csv` |
| Afi tipo / tipo cotizante | `tabla tipo cotizante - trabajadores.csv` |
| Cargo trabajador | `tabla cargo - trabajadores.csv` |
| EPS | `tabla_eps.csv` |
| AFP | `tabla_afp.csv` |
| ARL traslado | `arl riesgos.xlsx` |
