# 01 - Que es AFILEGA_FA_IMA_LA_V2

## Proposito

`AFILEGA_FA_IMA_LA_V2` es un sistema local y portable para gestionar afiliaciones ARL de empresas y contratistas. El objetivo es recibir paquetes documentales, validar los documentos, extraer informacion mediante OCR, apoyar la digitacion operativa y generar la informacion necesaria para el proceso de afiliacion, incluyendo reglas compatibles con el flujo 926.

El sistema fue preparado para funcionar en esta maquina mediante contenedores Docker y para poder llevarse a un servidor Linux manteniendo la misma estructura de servicios.

## Que problema resuelve

El proceso de afiliacion ARL requiere revisar paquetes con multiples documentos, identificar cada tipo documental, validar que la informacion sea consistente y capturar datos en formularios operativos. El sistema ayuda a:

- Recibir paquetes documentales de afiliacion.
- Clasificar documentos del contrato.
- Ejecutar OCR sobre PDFs e imagenes.
- Alimentar una base de conocimiento RAG con formatos, reglas y evidencias.
- Prellenar y validar campos de digitacion cuando la informacion sea confiable.
- Permitir digitacion manual con reglas de campos obligatorios, tipos de dato y catalogos.
- Validar datos de afiliacion, sede, centros de trabajo y trabajadores.
- Generar y revisar informacion asociada al plano 926.
- Mantener trazabilidad del expediente y de las validaciones.

## Usuarios principales

### Operador Imagine

Usuario que recibe contratos, carga documentos, clasifica, revisa OCR, digita informacion faltante y valida reglas antes de entregar.

### Revisor operativo

Usuario que consulta el expediente, revisa observaciones, documentos, datos capturados, validaciones y estado del proceso.

### Equipo tecnico

Equipo responsable de ajustar formularios, reglas, catalogos, RAG, Docker, backend, frontend y despliegue en Linux.

## Flujo general

1. Se ingresa a la bandeja de entrada.
2. Se crea un nuevo contrato.
3. Se diligencian los datos de radicacion.
4. Se cargan los documentos del contrato.
5. El sistema ejecuta clasificacion documental, OCR y validaciones.
6. El operador entra a digitacion.
7. Se revisan y completan los formularios de Afiliacion, Sede y Trabajadores.
8. Se validan reglas obligatorias, formatos y catalogos.
9. Se genera o revisa la informacion operativa del 926.
10. El expediente queda disponible en bandeja con su estado.

## Modulos funcionales

### Bandeja de entrada

Lista contratos radicados y permite ver su estado operativo. Muestra tarjetas/estados como radicadas, en proceso, por entregar y en devolucion.

### Nuevo contrato

Pantalla para radicar un paquete. Captura datos iniciales: consecutivo, clase de afiliacion, fechas, tipo documento, identificacion, razon social, sucursal y ARL traslado cuando aplique.

### Clasificacion documental

Permite revisar los documentos cargados, corregir su tipo documental y organizar el paquete antes de la validacion.

### Digitacion

Formulario principal de captura manual. Tiene tres pestanas:

- Afiliacion.
- Sede.
- Trabajadores.

Los campos tienen reglas de obligatoriedad, longitud, tipo de dato, catalogos, calculos automaticos y validaciones cruzadas.

### Validacion OCR y visor documental

Permiten comparar lo leido en documentos contra lo digitado, abrir documentos y revisar evidencia.

### Reporte ejecutivo

Resume el estado del contrato, las observaciones y los resultados relevantes del flujo.

### Generacion 926

El sistema conserva reglas y estructura para producir o validar informacion operacional compatible con el archivo 926.

## Tipos de informacion que maneja

- Datos de radicacion.
- Datos de empresa o contratista.
- Informacion de representante legal.
- Camara de Comercio.
- Datos de contacto de pagos.
- Datos de contacto SST.
- Sedes y centros de trabajo.
- Trabajadores asociados a centros.
- Catalogos EPS, AFP, cargos, tipo cotizante, actividad economica, vinculador laboral y ubicaciones.
- Documentos PDF, imagenes y paquetes ZIP.
- OCR de documentos.
- Conocimiento semilla para RAG.
- Trazabilidad de validaciones y hallazgos.

## Reglas importantes del negocio

- Los datos se guardan en mayuscula.
- Los campos obligatorios deben completarse antes de cerrar la digitacion.
- NIT debe tener 9 digitos cuando el tipo de documento sea NIT.
- CC/TI de trabajadores debe tener 7, 8 o 10 digitos; no se permite longitud 9.
- Telefonos y celulares se validan con 10 digitos.
- Correos deben tener formato valido.
- Trabajadores deben estar asociados a un centro de trabajo.
- No se debe repetir tipo y numero de documento entre trabajadores.
- El documento del trabajador no debe ser igual al documento de la empresa.
- El numero de trabajadores por centro debe coincidir con los trabajadores registrados.
- Salario/IBC debe estar entre 1 y 25 SMMLV, excepto tipo cotizante 51.
- Grado de riesgo y tarifa se calculan/controlan por reglas.
- Para traslado, ARL traslado y fecha de inicio vigencia son reglas especiales.

## Entrega esperada para Linux

El proyecto debe poder instalarse en Linux copiando el repositorio y levantando Docker Compose. El servidor destino no debe requerir instalar manualmente Python, Node, Postgres, Qdrant ni OCR fuera de Docker.

Documento de despliegue relacionado:

- `DEPLOY.md`

Documentos de validaciones y formularios:

- `docs/VALIDACIONES_AFILIACIONES_AFILEGA.md`
- `docs/ESPECIFICACION_FORMULARIOS_DIGITACION_AFILEGA.md`

