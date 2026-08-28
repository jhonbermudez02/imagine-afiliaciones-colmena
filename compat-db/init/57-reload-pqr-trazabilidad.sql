--
-- Reemplazo del contenido de pqr_colmena.afa_trazabilidad.
--
-- Origen: files_migration/new_feature/pqr_colmena/data_afa_trazabilidad.csv
--
-- Deja la tabla SOLO con las 11 gestiones de las radicaciones 923902..923905, que son
-- las mismas que traen valores y afa_adjuntosrad en ese export. Es un reemplazo, no una
-- adicion: el TRUNCATE descarta las 74.224 filas historicas (2020-12-06 a 2026-08-14)
-- que carga 55-pqr-colmena-data.sql desde /pqr_seed/data-afa_trazabilidad.csv.
--
-- Decision explicita del responsable del dato, no un efecto colateral: los ids del CSV
-- (77094..77112) no chocan con ninguno de los existentes (max 76996), asi que sin el
-- TRUNCATE lo natural habria sido acumular.
--
-- PARA VOLVER ATRAS: en un contenedor nuevo basta con sacar este script del init; 55
-- vuelve a cargar el historico completo. El CSV historico sigue intacto en
-- files_migration/schemassql/pqr_colmena/data-afa_trazabilidad.csv. Sobre el compat-db
-- local ya provisionado, recargarlo a mano:
--   psql -U <usuario> -d pqr_colmena -c 'TRUNCATE public.afa_trazabilidad;'
--   psql -U <usuario> -d pqr_colmena -c "\copy public.afa_trazabilidad FROM 'data-afa_trazabilidad.csv' WITH (FORMAT csv)"
--
-- AMBITO: SOLO el compat-db local/de pruebas, que es una reproduccion parcial del legacy.
-- NO correr contra el servidor: alla la base ya esta completa y con la trazabilidad real,
-- y el TRUNCATE de abajo la borraria para dejar 11 filas de muestra. Este script existe
-- para que un contenedor limpio quede igual al entorno de trabajo local, nada mas.
--
-- Idempotente por construccion: TRUNCATE + INSERT fijos dejan siempre el mismo estado.
--

\set ON_ERROR_STOP on

BEGIN;

TRUNCATE public.afa_trazabilidad;

INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77094,923902,119609,389,'E9B5J2R7','2026-08-18 04:37:49-05'::timestamptz,'2026-08-18 16:24:25.556177-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77096,923903,119610,389,'C2C1M5A7','2026-08-18 04:25:41-05'::timestamptz,'2026-08-18 16:25:41.555296-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77103,923904,119626,389,'D6C8G5A1','2026-08-19 08:37:30-05'::timestamptz,'2026-08-19 08:37:30.200678-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77106,923905,119630,389,'E9B5J2R7','2026-08-19 10:36:08-05'::timestamptz,'2026-08-19 10:36:08.37819-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77107,923905,119630,391,NULL,NULL,'2026-08-19 10:36:08.38385-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77095,923902,119609,391,'pr03rola','2026-08-19 10:45:57.782828-05'::timestamptz,'2026-08-18 16:24:25.568006-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77108,923902,119609,390,'pr03rola','2026-08-19 10:45:57.782828-05'::timestamptz,'2026-08-19 10:45:57.782828-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77097,923903,119610,391,'pr03rola','2026-08-19 11:36:47.016034-05'::timestamptz,'2026-08-18 16:25:41.559653-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77111,923903,119610,390,'pr03rola','2026-08-19 11:36:47.016034-05'::timestamptz,'2026-08-19 11:36:47.016034-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77104,923904,119626,391,'nova_case_workf','2026-08-19 11:46:38.821555-05'::timestamptz,'2026-08-19 08:37:30.20661-05'::timestamptz,NULL);
INSERT INTO public.afa_trazabilidad(id_trazabilidad,id_radicacion_sa,afi_rad_na,actividad,usuario_gestion,fecha_gestion,fecha_asignacion,observacion)
  VALUES (77112,923904,119626,390,'nova_case_workf','2026-08-19 11:46:38.821555-05'::timestamptz,'2026-08-19 11:46:38.821555-05'::timestamptz,NULL);

--
-- La secuencia queda por encima del maximo cargado; los ids vienen explicitos en el
-- export, asi que sin esto el proximo nextval chocaria con las filas recien insertadas.
--
SELECT setval('public.afa_trazabilidad_id_trazabilidad_seq', COALESCE((SELECT max(id_trazabilidad) FROM public.afa_trazabilidad), 0) + 1, false);

COMMIT;
