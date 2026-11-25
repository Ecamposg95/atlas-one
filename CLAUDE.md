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
organización (POS, inventario, CRM, citas, restaurante…). Un **plan comercial** (`organization.plan`: FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS; catálogo en `app/services/plans.py`) pone topes de usuarios activos y sucursales que venden y gobierna los módulos de crecimiento; nunca apaga lo ya encendido.

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

Requiere **Python 3.11+** y **Node 20**. Si existe `.venv/` úsalo; si no, cualquier Python 3.11+ con `requirements.txt` instalado corre la suite (en esta máquina es el `python3` del sistema).

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

**CI/CD** (`.github/workflows/ci.yml`): Python 3.11, Node 20 — `pytest` + `vitest` + `tsc` + `vite build` (+ presupuesto de la ruta crítica: `frontend/presupuesto_bundle.json`, ver `docs/DEPLOY.md`). Corre en push y en PR a `main`. **En push a `main`, si todo pasa, un job adicional (`deploy-ionos`) despliega automáticamente a producción** (VPS IONOS, `app.atlasone.com.mx`) por SSH: construye la imagen (`Dockerfile` de la raíz), la levanta con `docker compose`, y verifica el commit desplegado + `/health`. Detalle completo en [`docs/DEPLOY.md`](docs/DEPLOY.md).

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
                     #   customers, appointments, tables, kitchen, recipes, bar, conteos
                     #   (conteo físico con escáner), + stubs
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

### Cambiar el plan de una organización
- Desde `/platform/organizations/{id}` (selector "Plan y uso") o `PUT /api/platform/organizations/{id}` con `{"plan": "PRO"}`. Claves válidas en `app/services/plans.py::claves_validas()`.
- Cambiar de plan NO toca `organization_modules`: los módulos encendidos se heredan y la pantalla los marca "Fuera de plan". Los topes (usuarios activos, sucursales que venden) solo frenan altas nuevas con un 403 cuyo `detail` nombra el plan mínimo.
- `plans.asignar_plan(org, clave)` es el único que escribe `organization.plan`. Si la organización tiene suscripción (`app/modules/suscripciones/`, cobro de la mensualidad: `/platform/suscripciones` y la sección «Suscripción» de la ficha), el plan se mueve junto en los dos sentidos; el precio pactado no cambia solo. Ese módulo es de registro manual y su estado `suspendida` no bloquea nada.
- Módulos permitidos = base ∪ preset del giro ∪ crecimiento del plan. Para añadir un módulo a un plan, edita `_START/_PRO/_BUSINESS/_SCALE` en `plans.py` y corre `tests/test_planes.py`.

### Dar de alta una tienda (cualquier origen)
Playbook completo con reglas, trampas y qué preguntar: [`docs/playbooks/altas-de-clientes.md`](docs/playbooks/altas-de-clientes.md).

### Dar de alta una tienda que llega de rmazh (Data X POS)
1. Exportar desde rmazh en **solo lectura** con `scripts/adhoc/2026-09-01/coqueta/export_coq2.py` (repo Atlas-Rmazh, por `railway ssh`; pasar la sucursal con existencias, no el HQ). Guarda el xlsx y el JSON de usuarios **fuera del repo** (trae hashes).
2. `scripts/onboard_org.py` crea org + matriz (`can_sell=True`) + admin. Luego fija `branches.printer_name` y, si la tienda ya emitía folios, `branches.folio_inicial` (siguiente al último de rmazh).
3. `scripts/import_rmazh_users.py usuarios.json --org N --branch M --dry-run` → real. Copia los hashes bcrypt: la gente entra con su contraseña de siempre.
4. `scripts/import_rmazh_export.py catalogo.xlsx --org N --branch M --dry-run` → revisar incidencias y "EXISTENCIAS MAYORES A 500" → real. Idempotente; `--tope N` recorta relleno.
5. Verificar el POS **con el cajero**, no con el admin (`GET /api/products/pos/search`).

**Con historial completo** (ventas, cortes, movimientos; Novedades America 2026-11-03): `scripts/export_rmazh_org.py` por stdin en el contenedor de rmazh (`railway ssh -s Atlas-API -- 'cd /app && /opt/venv/bin/python - <org>' < script > salida.txt`, trae hashes → fuera del repo) y `scripts/import_rmazh_org.py salida.txt --nombre … --plan … --giro … [--sucursales 12,13]` dentro de `atlas-one-prod` (`docker cp` + `PYTHONPATH=/app`; ensayo por omisión, `--ejecutar` confirma). Renumera ids enteros, conserva UUIDs y verifica antes de confirmar. Apaga a los usuarios en rmazh **antes** de exportar (y reactívalos en Atlas ONE: llegan inactivos). Si alguien vuelve a vender en rmazh, `scripts/fusionar_rmazh_ventas.py nueva.txt --org N --desde <hora de la exportación del corte>` agrega solo lo que falta (idempotente).

