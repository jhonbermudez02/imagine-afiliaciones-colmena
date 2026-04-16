# Matriz Comparativa De Validaciones Legacy Access Vs Portal Actual

Fuentes revisadas:
- [/Users/escobar/Downloads/carga contrato.txt](/Users/escobar/Downloads/carga%20contrato.txt)
- [/Users/escobar/Downloads/carga_sede.txt](/Users/escobar/Downloads/carga_sede.txt)
- [/Users/escobar/Downloads/cargue_dpendientes.txt](/Users/escobar/Downloads/cargue_dpendientes.txt)
- [/Users/escobar/Downloads/cargue_independientes.txt](/Users/escobar/Downloads/cargue_independientes.txt)

Criterio:
- `Cubierto`: ya existe una validación equivalente en el portal actual
- `Parcial`: existe algo parecido, pero no con el mismo alcance o no para todos los flujos
- `Faltante`: no vi una validación equivalente clara en el portal actual
- `Descartar/No copiar`: existe en legacy, pero negocio ya la corrigió o el legado la implementa mal

## Resumen Ejecutivo

Lo ya cubierto en el portal actual:
- duplicados de trabajadores
- cédula no numérica y longitudes por tipo documental principal
- edad mínima
- piso de año de nacimiento `1905`
- sexo obligatorio
- salario mínimo
- EPS/AFP contra catálogos
- modalidad, jornada, tipo salario
- documento del trabajador no igual al del contrato
- vigencia de cámara
- reglas nuevas para estudiantes
- bloque principal del formulario:
  - cédula del responsable de sede/CT
  - teléfono de sede principal
  - correos principales
- independientes:
  - `tipo_cotizante`
  - `tipo_contrato`
  - `fecha_inicio_contrato`
  - `fecha_fin_contrato`
  - `valor_contrato`
  - `valor_mensual`
  - `ibc`
  - `actividad_economica`
  - `codigo_CT`
  - `actividad_economica_CT`
  - `zona_CT`

Lo que aparece en legacy y todavía debemos revisar mejor:
- validación dura de departamento/municipio contra catálogo
- actividad especial / trabajo en alturas
- contactos del centro de trabajo cuando el parser los exponga de forma estable en contratos reales
- tope máximo de salario/IBC

Lo que no debemos copiar ciegamente:
- regla legacy de traslado “mes subsiguiente”
- normalizaciones blandas que llenan `99`, `SIN AFP` o `SIN EPS` en vez de bloquear

## Matriz

