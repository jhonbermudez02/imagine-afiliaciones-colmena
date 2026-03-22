CREATE SCHEMA IF NOT EXISTS auxilios;

CREATE TABLE IF NOT EXISTS auxilios.not_solicitudes (
  solicitud_id INT,
  tramite TEXT,
  id_afiliado TEXT,
  tipo_solicitud TEXT,
  estado_flujo TEXT,
  proceso TEXT
);
TRUNCATE auxilios.not_solicitudes;
INSERT INTO auxilios.not_solicitudes VALUES (123, '456', '111', 'INV', 'Notificado', 'NOTIFICACIONES AUXILIOS');

CREATE TABLE IF NOT EXISTS auxilios.not_estado_post (
  estado_post_id INT PRIMARY KEY,
  estado_post TEXT,
  activo BOOLEAN
);
INSERT INTO auxilios.not_estado_post (estado_post_id, estado_post, activo)
VALUES (1, 'ESTADO TEST', TRUE)
ON CONFLICT (estado_post_id) DO UPDATE SET estado_post = EXCLUDED.estado_post, activo = EXCLUDED.activo;

CREATE TABLE IF NOT EXISTS auxilios.not_estados_post_solicitud (
  id_estado_post_solicitud SERIAL PRIMARY KEY,
  solicitud_id INT,
  id_estado_post INT,
  marca BOOLEAN,
  observacion TEXT,
  user_insert TEXT,
  usuario_solucion TEXT,
  fecha_insert TIMESTAMP,
  fecha_solucion TIMESTAMP
);
DELETE FROM auxilios.not_estados_post_solicitud;
INSERT INTO auxilios.not_estados_post_solicitud
(solicitud_id, id_estado_post, marca, observacion, user_insert, usuario_solucion, fecha_insert, fecha_solucion)
VALUES (123, 1, TRUE, 'POST TEST', 'IMAGINE', 'IMAGINE', now(), now());

CREATE TABLE IF NOT EXISTS tblpnpension (
  pi TEXT,
  lo TEXT,
  pn INT,
  ce TEXT,
  codoficina TEXT
);
TRUNCATE tblpnpension;
INSERT INTO tblpnpension VALUES ('https://example.com/doc1.pdf', 'L01', 999, '111', '001');

CREATE TABLE IF NOT EXISTS tblanpension (
  pi TEXT,
  lo TEXT,
  ax TEXT,
  pn INT,
  ce TEXT,
  stiker TEXT
);
TRUNCATE tblanpension;
INSERT INTO tblanpension VALUES ('https://example.com/doc1.pdf', 'L01', 'AX-TEST', 999, '111', 'STK-001');

CREATE TABLE IF NOT EXISTS tblcodigospension (
  codigo TEXT,
  categoria TEXT,
  descripcion TEXT
);
TRUNCATE tblcodigospension;
INSERT INTO tblcodigospension VALUES ('L01', 'SOLICITUDES DE INVALIDEZ', 'DOC TEST');

CREATE TABLE IF NOT EXISTS auxilios.not_relacion_imagenes (
  pn INT,
  tramite TEXT,
  id_prestacion INT,
  solicitud_id INT,
  id_documento INT,
  modalidad TEXT,
  eps TEXT
);
TRUNCATE auxilios.not_relacion_imagenes;
INSERT INTO auxilios.not_relacion_imagenes VALUES (999, '456', 1, 123, 1, '1', NULL);

CREATE TABLE IF NOT EXISTS auxilios.not_marca_imagenes (
  id_marca SERIAL PRIMARY KEY,
  ax TEXT,
  pn INT,
  tramite TEXT,
  marca INT,
  solicitud_id INT
);
TRUNCATE auxilios.not_marca_imagenes;
INSERT INTO auxilios.not_marca_imagenes (ax, pn, tramite, marca, solicitud_id)
VALUES ('AX-TEST', 999, '456', 1, 123);

CREATE TABLE IF NOT EXISTS auxilios.not_documentos_prestaciones (
  id_documento INT,
  id_prestacion INT,
  obligatorio INT
);
TRUNCATE auxilios.not_documentos_prestaciones;
INSERT INTO auxilios.not_documentos_prestaciones VALUES (1, 1, 1);

CREATE TABLE IF NOT EXISTS auxilios.not_documentos (
  id_documento INT PRIMARY KEY,
  desc_documento TEXT
);
INSERT INTO auxilios.not_documentos (id_documento, desc_documento)
VALUES (1, 'Documento prueba')
ON CONFLICT (id_documento) DO UPDATE SET desc_documento = EXCLUDED.desc_documento;

CREATE TABLE IF NOT EXISTS auxilios.not_imagenes_temporal (
  na TEXT,
  clasificacion TEXT
);
TRUNCATE auxilios.not_imagenes_temporal;
INSERT INTO auxilios.not_imagenes_temporal VALUES ('999', '');

CREATE TABLE IF NOT EXISTS auxilios.not_reclamantes (
  id_ben SERIAL PRIMARY KEY,
  not_solicitud_id INT,
  tramite TEXT,
  tipoid_beneficiario TEXT,
  identificacion TEXT,
  nombre_beneficiario TEXT,
  direccion TEXT,
  telefono_beneficiario TEXT,
  estado_reclamante TEXT
);
TRUNCATE auxilios.not_reclamantes;
INSERT INTO auxilios.not_reclamantes
(not_solicitud_id, tramite, tipoid_beneficiario, identificacion, nombre_beneficiario, direccion, telefono_beneficiario, estado_reclamante)
VALUES (123, '456', 'CC', '123456789', 'BEN TEST', 'DIR', 'TEL', NULL);

