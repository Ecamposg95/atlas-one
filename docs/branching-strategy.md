# Branching Strategy

> Actualizado: 2026-09-22
> Rama por defecto: `main`

> **Nota histórica:** hasta el 2026-07-28 este archivo describía el esquema
> `release/beta → release/qa → release/production` (ajeno a este repo, es de **Data X
> POS**). Del 2026-07-28 al 2026-09-22 hubo dos ramas activas, `main` (Railway,
> producción) y `staging` (VPS IONOS). El 2026-09-22, `staging` se fusionó a `main`
> (fast-forward limpio — `staging` era ancestro estricto) y producción se cortó de
> Railway al VPS. **Hoy solo existe `main`.**

## Rama activa

```
┌──────────────────────────────────────────────────────────────┐
│  main                                          [DEFAULT]     │
│  · TRONCO ÚNICO — no hay `staging`                            │
│  · PRODUCCIÓN EN VIVO — app.atlasone.com.mx (VPS IONOS)       │
│  · CI/CD (GitHub Actions) construye y despliega automático    │
│    en cada push, después de pytest + vitest + tsc + build     │
└──────────────────────────────────────────────────────────────┘
```

`staging` (`origin/staging`) queda como rama muerta en el remoto — es ancestro de
`main`, no diverge, y no alimenta ningún destino. No se borra por ahora (referencia
histórica), pero **no trabajes sobre ella**: cualquier PR nuevo va contra `main`.

## Reglas

1. **`main` es producción.** Un push la reconstruye y despliega automáticamente al VPS
   IONOS (`app.atlasone.com.mx`) — ver [`../docs/DEPLOY.md`](DEPLOY.md). No es una rama
   de integración: es producción en vivo.
2. **Los PRs nuevos apuntan a `main`.** Ya no hay una rama de staging intermedia; el
   propio CI (pytest + vitest + tsc + build) es el gate antes de que el job de deploy
   corra.
3. **Cambios a `main` fuera del horario de la tienda** (opera hasta cerca de las
   20:00 hora de México) — el deploy es automático e inmediato, así que un push a
   media tarde reconstruye producción en el momento, no en una ventana elegida.
4. **Force-push prohibido** en `main`.
5. **`Dockerfile`, `.dockerignore` y `.github/workflows/ci.yml` SÍ deben estar en
   `main`** — son parte del pipeline de despliegue, no algo a evitar (a diferencia del
   esquema anterior, donde el `Dockerfile` estaba reservado a `staging` porque Railway
   lo priorizaba sobre Railpack sin que lo pidiera nadie). `nixpacks.toml`/`railway.json`/
   `Procfile` se conservan de reserva, sin uso activo hoy.

## Convenciones de nombres

- `feat/<scope>-<descripcion>` — nueva funcionalidad
- `fix/<scope>-<descripcion>` — corrección
- `chore/<descripcion>` — mantenimiento (docs, dependencias, configuración)
- `security/<scope>` — endurecimiento
- `docs/<scope>` — solo documentación

Todas se integran a `main` vía merge (o PR) cuando están listas — no hay una rama de
integración intermedia que absorba el riesgo antes de producción; el CI es el único
colchón.

## Despliegue

| Rama | Destino | Base | Builder |
|---|---|---|---|
| `main` | VPS IONOS `atlas-prod-01` (`app.atlasone.com.mx`) — **cliente real cobrando** | Postgres 18 en el VPS | `Dockerfile` (multi-stage), CI/CD por GitHub Actions |

Detalle completo del pipeline en [`DEPLOY.md`](DEPLOY.md). Mapa de qué corre en cada
dominio del VPS en [`infra/deployment-map.md`](./infra/deployment-map.md).

## Deuda abierta

- [x] **`SECRET_KEY` en producción** — verificado el 2026-09-22 dentro del contenedor del
      VPS: definida, 64 caracteres, distinta del default público de
      `app/core/security/config.py` (el histórico de Railway nunca la definió).
- [ ] Decidir el destino final de `origin/staging` (borrarla o dejarla como referencia).
- [ ] Decidir el destino final del proyecto de Railway (`rmazh` sigue ahí, fuera de
      alcance de este repo — ver `docs/infra/deployment-map.md`).
