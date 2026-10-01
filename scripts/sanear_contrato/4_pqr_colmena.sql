-- ==========================================================
-- BD: pqr_colmena   |  Contrato 60000661
-- Reabre la gestión para que el contrato vuelva a Pendientes.
-- ==========================================================

-- 1) Ejecutar esto primero y ubicar las dos filas que cerró la aprobación:
--    ID_CIERRE  = la fila con actividad 390 del día de la aprobación
--    ID_GESTION = la fila de la misma radicación con la MISMA fecha_gestion que la 390
SELECT t.id_trazabilidad, t.id_radicacion_sa, t.actividad, t.usuario_gestion,
       t.fecha_asignacion, t.fecha_gestion, t.observacion
  FROM afa_trazabilidad t
 WHERE t.id_radicacion_sa IN (
        SELECT v.id_radicacion_sa
          FROM valores v
          JOIN tipo_solicitud_campo b ON b.id_tipo_solicitud_campo = v.id_tipo_solicitud_campo
          JOIN campos c ON c.id_campo = b.id_campo
         WHERE c.label = 'Contrato' AND v.valor = '60000661')
 ORDER BY t.id_radicacion_sa, t.id_trazabilidad;

-- 2) Reemplazar ID_CIERRE, ID_GESTION y USUARIO_ANTERIOR y ejecutar.
--    USUARIO_ANTERIOR = usuario asignado antes de aprobar (en el case.json:
--    analysis.pqr_trazabilidad.usuario_gestion_anterior). Si no se sabe, dejar NULL sin comillas.
BEGIN;
DELETE FROM afa_trazabilidad WHERE id_trazabilidad = ID_CIERRE AND actividad = 390;
UPDATE afa_trazabilidad
   SET fecha_gestion = NULL, usuario_gestion = 'USUARIO_ANTERIOR'
 WHERE id_trazabilidad = ID_GESTION;
COMMIT;

-- 3) Verificación: debe aparecer el contrato
SELECT * FROM afa_pendientes WHERE contrato = '60000661';
