# Especificacion de formularios de digitacion AFILEGA

Este documento describe la estructura que debe replicar otro sistema para construir los formularios de digitacion del modulo AFILEGA. La fuente funcional es el frontend actual:

- `frontend-nova/index.html`
- `frontend-nova/main.js`
- `frontend-nova/digitacion-catalogs.js`
- `frontend-nova/colombia-locations.js`
- `frontend-nova/camara-comercio-catalog.js`
- `frontend-nova/cargo-trabajadores-catalog.js`
- `frontend-nova/tipo-cotizante-trabajadores-catalog.js`
- `frontend-nova/vinculador-laboral-contratante-catalog.js`

## Estructura general

La digitacion esta dividida en cuatro formularios funcionales:

1. Radicacion del contrato: se captura antes de cargar documentos, en la pantalla Nuevo contrato.
2. Afiliacion: datos de contratante/responsable, representante legal, Camara de Comercio, contacto pagos y contacto SST.
3. Sede: sede principal, centro de trabajo principal y centros adicionales.
4. Trabajadores: trabajadores amarrados a centro de trabajo, con opcion de agregar varios y cargue masivo Excel.

Reglas globales:

- Los datos se guardan en mayuscula.
- Los campos con `*` son obligatorios.
- Los combos deben tener opcion inicial vacia: `Selecciona...`.
- Los telefonos y celulares se validan como numericos de 10 digitos.
- Los correos deben cumplir formato `usuario@dominio.ext`.
- Los campos de solo lectura se muestran pero no se editan.
- El salto entre campos debe funcionar con Enter.
- En afiliaciones de tipo `Independiente - Contratista` no se exige la seccion Trabajadores.

## Catalogos requeridos

| Catalogo | Archivo fuente | Uso | Tamano actual |
|---|---|---:|---:|
| EPS | `frontend-nova/digitacion-catalogs.js` | Campo EPS trabajador | 130 |
| AFP | `frontend-nova/digitacion-catalogs.js` | Campo AFP trabajador | 12 |
| Actividad economica ARP/926 | `frontend-nova/digitacion-catalogs.js` | Codigo actividad afiliacion y sedes | 1425 |
| Actividad Camara de Comercio | `frontend-nova/camara-comercio-catalog.js` | Codigo actividad Camara | 1063 |
| Cargo trabajadores | `frontend-nova/cargo-trabajadores-catalog.js` | Cargo trabajador | 401 |
| Tipo cotizante | `frontend-nova/tipo-cotizante-trabajadores-catalog.js` | Afi tipo trabajador | 28 |
| Vinculador laboral | `frontend-nova/vinculador-laboral-contratante-catalog.js` | Vinculador laboral contratante | 10 |
| Departamentos/municipios | `frontend-nova/colombia-locations.js` | Combos dependientes departamento/municipio | 33 departamentos, 1121 municipios |

Los campos de catalogo deben permitir busqueda por codigo y por nombre cuando aplique. En `cargo`, `EPS` y `AFP` se debe guardar el codigo, aunque en pantalla se muestre codigo + descripcion.

## 1. Radicacion del contrato

Pantalla: Nuevo contrato.

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Consecutivo Radicacion | `numero_radicacion` | input texto readonly | Si | Secuenciador automatico Imagine. No editable. |
| Clase afiliacion | `tipo_afiliacion` | select | Si | `Primera vez`, `Traslado`, `Independiente - Contratista`. |
| Fecha radicacion Alfa | `fecha_radicacion` | date | Si | No puede ser mayor a la fecha actual. |
| Fecha inicio vigencia | `fecha_inicio_vigencia` | date | Si | Si Clase afiliacion es `Traslado`, calcular mes subsiguiente a Fecha radicacion Alfa. |
| Fecha recibido Imagine | `fecha_recibido_imagine` | date | Si | Debe ser mayor o igual a Fecha radicacion Alfa y menor o igual a fecha actual. |
| ARL traslado | `empresa_arl_anterior` | select | Condicional | Obligatorio si Clase afiliacion es `Traslado`. Catalogo ARL traslado. |
| Tipo documento | `empleador_tipo_documento` | select | Si | `NIT`, `CC`, `CE`, `TI`, `PE`, `PT`. |
| No. de identificacion | `nit` | input numerico | Si | Si tipo `NIT`, longitud 9. Si tipo `CC`, longitud 7, 8 o 10; no permite longitud 9. |
| Razon social | `razon_social` | input texto | Si | Alfanumerico, guardar en mayuscula. |
| Sucursal ARL | `sucursal` | select | Si | `Barranquilla`, `Cali`, `Direccion General`, `Medellin`. |

