# AFI Colima — Guía de Instalación

Sistema de validación de afiliaciones ARL para Colmena.

---

## Requisitos del servidor

| Requisito | Mínimo | Recomendado |
|---|---|---|
| Sistema operativo | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 LTS |
| RAM | 4 GB | 8 GB o más |
| Disco | 20 GB | 50 GB |
| CPU | 2 núcleos | 4 núcleos |
| Puertos | 8020 abierto | 8020 abierto |

---

## 1. Instalar Docker

```bash
# Actualizar paquetes
sudo apt-get update

# Instalar dependencias
sudo apt-get install -y ca-certificates curl gnupg

# Agregar repositorio Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Agregar usuario al grupo docker (no requiere sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verificar instalación
docker --version
docker compose version
```

---

## 2. Clonar el repositorio

```bash
git clone https://github.com/IOhernan/imagine-afiliaciones.git
cd imagine-afiliaciones
```

---

## 3. Configurar datos iniciales

```bash
# Crear carpetas necesarias
mkdir -p data/cases data/evals data/postgres

# Copiar archivo de destinatarios de correo
# (recibir este archivo por canal seguro de Imagine S.A.S.)
# Ubicarlo en: data/evals/pilot_notification_recipients.json
```

Estructura del archivo `pilot_notification_recipients.json`:
```json
{
  "sender": {
    "name": "Imagine S.A.S.",
    "email": "correo-remitente@dominio.com"
  },
  "recipients": [
    {
      "name": "Nombre Apellido",
      "email": "correo@dominio.com"
    }
  ]
}
```

---

## 4. Levantar el sistema

```bash
# Primera vez (descarga imágenes y modelos — puede tardar 10-15 min)
docker compose -f docker-compose.deploy.yml up -d

# Ver progreso
docker compose -f docker-compose.deploy.yml logs -f imagine_backend
```

> **Nota:** El primer arranque descarga el modelo de inteligencia artificial (~120MB). 
> Espere hasta ver el mensaje `Application startup complete` en los logs.

---

## 5. Verificar instalación

```bash
# Verificar que todos los contenedores están corriendo
docker compose -f docker-compose.deploy.yml ps

# Verificar salud del sistema
curl -s http://localhost:8020/api/testers | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('Operadores registrados:', len(d.get('items', [])))
"

# Acceder al sistema
# Abrir en navegador: http://IP-DEL-SERVIDOR:8020
```

---

## 6. Comandos útiles

```bash
# Ver estado de contenedores
docker compose -f docker-compose.deploy.yml ps

# Ver logs del backend
docker compose -f docker-compose.deploy.yml logs -f imagine_backend

# Reiniciar el sistema
docker compose -f docker-compose.deploy.yml restart

# Detener el sistema
docker compose -f docker-compose.deploy.yml down

# Actualizar a la última versión
git pull origin main
docker compose -f docker-compose.deploy.yml build --no-cache imagine_backend imagine_frontend
docker compose -f docker-compose.deploy.yml up -d
docker compose -f docker-compose.deploy.yml restart imagine_frontend
```

---

## 7. Solución de problemas

**El sistema no carga después de reiniciar el backend:**
```bash
docker compose -f docker-compose.deploy.yml restart imagine_frontend
```

**Verificar salud de todos los servicios:**
```bash
curl -s http://localhost:8020/health
```

**Ver uso de recursos:**
```bash
docker stats --no-stream
```

---

## Soporte

Imagine S.A.S. — hdescobar@imagine-tech.com
