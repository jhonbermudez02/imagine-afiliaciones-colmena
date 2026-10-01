-- ==========================================================
-- BD: img004   |  Contrato 60000661  |  Reemplazar XXX por el lote
-- ==========================================================

-- Verificación previa
SELECT lt, f01, count(*), min(sr), max(sr) FROM bkempresasarp WHERE lt = XXX GROUP BY lt, f01;
SELECT afi_rad_na, afi_rad_estado, afi_rad_fecharecibido, afi_rad_fechadigitacion, afi_rad_fechaplano
  FROM afi_rad WHERE afi_rad_contrato = 60000661;

BEGIN;
-- va primero: usa el rango de sr de bkempresasarp antes de borrarla
DELETE FROM afi_devoluciones
 WHERE dev_sr BETWEEN (SELECT min(sr) FROM bkempresasarp WHERE lt = XXX)
                  AND (SELECT max(sr) FROM bkempresasarp WHERE lt = XXX);
DELETE FROM bkafiliadosarp        WHERE lote = XXX;
DELETE FROM bkcentrot             WHERE lote = XXX;
DELETE FROM bkwddias              WHERE lote = XXX;
DELETE FROM bkwdestudiantes       WHERE lote = XXX;
DELETE FROM bkwdindependientes    WHERE lote = XXX;
DELETE FROM bkwdcomisiones        WHERE lote = XXX;
DELETE FROM bkempresasarp         WHERE lt   = XXX AND f01 = 60000661;
DELETE FROM planillasafiliadosarp WHERE lote = XXX;
DELETE FROM anexosafiliadosarp    WHERE lote = XXX;
DELETE FROM estadistico           WHERE lote = XXX;
DELETE FROM tr                    WHERE nl   = XXX;
DELETE FROM lc                    WHERE fileid = XXX;
UPDATE afi_rad
   SET afi_rad_estado = 'Radicada', afi_rad_fechadigitacion = NULL, afi_rad_fechaplano = NULL
 WHERE afi_rad_contrato = 60000661 AND afi_rad_estado IN ('Indexado', 'Plano');
COMMIT;
