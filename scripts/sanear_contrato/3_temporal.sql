-- ==========================================================
-- BD: temporal   |  Contrato 60000661  |  Reemplazar XXX por el lote
-- ==========================================================

-- Verificación previa: trámites que creó la app para el contrato (lote = case-...)
SELECT idtramite, numerocontrato, lote, estado, fecha_insert
  FROM proc_servicios_obtenertramites
 WHERE numerocontrato = '60000661' AND lote LIKE 'case-%';

BEGIN;
DELETE FROM proc_servicios_obtenertrabajadortramite WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenerhoraslaborales    WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenersedetramite       WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenerempleadortramite  WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenercomisionestramite WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenerarchivosadjuntos  WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_consulta                 WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_trazabilidad             WHERE idtramite IN (SELECT idtramite FROM proc_servicios_obtenertramites WHERE numerocontrato = '60000661' AND lote LIKE 'case-%');
DELETE FROM proc_servicios_obtenertramites          WHERE numerocontrato = '60000661' AND lote LIKE 'case-%';
-- restos del lote (normalmente ya vienen vacíos)
DELETE FROM lc          WHERE fileid = XXX;
DELETE FROM tr          WHERE nl     = XXX;
DELETE FROM estadistico WHERE lote   = XXX;
COMMIT;