Valores actuales de ARL traslado:

`0 NO SUMINISTRADO`, `0 DESCONOCIDO`, `1 COLPATRIA`, `10 COLFONDOS`, `11 INVERTIR`, `12 ING`, `13 OLD MUTUAL`, `14 PROTECCION`, `16 CALDAS`, `19 PENSIONAR`, `2 COLPENSIONES`, `20 FONPRENOR`, `23 CAJANAL`, `24 PENSIONADOS`, `25 BONSALUD`, `3 PORVENIR`, `4 SKANDIA`, `5 HORIZONTE`, `50 MUNICIPIO`, `6 GANADERA`, `73 CONSORCIO FIDUFOSYGA`, `75 CAJA DE PREVISION SOCIAL UNIV.DCT`, `77 SERV. DE SALUD DE LA UNIV. DEL CAUCA`, `8 DAVIVIR`, `9 SKANDIA`, `95 CAJA DE PREVISION SOCIAL STAFE DE BOGOTA`, `98 CAPRECUNDI`, `99 SIN AFP`.

## 2. Digitacion / Afiliacion

Pestana: Afiliacion.

### 2.1 Contratante / responsable de afiliacion

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Clase afiliacion | `tipo_afiliacion` | select readonly | Si | `Primera vez`, `Traslado`, `Independiente - Contratista`. Se trae desde radicacion. |
| Tipo Id | `empleador_tipo_documento` | select readonly | Si | `CC`, `NIT`, `SC`, `PT`, `PE`. Se trae desde radicacion. |
| Nro NIT | `nit` | input readonly numerico | Si | Si Tipo Id es `NIT`, 9 digitos. Si `CC`, 7, 8 o 10; no longitud 9. |
| Razon social | `razon_social` | input texto | Si | Alfanumerico, maximo 200, mayuscula. |
| Digito verificacion | `nit_dv` | input numerico | Si | Un digito. Debe coincidir con calculo DV del NIT. |
| Codigo actividad economica | `codigo_actividad_economica` | input catalogo | Si | Catalogo actividad economica ARP/926. Debe ser codigo valido de 7 digitos. |
| Actividad principal | `actividad_principal_empresa` | input texto | No | Se autocompleta desde codigo actividad. |
| Riesgo | `clase_riesgo_empresa` | select | Si | `1/I`, `2/II`, `3/III`, `4/IV`, `5/V`. |
| Direccion sede principal | `direccion_empresa` | input texto | Si | Alfanumerico/direccion. |
| Departamento | `departamento_empresa` | select | Si | Catalogo Colombia. Debe sincronizar con municipio. |
| Municipio / distrito | `municipio_empresa` | select dependiente | Si | Al escoger municipio debe inferirse/validarse departamento. |
| Correo electronico | `correo_empresa` | email | Si | Correo valido. |
| Telefono | `telefono_empresa` | tel numerico | Si | 10 digitos. |
| Tipo persona | `tipo_persona` | select | No | `Juridica`, `Natural`. |
| Tipo aportante | `empresa_tipo_aportante` | select | Si | Tabla `gar_tipos_aportantes`; valores actuales 1,2,3,4,5,6,7,8,999. |
| Clase aportante | `empresa_clase_aportante` | input numerico | Si | Codigo numerico, maximo 3 digitos; puede derivarse de Tipo aportante. |
| Vinculador laboral | `empresa_vinculador_laboral` | select catalogo | Si | Catalogo vinculador laboral contratante. |

### 2.2 Representante legal

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Nombre completo | `rep_legal_nombre_completo` | input texto | Si | Solo letras, espacios y signos permitidos. |
| Tipo documento | `rep_legal_tipo_documento` | select | Si | `CC`, `NIT`, `SC`, `PT`, `PE`. |
| Numero documento | `rep_legal_numero_documento` | input numerico | Si | Regla general documento: 5 a 15 digitos; si aplica CC, 7/8/10. |
| Correo representante | `rep_legal_correo` | email | Si | Correo valido. |
| Cargo | `rep_legal_cargo` | input texto | Si | Solo letras y espacios. |

