# Plantilla de levantamiento para otro sistema de afiliaciones ARL

## Objetivo

Esta plantilla sirve para documentar otro sistema de afiliaciones ARL antes de adaptar las buenas practicas del sistema Imagine Afiliaciones.

Debe ser diligenciada por negocio, operacion y tecnologia. La idea es entender como funciona realmente el proceso actual, que validaciones existen, cuales faltan y que reglas deben automatizarse o mantenerse bajo decision humana.

## 1. Identificacion del proceso

| Campo | Respuesta |
| --- | --- |
| Nombre del proceso |  |
| ARL o entidad destino |  |
| Responsable de negocio |  |
| Responsable operativo |  |
| Responsable tecnico |  |
| Sistema actual o legacy |  |
| Salida final del proceso |  |
| Frecuencia de procesamiento |  |
| Volumen promedio mensual |  |

## 2. Unidad de control

Definir cual es el identificador principal del caso.

| Pregunta | Respuesta |
| --- | --- |
| El proceso se controla por contrato, solicitud, empresa, lote o trabajador? |  |
| El identificador es unico? |  |
| Donde aparece ese identificador? |  |
| Que pasa si el identificador no viene? |  |
| Hay riesgo de duplicados? |  |
| Como se detectan duplicados hoy? |  |

Recomendacion: si existe numero de contrato, debe mostrarse en bandejas, reportes, validaciones y auditoria.

## 3. Flujo operativo actual

Describir el proceso paso a paso.

| Paso | Responsable | Entrada | Accion | Salida | Dolor actual |
| --- | --- | --- | --- | --- | --- |
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |
| 4 |  |  |  |  |  |
| 5 |  |  |  |  |  |

Preguntas de apoyo:

- Quien recibe los documentos?
- Quien revisa la informacion?
- Quien corrige errores?
- Quien decide si se devuelve?
- Quien genera la salida final?
- Donde se guarda evidencia?

## 4. Mapa documental

Registrar todos los documentos que llegan o se generan.

| Documento | Obligatorio | Formato | Fuente | Datos que aporta | Documento oficial para que dato | Riesgo si falta |
| --- | --- | --- | --- | --- | --- | --- |
| Excel de afiliacion |  |  |  |  |  |  |
| Formulario |  |  |  |  |  |  |
| Camara de comercio |  |  |  |  |  |  |
| Anexo de sedes |  |  |  |  |  |  |
| Entrega de documentos |  |  |  |  |  |  |
| Otro |  |  |  |  |  |  |

## 5. Diccionario de datos criticos

Cada dato importante debe tener fuente, regla y consecuencia.

| Dato | Fuente principal | Fuente de contraste | Obligatorio | Regla esperada | Error si falla |
| --- | --- | --- | --- | --- | --- |
| Numero de contrato |  |  |  |  |  |
| NIT |  |  |  |  |  |
| Razon social |  |  |  |  |  |
| Tipo de documento trabajador |  |  |  |  |  |
| Numero de documento trabajador |  |  |  |  |  |
| Nombre trabajador |  |  |  |  |  |
| EPS |  |  |  |  |  |
| AFP |  |  |  |  |  |
| ARL |  |  |  |  |  |
| Salario |  |  |  |  |  |
| Modalidad laboral |  |  |  |  |  |
| Centro de trabajo |  |  |  |  |  |
| Ciudad o localidad |  |  |  |  |  |
| Actividad economica |  |  |  |  |  |
| Clase de riesgo |  |  |  |  |  |
| Tarifa |  |  |  |  |  |

## 6. Matriz de validaciones

Clasificar cada validacion segun severidad.

| Codigo | Validacion | Fuente | Severidad | Mensaje al operador | Accion esperada | Excepcionable |
| --- | --- | --- | --- | --- | --- | --- |
| VAL-001 | Numero de contrato presente |  | Bloqueante |  |  | No |
| VAL-002 | NIT coincide entre fuentes |  | Bloqueante |  |  | No |
| VAL-003 | Razon social coincide |  | Bloqueante/Advertencia |  |  | Segun politica |
| VAL-004 | Documento trabajador numerico |  | Bloqueante |  |  | No |
| VAL-005 | EPS existe en catalogo |  | Advertencia/Bloqueante |  |  | Si |
| VAL-006 | Actividad economica valida |  | Bloqueante |  |  | No |
| VAL-007 | Plano cumple longitudes |  | Bloqueante |  |  | No |

Severidades sugeridas:

- Bloqueante: impide continuar.
- Advertencia: requiere revision, pero puede continuar.
- Informativa: no detiene, solo documenta.
- Excepcionable: puede aceptarse manualmente para ese contrato con justificacion.

## 7. Catalogos requeridos

Definir los catalogos que necesita el sistema.

