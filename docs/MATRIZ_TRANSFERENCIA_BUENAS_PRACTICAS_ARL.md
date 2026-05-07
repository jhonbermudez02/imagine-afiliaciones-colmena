# Matriz de transferencia de buenas practicas ARL

Esta matriz permite decidir que practicas del sistema actual se pueden llevar a otro sistema de afiliaciones ARL.

Escala sugerida:

- Igual: se puede adoptar casi sin cambios.
- Adaptar: aplica el principio, pero cambian reglas, campos o fuentes.
- No aplica: no corresponde al otro proceso.
- Pendiente: requiere validacion con negocio o tecnologia.

| Practica del sistema actual | Para que sirve | Transferencia sugerida | Observacion para el otro sistema |
| --- | --- | --- | --- |
| Numero de contrato como identificador del caso | Permite controlar cada carga, validacion y reproceso | Igual | Debe ser visible en bandejas, reportes y mensajes de error |
| Carga integral de Excel y soportes PDF | Recibe el expediente completo del contrato | Adaptar | Cambian nombres de archivos y documentos obligatorios |
| Clasificacion documental automatica | Identifica formulario, anexos, camara, entrega y otros soportes | Adaptar | Debe entrenarse o parametrizarse con documentos del otro negocio |
| OCR y extraccion de campos | Lee informacion que no viene estructurada | Igual | Mantener validaciones deterministicas sobre datos criticos |
| Cruce de razon social entre fuentes | Evita aprobar contratos de empresa equivocada | Adaptar | Definir fuentes oficiales y tolerancia formal permitida |
| Comparacion de NIT | Controla identidad de empresa | Igual | Debe ser bloqueante cuando no coincida |
| Validacion de numero de contrato en soportes | Asegura que los documentos corresponden al caso | Igual | Puede incluir tolerancia controlada para OCR ambiguo |
| Validacion de documento numerico del trabajador | Evita datos invalidos en afiliacion | Igual | Debe conservar caracteres originales para no ocultar errores |
| Validacion de modalidad laboral | Controla valores esperados por negocio | Adaptar | El catalogo de modalidades puede cambiar |
| Validacion de centros de trabajo | Asegura sede, ciudad, riesgo y actividad economica | Adaptar | Depende de reglas del plano y de la ARL |
| Actividad economica como fuente de clase/riesgo/tarifa | Calcula datos operativos del plano | Adaptar | Requiere catalogo oficial actualizado para ese proceso |
| Catalogos EPS, AFP y ARL | Normaliza nombres y codigos de entidades | Igual | Puede compartirse como catalogo maestro base |
| Catalogo de codigos PILA | Normaliza codigos usados en liquidacion o afiliacion | Adaptar | Verificar cuales codigos aplican en el otro flujo |
| Catalogo SMMLV | Valida salarios contra referencias anuales | Igual | Debe mantenerse actualizado por vigencia |
| Bandejas por estado operativo | Permite seguimiento de contratos | Igual | Estados pueden cambiar, pero la trazabilidad debe mantenerse |
| Separacion de bloqueantes y advertencias | Evita mezclar errores criticos con alertas menores | Igual | Definir severidad por regla |
| Excepcion manual por contrato | Controla falsos positivos sin cambiar reglas generales | Igual | Debe exigir justificacion y quedar auditada |
| Reproceso posterior a una excepcion | Recalcula el caso con la excepcion aceptada | Igual | La excepcion solo debe aplicar al hallazgo especifico |
| Bloqueo de duplicados aprobables | Evita reprocesar contratos ya aceptados | Igual | La busqueda debe usar numero de contrato normalizado |
| RAG como base de conocimiento | Consulta normativa, checklist y criterios operativos | Igual | Debe cargarse con conocimiento propio del otro negocio |
| RAG separado de validaciones criticas | Evita que una respuesta probabilistica apruebe errores | Igual | Las reglas bloqueantes deben ser auditables |
| Comparacion contra legacy | Garantiza continuidad del proceso historico | Adaptar | Solo aplica si el otro sistema tiene salida heredada |
| Generacion de plano | Produce archivo operativo para la ARL | Adaptar | Estructura, longitudes y reglas dependen del destino |
| Auditoria de decisiones humanas | Explica quien acepto, rechazo o modifico un caso | Igual | Necesario para control interno y calidad |
| Administracion de tablas maestras | Permite mantener catalogos sin tocar codigo | Igual | Requiere permisos y control de cambios |
| Reporte ejecutivo por contrato | Resume estado, bloqueantes y decision | Igual | Debe adaptarse al lenguaje del otro proceso |

## Preguntas para levantar el otro sistema

1. Cual es la unidad principal de control: contrato, empresa, solicitud o trabajador?
2. Que documentos son obligatorios?
3. Cuales son las fuentes oficiales para razon social, NIT y numero de contrato?
4. Que validaciones deben ser bloqueantes?
5. Que validaciones pueden ser advertencias?
6. Existe plano, archivo final o integracion operativa?
7. Existe un sistema legacy contra el cual comparar?
8. Que catalogos oficiales usa el proceso?
9. Quien puede aceptar excepciones manuales?
10. Que evidencia debe quedar en auditoria?

## Primer plan de adopcion

1. Mapear documentos y campos del otro negocio.
2. Identificar validaciones comunes y validaciones propias.
3. Construir catalogos maestros necesarios.
4. Definir severidad de cada regla.
5. Implementar bandejas y reporte con estados claros.
6. Incorporar excepciones manuales por contrato.
7. Cargar conocimiento operativo al RAG.
8. Comparar la salida contra el proceso legacy o contra casos reales ya validados.

