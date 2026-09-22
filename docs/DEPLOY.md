# Despliegue — Atlas One en el VPS IONOS

> Vigente desde 2026-09-22 (`4054d6e`, rama `feat/deploy-ionos-en-pipeline`). Reemplaza a
> Railway como destino de producción — ver [`RAILWAY_DEPLOY.md`](../RAILWAY_DEPLOY.md)
> para la guía histórica (ya no aplica).

**Producción = `https://app.atlasone.com.mx`, en el VPS IONOS (`atlas-prod-01`,
`74.208.190.44`). Cada push a `main` la reconstruye y la reemplaza automáticamente.**
No hay rama `staging`: `main` es tronco único (ver
[`branching-strategy.md`](branching-strategy.md)).

---

## 1. El pipeline

`.github/workflows/ci.yml`, job `deploy-ionos`. Corre **solo** en push a `main`, y
**solo si** `backend-tests` (pytest), `frontend-tests` (vitest), `frontend-typecheck`
(`tsc --noEmit`) y `frontend-build` (`vite build`) pasaron primero — el despliegue es
el último eslabón, no un paso en paralelo con las pruebas. Un solo despliegue a la vez
(`concurrency: group: deploy-ionos, cancel-in-progress: false`): un segundo push espera
al primero en vez de cancelarlo, para no dejar el contenedor a medias.

Pasos (todos por SSH con una llave de despliegue dedicada, secretos `IONOS_SSH_KEY` /
`IONOS_KNOWN_HOSTS` / `IONOS_HOST` — huella fijada, sin `ssh-keyscan` en caliente):

1. **Envía el código.** `tar` del working tree (sin `.git`, sin `node_modules`) por SSH
   a `/srv/apps/atlas-one-prod/src`. El commit desplegado viaja dentro del árbol como
   `.commit_desplegado`, para poder verificarlo después DENTRO del contenedor.
2. **Construye y levanta.** `docker compose build && docker compose up -d` en
   `/srv/apps/atlas-one-prod` (el `docker-compose.yml` vive en el servidor, con
   `context: ./src`).
3. **Verifica el commit.** Hasta 30 intentos de 5s comparando
   `docker exec atlas-one-prod cat /app/.commit_desplegado` contra `github.sha`. Si no
   coincide en 2.5 minutos, falla el job y muestra `docker logs --tail 40`.
4. **Verifica salud.** Hasta 30 intentos de 5s contra `https://app.atlasone.com.mx/health`
   esperando `200`.

Sin estos dos últimos pasos "se desplegó" sería un acto de fe — ya pasó que el build no
tomaba y el contenedor seguía con la imagen vieja sin avisar.

## 2. La imagen

`Dockerfile` en la raíz del repo (multi-stage):

1. **`frontend`** (`node:20-alpine`): `npm ci && npm run build` → `frontend/dist`.
2. **`pydeps`** (`python:3.12-slim` + toolchain de build: `build-essential`, `pkg-config`,
   `libpq-dev`, `libcairo2-dev`): crea el venv en `/opt/venv` e instala
   `requirements.txt`.
3. **`runtime`** (`python:3.12-slim`, solo librerías runtime: `libpq5`, `libcairo2`,
   `tzdata`, `TZ=America/Mexico_City`): copia el venv del stage 2, copia el código, y
   pisa `frontend/dist` con el build fresco del stage 1.

`CMD`: `python scripts/railway_init.py && exec uvicorn app.main:app --host 0.0.0.0
--port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'`. El script se sigue
llamando `railway_init.py` — el nombre es historia, no describe el destino; sigue
siendo el único mecanismo de migraciones automáticas (regla de oro #3 de
[`CLAUDE.md`](../CLAUDE.md)) y corre igual aquí que corría en Railway.

`.dockerignore` excluye `.git`, `node_modules`, `.venv`, `tests`, `docs/`, `*.md` y
cualquier `.pdf`/`context/` — nada de documentación o credenciales entra a la imagen.

## 3. Verificar un despliegue

```bash
ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado'   # debe ser el sha del push
ssh ionos 'docker logs --tail 60 atlas-one-prod'
curl -s https://app.atlasone.com.mx/health
```

Verifica siempre **contra el contenedor**, no contra `src/` del servidor — `docker
inspect -f "{{.State.StartedAt}}"` delata un `build` que no levantó la imagen nueva.

## 4. Rollback

No hay un botón "Rollback" (a diferencia del dashboard de Railway). Para volver a un
commit anterior:

```bash
git checkout <commit-bueno>
git tar --exclude=.git --exclude=node_modules -cf - . | \
  ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'
ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'
```

O revertir el commit malo en `main` y dejar que el pipeline vuelva a correr — es la vía
preferida porque deja rastro en el historial y corre las pruebas antes de reconstruir.

## 5. Servidor y otros servicios en el mismo VPS

`atlas-prod-01` aloja más de una app detrás de Caddy (TLS automático). Detalle completo,
credenciales de acceso y mantenimiento en
[`infra/ionos-vps.md`](infra/ionos-vps.md). Mapa de qué corre en cada dominio en
[`infra/deployment-map.md`](infra/deployment-map.md).

## 6. Variables de entorno en producción

Igual que antes (ver tabla completa en [`RAILWAY_DEPLOY.md §3`](../RAILWAY_DEPLOY.md) —
sigue siendo la referencia del significado de cada variable, solo cambió dónde se
capturan: hoy en el `env_file:` del `docker-compose.yml` del servidor, no en el panel de
Railway). Igual que en Railway, `SECRET_KEY` es la que más importa asegurar — ver la
nota de seguridad en `docs/infra/deployment-map.md`.

## 7. Qué NO cambió

- `scripts/railway_init.py` sigue siendo el único mecanismo de migraciones automáticas
  (regla de oro #3). El nombre del archivo no se va a renombrar solo por el cambio de
  destino — renombrarlo tocaría cuatro rutas de arranque (`Procfile`, `nixpacks.toml`,
  `railway.json`, este `Dockerfile`) por un cambio cosmético.
- `nixpacks.toml`/`railway.json`/`Procfile` siguen en el repo, de reserva, por si algún
  día se vuelve a desplegar algo en Railway (p. ej. `rmazh`, que sigue ahí — ver
  `docs/infra/deployment-map.md`).
