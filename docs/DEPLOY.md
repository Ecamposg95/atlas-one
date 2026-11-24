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

**Presupuesto de bundle:** el paso "Presupuesto de descarga de la ruta crítica" de `frontend-build` (`scripts/presupuesto_bundle.py`) mide los bytes de login → POS contra `frontend/presupuesto_bundle.json`; si lo rebasa, `frontend-build` falla y **`deploy-ionos` no corre**. Lee la salida del paso (medido vs `tope_bytes`); para subir el tope edita ese JSON en el mismo PR y justifícalo en el commit.

Pasos (todos por SSH con una llave de despliegue dedicada, secretos `IONOS_SSH_KEY` /
`IONOS_KNOWN_HOSTS` / `IONOS_HOST` — huella fijada, sin `ssh-keyscan` en caliente):

1. **Envía el código.** Primero vacía el código fuente del `src/` del servidor
   (`frontend/src`, `frontend/public`, `scripts` y todo `app/` menos `app/static`, donde
   pueden vivir fotos anteriores a Cloudinary) y luego extrae el `tar` del working tree
   (sin `.git`, sin `node_modules`) por SSH a `/srv/apps/atlas-one-prod/src`. Sin ese
   vaciado, un archivo borrado en `main` sobrevive en el servidor: el 2026-10-21
   `InicioBasico.tsx` quedó huérfano, `tsc` lo compiló contra una API que ya no existía y
   el build de la imagen falló. El commit desplegado viaja dentro del árbol como
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
# 1. Vaciar el código fuente del servidor (app/static se respeta), igual que el job de CI:
#    tar -x no borra lo que ese commit no tenía y un huérfano puede tirar el build de tsc.
ssh ionos 'cd /srv/apps/atlas-one-prod/src && rm -rf frontend/src frontend/public scripts && find app -mindepth 1 -maxdepth 1 ! -name static -exec rm -rf {} +'
# 2. Enviar el commit bueno (git archive lee del commit, no del working tree: no hace
#    falta `git checkout` ni se cuelan node_modules o cambios sin confirmar).
git archive --format=tar <commit-bueno> | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'
ssh ionos 'echo <commit-bueno-sha-completo> > /srv/apps/atlas-one-prod/src/.commit_desplegado'
# 3. Construir y levantar, juntos.
ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'
# 4. Verificar contra el contenedor.
ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado'
curl -s https://app.atlasone.com.mx/health
```

El paso de `.commit_desplegado` importa: en un despliegue normal lo escribe el job de CI;
sin él, el contenedor seguiría anunciando el commit anterior. Las migraciones de
`railway_init.py` son aditivas y no se deshacen con el rollback: el código viejo convive
con las columnas nuevas.

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

### Inteligencia artificial (Cargar mercancía y agente)

Todas van en el `env_file:` del servidor. Arquitectura y ejemplos en [`ai/README.md`](ai/README.md);
operación de Cargar mercancía en [`ai/cargar-mercancia.md`](ai/cargar-mercancia.md).

| Variable | Para qué | Por omisión |
|---|---|---|
| `ANTHROPIC_API_KEY` | Llave de Anthropic. Sin ninguna llave útil para la tarea, los endpoints de IA responden 503 "IA no configurada: falta … en el servidor." y no se crea la carga | vacía |
| `AI_MODELOS_CONSULTA` | Lista ordenada `proveedor:modelo` separada por comas para la tarea `consulta`; si el primero falla por red, 5xx o cuota, se usa el siguiente | `anthropic:claude-haiku-5-5` |
| `AI_MODELOS_CAPTURA` | Igual, para `captura` (Cargar mercancía, altas) | `anthropic:claude-opus-5-5` |
| `AI_MODELOS_ANALISIS` | Igual, para `analisis` (reportes) | `anthropic:claude-opus-5-5` |
| `AI_MODELO` | Heredada: modelo de Anthropic para `captura` cuando `AI_MODELOS_CAPTURA` no está puesta | sin definir |
| `LLM_API_KEY` | Llave del proveedor `compatible` (API compatible con OpenAI) | vacía |
| `LLM_BASE_URL` | URL base del proveedor `compatible` | capa compatible de Gemini |
| `LLM_MODEL` | Modelo de `compatible` cuando la entrada de la lista no lo nombra | `gemini-3.8-flash` |
| `AI_PROVEEDOR_<NOMBRE>_BASE_URL`, `AI_PROVEEDOR_<NOMBRE>_API_KEY` | Otro servicio compatible con OpenAI, usable en las listas como `<nombre>:<modelo>` (p. ej. `AI_PROVEEDOR_GROQ_…` → `groq:llama-x`) | sin definir |
| `AI_TOKENS_DIA_ORG` | Si está puesta, tope global de tokens (entrada + salida) por organización y día; tapa el cupo del plan. Una organización con `ai_tokens_dia` propio no la obedece | sin definir (cupo del plan: 2 000 000, provisional) |
| `AI_TOKENS_DIA_USUARIO` | Tope de tokens por persona y día | sin definir (sin tope por persona) |
| `AI_TIMEOUT_SEG` | Tope en segundos de cada llamada a Anthropic; el SDK reintenta una sola vez | `300` |
| `CARGAS_PROCESO_EN_LINEA` | Con `1`, la lectura de una carga corre en el hilo de la petición. Solo para pruebas | sin definir |

Cambio respecto a antes de la fase A0: `AI_TOKENS_DIA_ORG` ya no vale `200000` por omisión; sin la
variable manda el cupo del plan. La excepción por organización (lista de modelos y cupo) no es variable:
son las columnas `organization.ai_modelos` y `organization.ai_tokens_dia`, que guarda
`PUT /api/platform/organizations/{id}`.

Las dependencias `anthropic` y `pypdf` están en `requirements.txt`, así que la etapa `pydeps` de la imagen
las instala sola; no hay paso manual. Tras desplegar, `railway_init.py` crea las tablas `cargas_*` y
`ai_llamadas`, y las columnas `organization.reglas_carga`, `organization.ai_modelos` y
`organization.ai_tokens_dia`.

## 7. Qué NO cambió

- `scripts/railway_init.py` sigue siendo el único mecanismo de migraciones automáticas
  (regla de oro #3). El nombre del archivo no se va a renombrar solo por el cambio de
  destino — renombrarlo tocaría cuatro rutas de arranque (`Procfile`, `nixpacks.toml`,
  `railway.json`, este `Dockerfile`) por un cambio cosmético.
- `nixpacks.toml`/`railway.json`/`Procfile` siguen en el repo, de reserva, por si algún
  día se vuelve a desplegar algo en Railway (p. ej. `rmazh`, que sigue ahí — ver
  `docs/infra/deployment-map.md`).