| Catalogo | Existe hoy | Fuente oficial | Responsable de mantenimiento | Frecuencia de actualizacion | Uso en validacion |
| --- | --- | --- | --- | --- | --- |
| EPS |  |  |  |  |  |
| AFP |  |  |  |  |  |
| ARL |  |  |  |  |  |
| Actividades economicas |  |  |  |  |  |
| Codigos PILA |  |  |  |  |  |
| SMMLV |  |  |  |  |  |
| Modalidades laborales |  |  |  |  |  |
| Ciudades/localidades |  |  |  |  |  |
| Intermediarios/asesores |  |  |  |  |  |

## 8. Estados y bandejas

Definir como se vera el trabajo operativo.

| Estado | Significado | Quien actua | Accion siguiente |
| --- | --- | --- | --- |
| Cargado | Caso recibido | Sistema | Analizar |
| En analisis | Extraccion y validacion en curso | Sistema | Esperar resultado |
| Observado | Tiene bloqueantes o inconsistencias | Operador | Corregir, devolver o aceptar excepcion |
| Rechazado | No cumple condiciones minimas | Operador/negocio | Cerrar o devolver |
| Aprobable | Cumple reglas para continuar | Operador/sistema | Generar salida final |
| Procesado | Salida generada o flujo terminado | Sistema/operador | Auditar o consultar |

Campos minimos de bandeja:

- Identificador del caso.
- Empresa.
- NIT.
- Estado.
- Fecha de carga.
- Numero de bloqueantes.
- Responsable.
- Accion siguiente.

## 9. Excepciones manuales

Definir cuando un operador puede aceptar un hallazgo.

| Pregunta | Respuesta |
| --- | --- |
| Que roles pueden aceptar excepciones? |  |
| Que errores nunca pueden aceptarse manualmente? |  |
| Que justificacion minima se exige? |  |
| Se debe adjuntar evidencia? |  |
| La excepcion vence o queda permanente para el caso? |  |
| Quien audita las excepciones? |  |

Regla recomendada: la excepcion solo aplica al contrato y al hallazgo especifico. No debe modificar la regla general.

## 10. RAG y conocimiento operativo

Documentar que informacion debe cargar el RAG.

| Tema | Documento fuente | Responsable | Uso esperado |
| --- | --- | --- | --- |
| Normativa |  |  | Consulta y explicacion |
| Checklist operativo |  |  | Ayuda al operador |
| Glosario |  |  | Normalizacion de lenguaje |
| Reglas de devolucion |  |  | Explicar bloqueantes |
| Manual de plano |  |  | Apoyo a generacion y validacion |
| Casos frecuentes |  |  | Entrenamiento operativo |

El RAG debe responder preguntas y entregar contexto. Las reglas bloqueantes deben estar implementadas como validaciones auditables.

## 11. Salida final o plano

Si el proceso genera archivo plano, integracion o reporte final, documentar:

| Campo | Respuesta |
| --- | --- |
| Nombre del archivo o integracion |  |
| Sistema receptor |  |
| Formato |  |
| Longitudes fijas |  |
| Separador |  |
| Codificacion |  |
| Reglas de rechazo del receptor |  |
| Casos historicos para comparar |  |

Validaciones minimas del plano:

- Longitud de cada linea.
- Tipo de linea.
- Campos obligatorios.
- Codigos oficiales.
- Actividad economica.
- Riesgo, clase, grado y tarifa.
- Intermediarios o comisiones si aplican.
- Coherencia entre trabajador, sede y empresa.

## 12. Casos de prueba historicos

Seleccionar casos reales para probar el nuevo modelo.

| Caso | Tipo | Resultado esperado | Motivo |
| --- | --- | --- | --- |
| Caso aprobado simple | Positivo | Aprobable | Flujo normal |
| Caso con NIT diferente | Negativo | Bloqueante | Identidad empresa |
| Caso con razon social diferente | Negativo | Bloqueante/advertencia | Politica negocio |
| Caso con OCR dificil | Controlado | Excepcionable | Falso positivo posible |
| Caso con multiples sedes | Complejo | Aprobable u observado | Reglas de riesgo |
| Caso duplicado | Negativo | Bloqueante | Evitar reproceso |
| Caso con plano rechazado historico | Negativo | Bloqueante | Validar salida final |

## 13. Criterios de salida a pruebas

El otro sistema esta listo para pruebas cuando:

- Puede cargar un expediente completo.
- Identifica correctamente el caso.
- Clasifica documentos principales.
- Extrae datos criticos.
- Ejecuta prevalidacion.
- Explica bloqueantes y advertencias.
- Permite excepciones manuales auditadas.
- Usa catalogos maestros.
- Consulta conocimiento RAG.
- Genera salida final solo cuando corresponde.
- Permite comparar resultados contra casos historicos.

