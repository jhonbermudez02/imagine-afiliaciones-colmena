# AFILEGA MDB Fuente Oficial De Validaciones

Fuente que prevalece: `/Users/escobar/Downloads/Afiliaciones.mdb`.

Este archivo Access corresponde al sistema AFILEGA_FA_IMA_LA_V2. Cualquier matriz o catálogo heredado de otro sistema queda como referencia secundaria y no debe imponerse cuando contradiga este MDB.

## Identificación

- Base: Microsoft Access `Afiliaciones.mdb`
- Versión reportada en tabla `VersionL`: `5.2`
- Usuario local observado en `datos_local`: `dirojas`

## Tablas Legacy Principales

- `afi_empresa_local`: datos del empleador/contratante.
- `afi_centros_local`: centros de trabajo y sedes.
- `afi_medio_local` y `afi_medio_local__`: trabajadores, EPS, AFP, IBC, tipo y subtipo cotizante.
- `Plano_Emp_Tmp`: estructura legacy para plano de empresa.
- `Plano_Emp_TmpN`: estructura legacy para plano de trabajadores.
- `Plano_Nov_Tmp`: estructura legacy de novedades.
- `afi_documentos`: catálogo oficial de tipos documentales del MDB.
- `afi_digito`: multiplicadores oficiales para calcular el dígito de verificación del NIT.

## Catálogo Documental Del MDB

1. AFILIACION
2. SEDES
3. LISTADO TRABAJADORES
4. CARTA
5. CEDULA
6. RUT
7. CAMARA DE COMERCIO
10. NOMINA ANEXA

Los nombres documentales operativos modernos se deben mapear a estos códigos cuando se genere compatibilidad legacy/926. Por ejemplo: formulario de afiliación va a `1`, sedes va a `2`, relación de ingreso/listado de trabajadores va a `3`, cédulas van a `5`, RUT va a `6`, cámara de comercio va a `7`, y listado documentos entregados o nómina anexa va a `10`. Los nombres NIT, ANEXO y PLANILLA DE PAGO no deben mostrarse como tipos documentales operativos.

## Reglas De Validación Que Deben Prevalecer

- El NIT debe validarse contra dígito de verificación cuando el DV esté disponible.
- Multiplicadores de DV, en orden legacy: `71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3`.
- Departamento legacy usa código de 2 caracteres y municipio/ciudad usa código de 3 caracteres en tablas planas.
- Actividad económica de centro de trabajo usa longitud 7 en `afi_centros_local`.
- Clase de riesgo de centro de trabajo usa longitud 1 en el MDB, aunque en pantalla pueda mostrarse como I a V.
- Teléfonos y fax usan máximo 10 caracteres.
- Documentos de trabajador usan máximo 15 caracteres en tablas locales y 16 en plano de novedades.
- Nombres y apellidos de trabajador usan máximo 80 caracteres.
- Razón social de empresa usa máximo 200 caracteres.
- Dirección de empresa usa máximo 50 caracteres; dirección de centro de trabajo usa máximo 80.
- EPS y AFP en `afi_medio_local` usan máximo 30 caracteres.
- Cargo/actividad del trabajador en `afi_medio_local` usa texto descriptivo hasta 150 caracteres.
- Tipo de cotizante observado en el MDB: `1` y `19`.
- Subtipo de cotizante observado en el MDB: `999`.
- Novedades observadas en `Plano_Nov_Tmp`: `00` y `08`.
- Estado de novedad observado: `1`.
- Autoliquidación observada: `N`.
- Origen observado: `C`.
- Para la digitación se deben conservar campos legacy de empresa como forma de pago, tipo aportante, vinculador laboral, régimen, naturaleza jurídica, clase de sociedad, tamaño, grupo empresarial, tipo/zona de localización, Pyme, OLCSA, contratante y ARL anterior.
- Para centros de trabajo se deben conservar transporte, grado, tarifa, tipo de localización, contacto, cargo del contacto y fax cuando el OCR o el operador los entregue.
- Para novedades se deben capturar estado, autoliquidación, origen, días, valor anterior, valor nuevo y traslado cuando aplique.
- En generación compatible con MDB, los departamentos se deben convertir a código legacy de 2 dígitos y los municipios a código legacy de 3 dígitos. Si el dato llega como DIVIPOLA de 5 dígitos, el departamento son los 2 primeros dígitos y el municipio son los 3 últimos.

## Criterio Operativo

Cuando el sistema reciba OCR o digitación, debe conservar los nombres comprensibles para el operador, pero guardar y validar contra las reglas anteriores para no romper el plano legacy. Si existe conflicto entre una regla de otro sistema y este MDB, gana este MDB.
