# Mapa de despliegues — Atlas ONE

> Última actualización: 2026-09-22 — corte de producción de Railway al VPS IONOS.
> Historia del corte: `docs/superpowers/plans/2026-09-01-migracion-atlas-one-ionos.md`
> (plan) y `.github/workflows/ci.yml` (pipeline final, distinto del plan original: en
> vez de `git archive`/rsync manual, CI/CD empuja por SSH y verifica el commit
> desplegado — ver [`../DEPLOY.md`](../DEPLOY.md)).

Dónde vive cada cosa y qué rama la alimenta. Léelo antes de tocar `main`.

## Estado actual

| Destino | Rama | Base de datos | Quién lo usa |
|---|---|---|---|
| `app.atlasone.com.mx` | `main` | Postgres 18 en el VPS (`atlas_one_prod`) | **Producción — Novedades Kaory, Ginebra, Imaltzin, Eleven Fashion, todos los días** |
| `atlasone.com.mx` | — | — | Landing estática |
| `rmazh.atlasone.com.mx` | — | — | Reservado para otro repositorio |

`atlas-one.up.railway.app` **ya no sirve producción**: el 2026-09-22 se cortó el
tráfico de Kaory al VPS. El proyecto de Railway (`atlas-bos`) sigue existiendo
—apagarlo es un paso aparte, pendiente— pero no tiene despliegue automático activo
desde `main` y no debe tratarse como destino vigente.

## ⚠️ `main` despliega producción automáticamente

`.github/workflows/ci.yml`, job `deploy-ionos`, tiene despliegue automático por SSH al
VPS IONOS. **Cada push a `main` reconstruye y reemplaza el punto de venta que Kaory,
Ginebra, Imaltzin y Eleven están usando**, después de que pytest + vitest + tsc + build
pasen en el mismo workflow. No es una rama de integración: es producción en vivo.

La tienda de Kaory opera hasta cerca de las 20:00 hora de México. Cualquier cambio que
pueda afectar el arranque debería entrar fuera de ese horario.

### El `Dockerfile` SÍ debe estar en `main`

A diferencia del esquema anterior (Railway priorizaba un `Dockerfile` en la raíz por
encima de Railpack sin que nadie lo pidiera, así que se mantenía fuera de `main` a
propósito), hoy el `Dockerfile` de la raíz **es** el mecanismo de build de producción
— lo usa `docker compose build` en el VPS. Vive en `main` porque tiene que estar ahí.

## Ramas

```
main  ──▶ VPS IONOS (app.atlasone.com.mx) — Kaory, Ginebra, Imaltzin, Eleven
```

Tronco único desde el 2026-09-22: `staging` (que traía Gastro Suite, ledger de botellas
del bar, Fase 4 del shell móvil y ~300 commits más) se fusionó a `main` por
fast-forward — era su ancestro estricto, así que el FF fue limpio y no hubo merge
commit que resolver. Detalle del corte completo (verificación de datos, smoke test,
unificación de ramas) en `docs/superpowers/plans/2026-09-01-migracion-atlas-one-ionos.md`.

El entorno `staging` de Railway se había **eliminado el 2026-07-28** (antes de este
corte); su contenido corrió en el VPS bajo `app.atlasone.com.mx` (base `atlas_one_beta`,
datos demo) hasta que ese mismo dominio pasó a servir producción real el 2026-09-22.
Respaldo del entorno demo viejo en `/srv/backups/railway_staging.dump`.

## Variables de entorno

En el VPS se capturan en el `env_file:` del `docker-compose.yml` de
`/srv/apps/atlas-one-prod` (no en un panel como el de Railway).

| Variable | Notas |
|---|---|
| `DATABASE_URL` | Apunta al Postgres 18 del propio VPS (`atlas_one_prod`) |
| `SECRET_KEY` | **Definida en el VPS con un valor real** (generado en la migración) — ya no usa el default del repositorio en producción |
| `LOG_LEVEL` | **En MAYÚSCULAS.** `app/main.py:27` lo pasa directo a `logging`; con `info` uvicorn muere con `ValueError: Unknown level` |
| `CLOUDINARY_URL` | Sin ella las imágenes van a `app/static/{product_images,branch_logos,uploads}` |
| `SUPERADMIN_USER` / `SUPERADMIN_PASS` | Solo aplican si el usuario no existe; `railway_init.py` no cambia contraseñas existentes |

### Deuda de seguridad — resuelta para este destino

`app/core/security/config.py` usa `_DEFAULT_SECRET =
"atlas_erp_secret_key_change_me_in_prod"` como respaldo de `SECRET_KEY`. El VPS ya
define un `SECRET_KEY` real (ver arriba), así que producción hoy **no** firma JWT con
el default público del repositorio. El proyecto de Railway (si sigue sirviendo algo,
p. ej. `rmazh`) puede seguir sin definirla — verificar ahí por separado si aplica.

## Corte de producción al VPS — hecho (2026-09-22)

`app.atlasone.com.mx` es la puerta de producción desde el 2026-09-22; la terminal de
Kaory habla con ese dominio, ya no con `atlas-one.up.railway.app`. Procedimiento
seguido (plan completo en
`docs/superpowers/plans/2026-09-01-migracion-atlas-one-ionos.md`):

1. Reconfigurar el origen que valida el agente de impresión de la tienda para el
   dominio nuevo y verificar una impresión real. El agente vive hoy en su propio
   repositorio (`Ecamposg95/Atlas-Print-Agent`, ver `docs/API_REFERENCE.md §Impresora`)
   — su configuración de CORS/orígenes ya no es parte de este repo.
2. Se resincronizó la base desde Railway (dump completo, purga de organizaciones demo).
3. Se verificaron los conteos de `sales_documents`, `payments` e `inventory_movements`.
4. Se apuntó la terminal de Kaory al dominio nuevo.
5. Prueba de humo: venta real con ticket impreso, corte de caja.
6. Railway se dejó encendido como rollback — sigue así (ver arriba); apagarlo es
   trabajo aparte, no bloqueante.
7. `staging` se fusionó a `main` por fast-forward (ver `branching-strategy.md`) y el
   despliegue pasó de rsync manual a CI/CD (`docs/DEPLOY.md`).

Ver [`ionos-vps.md`](./ionos-vps.md) para el detalle del servidor.
