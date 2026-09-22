# CLAUDE.md — Guía para agentes (Atlas BOS / Atlas One)

Lee esto **completo** antes de tocar el repo. Es la fuente de verdad operativa; las
referencias profundas están en [`docs/`](docs/README.md). Si algo aquí contradice al
código, gana el código — corrige este archivo.

---

## 1. Qué es esto (en 30 segundos)

Suite de negocio multi-tenant, modular, API-first para negocios físicos en LatAm.
**Backend** FastAPI + SQLAlchemy + PostgreSQL (`app/`). **Frontend** React + Vite + TS
(SPA/PWA, `frontend/`), servido por el backend en prod. Una sola base de código sirve a
todos los verticales; un **preset de industria** decide qué **módulos** se activan por
organización (POS, inventario, CRM, citas, restaurante…).

Orientación rápida: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) · [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) ·
[`docs/RBAC.md`](docs/RBAC.md) · [`docs/FRONTEND_VIEWS.md`](docs/FRONTEND_VIEWS.md).

---

## 2. Reglas de oro (NO negociables)

1. **`main` = producción con clientes vivos. NUNCA hagas push a `main` sin permiso explícito del usuario.** Es tronco único (no hay `staging`, se fusionó a `main` el 2026-09-22): trabaja en `feat/*`/`fix/*` y fusiona a `main` solo con permiso. Pushear `main` despliega automáticamente a producción (VPS IONOS, `app.atlasone.com.mx`) vía CI/CD — ver [`docs/DEPLOY.md`](docs/DEPLOY.md). Railway **ya no es producción**.
2. **Commit/push solo cuando el usuario lo pida.** Si estás en `main`, crea rama antes — un push directo a `main` dispara el deploy real.
3. **Migraciones de esquema van en `scripts/railway_init.py`** (ALTERs idempotentes + `create_all`). Corre en cada deploy. NO uses Alembic (versions/ está vacío, de reserva). Tablas nuevas se crean solas al registrar el modelo en `app/models/__init__.py`.
4. **FKs a IDs UUID deben ser `String(36)`, nunca Integer.** `product_variants.id`, `sales_documents.id`, `parked_tickets.id`, `departments.id` son UUID. SQLite no valida el mismatch; Postgres crashea en `create_all`. (Dos convenciones de PK conviven — ver [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md).)
5. **Toda query de negocio filtra `organization_id`** (multi-tenancy). Usa `get_tenant_scoped`/`scoped_query` de `app/core/tenant_query.py`.
6. **Comunicación entre módulos = eventos, no llamadas directas.** Publica con `EventBus.enqueue(db, Event)` **dentro de la misma transacción**; los subscribers deben ser **idempotentes**. Ver [`docs/ARCHITECTURE.md §3`](docs/ARCHITECTURE.md).
7. **`with_for_update()` es no-op en SQLite y real en Postgres.** Los tests corren en SQLite; la concurrencia real solo se ejercita en prod. No asumas que un test "prueba" el lock.
8. **`app/routers/sales.py::create_sale` es el motor ATS-crítico** (checkout). Cámbialo con extremo cuidado y tests; un error cobra o descuadra inventario de clientes reales.

---

## 3. Comandos (verificados)

Requiere **Python 3.11** y **Node 20**. El venv local es `.venv/`.

```bash
# --- Backend ---
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # necesita: apt install libcairo2-dev pkg-config libpq-dev
                                          # (xhtml2pdf → pycairo compila contra cairo del sistema)
python scripts/railway_init.py           # crea/migra DB (idempotente) + seeds de presets/módulos
uvicorn app.main:app --reload            # API en :8000 · Swagger en /docs

# --- Frontend ---
cd frontend && npm ci
npm run dev                               # Vite en :5173
npm run build                             # tsc && vite build  (esto corre el CI — debe pasar tsc)

# --- Tests (SQLite en memoria, ~30-50s) ---
.venv/bin/python -m pytest -q --ignore=tests/test_cash_complete.py
.venv/bin/python -m pytest -q tests/test_gastro_phase2.py            # un archivo
.venv/bin/python -m pytest -q -p no:warnings tests/test_outbox.py    # silenciar warnings

# --- Docker (stack local: backend + postgres:17 + pgAdmin) ---
docker compose up -d                      # DATABASE_URL=postgresql://postgres:toor@db:5432/railway
```