### 2.3 Camara de Comercio

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Fecha constitucion | `camara_fecha_constitucion` | date | Si | Fecha valida, no puede ser mayor a la fecha actual. |
| Regimen | `camara_regimen` | select | Si | `Simple`, `Comun`, `Especial`. |
| Codigo actividad | `camara_codigo_actividad` | input catalogo | Si | Catalogo Camara de Comercio. Codigo numerico de 4 a 7 digitos. |
| Actividad principal | `camara_actividad_principal` | input texto | Si | Se autocompleta desde codigo Camara. Maximo funcional 250 caracteres. |
| OLCSA / PYME | `camara_olcsa_pyme` | select | Si | `OLCSA`, `PYME`. |
| Naturaleza | `camara_naturaleza` | select | Si | `Privada`, `Publica`. |
| Clase sociedad | `camara_clase_sociedad` | select | Si | `SA`, `SAS`, `LTDA`. |
| Tamano | `camara_tamano` | select | Si | `Pequena`, `Mediana`, `Grande`. |
| Grupo empresarial | `camara_grupo_empresarial` | input texto | No | Texto libre. |
| Tipo localizacion | `camara_tipo_localizacion` | input texto | No | Texto/codigo. |
| Zona localizacion | `camara_zona_localizacion` | select | No | `U`, `R` o equivalente urbano/rural segun catalogo. |

### 2.4 Datos contacto pagos

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion |
|---|---|---|---|---|
| Nombre | `contacto_pagos_nombre` | input texto | Si | Solo letras y espacios. |
| Cargo | `contacto_pagos_cargo` | input texto | Si | Solo letras y espacios. |
| Correo electronico | `contacto_pagos_correo` | email | Si | Correo valido. |
| Direccion | `contacto_pagos_direccion` | input texto | Si | Alfanumerico/direccion. |
| Departamento | `contacto_pagos_departamento` | select | Si | Catalogo Colombia. |
| Ciudad | `contacto_pagos_municipio` | select dependiente | Si | Depende del departamento. |
| Telefono | `contacto_pagos_telefono` | tel numerico | Si | 10 digitos. |
| Celular | `contacto_pagos_celular` | tel numerico | Si | 10 digitos. |

### 2.5 Datos contacto SST

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion |
|---|---|---|---|---|
| Nombre | `contacto_sst_nombre` | input texto | Si | Solo letras y espacios. |
| Cargo | `contacto_sst_cargo` | input texto | Si | Solo letras y espacios. |
| Correo electronico | `contacto_sst_correo` | email | Si | Correo valido. |
| Direccion | `contacto_sst_direccion` | input texto | Si | Alfanumerico/direccion. |
| Departamento | `contacto_sst_departamento` | select | Si | Catalogo Colombia. |
| Ciudad | `contacto_sst_municipio` | select dependiente | Si | Depende del departamento. |
| Telefono | `contacto_sst_telefono` | tel numerico | Si | 10 digitos. |
| Celular | `contacto_sst_celular` | tel numerico | Si | 10 digitos. |

## 3. Digitacion / Sede

Pestana: Sede.

### 3.1 Sede

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Nombre sede o centro | `sede_nombre` | input texto | Si | Solo letras/alfanumerico segun nombre de sede. |
| Sucursal | `sede_sucursal` | select | Si | `Barranquilla`, `Cali`, `Direccion General`, `Medellin`. |

