--
-- Carga de datos de pqr_colmena: afa_adjuntosrad (tabla nueva) y las filas nuevas de
-- valores, correspondientes a las radicaciones 923902..923905.
--
-- Origen: files_migration/new_feature/pqr_colmena/data_{afa_adjuntosrad,valores}.csv
--
-- Por que no va en 55-pqr-colmena-data.sql: ese script carga por \copy desde /pqr_seed
-- y SOLO si la tabla esta vacia, asi que en una base ya provisionada -que es el caso de
-- valores, con las 15 filas del cargue inicial- no volveria a entrar nunca. Aca los
-- INSERT son fila por fila con guarda por id, de modo que el script sirve igual para el
-- init de un contenedor limpio y para aplicarlo a mano sobre un compat-db local ya
-- provisionado:
--
--   psql -U <usuario> -d pqr_colmena -f 56-seed-pqr-adjuntos-valores.sql
--
-- AMBITO: solo el compat-db local/de pruebas. El servidor ya tiene la base completa con
-- estos datos; alla no hay nada que sembrar.
--
-- Es seguro correrlo mas de una vez: cada INSERT trae WHERE NOT EXISTS sobre su id.
-- No hay ON CONFLICT porque estas tablas no declaran PK a proposito (ver el comentario
-- de 50-pqr-colmena-schema.sql), y sin restriccion unica ON CONFLICT no aplica.
--
-- data_campos.csv y data_tipo_solicitud_campo.csv del mismo export son identicos a los
-- CSV que ya carga 55-pqr-colmena-data.sql (131 y 272 filas, sin diferencias), asi que
-- no se repiten aca.
--

\set ON_ERROR_STOP on


-- ----------------------------------------------------------------------------
-- afa_adjuntosrad: 17 adjuntos de las radicaciones 923902..923905
-- ----------------------------------------------------------------------------
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817390,'D6C8G5A1','2026-08-19 08:37:21.527631-05'::timestamptz,923904,'CARDONA GUEVARA WILMER_FORMULARIO.pdf','/imagenes4/img11/20260819/Pia/00000003/075ca1ed-3d6b-4279-a3c6-f55eec0e6d5d/CARDONA GUEVARA WILMER_FORMULARIO.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817390);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817391,'D6C8G5A1','2026-08-19 08:37:21.777019-05'::timestamptz,923904,'FORMULARIO.xlsx','/imagenes4/img11/20260819/Pia/00000003/78d8b709-01d2-476d-a4ee-11784e5d009e/FORMULARIO.xlsx','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817391);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817392,'D6C8G5A1','2026-08-19 08:37:24.515959-05'::timestamptz,923904,'CARDONA GUEVARA WILMER_DOCUMENTOS UNIFICADOS.pdf','/imagenes4/img11/20260819/Pia/00000003/cbd8e606-017d-4f65-b0e1-707555986e71/CARDONA GUEVARA WILMER_DOCUMENTOS UNIFICADOS.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817392);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817393,'E9B5J2R7','2026-08-19 10:35:38.933505-05'::timestamptz,923905,'SEDE1.pdf','/imagenes4/img11/20260819/Pia/00000003/bf638c41-f7aa-4622-a05a-b6596269c949/SEDE1.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817393);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817394,'E9B5J2R7','2026-08-19 10:35:39.239117-05'::timestamptz,923905,'FORMULARIO.pdf','/imagenes4/img11/20260819/Pia/00000003/373d5411-0339-46d7-9f1e-b51d861e821e/FORMULARIO.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817394);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817395,'E9B5J2R7','2026-08-19 10:35:40.565371-05'::timestamptz,923905,'UNIFICADOS 2.pdf','/imagenes4/img11/20260819/Pia/00000003/6c220177-ddc1-42bb-8ea7-11e47d804995/UNIFICADOS 2.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817395);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817396,'E9B5J2R7','2026-08-19 10:35:41.074039-05'::timestamptz,923905,'LISTADO W.xlsx','/imagenes4/img11/20260819/Pia/00000003/c84b5934-0301-474a-a33d-2a86f2c55939/LISTADO W.xlsx','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817396);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817380,'E9B5J2R7','2026-08-18 16:24:02.852572-05'::timestamptz,923902,'Gladys Amanda Niño de Rengifo SERV. DOMESTICO.pdf','/imagenes4/img11/20260818/Pia/00000003/737e6d73-7106-4999-9709-4a2f9f267c7f/Gladys Amanda Niño de Rengifo SERV. DOMESTICO.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817380);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817381,'E9B5J2R7','2026-08-18 16:24:18.776449-05'::timestamptz,923902,'SEDE.pdf','/imagenes4/img11/20260818/Pia/00000003/79db10a8-1fb1-4255-b2be-730169cf741e/SEDE.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817381);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817382,'E9B5J2R7','2026-08-18 16:24:18.821076-05'::timestamptz,923902,'FORMULARIO.pdf','/imagenes4/img11/20260818/Pia/00000003/4ca21c42-99f9-4fde-a211-cdf24b9effb7/FORMULARIO.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817382);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817383,'E9B5J2R7','2026-08-18 16:24:18.861507-05'::timestamptz,923902,'LISTADO.xlsx','/imagenes4/img11/20260818/Pia/00000003/297c82ca-e9b5-4e41-bc60-530f0fed9f00/LISTADO.xlsx','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817383);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817384,'C2C1M5A7','2026-08-18 16:25:32.96018-05'::timestamptz,923903,'Afiliacion ASESORIAS, GESTION Y SERVICIOS UNIVERSAL.pdf','/imagenes4/img11/20260818/Pia/00000003/37b80696-9ae0-49ae-8e2a-94a50acb084d/Afiliacion ASESORIAS, GESTION Y SERVICIOS UNIVERSAL.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817384);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817385,'C2C1M5A7','2026-08-18 16:25:33.211962-05'::timestamptz,923903,'SAT.pdf','/imagenes4/img11/20260818/Pia/00000003/29159bb8-7f74-4da0-a325-fd3923c65596/SAT.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817385);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817386,'C2C1M5A7','2026-08-18 16:25:33.285459-05'::timestamptz,923903,'Afiliacion ASESORIAS, GESTION Y SERVICIOS UNIVERSAL.xlsx','/imagenes4/img11/20260818/Pia/00000003/e1efa9d3-51c2-460f-a249-26485c5e32ee/Afiliacion ASESORIAS, GESTION Y SERVICIOS UNIVERSAL.xlsx','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817386);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817387,'C2C1M5A7','2026-08-18 16:25:35.959316-05'::timestamptz,923903,'Sede 01.pdf','/imagenes4/img11/20260818/Pia/00000003/ceb7aa77-d275-4e62-82cf-5b6829243a34/Sede 01.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817387);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817388,'C2C1M5A7','2026-08-18 16:25:36.203241-05'::timestamptz,923903,'Documentacion FIN.pdf','/imagenes4/img11/20260818/Pia/00000003/9904c143-c45d-4629-aa66-d7886cce8b0c/Documentacion FIN.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817388);
INSERT INTO public.afa_adjuntosrad(id_adjunto,usuario,fecha_insert,id_radicacion,nombre_original,path,tipo,orden,desc_documental,tiene_error,errores_validacion)
  SELECT 817389,'D6C8G5A1','2026-08-19 08:37:21.495504-05'::timestamptz,923904,'CARDONA GUEVARA WILMER_ANEXO AL FORMULARIO.pdf','/imagenes4/img11/20260819/Pia/00000003/45bca327-e36a-453b-a1a7-10170f4d5c6e/CARDONA GUEVARA WILMER_ANEXO AL FORMULARIO.pdf','radicacion',NULL,NULL,false,NULL
  WHERE NOT EXISTS (SELECT 1 FROM public.afa_adjuntosrad WHERE id_adjunto = 817389);

