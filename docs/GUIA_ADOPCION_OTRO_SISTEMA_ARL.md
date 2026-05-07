# Guia de adopcion para otro sistema de afiliaciones ARL

## Objetivo

Esta guia explica como usar el sistema actual de Imagine Afiliaciones como referencia para mejorar otro sistema de afiliaciones ARL.

La idea no es copiar todo literalmente. La idea es identificar las practicas fuertes del sistema actual y trasladarlas al otro negocio respetando sus propias reglas, documentos, responsables, planos y criterios administrativos.

## Principio central

Todo sistema de afiliaciones ARL debe responder con claridad estas preguntas:

- Que contrato o solicitud se esta procesando?
- A que empresa pertenece?
- Que trabajadores se estan afiliando?
- Que documentos soportan la afiliacion?
- Que datos se extrajeron automaticamente?
- Que reglas se validaron?
- Que errores bloquean el proceso?
- Que errores son solo advertencias?
- Que decision tomo el sistema?
- Que decision tomo el operador?
- Que evidencia queda para auditoria?

Si el sistema no puede responder estas preguntas, el proceso queda debil frente a reprocesos, reclamaciones, auditorias o errores operativos.

## Metodo de adopcion

### 1. Levantar el flujo real del negocio

Antes de hablar de tecnologia, se debe documentar como trabaja hoy el equipo:

- Quien recibe la solicitud.
- Que archivos llegan.
- Como se identifica el contrato.
- Como se revisa la empresa.
- Como se revisan trabajadores.
- Que validaciones se hacen manualmente.
- Que errores generan devolucion.
- Que errores se corrigen internamente.
- Que archivo o resultado final se entrega.
- Que sistema legacy o externo recibe la informacion.

El objetivo es separar el proceso real del proceso ideal. Muchas reglas importantes viven en la practica diaria del equipo y no en documentos formales.

### 2. Definir la unidad de control

En el sistema actual, la unidad de control recomendada es el numero de contrato.

Para el otro sistema se debe confirmar si la unidad principal sera:

- Numero de contrato.
- Numero de solicitud.
- NIT de empresa mas periodo.
- Empresa mas lote.
- Trabajador.
- Otro identificador operativo.

La recomendacion es que cada caso tenga un identificador unico visible en todo el flujo: carga, bandeja, prevalidacion, reporte, auditoria y salida final.

### 3. Mapear documentos

Se debe construir una tabla de documentos esperados:

| Documento | Obligatorio | Fuente | Datos que aporta | Riesgo si falta |
| --- | --- | --- | --- | --- |
| Excel de afiliacion | Si | Operacion o cliente | Empresa, contrato, trabajadores, sedes | No se puede validar estructura |
| Formulario de afiliacion | Segun negocio | PDF | Empresa, NIT, contrato, firmas | Puede faltar soporte formal |
| Camara de comercio | Segun negocio | PDF | Razon social, NIT, existencia legal | Riesgo de empresa incorrecta |
| Anexos de sedes | Segun negocio | PDF o Excel | Centros de trabajo, actividad, ciudad | Riesgo y tarifa incorrectos |
| Entrega de documentos | Segun negocio | PDF | Confirmacion documental | Soporte puede no corresponder al contrato |

Cada negocio puede cambiar la lista, pero debe quedar claro que documento manda sobre cada dato.

### 4. Definir fuentes oficiales por dato

No todos los documentos tienen el mismo peso. Para cada dato critico se debe definir una fuente principal y fuentes de contraste.

| Dato | Fuente principal sugerida | Fuentes de contraste |
| --- | --- | --- |
| Numero de contrato | Excel/Formulario | Entrega de documentos, anexos |
| Razon social | Camara o documento legal | Excel, formulario, entrega |
| NIT | Camara o formulario | Excel, entrega |
| Trabajadores | Excel | Soportes anexos |
| Actividad economica | Catalogo oficial + sede | Excel, anexo de sedes |
| EPS/AFP/ARL | Catalogos maestros | Excel |
| Salario | Excel | Regla SMMLV |
| Ciudad/localidad | Excel o anexo | Catalogos territoriales si existen |

Esta definicion evita discusiones posteriores. Si dos fuentes no coinciden, el sistema debe saber cual pesa mas y cuando bloquear.

### 5. Separar reglas por severidad

Cada validacion debe clasificarse:

| Severidad | Significado | Ejemplo |
| --- | --- | --- |
| Bloqueante | No permite continuar | NIT diferente entre fuentes |
| Advertencia | Requiere revision, pero podria continuar | Telefono vacio o en cero |
| Informativa | Explica o complementa | Se detectaron dos sedes |
| Excepcionable | Puede aceptarse manualmente para un contrato | OCR leyo mal un numero visible correcto |

La severidad debe ser una decision de negocio, no solo tecnica.

### 6. Construir catalogos maestros

El otro sistema deberia tener catalogos administrables para:

- EPS.
- AFP.
- ARL.
- Actividades economicas.
- Codigos PILA si aplican.
- SMMLV por vigencia.
- Tipos de documento.
- Modalidades laborales.
- Ciudades o localidades si el proceso las controla.
- Asesores o intermediarios si hacen parte del plano.