### 3.2 Datos del centro de trabajo principal

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Codigo centro de trabajo | `sede_codigo` | input numerico | Si | Numerico. |
| Nombre centro de trabajo | `sede_centro_trabajo_nombre` | input texto | Si | Alfanumerico, maximo 60 caracteres. |
| Direccion centro de trabajo | `sede_direccion` | input texto | Si | Alfanumerico/direccion. |
| Departamento | `sede_departamento` | select | Si | Catalogo Colombia. |
| Municipio | `sede_municipio` | select dependiente | Si | Depende del departamento. |
| Zona | `sede_zona` | select | Si | `urbana`, `rural` o codigos equivalentes `U/R`. |
| Telefono | `sede_telefono` | tel numerico | Si | 10 digitos. |
| Celular | `sede_celular` | tel numerico | No | 10 digitos si se diligencia. |
| Fax | `sede_fax` | tel numerico | No | Numerico. |
| Correo | `sede_correo` | email | Si | Correo valido. |
| Codigo actividad economica | `sede_codigo_actividad` | input catalogo | Si | Catalogo actividad economica ARP/926, codigo de 7 digitos. |
| Clase de riesgo centro | `sede_clase_riesgo` | select | Si | `1`, `2`, `3`, `4`, `5`. |
| Nro trabajadores | `sede_numero_trabajadores` | input numerico | Si | Conteo numerico. Debe coincidir con cantidad de trabajadores registrados para ese centro. |
| Transporte | `sede_transporte` | select | Si | `S`, `N`. |
| Grado riesgo | `sede_grado` | select | Si | `1`, `2`, `3`, `4`, `5`. Primer digito debe coincidir con primer digito del codigo de actividad economica. |
| Tarifa | `sede_tarifa` | input number readonly | Si | Se calcula por grado: 1=0.522, 2=1.044, 3=2.436, 4=4.360, 5=6.960. |
| Tipo localizacion | `sede_tipo_localizacion` | input numerico | No | Codigo numerico. |
| Contacto centro | `sede_contacto` | input texto | Si | Solo letras y espacios. |
| Cargo contacto | `sede_cargo_contacto` | input texto | Si | Solo letras y espacios. |
| Responsable sede | `responsable_sede_principal_nombre_completo` | input texto | No | Solo letras y espacios. |
| Tipo doc responsable | `responsable_sede_principal_tipo_documento` | select | No | `CC`, `CE`, `TI`, `PE`, `PT`. |
| Doc responsable | `responsable_sede_principal_numero_documento` | input numerico | No | Documento numerico valido. |

### 3.3 Centros de trabajo adicionales

El boton `Agregar centro` abre un formulario con los mismos campos funcionales del centro principal. Cada centro adicional debe validar obligatorios antes de agregarse.

Campos obligatorios por centro adicional:

`codigo`, `nombre`, `sucursal`, `direccion`, `departamento`, `municipio`, `zona`, `telefono`, `codigo_actividad`, `clase`, `trabajadores`, `grado`, `contacto`, `cargo_contacto`.

Campos adicionales disponibles:

`celular`, `fax`, `correo`, `transporte`, `tarifa`, `tipo_localizacion`.

Reglas:

- Debe permitirse editar un centro agregado.
- Debe mostrarse claramente donde estan los errores.
- Los trabajadores deben poder asociarse a cualquiera de los centros registrados.
- La suma/cantidad de trabajadores del centro debe validarse contra los trabajadores asociados.

## 4. Digitacion / Trabajadores

Pestana: Trabajadores. No aplica para `Independiente - Contratista`.

| Campo visible | Clave tecnica | Control | Obligatorio | Validacion / valores |
|---|---|---|---|---|
| Centro de trabajo | `trabajador_centro_trabajo` | select | Si | Debe corresponder a un centro registrado. |
| Tipoid | `tipo_documento_afiliado` | select | Si | `CC`, `TI`, `PE`, `PT`, `CE`. |
| Numero_id | `documento_afiliado` | input numerico | Si | Si `CC` o `TI`: 7, 8 o 10 digitos; no longitud 9. Si `CE`: menos de 6 digitos. Otros: 5 a 15 digitos. |
| Primer_apellido | `primer_apellido` | input texto | Si | Solo letras y espacios. |
| Segundo_apellido | `segundo_apellido` | input texto | No | Solo letras y espacios si se diligencia. |
| primer_nombre | `primer_nombre` | input texto | Si | Solo letras y espacios. |
| segundo_nombre | `segundo_nombre` | input texto | No | Solo letras y espacios si se diligencia. |
| fecha_nacimiento | `fecha_nacimiento` | input numerico | Si | Formato `DDMMAAAA`; fecha valida. |
| edad | `edad` | input readonly | No | Se calcula con fecha de nacimiento. |
| sexo | `genero` | select | Si | `M`, `F`. |
| afi_tipo | `tipo_cotizante` | select catalogo | Si | Tabla tipo cotizante trabajadores. |
| salario | `ibc` | input numerico | Si | Numerico. No menor a SMMLV ni mayor a 25 SMMLV, excepto tipo cotizante `51`, que permite salario inferior al SMMLV. |
| cargo | `cargo_actividad` | input/autocomplete catalogo | Si | Tabla cargo trabajadores. Se guarda codigo; pantalla muestra descripcion. |
| eps | `eps` | input/autocomplete catalogo | Si | Codigo EPS valido. Buscar por codigo y nombre. |
| afp | `afp` | input/autocomplete catalogo | Si | Codigo AFP valido. Buscar por codigo y nombre. |

