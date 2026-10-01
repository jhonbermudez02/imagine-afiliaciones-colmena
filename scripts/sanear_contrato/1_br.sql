-- ==========================================================
-- BD: br   |  Contrato 60000661  |  Reemplazar XXX por el lote
-- ==========================================================

-- Verificación previa: debe salir SOLO el contrato 60000661
SELECT lt, f01, tp, count(*) FROM brempresasarp WHERE lt = XXX GROUP BY lt, f01, tp;
SELECT f28, f31, f32, f33 FROM brafiliadosarp WHERE lt = XXX;

BEGIN;
DELETE FROM brafiliadosarp     WHERE lt   = XXX;
DELETE FROM brcentrot          WHERE lote = XXX;
DELETE FROM brwddias           WHERE lote = XXX;
DELETE FROM brwdestudiantes    WHERE lote = XXX;
DELETE FROM brwdindependientes WHERE lote = XXX;
DELETE FROM brwdcomisiones     WHERE lote = XXX;
DELETE FROM brempresasarp      WHERE lt   = XXX AND f01 = 60000661;
COMMIT;