### Hacer responsiva una pantalla de admin
1. `const esTelefono = useEsTelefono()` (`hooks/useIsMobile.ts`, < 768).
2. Cabecera → `CabeceraPagina`, filtros → `BarraFiltros` (`components/ui/`).
3. La `<table>` no se toca: `esTelefono ? <ListaTarjetas><TarjetaFila…/></ListaTarjetas> : <table…>`, nunca `hidden md:block`.
4. Rejillas: `grid-cols-N` siempre con prefijo (`grid-cols-1 sm:grid-cols-2`).
5. Modales: `ui/Modal`, o `dax-modal` + `dax-modal-footer` si tienen cabecera propia; nunca un `fixed inset-0` nuevo (lo frena `overlaysFueraDelKit.test.ts`). Botones: clases `dax-btn-primary/-secondary/-danger/-ghost`; solo-icono con `dax-btn-icon` (lo vigila `botonesDelKit.test.ts`).
6. Verificar con capturas a 390/768/1024 y diff pixel a pixel a 1440 contra un baseline tomado antes de tocar código; la herramienta (Playwright, `capturas.mjs` + `diff1440.mjs`) se reconstruye según la Tarea 0 de `docs/superpowers/plans/2026-10-18-sp5-responsivo-admin-ola-2.md`.

### Esconder algo en modo básico
- El perfil (`basico` | `completo`) sale de `app/services/perfil_ui.py::perfil_efectivo` (solo `FREE` explícito → básico; plan NULL/vacío/desconocido o de paga → completo; la plataforma lo fuerza con `organization.perfil_ui`) y viaja en `/me/context.perfil_ui`. En pantalla: `useModoBasico()`.
- Menú: `OCULTAS_BASICO_SUCURSAL` / `OCULTAS_BASICO_HQ` en `components/layout/navPerfilBasico.ts`. POS: banderas de `opcionesPorPerfil` (`pages/pos/opcionesPos.ts`). Campos del producto: `OCULTOS_BASICO` en `app/modules/products/campos.py`. Pantalla entera: `<PorPerfil basico completo>` donde una ruta deba cambiar de componente por perfil; hoy ninguna ruta de `App.tsx` lo usa (Inicio y Reportes son una sola pantalla que se adapta). Una sección: `<MasOpciones activo={modoBasico}>`.
- Siempre render condicional (nunca `hidden`), sin tocar el backend, y lo que ya trae un dato se sigue viendo. Detalle: `docs/modo-basico.md`.

### Destapar un módulo cuando se termina
Lo que se vende y no está construido se oculta (decisión 2026-11-24). El estado de cada módulo (`disponible` | `en_construccion` | `oculto`) vive en `app/services/estado_modulos.py`; evidencia y pendientes en `docs/presets/ESTADO-DE-MODULOS.md`.
1. Con backend real **y** pantalla real: en `ESTADO_MODULOS` pasa la clave a `DISPONIBLE` (una línea `"clave": ESTADO,` por módulo: vitest lee ese formato) y bórrala de `NO_DISPONIBLES` en `frontend/src/utils/estadoModulos.ts`.
2. En `frontend/src/App.tsx` cambia su `<Navigate to="/" replace />` por la pantalla (`<RutaPorRol url="/x"><Suspense…>`). El ítem ya está en `ALL_NAV`, `HQ_NAV_GROUPS` y `ROLE_ROUTES`; si el módulo es nuevo, añádelo ahí con su `module`.
3. Los widgets de `pages/home/PresetHome.tsx` con ese `module` reaparecen solos; quítales `beta` si ya no aplica.
4. Corre `tests/test_estado_modulos.py` y `frontend/src/__tests__/estadoModulos.test.ts`, y actualiza el renglón en `docs/presets/ESTADO-DE-MODULOS.md` y `docs/FRONTEND_VIEWS.md`.
- Un módulo nuevo entra al catálogo como `OCULTO` (la prueba exige declararlo). Ocultar es solo interfaz: no apaga `organization_modules` ni cambia `require_module`; la plataforma lo ve marcado y lo puede encender.