Reglas de trabajadores:

- No permitir dos trabajadores con el mismo tipo y numero de documento.
- El documento del trabajador no puede ser igual al numero de la empresa.
- Los trabajadores quedan amarrados a un centro de trabajo.
- Debe existir opcion de agregar trabajador, modificar trabajador y cargue masivo Excel.
- Al modificar un trabajador no se debe borrar el cargo.
- El cargue masivo guarda codigos de cargo, EPS y AFP, no nombres.

## 5. Cargue masivo de trabajadores

Formato esperado:

| Columna Excel | Campo destino | Observacion |
|---|---|---|
| TI | `tipo_documento_afiliado` | Codigo documento. |
| Documento | `documento_afiliado` | Numerico. |
| PrimerApellido | `primer_apellido` | Texto. |
| SegundoApellido | `segundo_apellido` | Texto opcional. |
| PrimerNombre | `primer_nombre` | Texto. |
| SegundoNombre | `segundo_nombre` | Texto opcional. |
| EDAD | `edad` | Puede venir o calcularse. |
| FECHADENACIMIENTO | `fecha_nacimiento` | Se normaliza a `DDMMAAAA`. |
| Sexo | `genero` | `M` o `F`. |
| Codigo E.P.S | `eps` | Codigo EPS estandarizado. |
| Codigo AFP | `afp` | Codigo AFP estandarizado. |
| SALARIO | `ibc` | Numerico. |
| CODIGO CENTRO TRABAJO | `trabajador_centro_trabajo` | Debe existir en sedes. |
| CODIGO CARGO | `cargo_actividad` | Codigo cargo estandarizado. |
| FECHA DE INGRESO | campo auxiliar/importacion | Fecha. |
| FECHA DE RECEPCION | campo auxiliar/importacion | Fecha. |
| sucursal | campo auxiliar/importacion | Codigo o nombre. |
| riesgo | campo auxiliar/importacion | Riesgo 1 a 5. |
| tipo de cotizante | `tipo_cotizante` | Codigo catalogo. |

## 6. Reglas transversales de validacion

### Documentos

- Empresa Tipo Id `NIT`: Nro NIT debe tener exactamente 9 digitos.
- Empresa Tipo Id `CC`: numero debe tener 7, 8 o 10 digitos; no puede tener 9.
- Trabajador tipo `CC` o `TI`: numero debe tener 7, 8 o 10 digitos; no puede tener 9.
- Trabajador tipo `CE`: numero debe tener menos de 6 digitos.
- Otros documentos: entre 5 y 15 digitos.

### Fechas

- Radicacion Alfa no puede ser mayor a la fecha actual.
- Fecha recibido Imagine debe ser mayor o igual a Radicacion Alfa y menor o igual a fecha actual.
- Fecha inicio vigencia se calcula para traslado como mes subsiguiente.
- Camara de Comercio no puede tener fecha futura.
- Fecha nacimiento trabajador debe ser numerica `DDMMAAAA` y valida.

### Texto y numeros

- Campos alfabeticos: letras, espacios, apostrofe, punto y guion.
- Campos alfanumericos: letras, numeros y signos basicos de direccion/razon social.
- Campos numericos: bloquear caracteres no numericos.
- Telefonos y celulares: 10 digitos.
- Correos: formato con `@` y dominio.

### Actividad economica y riesgo