CREATE TABLE IF NOT EXISTS auxilios.not_pagos_reclamantes (
  solicitud_id INT,
  id_reclamante TEXT,
  apoderado TEXT,
  nom_apoderado TEXT,
  tel_apoderado TEXT,
  forma_pago TEXT,
  numero_cuenta TEXT,
  entidad_bancaria TEXT,
  tipo_cuenta TEXT
);
TRUNCATE auxilios.not_pagos_reclamantes;
INSERT INTO auxilios.not_pagos_reclamantes
(solicitud_id, id_reclamante, apoderado, nom_apoderado, tel_apoderado, forma_pago, numero_cuenta, entidad_bancaria, tipo_cuenta)
VALUES (123, '123456789', '0', 'APODERADO TEST', '3000000000', 'TRANSFERENCIA', '000123456', 'BANCO TEST', 'AHORROS');

CREATE TABLE IF NOT EXISTS auxilios.not_log (
  solicitud_id INT,
  usuario TEXT,
  estado_anterior TEXT,
  estado_actual TEXT,
  observacion TEXT
);
TRUNCATE auxilios.not_log;
INSERT INTO auxilios.not_log (solicitud_id, usuario, estado_anterior, estado_actual, observacion)
VALUES (123, 'IMAGINE', 'Notificado', 'EN GESTION', 'LOG TEST');

CREATE TABLE IF NOT EXISTS auxilios.not_bloqueo (
  na SERIAL PRIMARY KEY,
  estado INT,
  usuario TEXT,
  fecha_bloqueo TIMESTAMP DEFAULT now()
);
TRUNCATE auxilios.not_bloqueo;
INSERT INTO auxilios.not_bloqueo (estado, usuario) VALUES (0, 'IMAGINE');

CREATE TABLE IF NOT EXISTS auxilios.fun_solicitudes (
  tramite TEXT,
  estado_flujo TEXT
);
TRUNCATE auxilios.fun_solicitudes;
INSERT INTO auxilios.fun_solicitudes VALUES ('456', 'NUEVO');

CREATE TABLE IF NOT EXISTS auxilios.fun_reclamantes (
  id_ben SERIAL PRIMARY KEY,
  tramite TEXT,
  tipoid_beneficiario TEXT,
  identificacion TEXT,
  nombre_beneficiario TEXT,
  estado_reclamante TEXT
);
TRUNCATE auxilios.fun_reclamantes;
INSERT INTO auxilios.fun_reclamantes (tramite, tipoid_beneficiario, identificacion, nombre_beneficiario, estado_reclamante)
VALUES ('456', 'CC', '123456789', 'FUN BEN TEST', NULL);

CREATE TABLE IF NOT EXISTS auxilios.fun_pagos_reclamantes (
  id SERIAL PRIMARY KEY,
  tramite TEXT,
  id_reclamante TEXT,
  forma_pago TEXT,
  entidad_bancaria TEXT,
  tipo_cuenta TEXT,
  numero_cuenta TEXT,
  valor_reconocido NUMERIC
);
TRUNCATE auxilios.fun_pagos_reclamantes;
INSERT INTO auxilios.fun_pagos_reclamantes
(tramite, id_reclamante, forma_pago, entidad_bancaria, tipo_cuenta, numero_cuenta, valor_reconocido)
VALUES ('456', '123456789', 'TRANSFERENCIA', 'BANCO TEST', 'AHORROS', '000123456', 125000);

CREATE TABLE IF NOT EXISTS auxilios.fun_bancos (
  cod_banco TEXT PRIMARY KEY,
  nombre_banco TEXT
);
INSERT INTO auxilios.fun_bancos (cod_banco, nombre_banco)
VALUES ('001', 'BANCO TEST')
ON CONFLICT (cod_banco) DO UPDATE SET nombre_banco = EXCLUDED.nombre_banco;

CREATE TABLE IF NOT EXISTS auxilios.fun_log_reclamante (
  na SERIAL PRIMARY KEY,
  tramite TEXT,
  id_reclamante TEXT,
  usuario TEXT,
  estado_anterior TEXT,
  estado_actual TEXT,
  fecha_insert TIMESTAMP DEFAULT now()
);
TRUNCATE auxilios.fun_log_reclamante;
INSERT INTO auxilios.fun_log_reclamante
(tramite, id_reclamante, usuario, estado_anterior, estado_actual)
VALUES ('456', '123456789', 'IMAGINE', 'NUEVO', 'APROBADO FIDUCIA');

CREATE TABLE IF NOT EXISTS auxilios.fun_log_cierre_masivo (
  na SERIAL PRIMARY KEY,
  tramite TEXT,
  id_reclamante TEXT,
  valor TEXT,
  cod_banco TEXT,
  tipo_cta TEXT,
  cuenta TEXT,
  usuario_carga TEXT,
  estado TEXT,
  fecha_carga TIMESTAMP DEFAULT now()
);
TRUNCATE auxilios.fun_log_cierre_masivo;
INSERT INTO auxilios.fun_log_cierre_masivo
(tramite, id_reclamante, valor, cod_banco, tipo_cta, cuenta, usuario_carga, estado, fecha_carga)
VALUES ('456', '123456789', '125000', '001', 'AHORROS', '000123456', 'IMAGINE', 'Validado', now());
