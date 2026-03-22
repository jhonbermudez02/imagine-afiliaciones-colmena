# Produccion Imagine

## Contenedores oficiales

Estos son los contenedores que hoy forman el despliegue real del sistema:

- `imagine_frontend`: interfaz web
- `imagine_backend`: backend principal de Imagine
- `imagine_db`: base de datos principal
- `imagine_qdrant`: indice de conocimiento y busqueda semantica
- `imagine_ollama`: modelos locales
- `imagine_compat_backend`: motor de compatibilidad usado para flujo 926
- `imagine_compat_db`: base de datos del motor de compatibilidad

## Contenedores que no deben ir a produccion

Estos son de desarrollo, pruebas o stacks viejos y no deben mezclarse con el despliegue oficial:

- `afi_*`
- `clone_full_*`
- `nova_*`
- `qdrant`
- `ollama`

## Motivo de la separacion

Hoy el sistema todavia depende de dos bloques:

1. Imagine:
   - interfaz, backend, base principal, conocimiento y modelos
2. Compatibilidad 926:
   - backend y base del motor que replica el proceso historico

No es ideal a largo plazo, pero es la salida mas segura para produccion ahora porque no rompe el flujo que ya esta funcionando.

## Recomendacion de salida

Para salir a produccion sin romper:

1. Usar `docker-compose.prod.yml`
2. No reutilizar contenedores de pruebas
3. Publicar solo:
   - `3000` para frontend
   - `8000` para backend
4. Mantener red interna privada entre servicios
5. Documentar que `imagine_backend` depende de `imagine_compat_backend` para el 926

## Siguiente fase

Despues de estabilizar produccion, la siguiente mejora recomendada es absorber el motor de compatibilidad dentro de Imagine para reducir contenedores y operacion.
