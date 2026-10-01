# Sanear contrato 60000661 para reprocesarlo

SQL plano para pgAdmin. Cada archivo se ejecuta conectado a su base. Reemplazar `XXX`
por el lote (número sin ceros a la izquierda) y, en el de PQR, `ID_CIERRE`, `ID_GESTION`
y `USUARIO_ANTERIOR`.

| Orden | Archivo | Base |
|---|---|---|
| 1 | `1_br.sql` | br |
| 2 | `2_img004.sql` | img004 |
| 3 | `3_temporal.sql` | temporal |
| 4 | `4_pqr_colmena.sql` | pqr_colmena |

Antes de empezar: desplegar el código corregido y ejecutar primero los `SELECT` de
verificación de cada archivo.

Después de los SQL:
1. Borrar la carpeta de imágenes del lote: `/img11/<YYYYMMDD>/Afa/<lote a 8 dígitos>/`.
   Se ve en `brempresasarp.pi` antes de borrar.
2. Borrar el expediente en la app:
   `curl -X DELETE "http://<servidor>:8000/api/cases/<case_id>?cierre_ciclo=true"`.
3. Cargar el contrato de nuevo desde Pendientes, aprobarlo y verificar 21 trabajadores
   en el plano, con el paso "Generación 926" en `ok`.