- Codigo actividad economica afiliacion/sedes: catalogo ARP/926, 7 digitos.
- Codigo actividad Camara: catalogo Camara de Comercio, 4 a 7 digitos.
- Riesgo/clase/grado: valores 1 a 5.
- En sedes, primer digito del grado de riesgo debe coincidir con primer digito del codigo de actividad economica.
- Tarifa automatica por grado:
  - 1 -> 0.522
  - 2 -> 1.044
  - 3 -> 2.436
  - 4 -> 4.360
  - 5 -> 6.960

### Salario / IBC

- IBC trabajador no puede ser inferior al SMMLV configurado.
- IBC trabajador no puede superar 25 SMMLV.
- Excepcion: tipo cotizante `51` permite IBC inferior al SMMLV.

## 7. Payload tecnico sugerido

El otro sistema deberia guardar los datos con estas claves principales:

```json
{
  "radicacion": {
    "numero_radicacion": "",
    "tipo_afiliacion": "",
    "fecha_radicacion": "",
    "fecha_inicio_vigencia": "",
    "fecha_recibido_imagine": "",
    "empresa_arl_anterior": "",
    "empleador_tipo_documento": "",
    "nit": "",
    "razon_social": "",
    "sucursal": ""
  },
  "afiliacion": {
    "tipo_afiliacion": "",
    "empleador_tipo_documento": "",
    "nit": "",
    "razon_social": "",
    "nit_dv": "",
    "codigo_actividad_economica": "",
    "actividad_principal_empresa": "",
    "clase_riesgo_empresa": "",
    "direccion_empresa": "",
    "departamento_empresa": "",
    "municipio_empresa": "",
    "correo_empresa": "",
    "telefono_empresa": "",
    "tipo_persona": "",
    "empresa_tipo_aportante": "",
    "empresa_clase_aportante": "",
    "empresa_vinculador_laboral": "",
    "rep_legal_nombre_completo": "",
    "rep_legal_tipo_documento": "",
    "rep_legal_numero_documento": "",
    "rep_legal_correo": "",
    "rep_legal_cargo": "",
    "camara_fecha_constitucion": "",
    "camara_regimen": "",
    "camara_codigo_actividad": "",
    "camara_actividad_principal": "",
    "camara_olcsa_pyme": "",
    "camara_naturaleza": "",
    "camara_clase_sociedad": "",
    "camara_tamano": "",
    "camara_grupo_empresarial": "",
    "camara_tipo_localizacion": "",
    "camara_zona_localizacion": "",
    "contacto_pagos_nombre": "",
    "contacto_pagos_cargo": "",
    "contacto_pagos_correo": "",
    "contacto_pagos_direccion": "",
    "contacto_pagos_departamento": "",
    "contacto_pagos_municipio": "",
    "contacto_pagos_telefono": "",
    "contacto_pagos_celular": "",
    "contacto_sst_nombre": "",
    "contacto_sst_cargo": "",
    "contacto_sst_correo": "",
    "contacto_sst_direccion": "",
    "contacto_sst_departamento": "",
    "contacto_sst_municipio": "",
    "contacto_sst_telefono": "",
    "contacto_sst_celular": ""
  },
  "sedes": {
    "sede_nombre": "",
    "sede_sucursal": "",
    "sede_codigo": "",
    "sede_centro_trabajo_nombre": "",
    "sede_direccion": "",
    "sede_departamento": "",
    "sede_municipio": "",
    "sede_zona": "",
    "sede_telefono": "",
    "sede_celular": "",
    "sede_correo": "",
    "sede_codigo_actividad": "",
    "sede_clase_riesgo": "",
    "sede_numero_trabajadores": "",
    "sede_transporte": "",
    "sede_grado": "",
    "sede_tarifa": "",
    "sede_contacto": "",
    "sede_cargo_contacto": "",
    "sedes_adicionales": []
  },
  "trabajadores": [
    {
      "trabajador_centro_trabajo": "",
      "tipo_documento_afiliado": "",
      "documento_afiliado": "",
      "primer_apellido": "",
      "segundo_apellido": "",
      "primer_nombre": "",
      "segundo_nombre": "",
      "fecha_nacimiento": "",
      "edad": "",
      "genero": "",
      "tipo_cotizante": "",
      "ibc": "",
      "cargo_actividad": "",
      "eps": "",
      "afp": ""
    }
  ]
}
```