| Regla legacy | Archivo legacy | Estado actual | Observación |
| --- | --- | --- | --- |
| Salario menor o igual a 0 / menor a SMLV | `cargue_dpendientes.txt` | Cubierto | Ya existe `XLSX_SECONDARY_SMMLV_BLOCKER` en [/Users/escobar/Desktop/afi-nueva/backend/app/xlsx_rules.py](/Users/escobar/Desktop/afi-nueva/backend/app/xlsx_rules.py). |
| IBC menor a SMLV en independientes | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_IBC_INVALIDO` y además `valor_mensual` / `valor_contrato` mínimos en [/Users/escobar/Desktop/afi-nueva/backend/app/cases.py](/Users/escobar/Desktop/afi-nueva/backend/app/cases.py). |
| Tope máximo de salario: `25 * SMLV` | `cargue_dpendientes.txt` | Faltante | No existe hoy. Requiere confirmación de negocio antes de implementar, porque podría ser regla legacy específica y no universal. |
| Tipo de documento válido | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya existe `TIPO_DOCUMENTO_INVALIDO` en [/Users/escobar/Desktop/afi-nueva/backend/app/cases.py](/Users/escobar/Desktop/afi-nueva/backend/app/cases.py). |
| Longitud máxima de `CC` / `TI` | `cargue_dpendientes.txt` | Cubierto | Ya validamos `CC`, `TI`, `CD`, `RC` con máximo `10`. |
| Longitud máxima de `CE` | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya validamos `CE` con máximo `7`. |
| Longitud máxima de `PA` | `cargue_dpendientes.txt` | Descartar/No copiar | El parser actual no usa `PA`; el catálogo operativo vigente trabaja `PE`/`PT`. Requiere confirmación antes de introducir otra sigla. |
| Longitud máxima de `PT` | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya validamos `PT`/`PE` con máximo `15`. |
| Longitud exacta de `SC` | `cargue_independientes.txt` | Cubierto | Ya validamos `SC` con longitud exacta `9`. |
| Trabajador con mismo documento del contrato | `cargue_dpendientes.txt` | Cubierto | Ya existe `WORKER_DOCUMENT_EQUALS_EMPLOYER`. |
| Cédulas duplicadas | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya existe `DUPLICATE_WORKER_DOCUMENTS`. En nuestro sistema hoy está mejor que en legacy. |
| Primer apellido obligatorio | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Parcial | Hoy validamos nombre completo/no vacío, pero no primer apellido por separado. |
| Primer nombre obligatorio | `cargue_independientes.txt` | Parcial | Igual: nombre general cubierto, pero no fragmentado por componente. |
| Fecha de nacimiento válida y mayoría de edad | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya existe `EDAD_MINIMA_INVALIDA`. Además rechazamos fechas mal armadas por fila. |
| Año de nacimiento no menor a 1905 | `cargue_dpendientes.txt` | Cubierto | Ya existe `FECHA_NACIMIENTO_ANTIGUA_INVALIDA`. |
| Sexo obligatorio y normalizado | `cargue_dpendientes.txt`, `cargue_independientes.txt` | Cubierto | Ya existe `SEXO_VACIO` y `SEXO_INVALIDO`. |
| EPS contra tabla `EpsRiesgos` | ambos | Cubierto | Ya existe `XLSX_SECONDARY_EPS_INVALID` y homologaciones nuevas. |
| AFP contra tabla `AfpRiesgos` | ambos | Cubierto | Ya existe `XLSX_SECONDARY_AFP_INVALID` y homologaciones nuevas. |
| Correo con formato válido | `cargue_dpendientes.txt` | Cubierto | Ya bloqueamos correo inválido por fila y también en el bloque principal del formulario. |
| Departamento y municipio válidos | ambos | Parcial | Nuestro parser lee ubicación, pero no vi una validación dura equivalente contra catálogos de depto/ciudad. |
| Zona válida (`U/R`, urbana/rural) | ambos | Cubierto | Ya validamos `ZONA_INVALIDA`. |
| Modalidad válida | ambos | Cubierto | Ya validamos `MODALIDAD_INVALIDA`. |
| Jornada válida | `cargue_dpendientes.txt` | Cubierto | Ya validamos `JORNADA_INVALIDA`. |
| Tipo de salario válido | ambos | Cubierto | Ya validamos `TIPO_SALARIO_INVALIDO`. |
| Actividad especial / trabajo en alturas | `cargue_dpendientes.txt` | Parcial | Hoy leemos estudiante y actividad económica, pero no vi una validación explícita de trabajo en alturas como regla de negocio. |
| Centro de trabajo: código CT debe existir | `cargue_independientes.txt` | Cubierto | Ya existe `CENTRO_TRABAJO_CODIGO_VACIO`. |
| Centro de trabajo: actividad económica CT válida | `cargue_independientes.txt` | Parcial | Ya exigimos `actividad_economica_CT`, pero aún no la cruzamos contra catálogo ARP. |
| Centro de trabajo: zona CT obligatoria | `cargue_independientes.txt` | Cubierto | Ya existen `INDEPENDIENTE_ZONA_CT_VACIA` / `INDEPENDIENTE_ZONA_CT_INVALIDA`. |
| Teléfono del centro / responsable no inicia en 0 | `carga contrato.txt`, `carga_sede.txt` | Parcial | Ya bloqueamos teléfono de sede principal y teléfonos/celulares de filas; falta endurecer explícitamente el teléfono CT cuando venga por parser estable. |
| Teléfono/celular con longitud exacta | todos | Cubierto | Ya bloqueamos teléfonos/celulares inválidos por fila y teléfono principal de sede. |
| Tipo de cotizante obligatorio | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_TIPO_COTIZANTE_VACIO`. |
| Tipo de contrato obligatorio | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_TIPO_CONTRATO_VACIO`. |
| Fecha inicio contrato obligatoria | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_FECHA_INICIO_CONTRATO_VACIA`. |
| Fecha fin contrato obligatoria | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_FECHA_FIN_CONTRATO_VACIA`. |
| Fecha fin contrato no inferior a inicio cobertura | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_FECHA_FIN_CONTRATO_INVALIDA`. |
| Valor contrato no menor al mínimo | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_VALOR_CONTRATO_INVALIDO`. |
| Valor mensual no menor al mínimo | `cargue_independientes.txt` | Cubierto | Ya existe `INDEPENDIENTE_VALOR_MENSUAL_INVALIDO`. |
| Actividad económica válida contra tabla ARP | `cargue_independientes.txt` | Parcial | Ya exigimos actividad económica por fila, pero aún no la cruzamos contra catálogo ARP. |
| Vigencia de cámara | flujo Access/portal | Cubierto | Ya quedó en `60` días hábiles. |
| Traslado “mes subsiguiente” | `carga contrato.txt` | Descartar/No copiar | Negocio ya corrigió esa regla. |

## Prioridades Reales

### Prioridad 1

Estas sí parecen brechas relevantes del portal actual:
- cruce duro de actividad económica contra catálogo ARP
- validación dura de departamento/municipio contra catálogo
- validaciones explícitas del teléfono del centro de trabajo cuando el parser lo entregue estable
- validación estructurada de actividad especial / trabajo en alturas

### Prioridad 2

Estas requieren decisión de negocio antes de implementarlas:
- tope máximo de salario/IBC a `25 SMLV`
- introducir nuevas siglas documentales legacy no vistas hoy (`PA`) si negocio realmente las usa

## Observaciones De Calidad Del Legacy

El legacy también tiene errores o decisiones no deseables:
- duplica o mezcla criterios entre Access y carga
- a veces normaliza valores inválidos a `99`, `SIN AFP`, `SIN EPS` en vez de bloquear
- maneja algunas reglas con mensajes `MsgBox` y no con estados estructurados
- contiene comparaciones dudosas o corregidas por negocio, como la del traslado

## Siguiente Paso Recomendado

No seguir copiando a ciegas.

Lo correcto ahora es:
- usar esta matriz como corte de cobertura real frente al legacy
- seguir solo con brechas sustentadas por contratos reales o por decisión explícita de negocio
- evitar introducir reglas legacy dudosas sin evidencia, como topes automáticos o normalizaciones blandas
