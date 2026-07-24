# Matriz Legacy MDB vs Digitacion

Fuente oficial: `/Users/escobar/Downloads/Afiliaciones.mdb`, version 5.2.

Esta matriz es la guia operativa para que cada campo legacy tenga una entrada digitada, un destino de payload y una validacion. El backend es la fuente de verdad; el frontend replica las mismas reglas para ayudar al digitador antes de guardar.

| Legacy MDB / 926 | Campo Digitacion | Payload backend | Validacion |
| --- | --- | --- | --- |
| `empleador_tipo_documento` | `empleador_tipo_documento` | `legacy_mdb.empresa.emp_tipoid` / `form_fields.empleador_tipo_documento` | Tipo documento legacy |
| `empleador_numero_documento_nit` | `nit` | `legacy_mdb.empresa.emp_nit` / `form_fields.empleador_numero_documento_nit` | Numerico 5-15, limite MDB |
| `digito_verificacion` | `nit_dv` | `legacy_mdb.empresa.emp_digito` / `form_fields.digito_verificacion` | Calculo DV MDB |
| `empleador_razon_social` | `razon_social` | `legacy_mdb.empresa.emp_razonsocial` / `form_fields.empleador_razon_social` | Longitud MDB |
| `sede_principal_departamento` | `departamento_empresa` | `legacy_mdb.empresa.emp_departamento` | Tabla departamentos |
| `sede_principal_municipio_distrito` | `municipio_empresa` | `legacy_mdb.empresa.emp_ciudad` | Tabla municipios / homologacion |
| `sede_principal_direccion` | `direccion_empresa` | `legacy_mdb.empresa.emp_direccion` | Longitud MDB |
| `correo_empleador` | `correo_empresa` | `legacy_mdb.empresa.emp_email` | Email |
| `a_codigo_actividad_economica_principal` | `codigo_actividad_economica` | `legacy_mdb.empresa.emp_actividad` / `form_fields.a_codigo_actividad_economica_principal` | 7 digitos, catalogo ARP/926 |
| `a_clase_riesgo` | `clase_riesgo_empresa` | `legacy_mdb.empresa.emp_clase` / `form_fields.a_clase_riesgo` | Riesgo I-V y cruce contra actividad |
| `rep_legal_nombre_completo` | `rep_legal_nombre_completo` | `legacy_mdb.representante_legal.*` / `form_fields.rep_legal_nombre_completo` | Alfa, limite MDB |
| `rep_legal_tipo_documento` | `rep_legal_tipo_documento` | `legacy_mdb.representante_legal.*` / `form_fields.rep_legal_tipo_documento` | Tipo documento legacy |
| `rep_legal_numero_documento` | `rep_legal_numero_documento` | `legacy_mdb.representante_legal.*` / `form_fields.rep_legal_numero_documento` | Numerico 5-15 |
| `rep_legal_correo` | `rep_legal_correo` | `legacy_mdb.representante_legal.*` / `form_fields.rep_legal_correo` | Email |
| `responsable_sede_principal_*` | `responsable_sede_principal_*` | `legacy_mdb.responsable_sede_principal.*` / `form_fields.responsable_sede_principal_*` | Alfa/documento legacy |
| `a_numero_sedes` | `a_numero_sedes` | `legacy_mdb.formulario.a_numero_sedes` / `form_fields.a_numero_sedes` | Conteo numerico |
| `a_numero_centros_trabajo` | `a_numero_centros_trabajo` | `legacy_mdb.formulario.a_numero_centros_trabajo` / `form_fields.a_numero_centros_trabajo` | Conteo numerico |
| `a_numero_inicial_trabajadores_estudiantes` | `a_numero_inicial_trabajadores_estudiantes` | `legacy_mdb.formulario.*` / `form_fields.*` | Conteo numerico |
| `a_valor_total_nomina` | `a_valor_total_nomina` | `legacy_mdb.formulario.a_valor_total_nomina` / `form_fields.a_valor_total_nomina` | Monetario no negativo |
| `b_* traslado` | `b_numero_sedes`, `b_numero_centros_trabajo`, `b_numero_total_trabajadores_estudiantes`, `b_monto_total_cotizacion`, `estado_cuenta_empleador` | `legacy_mdb.formulario.*` / `form_fields.*` | Conteo, monto y estado de cuenta legacy |
| `sede_principal_codigo` | `sede_codigo` | `legacy_mdb.centro_trabajo.cen_codigo` / `form_fields.sede_principal_codigo` | Numerico, limite MDB |
| `sede_principal_nombre` | `sede_nombre` | `legacy_mdb.centro_trabajo.cen_nombre` / `form_fields.sede_principal_nombre` | Alfa, limite MDB |
| `sede_principal_telefono` | `sede_telefono` | `legacy_mdb.centro_trabajo.cen_telefono` / `form_fields.sede_principal_telefono` | Digitos 7-10 |
| `cen_tarifa` | `sede_tarifa` | `legacy_mdb.centro_trabajo.cen_tarifa` | Numerico no negativo |
| Centros multiples | `sedes_adicionales` | `legacy_mdb.centros_trabajo_adicionales[]` | Lineas estructuradas con depto/municipio/riesgo |
| Trabajador documento/nombres | `tipo_documento_afiliado`, `documento_afiliado`, nombres y apellidos | `legacy_mdb.trabajador.*` | Documento legacy, alfa y limites MDB |
| Trabajador nacimiento | `fecha_nacimiento` | `legacy_mdb.trabajador.afi_fecha_nacimiento` / `profile.fecha_nacimiento` | Fecha valida anterior a hoy |
| EPS / AFP | `eps`, `afp` | `legacy_mdb.trabajador.afi_cod_eps/afi_cod_afp` | Catalogo EPS/AFP PILA |
| IBC | `ibc` | `legacy_mdb.trabajador.afi_ibc` / `profile.nomina_total` | Monetario, mayor a cero, >= SMMLV |
| Contrato | `numero_contrato`, `tipo_contrato`, fechas y valores | `legacy_mdb.contrato.*` / `profile.*` | Fechas coherentes, mensual <= total |
| Novedad | `tipo_novedad`, fechas, valores, traslado, origen | `legacy_mdb.novedad.*` | Codigos MDB `00/08`, estado `1`, autoliquidacion `N`, origen `C` |