**CI/CD** (`.github/workflows/ci.yml`): Python 3.11, Node 20 — `pytest` + `vitest` + `tsc` + `vite build`. Corre en push y en PR a `main`. **En push a `main`, si todo pasa, un job adicional (`deploy-ionos`) despliega automáticamente a producción** (VPS IONOS, `app.atlasone.com.mx`) por SSH: construye la imagen (`Dockerfile` de la raíz), la levanta con `docker compose`, y verifica el commit desplegado + `/health`. Detalle completo en [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## 4. Mapa del repo (dónde vive qué)

```
app/
  main.py            # monta routers; startup = registra subscribers + arranca outbox worker + seeds
  core/
    database.py      # engine, Base, SessionLocal (DATABASE_URL o sqlite fallback)
    security/        # JWT, get_current_user, hashing (auth.py, jwt.py, config.py, guards.py)
    permissions.py   # require_module(key) — gating por módulo
    tenant_query.py  # get_tenant_scoped, scoped_query, _resolve_org_id (aislamiento por org)
    tenant_context.py# get_current_active_organization (resuelve org activa)
    events.py        # EventBus, EVENT_REGISTRY, SalesDocumentCreated
    outbox.py        # dispatcher + worker del outbox transaccional
  routers/           # routers CORE (sales, cash, inventory, reports, hr, quotes, returns, printer…)
    platform/        # 16 sub-routers SUPERADMIN (organizations, users, flags, incidents, stats…)
  modules/           # arquitectura modular (destino canónico): auth, users, tenants, products,
                     #   customers, appointments, tables, kitchen, recipes, bar, + stubs
  models/            # 73 tablas; varios archivos son shims que re-exportan desde modules/
  schemas/           # Pydantic
  services/          # capabilities_service (presets), feature_flags, cash_reconciliation, audit
  subscribers/       # recipes.py, tables.py, abasto.py (handlers de SalesDocumentCreated)
scripts/
  railway_init.py    # migraciones idempotentes + seeds — corre en cada deploy
  init_presets_v2.py # seed del catálogo de módulos y presets por industria
frontend/src/pages/  # 76 vistas (ver docs/FRONTEND_VIEWS.md)
docs/                # documentación de referencia — empieza por docs/README.md
tests/               # pytest (SQLite en memoria); conftest.py = fixtures + seed data
```

> **Migración Phase 2 en curso:** `app/modules/<x>/` es canónico; muchos `app/routers/<x>.py` y `app/models/<x>.py` son *reverse-shims*. Al editar, ubica el cuerpo real en `modules/`.

---

## 5. Recetas de tareas comunes

### Añadir un endpoint a un módulo existente
1. Handler en `app/modules/<x>/router.py` (o `app/routers/<x>.py`). Usa `Depends(get_current_user)` + `get_current_active_organization`. Filtra por org.
2. Schema request/response en `app/modules/<x>/schemas.py` (Pydantic v2, `from_attributes=True` para read).
3. Lógica de negocio en `services.py` (no en el router).
4. Test en `tests/test_<x>*.py` usando fixtures de `conftest.py` (`client`, `auth_admin`, `db`, `org`, `branch_a`).

### Añadir una tabla / modelo
1. Modelo en `app/models/<dominio>.py` o `app/modules/<x>/models.py`. Usa mixins (`TenantMixin` para org scoping). **FKs a UUID = `String(36)`.**
2. Regístralo: si es de módulo, ya lo cubre `from app.modules.<x> import models` en `app/models/__init__.py`; si no, añade el import.
3. `create_all` la crea sola. Para columnas NUEVAS en tablas EXISTENTES en prod, añade un ALTER idempotente en `scripts/railway_init.py`.
4. Enums Postgres nuevos: prefiere una columna `String` con constantes Python (evita migración de enum). Si necesitas enum DB, usa `ALTER TYPE … ADD VALUE IF NOT EXISTS` en AUTOCOMMIT en railway_init.

### Publicar/consumir un evento
- Define el evento en `app/core/events.py` con `@register_event`.
- Publica: `EventBus.enqueue(db, MiEvento(...))` **antes del commit** de la transacción de negocio.
- Consume: handler en `app/subscribers/<x>.py`, regístralo en el startup de `app/main.py`. **Hazlo idempotente** (guard por referencia única).

### Habilitar un módulo en un preset
Edita `scripts/init_presets_v2.py` (seed de `industry_presets`) y/o el fallback en `app/services/capabilities_service.py`. El módulo debe existir en el catálogo `modules` (`seed_global_modules`).

---

## 6. Gotchas que te van a morder

- **`tests/test_cash_complete.py` hace `sys.exit(1)` al importar** (es un script de integración que espera un server vivo). Rompe la colección de pytest. **Siempre** corre con `--ignore=tests/test_cash_complete.py`.
- **Baseline de tests rojos preexistente:** la suite tiene ~35 fallos + 4 errores NO relacionados con tu cambio (`test_seed_presets`, `test_tenant_query_helpers`, `test_upsell_recommendations`, algunos `test_product_creation`/`appointments`). Para saber si TÚ rompiste algo: `git stash` tus cambios, corre, compara el conteo. Un cambio limpio no aumenta `failed`.
- **Columnas raw fuera del ORM:** `parked_tickets.status`/`converted_to_sale_id`, `sales_documents.global_discount_pct`, `branches.printer_cols` existen en la DB (railway_init) pero NO en los modelos. Se leen con `setattr`/SQL crudo. No asumas que un `setattr` persiste si la columna no está mapeada. (`printer_cols` además tiene **cero lectores** en todo `app/` — no la uses como precedente, es candidata a `DROP COLUMN`.)
- **Locks no-op en SQLite:** para probar concurrencia real necesitas Postgres. Para dead-letter/outbox worker, el worker está **gateado off en SQLite** — en dev local los subscribers gastro no se disparan solos.
- **Doble convención de PK** (Integer vs UUID String(36)) — ver regla de oro #4.
- **RBAC dual y débil:** solo 3 routers usan `require_module`; ADMIN/DUEÑO hacen bypass; branch scoping NO está enforced a nivel framework. **No confíes en el RBAC como candado de seguridad** — ver los 12 huecos en [`docs/RBAC.md §5`](docs/RBAC.md).
- **`quotes convert-to-sale` NO emite el evento outbox** (a diferencia de `create_sale`): no descuenta insumos ni libera mesa.
- **Tres mecanismos de migración, no uno.** La regla de oro #3 solo documenta `scripts/railway_init.py` (automático, corre en cada deploy — hoy vía el `CMD` del `Dockerfile` de producción; `Procfile`/`railway.json` quedan de reserva). Pero también existen `scripts/migrate.py` + 25 `scripts/migrate_*.py` (con tabla `schema_migrations`) que **NO corren solos** — ahí viven índices únicos que protegen dinero real (`uq_sales_org_client_uuid` contra el cobro doble, `uq_sale_return_pending_per_sale` contra la devolución duplicada) y hay que correrlos a mano en cada entorno (VPS, bases restauradas). `alembic/` es el tercero: reserva vacía, no lo uses (regla de oro #3 sigue vigente para código nuevo). Ver `.superpowers/sdd/db-audit/schema-findings.md §7.1` (auditoría 2026-09-19, no versionada — gitignored). **Excepción 2026-09-22:** `scripts/migrate_add_payment_cash_session.py` (columna `payments.cash_session_id` + backfill) y `scripts/migrate_add_cash_movement_author.py` (`cash_movements.created_by_user_id`) ya **no hace falta correrlos a mano** — ambas columnas se sumaron a `railway_init.py` y corren solas en cada deploy; esos scripts quedan solo como vía "en caliente, sin reiniciar" opcional. Los dos índices únicos de dinero de arriba siguen siendo la única migración verdaderamente manual.
- **`tests/conftest.py` usa `sqlite:///file::memory:?cache=shared` sin `uri=True`.** Sin ese flag SQLAlchemy no lo interpreta como URI de SQLite: `file::memory:?cache=shared` se toma como nombre de archivo literal, así que la "DB en memoria" es en realidad un archivo real en el directorio de trabajo. Dos procesos de `pytest` corriendo en paralelo **en el mismo worktree** (dos agentes, o un worktree + su checkout original) se pisan esa base. Corre la suite de a uno por worktree, o en worktrees distintos.

---

## 7. Convenciones

- **Estilo:** sigue el código circundante (nombres, densidad de comentarios, idioma — comentarios suelen ser español). Pydantic v2. Type hints en firmas nuevas.
- **Commits:** mensajes claros, scope tipo `feat(bar):`, `fix(gastro):`, `docs:`. Termina con las líneas `Co-Authored-By` / `Claude-Session` que exige el harness.
- **Errores:** usa `HTTPException` con `detail` accionable; para mutaciones críticas, transacción atómica con rollback.
- **No dejes `print()` de debug** (hay algunos preexistentes en `sales.py`/`quotes.py` — no los imites).

---

## 8. Zonas peligrosas (cuidado extra)

- `app/routers/sales.py::create_sale` — motor de checkout (cobros reales).
- `app/routers/platform/organizations.py` delete `?force=true` — cascade manual sobre ~30 tablas; frágil ante tablas nuevas con FK a org.
- `scripts/railway_init.py` — corre en cada deploy contra prod al mergear a main (hoy vía CI/CD al VPS IONOS, no Railway — el nombre del archivo es historia). Cambios deben ser idempotentes y probados.
- Cualquier cambio a `app/core/{security,tenant_query,tenant_context,events,outbox}.py` — infraestructura transversal.
- `.github/workflows/ci.yml` job `deploy-ionos` y `Dockerfile`/`.dockerignore` de la raíz — un push a `main` los ejecuta contra producción real sin ventana de confirmación manual.

---

## 9. Dónde ir más profundo

| Necesito… | Doc |
|---|---|
| Ubicarme rápido: glosario, conceptos, índice concepto→código | [`docs/ONTOLOGY.md`](docs/ONTOLOGY.md) |
| Entender la arquitectura, eventos/outbox, tenancy | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Un endpoint concreto y su gating | [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) |
| Una tabla, columnas, enums, gotchas de esquema | [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) |
| Roles, permisos, auth, huecos de seguridad | [`docs/RBAC.md`](docs/RBAC.md) |
| Una vista del frontend (ruta→archivo→API) | [`docs/FRONTEND_VIEWS.md`](docs/FRONTEND_VIEWS.md) |
| Crear/mover un módulo (proceso completo) | [`docs/modules/MODULE_GUIDE.md`](docs/modules/MODULE_GUIDE.md) |
| Deploy y ramas | [`docs/DEPLOY.md`](docs/DEPLOY.md) · [`docs/branching-strategy.md`](docs/branching-strategy.md) · [`RAILWAY_DEPLOY.md`](RAILWAY_DEPLOY.md) (histórico, ya no describe producción) |
| Auditoría funcional del día (qué se corrigió, qué queda abierto) | [`docs/AUDITORIA-2026-09-22.md`](docs/AUDITORIA-2026-09-22.md) |

Índice completo: [`docs/README.md`](docs/README.md).
