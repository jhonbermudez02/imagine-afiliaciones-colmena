# Modelo conceptual del sistema de afiliaciones ARL

## Proposito

Este documento describe, a nivel conceptual, que hace el sistema de afiliaciones ARL, como lo hace y cuales practicas pueden reutilizarse en otros sistemas del mismo dominio.

No es una guia de codigo. Su objetivo es servir como puente entre negocio, operacion y tecnologia para transferir buenas practicas a otro sistema de afiliaciones ARL, aunque ese otro sistema tenga reglas, pantallas, planos o validaciones diferentes.

## Vision general

El sistema recibe contratos de afiliacion con archivos de soporte, extrae informacion desde Excel y PDF, ejecuta validaciones automaticas, clasifica documentos, consulta una base de conocimiento, permite intervencion del operador cuando aplica y prepara la informacion para continuar el flujo operativo, incluyendo generacion de plano cuando el caso cumple las reglas.

El flujo se organiza alrededor del contrato como unidad de control. Cada caso debe poder rastrearse por numero de contrato, empresa, NIT, documentos cargados, validaciones ejecutadas, errores encontrados, decisiones humanas y estado final.

## Flujo funcional

1. El operador carga un contrato con sus archivos asociados.
2. El sistema registra el caso y extrae identificadores principales: contrato, empresa, NIT y archivos recibidos.
3. El sistema clasifica los documentos: formulario, anexos, camara, entrega de documentos, Excel u otros soportes.
4. Se ejecuta OCR y extraccion de campos relevantes.
5. Se cruza la informacion entre fuentes: Excel, formulario, camara de comercio, entrega de documentos y otros soportes.
6. Se ejecuta la prevalidacion.
7. El sistema separa hallazgos bloqueantes, advertencias e informacion complementaria.
8. El operador revisa el resultado y puede reprocesar o aceptar excepciones puntuales por contrato.
9. Si el contrato es aprobable, se habilita el flujo de generacion operativa, como plano 926.
10. El sistema conserva trazabilidad del resultado y de las decisiones humanas.

## Componentes conceptuales

### Frontend operativo

Es la interfaz usada por el equipo de operacion. Debe permitir cargar contratos, revisar bandejas, inspeccionar documentos, ver resultados de OCR, revisar bloqueantes, consultar reportes y administrar catalogos.

La prioridad del frontend no es decorar el proceso, sino reducir friccion operativa: que el operador sepa que paso, por que paso y que accion puede tomar.

### Backend principal

Centraliza la logica de negocio: carga de casos, OCR, clasificacion documental, prevalidaciones, RAG, decisiones del caso, trazabilidad y exposicion de APIs al frontend.

Es el componente que debe proteger la calidad del proceso. Las reglas criticas deben vivir aqui, no solamente en pantalla.

### Backend de compatibilidad o legacy

Permite conservar reglas o formatos heredados, especialmente cuando el proceso depende de planos o validaciones existentes que ya operan en el negocio.

Su funcion conceptual es evitar que el nuevo sistema rompa la operacion actual mientras se moderniza el flujo.

### Base de conocimiento RAG

El RAG es el corazon de conocimiento del sistema. Permite consultar normativa, criterios operativos, glosarios, checklist, documentos de soporte y reglas que ayudan a explicar o complementar las decisiones automaticas.

El RAG no reemplaza las reglas deterministicas criticas. Debe apoyar busqueda, explicacion, clasificacion asistida y contexto operativo, pero las validaciones bloqueantes deben quedar controladas por reglas auditables.

### Catalogos maestros

Los catalogos permiten normalizar informacion frecuente: EPS, AFP, ARL, actividades economicas, codigos PILA, SMMLV, asesores y destinatarios de correo.

El valor de un catalogo no es solo validar, sino evitar ambiguedad. Por ejemplo, si un trabajador viene de una EPS escrita de forma parcial o inconsistente, el sistema puede apoyarse en el catalogo para mostrar el nombre completo y controlar equivalencias.

