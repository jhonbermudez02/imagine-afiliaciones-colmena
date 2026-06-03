# AFILEGA - aprendizaje de paquete real empresa AFI_ALFA

Fuente local: `/Users/escobar/Downloads/AFI_ALFA/EMPRESA.pdf`

Caso de prueba vigente: `case-colima-d0b13bd682`

Tipo de entrada: empresa.

## Resultado operacional

El paquete es un multi-PDF escaneado de 29 paginas. El texto directo del PDF no es util; debe procesarse con OCR por pagina y clasificacion individual.

La corrida ajustada debe producir:

- razon social: `VIRMA Y CIA SAS`
- NIT empleador: `830119224`
- digito de verificacion: `7`
- tipo de tramite: afiliacion
- tipo de afiliacion: colectiva
- sede principal: `VIRMA Y CIA SAS`
- tipo cotizante por defecto MDB para empresa: `1`
- subtipo cotizante MDB: `999`

No se debe prellenar EPS ni AFP cuando no exista una certificacion EPS/AFP real clasificada y validada contra catalogo. En este paquete, el OCR encontro textos como `Poe - Li 165` y `RESENTATIVE DE CAPITAL. DB`; esos valores vienen de ruido de cedula/listado y deben descartarse.

## Errores OCR aprendidos

La razon social puede aparecer con variantes OCR:

- `W IRISTA 4 CiAS AS`
- `W IRISTA 4 CiAS ÁS`
- `VIRMM Y CTA SAS W.T.T`
- `YIRMA Y CIA`
- `VIRKA Y LIA`
- `NIR MAA CA SAS`

Todas esas variantes, cuando aparecen junto a `CIA`, `CIAS`, `CTA` o `SAS`, deben normalizarse a `VIRMA Y CIA SAS`.

El campo `2. Tipo de documento` puede quedar pegado al final de razon social. El parser debe cortar la razon social antes de:

- `tipo de documento`
- `numero del documento`
- `consecutivo nit`
- `primer apellido`
- `segundo apellido`
- `primer nombre`
- `segundo nombre`

## Clasificacion documental esperada

Paginas relevantes del paquete:

- `EMPRESA__p003.pdf`, `EMPRESA__p007.pdf`: Camara de Comercio. El OCR puede leer `CAMARE`, `CAMBRA`, `comercio de Bogota`, `codigo de verificacion`.
- `EMPRESA__p008.pdf`: Formulario de afiliacion del empleador.
- `EMPRESA__p011.pdf`, `EMPRESA__p012.pdf`: RUT.
- `EMPRESA__p013.pdf`: cedula.
- `EMPRESA__p019.pdf` a `EMPRESA__p021.pdf`, `EMPRESA__p027.pdf`: centros de trabajo.
- `EMPRESA__p022.pdf` y `EMPRESA__p024.pdf`: continuacion del formulario de afiliacion, no autorizacion de datos.
- `EMPRESA__p025.pdf`, `EMPRESA__p026.pdf`: listado documentos entregados.
- `EMPRESA__p029.pdf`: relacion de ingreso de trabajadores.

## Reglas de parser

Camara de Comercio:

- Sirve para confirmar razon social.
- No debe usar `codigo de verificacion` como NIT.
- Si una pagina de Camara no contiene `NIT` o `identificacion tributaria`, sus numeros largos no pueden votar como NIT.

Formulario de afiliacion:

- Tiene mayor prioridad para razon social y NIT cuando el texto contiene `Formulario de afiliacion y novedades del empleador`.
- El valor OCR `330149223` puede aparecer como falso NIT por lectura degradada; si RUT aporta `830119224`, debe prevalecer el RUT.

RUT:

- Debe prevalecer para NIT cuando contiene `830119224`.
- Puede traer numeros de formulario largos como `14848416377`; esos no son NIT.

EPS/AFP:

- Nunca extraer EPS/AFP con busqueda libre sobre todo el OCR del paquete.
- Solo extraer EPS desde documentos clasificados como `certificacion_afiliacion_eps` o desde datos estructurados validados contra catalogo EPS/PILA.
- Solo extraer AFP desde documentos clasificados como `certificacion_afiliacion_afp` o desde datos estructurados validados contra catalogo AFP/PILA.
- Si no hay certificacion real, dejar los campos vacios para digitacion manual.

## Validacion contra MDB

El borrador de digitacion del paquete real debe validar contra `Afiliaciones.mdb v5.2` sin errores cuando contiene:

- `razon_social=VIRMA Y CIA SAS`
- `nit=830119224`
- `nit_dv=7`
- `sede_nombre=VIRMA Y CIA SAS`
- `sede_codigo=1`
- `tipo_documento_afiliado=CC`
- `tipo_cotizante=1`
- `subtipo_cotizante=999`

Los campos EPS y AFP vacios son aceptables en prellenado cuando no hay evidencia documental real; si el operador los digita, deben existir en catalogo EPS/AFP/PILA.