### Retirar una URL del admin (fusionar dos pantallas)
1. La pantalla que sobrevive absorbe lo que la otra hacía de más, gateado por rol (`esRolHq` de `frontend/src/utils/rolesHq.ts`) y, si aplica, por "más de una sucursal que vende" (`hooks/useSucursalesVendibles.ts`). `branch_id` solo viaja cuando un rol de oficina elige sucursal: el backend impone la sucursal a la cajera; al gerente según cada endpoint (`/sales/` y `/sales/stats` lo confinan, `/returns/` no: `HQ_ROLES` de `metricas_ventas.py` lo incluye). Revisa el router antes de decidir qué columnas enseñarle.
2. `git rm` la pantalla vieja y su `lazy()` en `App.tsx`; la ruta vieja pasa a `<RedirigirConQuery a="/nueva" />` (`components/layout/RedirigirConQuery.tsx`: conserva `?…` y `#…`). `app/main.py` no necesita redirect: la SPA sirve la ruta.
3. Quita la URL de `ALL_NAV`, `HQ_NAV_GROUPS`, `ROLE_ROUTES` y `OCULTAS_BASICO_HQ`; actualiza enlaces (`git grep -n '/ruta/vieja' -- frontend/src docs`).
4. Guardias: `__tests__/fusionesAdmin.test.ts` (añade la URL a `FUSIONADAS` y el archivo a `BORRADOS`), `coloresPorTokens` (saca el borrado de `PENDIENTES`; el reescrito va a `LIMPIOS`), `overlaysFueraDelKit` (`CONOCIDOS`), `pages/__tests__/responsivoOla2.test.ts` (`PAGINAS`), y `docs/FRONTEND_VIEWS.md`. Ejemplo completo: `docs/superpowers/plans/2026-10-25-admin-fase3-fusiones-menu.md`.

---

## 6. Gotchas que te van a morder