### Auditoria y trazabilidad

Cada contrato debe conservar evidencia del proceso: archivos cargados, extracciones, validaciones, estado recomendado, reprocesos, decisiones humanas y justificaciones.

La trazabilidad es necesaria para explicar por que un caso fue aprobado, observado o rechazado.

## Reglas y validaciones principales

Las validaciones deben separarse por naturaleza:

- Identidad del contrato: numero de contrato, NIT y razon social.
- Integridad documental: documentos obligatorios, clasificacion correcta y soportes relacionados.
- Calidad de datos: documentos numericos, salarios, telefonos, ciudades, modalidad, centros de trabajo y actividad economica.
- Consistencia entre fuentes: Excel contra formulario, camara, entrega de documentos y anexos.
- Reglas operativas: duplicados, estado aprobable, estructura de plano, intermediarios, comisiones y datos heredados del legacy.
- Reglas de catalogo: EPS, AFP, ARL, actividades economicas y codigos oficiales.

## Manejo de errores

El sistema debe diferenciar entre:

- Bloqueante: impide continuar porque hay riesgo operativo o documental.
- Advertencia: requiere revision pero no necesariamente detiene.
- Informativo: ayuda a entender el caso.
- Excepcion aceptada: hallazgo que fue revisado por un operador y aceptado solo para ese contrato.

Esta separacion evita dos extremos: rechazar contratos correctos por falsos positivos o aprobar contratos con errores reales.

## Excepciones manuales por contrato

Cuando el sistema detecta un bloqueante, el operador puede revisar la evidencia. Si concluye que el sistema se equivoco en ese caso especifico, puede usar la opcion "Aceptar para este contrato".

La excepcion debe cumplir estas reglas:

- Aplica solo al contrato actual.
- No modifica la regla general del sistema.
- Requiere justificacion del operador.
- Queda registrada para auditoria.
- Al reprocesar, ese hallazgo especifico deja de bloquear el caso.
- Si aparece el mismo error en otro contrato, debe volver a evaluarse.

Esta practica permite controlar falsos positivos sin debilitar el modelo de validacion.

## Estados del caso

Los estados deben expresar el avance real del contrato:

- Cargado: el caso fue recibido.
- En analisis: el sistema esta extrayendo y validando.
- Observado: hay bloqueantes o inconsistencias que requieren gestion.
- Rechazado: no cumple condiciones minimas.
- Aprobable: cumple reglas para continuar.
- Completado o aprobado: ya paso el flujo operativo definido.

Cada estado debe estar soportado por evidencia y no solo por una marca visual.

## Buenas practicas reutilizables

- Usar el numero de contrato como identificador operativo del caso.
- Separar OCR, extraccion, validacion y decision.
- Cruzar datos entre varias fuentes documentales.
- Mantener reglas criticas en backend.
- Usar catalogos oficiales y administrables.
- Tener bandejas por estado real del caso.
- Bloquear duplicados cuando ya existe un contrato aprobable.
- Permitir excepciones manuales solo con justificacion.
- Conservar trazabilidad de decisiones humanas.
- Usar RAG como base de conocimiento y soporte, no como unica autoridad de validacion.
- Comparar contra el legacy cuando exista una salida operativa historica.

## Criterio para adaptar a otro sistema

El otro sistema puede tener diferente negocio, diferente ARL, diferentes documentos o diferentes reglas. Aun asi, puede adoptar el modelo conceptual:

- Misma arquitectura de control por contrato.
- Misma separacion entre fuentes, reglas, decision y auditoria.
- Mismo enfoque de catalogos maestros.
- Misma posibilidad de excepcion auditada por contrato.
- Misma filosofia de prevalidar antes de generar una salida operativa.

Lo que debe cambiar son las reglas particulares, los documentos obligatorios, los campos de plano y las decisiones administrativas propias de ese negocio.

