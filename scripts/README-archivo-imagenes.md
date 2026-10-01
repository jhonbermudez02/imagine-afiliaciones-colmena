# Archivado de documentos en el repositorio de imágenes

## Por qué `/legacy_share` es un symlink y no un volumen

El repositorio de imágenes es un NFS (`fileimaginex.arp.fs.net`) montado en el host. Hay
**dos filers publicados bajo el mismo nombre DNS**, uno por sede, así que el nombre no
distingue nada: la única señal fiable de a cuál se está escribiendo es el `addr=` de
`/proc/mounts`.

Un **bind mount de Docker se resuelve una sola vez**, al arrancar el contenedor. Si el
host desmonta y vuelve a montar ese NFS —failover de la NAS, cambio de IP del filer— el
contenedor queda pegado al montaje anterior y sigue archivando ahí **sin dar ningún
error**. Los documentos terminan en el filer equivocado y el front no los encuentra.

El PHP legacy nunca tuvo este problema porque entra por symlinks de `/var/www/html`, y un
symlink se resuelve en cada acceso.

`docker-compose.deploy.external-db.yml` hace lo mismo:

- monta el **punto de montaje** del NFS (`LEGACY_IMG_MOUNT_ROOT`, p.ej. `/imagenes4`) en la
  misma ruta dentro del contenedor, con `propagation: rslave`, para que los remontajes del
  host se propaguen;
- el entrypoint apunta `/legacy_share` —la ruta fija que usa el código— a
  `LEGACY_IMG_HOST_MOUNT` con un symlink.

Montar directamente la subcarpeta de archivado no sirve: la propagación viaja por puntos
de montaje, y esa subcarpeta está por debajo del punto, no es el punto.

## Requisito en el host (una vez por servidor)

El montaje tiene que ser compartido, o la propagación no llega:

```bash
findmnt -o TARGET,PROPAGATION /imagenes4     # debe decir "shared"
mount --make-rshared /imagenes4              # si dice "private"
```

Para que sobreviva a reinicios, `shared` debe venir del montaje inicial; en la mayoría de
los sistemas con systemd se hereda de `/`. Verificarlo después de un reinicio.

## Variables del `.env`

| Variable | Ejemplo | Qué es |
|---|---|---|
| `LEGACY_IMG_MOUNT_ROOT` | `/imagenes4` | Punto de montaje del NFS en el host |
| `LEGACY_IMG_HOST_MOUNT` | `/imagenes4/img11` | Carpeta de archivado dentro de ese montaje |
| `LEGACY_IMG_EXPECTED_NDISCO` | `img11` | Debe coincidir con `server.ndisco` de `img004` |

`LEGACY_IMG_HOST_MOUNT` tiene que estar **dentro** de `LEGACY_IMG_MOUNT_ROOT`.

## Verificar

```bash
# El symlink que dejó el entrypoint
docker compose -f docker-compose.deploy.external-db.yml logs imagine_compat_backend | grep archivado

# El filer al que se está escribiendo de verdad
docker compose -f docker-compose.deploy.external-db.yml exec imagine_compat_backend \
  sh -c 'grep " /imagenes4 " /proc/mounts'
grep " /imagenes4 " /proc/mounts
```

Los dos `addr=` deben coincidir. Ojo al comparar: las opciones NFS traen también
`clientaddr=`, que es la IP de esta máquina, no la del filer.

## Recuperar documentos archivados en el filer equivocado

Montar el otro filer en solo lectura y copiar solo las fechas afectadas:

```bash
mkdir -p /mnt/filer_otro
mount -t nfs4 -o ro <IP_DEL_OTRO_FILER>:/imagenes4 /mnt/filer_otro
ls -lat /mnt/filer_otro/img11/ | head -20

rsync -av --dry-run --ignore-existing \
  /mnt/filer_otro/img11/<YYYYMMDD>/ /imagenes4/img11/<YYYYMMDD>/

umount /mnt/filer_otro
```

La base de datos no se toca: la ruta guardada en `pi` no lleva la IP del filer, así que con
los archivos en su sitio el front los encuentra solo.