- **`tests/test_cash_complete.py` hace `sys.exit(1)` al importar** (es un script de integración que espera un server vivo). Rompe la colección de pytest. **Siempre** corre con `--ignore=tests/test_cash_complete.py`.
- **Baseline de tests rojos preexistente:** la suite tiene ~35 fallos + 4 errores NO relacionados con tu cambio (`test_seed_presets`, `test_tenant_query_helpers`, `test_upsell_recommendations`, algunos `test_product_creation`/`appointments`). Para saber si TÚ rompiste algo: `git stash` tus cambios, corre, compara el conteo. Un cambio limpio no aumenta `failed`.
- **Columnas raw fuera del ORM:** `parked_tickets.status`/`converted_to_sale_id`, `sales_documents.global_discount_pct`, `branches.printer_cols` existen en la DB (railway_init) pero NO en los modelos. Se leen con `setattr`/SQL crudo. No asumas que un `setattr` persiste si la columna no está mapeada. (`printer_cols` además tiene **cero lectores** en todo `app/` — no la uses como precedente, es candidata a `DROP COLUMN`.)
- **Locks no-op en SQLite:** para probar concurrencia real necesitas Postgres. Los candados del dinero (existencias y documento en `create_sale`/`cancel_sale`/`convert-to-sale`/`approve_return`, saldo del cliente en abonos) se prueban con `scripts/prueba_concurrencia_ventas.py` contra un Postgres desechable (instrucciones en su docstring); `tests/test_candados_dinero.py` y `tests/test_candados_saldo_cliente.py` solo vigilan que nadie los quite. Orden global de candados: (devolución →) documento de venta → existencias (por id) → cliente (`customers/services.py::cliente_con_candado`); respétalo o habrá interbloqueos. Una fila que la sesión ya cargó NO se refresca al releerla con `with_for_update()`: usa `populate_existing()` si pudo haberse leído antes sin candado. Para dead-letter/outbox worker, el worker está **gateado off en SQLite** — en dev local los subscribers gastro no se disparan solos.
- **Doble convención de PK** (Integer vs UUID String(36)) — ver regla de oro #4.
- **RBAC dual y débil:** solo 3 routers usan `require_module`; ADMIN/DUEÑO hacen bypass; branch scoping NO está enforced a nivel framework. **No confíes en el RBAC como candado de seguridad** — ver los 12 huecos en [`docs/RBAC.md §5`](docs/RBAC.md).
- **`quotes convert-to-sale` SÍ emite `SalesDocumentCreated`** (desde 2026-11-24, igual que `create_sale`: `EventBus.enqueue` dentro de la misma transacción + `drain_now` tras el commit), así que descuenta insumos de receta y revisa reabasto. Dos matices: el subscriber de recetas descuenta en `quote.branch_id` (la sucursal donde se cotizó), aunque el stock del producto se descuente en la sucursal de quien cobra; y el subscriber de mesas no hace nada aquí (una cotización no nace de un ticket pausado).
- **Tres mecanismos de migración, no uno.** La regla de oro #3 solo documenta `scripts/railway_init.py` (automático, corre en cada deploy — hoy vía el `CMD` del `Dockerfile` de producción; `Procfile`/`railway.json` quedan de reserva). Pero también existen `scripts/migrate.py` + 25 `scripts/migrate_*.py` (con tabla `schema_migrations`) que **NO corren solos** — hay que correrlos a mano en cada entorno (VPS, bases restauradas). `alembic/` es el tercero: reserva vacía, no lo uses (regla de oro #3 sigue vigente para código nuevo). Ver `.superpowers/sdd/db-audit/schema-findings.md §7.1` (auditoría 2026-09-19, no versionada — gitignored). **Excepción 2026-09-22:** `scripts/migrate_add_payment_cash_session.py` (columna `payments.cash_session_id` + backfill) y `scripts/migrate_add_cash_movement_author.py` (`cash_movements.created_by_user_id`) ya **no hace falta correrlos a mano** — ambas columnas se sumaron a `railway_init.py` y corren solas en cada deploy; esos scripts quedan solo como vía "en caliente, sin reiniciar" opcional. **Excepción 2026-11-24:** los dos índices únicos que protegen dinero real (`uq_sales_org_client_uuid` contra el cobro doble, `uq_sale_return_pending_per_sale` contra la devolución duplicada) y la columna `sales_documents.client_uuid` también corren ya solos: `railway_init.py::asegurar_indices_unicos_de_dinero`. Si la base trae duplicados preexistentes el índice NO se crea, el arranque sigue y queda un aviso `RAILWAY_INIT: … NO se creo` en el log (búscalo tras restaurar una base); el siguiente deploy lo reintenta. Los scripts `migrate_add_sales_client_uuid.py` / `migrate_add_unique_pending_return.py` quedan como vía opcional "en caliente".
- **`tests/conftest.py` usa `sqlite:///file::memory:?cache=shared` sin `uri=True`.** Sin ese flag SQLAlchemy no lo interpreta como URI de SQLite: `file::memory:?cache=shared` se toma como nombre de archivo literal, así que la "DB en memoria" es en realidad un archivo real en el directorio de trabajo. Dos procesos de `pytest` corriendo en paralelo **en el mismo worktree** (dos agentes, o un worktree + su checkout original) se pisan esa base. Corre la suite de a uno por worktree, o en worktrees distintos.
- **El `src/` del servidor no es un checkout limpio.** El deploy extrae un `tar` encima de `/srv/apps/atlas-one-prod/src`; hasta bc475e8 (2026-10-22) nada borraba lo que el repo había eliminado, y un `.tsx` huérfano tiró el build de la imagen (tsc compila todo `frontend/src`, importado o no) aunque el CI con checkout limpio había pasado. Hoy el job vacía `frontend/src`, `frontend/public`, `scripts` y `app/` menos `app/static` antes de extraer; el deploy manual de `docs/infra/ionos-vps.md` debe hacer lo mismo. Si un deploy falla en "Deploy a IONOS" con un archivo que ya no existe en `main`, es esto. Si `backend-tests` cae por una prueba que pasa en local, `gh run rerun <id> --failed` relanza el job y el deploy que dependía de él; no hace falta otro push.
- **Una sola regla de venta en reportes.** `app/services/metricas_ventas.py` define qué cuenta como venta (cobradas o fiadas a cliente —solo tickets INVOICE; cotizaciones y pedidos PENDING no cuentan— − devoluciones aprobadas, día de México; `filtro_venta_reconocida` de `cash_reconciliation.py`) y el ámbito por rol. Un reporte nuevo lo consume; no escribas otro `status.in_(...)` a mano.
- **Ventas de la cajera: una sola regla.** Vive en `app/services/ventas_cajero.py` (`es_cajero`, `rango_hoy_mx`, `venta_visible_para_cajero`); cualquier endpoint nuevo que exponga ventas a la cajera (o al vendedor) debe usarla: su sucursal y dentro del plazo de la tienda (`organization.dias_ventas_caja`, 30 por omisión, 0 = solo hoy), nunca totales. Las devoluciones de la caja siguen el mismo plazo; reglas del mostrador (motivos, método de reembolso, monto libre `organization.devolucion_libre_hasta`, PIN del gerente) en `app/services/devoluciones.py`.
- **Colores por tokens en el admin.** `frontend/src/__tests__/coloresPorTokens.test.ts` prohíbe `text-white`, `text-slate-*`, `bg-slate-*`, `border-slate-*` y hex sueltos en `pages/hq|home|finance|sales|inventory|core|reports` y `components/reports|graficas`, salvo la lista `PENDIENTES` (deuda que cada fase vacía: al limpiar un archivo, bórralo de la lista). Pinta con `text-dax-*`/`bg-dax-*`/`border-dax-*` (`tailwind.config.js`) y, para chart.js, con `useTemaGrafica()` de `components/graficas`. El bloque `html.light … !important` de `index.css` no admite reglas nuevas (tope en esa prueba). El tema oscuro es full black (tokens de `index.css`); lo guarda `frontend/src/__tests__/temaFullBlack.test.ts`.

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