-- ----------------------------------------------------------------------------
-- valores: 36 filas nuevas (ids 15945669..15945704) del formulario dinamico de
-- las radicaciones 923902..923905. Las 15 filas previas (923844..923864) quedan
-- intactas.
-- ----------------------------------------------------------------------------
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945669,923902,229,'1206083'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945669);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945670,923902,230,'20286445'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945670);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945671,923902,231,'Gladys Amanda Niño de Rengifo'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945671);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945672,923902,232,'648'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945672);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945673,923902,233,'8'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945673);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945674,923902,234,'1'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945674);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945675,923902,235,'652'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945675);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945676,923902,237,'658'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945676);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945677,923902,238,'663'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945677);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945678,923903,229,'60000444'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945678);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945679,923903,230,'902050457'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945679);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945680,923903,231,'ASESORIAS, GESTION Y SERVICIOS - UNIVERSAL S.A.S'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945680);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945681,923903,232,'648'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945681);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945682,923903,233,'25'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945682);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945683,923903,234,'3'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945683);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945684,923903,235,'652'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945684);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945685,923903,237,'658'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945685);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945686,923903,238,'664'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945686);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945687,923904,229,'1206082'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945687);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945688,923904,230,'80901709'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945688);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945689,923904,231,'CARDONA GUEVARA WILMER '
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945689);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945690,923904,232,'648'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945690);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945691,923904,233,'7'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945691);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945692,923904,234,'1'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945692);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945693,923904,235,'651'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945693);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945694,923904,237,'658'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945694);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945695,923904,238,'663'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945695);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945696,923905,229,'60000443'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945696);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945697,923905,230,'902087342'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945697);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945698,923905,231,'CONSORCIO RIO NEGRO'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945698);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945699,923905,232,'648'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945699);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945700,923905,233,'22'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945700);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945701,923905,234,'1'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945701);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945702,923905,235,'653'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945702);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945703,923905,237,'658'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945703);
INSERT INTO public.valores(id_valor,id_radicacion_sa,id_tipo_solicitud_campo,valor)
  SELECT 15945704,923905,238,'664'
  WHERE NOT EXISTS (SELECT 1 FROM public.valores WHERE id_valor = 15945704);

--
-- Realinear las secuencias: los ids vienen explicitos en el export, asi que sin esto
-- el proximo nextval seguiria en el valor viejo y chocaria con lo recien insertado.
--
SELECT setval('public.afa_adjuntosrad_id_adjunto_seq', COALESCE((SELECT max(id_adjunto) FROM public.afa_adjuntosrad), 0) + 1, false);
SELECT setval('public.valores_id_valor_seq', COALESCE((SELECT max(id_valor) FROM public.valores), 0) + 1, false);
