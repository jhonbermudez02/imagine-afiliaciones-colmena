# Matriz De Extracción Legacy: `json_afa.php`

Fuente revisada:
- `/Users/escobar/Downloads/json_afa.php`

Objetivo:
- identificar qué bloques del layout legacy extraía este PHP
- mapearlos contra la lectura actual del portal
- separar extracción de validación de negocio

Conclusión ejecutiva:
- `json_afa.php` no implementa validaciones de negocio ni causales de rechazo
- su función es transformar JSON intermedio del XLSX a TXT legacy
- sí sirve como referencia de extracción estructural del layout

## Resumen

| Bloque legacy | Cómo lo extrae `json_afa.php` | Equivalente actual | Cobertura actual |
| --- | --- | --- | --- |
| Formulario base | Lee `contrato_<id>.json` y exporta filas específicas | `_extract_form_fields_from_sheet()` y `_extract_form_fields_from_clean_lines()` en `cases.py` | Alta |
| Tipo de trámite | Usa `fila_13[13] == 'X'` para detectar traslado | `detect_tipo_tramite()` + chequeo de filas 25/28 | Alta |
| Afiliación | Toma campos desde `fila_26` | `a_*` en `_extract_form_fields_from_sheet()` | Alta |
| Traslado | Toma campos desde `fila_29` y `fila_30` | `b_*` en `_extract_form_fields_from_sheet()` | Alta |
| Conteo de trabajadores desde formulario | Usa `fila_26[21]` o `fila_29[32]` | `a_numero_inicial_trabajadores_estudiantes` / `b_numero_total_trabajadores_estudiantes` | Alta |
| Bloque de trabajadores por sede | Busca `"Número de trabajadores"` y calcula fila inicial | `_extract_worker_records_from_rows()` + `_extract_worker_sheet_control_totals()` | Media/Alta |
| Hojas `Sede X - Trabajadores` | Procesa todos los `*Trabajadores*.json` | `_read_xlsx()` recorre hojas y normaliza nombres | Alta |
| Independientes 723 | Lee `independientes_<id>.json` y exporta a TXT | `_generate_clean_from_workbook()` + clean preview; lectura parcial actual | Media |

## Detalle Por Bloque

### 1. Formulario base

`json_afa.php` exporta estas filas/columnas del JSON del formulario:

- `fila_6` -> `[6, 11, 17, 24, 33, 41]`
- `fila_7` -> `[6, 11, 17, 24, 36, 43]`
- `fila_13` -> `[3, 8, 13, 19, 25, 27, 32, 38, 40, 44, 46]`
- `fila_16` -> `[3, 9, 19, 21, 23, 32, 47]`
- `fila_17` -> `[3, 9, 20, 32, 42]`
- `fila_18` -> `[3, 7, 9, 15, 21, 26]`
- `fila_20` -> `[3, 7, 12, 16, 20, 33, 39]`
- `fila_21` -> `[3, 7, 12, 33, 39]`
- `fila_22` -> `[3, 7, 16, 19, 20, 27, 39, 44]`
- `fila_23` -> `[3, 10, 21, 33, 43]`
- `fila_24` -> `[3, 7, 9, 15, 21, 26]`
- `fila_26` -> `[6, 7, 12, 15, 16, 18, 21, 23, 29, 38, 42]`
- `fila_29` -> `[3, 7, 12, 15, 18, 23, 26, 28, 32, 33, 38, 42, 45]`
- `fila_30` -> `[3]`

Cobertura actual:
- `cases.py` ya lee este mismo bloque por coordenadas fijas en `_extract_form_fields_from_sheet()`
- además tiene fallback por labels en `_extract_form_fields_from_clean_lines()`

Lectura actual relevante:
- fila 7: fechas y radicación
- filas 16-18: empleador y representante
- filas 20-24: sede principal y responsable
- fila 26: bloque `a_*` de afiliación
- filas 29-30: bloque `b_*` de traslado

### 2. Tipo de trámite

Legacy:
- usa `fila_13[13] == 'X'` para decidir si el caso es `Traslado`
- si no, toma el bloque de `Afiliación`

Actual:
- `detect_tipo_tramite()` en `cases.py`
- refuerzo con contenido de fila 25 y fila 28

Cobertura actual:
- alta

### 3. Conteo de trabajadores desde formulario

Legacy:
- para `Traslado` usa `fila_29[32]`
- para `Afiliación` usa `fila_26[21]`

Actual:
- `a_numero_inicial_trabajadores_estudiantes`
- `b_numero_total_trabajadores_estudiantes`
- luego cae a `profile.numero_trabajadores`

Cobertura actual:
- alta

### 4. Bloque de trabajadores en hojas de sede

Legacy:
- recorre cada JSON `*Trabajadores*.json`
- primero exporta unas filas fijas:
  - `fila_12`, `fila_13`, `fila_14`, `fila_15`, `fila_16`, `fila_18`
- luego busca el texto `"Número de trabajadores"`
- toma la fila donde aparece
- calcula:
  - `linea_trab = linea + 2`
  - `trab = valor_pos38`
- y lee `trab` filas desde ahí usando un conjunto fijo de columnas `camposFila39`

Actual:
- `_extract_worker_records_from_rows()` detecta el header real
- `_extract_worker_sheet_control_totals()` detecta totales de control
- `_read_xlsx()` consolida registros, conteos y nómina por hoja

Cobertura actual:
- media/alta

Observación:
- aquí sí hay una referencia útil del legacy: la búsqueda de `"Número de trabajadores"` como ancla del bloque
- puede servir como fallback adicional si aparece un formato raro donde el header no se detecte bien

### 5. Independientes 723

Legacy:
- procesa `independientes_<id>.json`
- busca `"Nº CONTRATO INDEPENDIENTE"`
- a partir de esa fila calcula el bloque detalle
- recorre `trab` filas con 88 columnas

Actual:
- no hay una validación/lectura específica tan estructurada como en el PHP
- hoy lo más parecido está en `clean_preview` y extracción general

Cobertura actual:
- media

Observación:
- si negocio sigue usando mucho `INDEPENDIENTES 723`, aquí sí podría haber una brecha de extracción

## Qué No Hace El Legacy

Este PHP no implementa reglas de negocio de rechazo/aprobación. No encontré lógica para:

- cédulas duplicadas
- salarios inflados
- salario mínimo
- EPS/AFP válidas
- edad mínima
- sexo obligatorio
- validación de fechas
- validación de nómina
- vigencia de cámara
- razón social
- soportes obligatorios

Eso significa:
- no se debe usar `json_afa.php` como fuente de validaciones faltantes
- sí se puede usar como referencia de layout y extracción

## Recomendación

Usar este archivo para:
- auditar cobertura de extracción
- reforzar fallback de lectura en hojas de trabajadores
- revisar si falta algo específico de `INDEPENDIENTES 723`

No usar este archivo para:
- copiar reglas de negocio
- decidir causales de rechazo

## Siguiente Paso Sugerido

Buscar el verdadero validador legacy:
- PHP/Python/SQL/BAT que construya errores, mensajes o decisiones
- cualquier módulo que haga comparaciones o genere rechazos

Si no aparece otro validador, entonces el siguiente análisis útil sería:
- comparar este mapeo de extracción con contratos reales que hoy todavía fallan por lectura del layout