Los catalogos reducen errores de digitacion y permiten normalizar nombres incompletos, abreviados o escritos de forma diferente.

### 7. Definir prevalidacion

La prevalidacion debe ocurrir antes de generar cualquier salida operativa.

Debe revisar como minimo:

- Identidad del contrato.
- Identidad de la empresa.
- Existencia de documentos obligatorios.
- Coherencia entre Excel y soportes.
- Datos basicos de trabajadores.
- Catalogos obligatorios.
- Reglas de actividad economica y riesgo.
- Reglas de duplicidad.
- Reglas especificas del plano o integracion final.

El resultado debe ser claro para operacion: aprobable, observado o rechazado, con razones concretas.

### 8. Incorporar excepciones manuales controladas

El otro sistema deberia adoptar la opcion de aceptar un hallazgo solo para un contrato especifico.

Condiciones minimas:

- El operador debe ver el error exacto.
- Debe poder revisar evidencia.
- Debe escribir una justificacion.
- El sistema debe reprocesar el contrato.
- La excepcion solo aplica a ese contrato y a ese hallazgo.
- La regla general no cambia.
- La decision queda disponible para auditoria.

Esto es importante porque los sistemas automaticos pueden tener falsos positivos, especialmente con OCR o documentos escaneados.

### 9. Diseñar bandejas operativas

Las bandejas deben ayudar a trabajar, no solo listar contratos.

Vista minima recomendada:

- Contrato.
- Empresa.
- NIT.
- Estado.
- Fecha de carga.
- Numero de bloqueantes.
- Responsable o usuario.
- Accion siguiente.

Estados recomendados:

- Cargado.
- En analisis.
- Observado.
- Rechazado.
- Aprobable.
- Procesado.

### 10. Cargar conocimiento al RAG

El RAG debe alimentarse con documentos que realmente ayuden al operador y al sistema:

- Normativa aplicable.
- Manuales internos.
- Checklist de validacion.
- Glosario operativo.
- Reglas de negocio explicadas.
- Casos frecuentes.
- Criterios de devolucion.
- Instrucciones de plano o integracion.

El RAG debe ser consultivo y explicativo. Las decisiones bloqueantes deben seguir siendo reglas controladas y auditables.

### 11. Comparar contra legacy o casos historicos

Si existe un sistema actual o legacy, se debe hacer comparacion con casos reales:

- Casos aprobados correctamente.
- Casos rechazados correctamente.
- Casos con errores conocidos.
- Casos con documentos dificiles.
- Casos con multiples sedes.
- Casos con intermediarios o comisiones.
- Casos con diferencias en razon social.

La meta no es que el sistema nuevo copie todos los errores del legacy, sino que entienda donde debe coincidir y donde debe mejorar.

## Entregables sugeridos para el otro sistema

1. Documento conceptual del proceso.
2. Mapa de documentos obligatorios y opcionales.
3. Diccionario de datos criticos.
4. Matriz de validaciones.
5. Catalogos maestros requeridos.
6. Definicion de estados y bandejas.
7. Modelo de excepciones manuales.
8. Base inicial de conocimiento RAG.
9. Casos de prueba historicos.
10. Criterios de aceptacion para salida a pruebas.

## Matriz base de validaciones

| Grupo | Validacion | Severidad sugerida | Comentario |
| --- | --- | --- | --- |
| Contrato | Numero de contrato presente | Bloqueante | Sin contrato no hay trazabilidad |
| Contrato | Contrato no duplicado en estado aprobable | Bloqueante | Evita reprocesos indebidos |
| Empresa | NIT coincide entre fuentes | Bloqueante | Identidad juridica critica |
| Empresa | Razon social coincide formalmente | Bloqueante o advertencia | Depende de la politica del negocio |
| Documentos | Soportes obligatorios presentes | Bloqueante | Segun matriz documental |
| Documentos | Documento clasificado correctamente | Advertencia o bloqueante | Depende del soporte |
| Trabajador | Documento de identidad numerico | Bloqueante | Evita errores de afiliacion |
| Trabajador | Salario valido contra SMMLV | Bloqueante o advertencia | Depende de regla de negocio |
| Trabajador | EPS/AFP existe en catalogo | Advertencia o bloqueante | Se recomienda catalogo maestro |
| Sede | Centro de trabajo completo | Bloqueante | Impacta riesgo y plano |
| Sede | Actividad economica valida | Bloqueante | Impacta clase, grado y tarifa |
| Plano | Longitudes y formatos correctos | Bloqueante | Evita rechazo del archivo final |
| Operacion | Excepcion manual justificada | Informativo auditado | No debe alterar regla general |

## Criterios de exito

El otro sistema habra adoptado bien estas practicas si puede demostrar:

- Cada contrato tiene trazabilidad completa.
- Los errores bloqueantes son explicables.
- El operador entiende que debe corregir o aceptar.
- Las excepciones quedan justificadas.
- Los catalogos reducen ambiguedad.
- El RAG ayuda a consultar conocimiento, no a inventar reglas.
- El plano o salida final se genera solo cuando el caso cumple.
- Los resultados se pueden comparar contra casos historicos.

