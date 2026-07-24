# AFILEGA RPA completo, digitación persistida y 926 legacy

Fecha de aprendizaje: 2026-05-11.

## Fuente de verdad operativa

El sistema AFILEGA_FA_IMA_LA_V2 debe conservar la digitación manual del operador dentro del caso y no solo en el navegador. La digitación guardada debe quedar bajo `analysis.digitacion_manual`, con validación MDB y payload `legacy_mdb`.

Cuando un caso se reanaliza, `analysis.digitacion_manual` debe preservarse. Si su validación MDB está correcta, sus campos prevalecen sobre OCR para el perfil operativo (`xlsx_profile.profile`) y para campos equivalentes del formulario (`xlsx_profile.form_fields` / `flat_pairs`).

## Regla práctica para OCR sucio

Si el OCR del formulario trae razón social contaminada con texto de etiquetas, por ejemplo `Tipo de documento`, no debe reemplazar una digitación manual válida. Si Cámara de Comercio trae razón social legible pero el formulario/Excel está contaminado por OCR y el RUT/NIT es consistente, el hallazgo debe quedar como revisión visual no bloqueante.

## Flujo PDF-only

Los paquetes sin XLSX deben poder correr RPA completo. Si no existe `contrato_clean` desde Excel, el backend debe construir un `contrato_clean_auto.txt` desde el perfil OCR/digitación y documentos del caso. Si tampoco hay relación de trabajadores estructurada, debe construir un bloque `independientes_clean` de respaldo para que el clone legacy pueda importar empleador y trabajador.

## Resultado verificado

Caso verificado: `case-colima-20e578232d`.

El RPA completo ejecutó correctamente:

- Prevalidación documental: OK.
- Manifiesto: OK.
- Carga lote legacy: OK.
- Limpieza/preparación: OK.
- Importación a `proc_servicios`: OK.
- Sincronización al engine legacy: OK.
- Prebuild validaciones legacy: OK.
- Reporte previo: OK.
- Generación 926: OK.
- Reporte final: OK.
- Cierre: OK.

El endpoint `/api/cases/case-colima-20e578232d/926` entregó contenido legacy real después del workflow, con `output_926.mode = legacy` y `legacy.ok = true`.

## Nota para operación

Si el 926 sale con nombres contaminados por OCR, no se debe cambiar a mano el plano. El operador debe corregir el formulario en Digitación, guardar el borrador en backend, reanalizar y volver a correr el workflow. Así el perfil, reporte y 926 toman la fuente manual validada contra MDB.
