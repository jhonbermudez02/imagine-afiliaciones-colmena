-- Inventario de lógica oculta para homologación legacy
-- Ejecutar con permisos de lectura sobre catálogos del motor PostgreSQL.

-- 1) Triggers por tabla objetivo
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  t.tgname AS trigger_name,
  pg_get_triggerdef(t.oid, true) AS trigger_def
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
  AND (
    (n.nspname = 'auxilios' AND c.relname IN (
      'fun_reclamantes',
      'fun_solicitudes',
      'fun_pagos_reclamantes',
      'fun_respuesta_banco',
      'fun_tramite_solicitud'
    ))
    OR (n.nspname = 'public' AND c.relname = 'prerradicacion')
  )
ORDER BY 1,2,3;

-- 2) Reglas (RULES) por tabla objetivo
SELECT
  schemaname AS schema_name,
  tablename AS table_name,
  rulename AS rule_name,
  definition
FROM pg_rules
WHERE (
    schemaname = 'auxilios' AND tablename IN (
      'fun_reclamantes',
      'fun_solicitudes',
      'fun_pagos_reclamantes',
      'fun_respuesta_banco',
      'fun_tramite_solicitud'
    )
  )
  OR (schemaname = 'public' AND tablename = 'prerradicacion')
ORDER BY 1,2,3;

-- 3) Funciones referenciadas por triggers detectados en tablas objetivo
SELECT DISTINCT
  pn.nspname AS function_schema,
  p.proname AS function_name,
  pg_get_function_identity_arguments(p.oid) AS args,
  pg_get_functiondef(p.oid) AS function_def
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
JOIN pg_namespace pn ON pn.oid = p.pronamespace
WHERE NOT t.tgisinternal
  AND (
    (n.nspname = 'auxilios' AND c.relname IN (
      'fun_reclamantes',
      'fun_solicitudes',
      'fun_pagos_reclamantes',
      'fun_respuesta_banco',
      'fun_tramite_solicitud'
    ))
    OR (n.nspname = 'public' AND c.relname = 'prerradicacion')
  )
ORDER BY 1,2,3;

-- 4) Vista rápida de constraints FK/UNIQUE/CHECK en tablas objetivo
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  con.conname AS constraint_name,
  con.contype AS constraint_type,
  pg_get_constraintdef(con.oid, true) AS constraint_def
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (
    n.nspname = 'auxilios' AND c.relname IN (
      'fun_reclamantes',
      'fun_solicitudes',
      'fun_pagos_reclamantes',
      'fun_respuesta_banco',
      'fun_tramite_solicitud'
    )
  )
  OR (n.nspname = 'public' AND c.relname = 'prerradicacion')
ORDER BY 1,2,3;

