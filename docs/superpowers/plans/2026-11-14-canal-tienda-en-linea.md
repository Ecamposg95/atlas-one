# Canal «Tienda en línea» — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una web externa (primero `eleven.boutique`) lea por API el catálogo publicado de una organización, con disponibilidad sí/no y sin precios, y le devuelva métricas y prospectos.

**Architecture:** Llaves `api_key` existentes conectadas por una dependencia propia del canal (nunca a rutas de usuario). Campos aditivos en catálogo + módulo `tienda_en_linea` por org. Disponibilidad materializada en `channel_availability`, mantenida por un listener `before_flush` sobre `StockOnHand` (sin tocar `create_sale`) y un recálculo de respaldo. Router de solo lectura `/api/channel/v1` con schemas cerrados y paginación por cursor.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic v2, pytest (SQLite), React + Vite + TS, vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-canal-tienda-en-linea-design.md`

## Global Constraints

- Rama `feat/canal-tienda-en-linea` (worktree `.worktrees/canal-tienda`); nada a `main` sin permiso explícito. PRs: **PR1 = T1**, **PR2 = T2–T5**, **PR3 = T6**, **PR4 = T7**, **PR5 (fase 2) = T8**.
- Esquema solo aditivo e idempotente en `scripts/railway_init.py` (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`); FKs a UUID = `String(36)`.
- Defaults que no cambian nada: `web_published=false`, `is_premium=false`, `parent_id=NULL`; módulo `tienda_en_linea` fuera de todo preset y plan.
- Toda consulta filtra `organization_id`; en el canal el org sale **solo** de la llave.
- El canal nunca devuelve claves que contengan `price|cost|tax|iva|supplier|proveedor|qty|stock|barcode`.
- Scopes válidos exactos: `catalog:read`, `leads:write`. Rate limit: 120 req/min por llave → 429 + `Retry-After`.
- Paginación del canal: `limit` 1..200, default 100; respuesta `{items, next_cursor, server_time}`.
- UI: render condicional (nunca `hidden`), colores `dax-*`, modales con `ui/Modal`, botones `dax-btn-*` (ver CLAUDE.md §5 y §6).
- Suite: `python3 -m pytest -q --ignore=tests/test_cash_complete.py` (una corrida por worktree); front: `cd frontend && npx vitest run && npm run build`.
- Commits `feat(canal): …` / `feat(productos): …` en español, con las líneas `Co-Authored-By`/`Claude-Session` del harness.

## Review Focus

1. **Venta en org sin el módulo** — el listener de disponibilidad no debe emitir ni una consulta extra en `create_sale` (T5 lo mide con un contador de statements).
2. **Muchos productos con el mismo `updated_at`** (publicación en bloque los iguala al milisegundo) — el cursor `(updated_at, id)` no debe saltar ni repetir items entre páginas (T6).
3. **Variante cuya existencia está en varias sucursales y solo algunas cuentan** — vender en una sucursal no-web no cambia nada; vender la última pieza en la única sucursal web sí (T5).
4. **JWT de usuario contra el canal y llave `atlas_…` contra `/api/products`** — ambos 401, nunca cruce (T1).
5. **Producto despublicado, luego borrado, luego republicado** — la web recibe `deleted:true` y luego el producto completo otra vez, sin quedar huérfano (T6).

---

### Task 1: Llaves de canal conectadas al auth (PR1)

**Files:**
- Create: `app/core/security/channel_keys.py`
- Modify: `app/routers/platform/api_keys.py` (POST valida scopes), `frontend/src/pages/platform/PlatformApiKeys.tsx` (casillas de scope)
- Test: `tests/test_channel_keys.py`

**Interfaces:**
- Produces: `CHANNEL_SCOPES = ("catalog:read", "leads:write")`; `@dataclass(frozen=True) ChannelContext(organization_id: int, key_id: int, scopes: frozenset[str])`; `require_channel_key(scope: str) -> Callable[..., ChannelContext]` (dependencia FastAPI); `MODULO_CANAL = "tienda_en_linea"`; `canal_activo(db, org_id: int) -> bool` (consulta `organization_modules`, cache en memoria 60 s, `invalidar_cache_canal(org_id)`).

- [ ] **Step 1: Pruebas que fallan** en `tests/test_channel_keys.py` usando una ruta de prueba montada en el test (`app.get("/_t/canal")` con `Depends(require_channel_key("catalog:read"))` que devuelve `ctx.organization_id`). Helper `_emitir(db, org, scopes)` que usa `generate_api_key()` y crea `ApiKey(scopes=json.dumps(scopes))`; helper que enciende `tienda_en_linea` como `catalog_module_enabled` de `conftest.py`.
  - `test_llave_valida` → 200 y `org.id`; también con header `X-Api-Key`.
  - `test_sin_llave` → 401; `test_llave_revocada` → 401; `test_llave_desconocida` → 401.
  - `test_sin_scope` (llave solo `leads:write`) → 403.
  - `test_jwt_de_usuario_en_canal` (`auth_admin` header) → 401.
  - `test_llave_en_ruta_de_usuario` (`GET /api/products/` con la llave) → 401.
  - `test_modulo_apagado` → 404.
  - `test_rate_limit`: 120 llamadas 200, la 121 → 429 con header `Retry-After`; otra llave no se ve afectada.
  - `test_last_used_una_vez_por_minuto`: dos llamadas seguidas → un solo cambio de `last_used_at` (congela el reloj con monkeypatch de `_ahora`).
  - `test_crear_llave_scope_invalido` (`POST /api/platform/api-keys` como `auth_superadmin`, `scopes=["todo"]`) → 422.
- [ ] **Step 2:** `python3 -m pytest -q tests/test_channel_keys.py` → FAIL (módulo no existe).
- [ ] **Step 3: Implementar** `channel_keys.py`. Bearer sin prefijo `atlas_` → 401. No usar `verify_api_key` tal cual (hace commit en cada request): consulta la fila por hash y actualiza `last_used_at` solo si pasaron ≥60 s. Rate limit: `dict[int, collections.deque[float]]` + `threading.Lock`, ventana 60 s. Validación de scopes en el POST de plataforma contra `CHANNEL_SCOPES`.
- [ ] **Step 4:** pruebas del archivo → PASS; suite completa sin fallos nuevos.
- [ ] **Step 5: Commit** `feat(canal): llaves de servidor con scopes, rate limit y módulo tienda_en_linea`.

### Task 2: Módulo y esquema del catálogo web (PR2)

**Files:**
- Create: `app/modules/products/imagenes.py` (modelo `ProductImage` + servicio), `app/modules/canal/__init__.py`, `app/modules/canal/models.py` (vacío por ahora salvo import), `app/modules/products/services/web.py`
- Modify: `app/modules/products/models.py` (columnas), `app/models/__init__.py` (registrar), `app/services/capabilities_service.py` y `scripts/init_presets_v2.py` (módulo en catálogo, sin presets), `scripts/railway_init.py`, `app/modules/products/schemas.py` (`ProductRead.web_published`, `DepartmentRead.parent_id`, marca `is_premium`), `app/modules/products/router/__init__.py` (create/update de marcas y departamentos aceptan los campos nuevos), `app/modules/products/services/productos.py` y `services/variantes.py` (llaman `tocar_producto`)
- Test: `tests/test_catalogo_web_esquema.py`

**Interfaces:**
- Consumes: `MODULO_CANAL` (T1).
- Produces: columnas `Product.web_published: bool`, `Product.web_published_at: datetime|None`, `Brand.is_premium: bool`, `Department.parent_id: str|None`; modelo `ProductImage(id, organization_id, product_id, url, alt, position, is_primary, created_at, updated_at, deleted_at)` tabla `product_images`; `tocar_producto(db, product_id: str) -> None` (pone `updated_at = now`); `validar_padre(db, org_id: int, dept_id: str|None, parent_id: str|None) -> None` (HTTPException 422: otra org, 3 niveles, ciclo, padre con padre); `backfill_imagenes(db) -> int`.

- [ ] **Step 1: Pruebas que fallan**:
  - `test_defaults_no_cambian_listado`: `GET /api/products/` como admin trae `web_published: false` y el resto de las claves de antes (compara contra el set de claves previo + `web_published`).
  - `test_backfill_imagen_primaria_idempotente`: producto con `image_url` → `backfill_imagenes` crea 1 `ProductImage(is_primary=True, position=0)`; segunda llamada → 0.
  - `test_parent_id_dos_niveles` (crear "Ropa" y "Camisas" con padre Ropa → ok; "Manga larga" con padre Camisas → 422), `test_parent_id_otra_org` → 422, `test_parent_id_ciclo` → 422.
  - `test_marca_premium` (PUT `/api/brands/{id}` `{"is_premium": true}` → lo devuelve el GET).
  - `test_editar_variante_toca_producto`: `updated_at` del producto sube al editar una variante por `PUT /api/products/variants/{id}`.
  - `test_modulo_en_catalogo_sin_presets`: tras `seed_global_modules`, existe `Module(key="tienda_en_linea")` y ningún `industry_presets` lo incluye.
- [ ] **Step 2:** correr → FAIL.
- [ ] **Step 3: Implementar.** En `railway_init.py`: los 4 `ADD COLUMN`, `create_all` crea `product_images`, `backfill_imagenes` en SQL (`INSERT … SELECT … WHERE NOT EXISTS`), índices `ix_<tabla>_org_updated (organization_id, updated_at)` en `products`, `product_variants`, `brands`, `departments`, `product_images`. `image_url` del producto queda como está.
- [ ] **Step 4:** pruebas → PASS; suite completa sin fallos nuevos; `python3 scripts/railway_init.py` contra una SQLite vacía corre dos veces sin error.
- [ ] **Step 5: Commit** `feat(catalogo): campos de tienda web, galería y departamento padre`.

### Task 3: Publicar, galería y configuración del canal — backend (PR2)

**Files:**
- Modify: `app/modules/products/router/bulk.py` (endpoint de publicación), `app/modules/products/router/core.py` (endpoints de galería junto a `/{product_id}/image`), `app/modules/products/services/web.py`
- Create: `app/modules/canal/config_router.py` (montado en `app/main.py` en `/api/canal`)
- Test: `tests/test_catalogo_web_publicar.py`

**Interfaces:**
- Consumes: T2 (`tocar_producto`, `ProductImage`), T1 (`canal_activo`, `invalidar_cache_canal`).
- Produces:
  - `POST /api/products/web-publish` body `{"ids": [str] | null, "filtro": {"search","brand_id","department_id"} | null, "published": bool}` → `{"processed": int}`. Solo `ADMINISTRADOR`/`DUEÑO` (403 a los demás); 404 si el canal no está activo. Fija `web_published_at = now` al publicar si estaba NULL o despublicado; siempre `tocar_producto`. Lotes de 500.
  - `GET /api/products/{id}/images`, `POST /api/products/{id}/images` (multipart `file`, `alt?`), `PUT /api/products/{id}/images/order` `{"ids":[...], "primary_id": str}`, `DELETE /api/products/{id}/images/{image_id}` (soft delete). Tras cada cambio `sincronizar_image_url(db, product)` copia la URL primaria a `products.image_url` (o NULL si no queda ninguna) y llama `tocar_producto`. Sube con `app/utils/image_storage.upload_image` igual que `/{product_id}/image`.
  - `POST /{product_id}/image` existente también crea/actualiza la imagen primaria de la galería (una sola fuente).
  - `GET /api/canal/config` → `{"activo": bool, "sucursales_web": [int] | null, "sucursales": [{id, name, can_sell}]}`; `PUT /api/canal/config` `{"sucursales_web": [int] | null}` (admin/dueño; ids de otra org → 422); guarda en `organization_modules.config_json` y llama `recalcular_disponibilidad` (T5; en esta tarea deja un hook `al_cambiar_sucursales(db, org_id)` que T5 implementa).
- [ ] **Step 1: Pruebas que fallan**: publicar por ids y por filtro; cajero y gerente → 403; canal apagado → 404; ids de otra org no se tocan (`processed` cuenta solo los propios); republicar no cambia `web_published_at`; galería: subir 2, reordenar, la primaria pasa a `image_url`; borrar la primaria → la siguiente es primaria; borrar todas → `image_url` NULL; `/{id}/image` legacy crea la primaria; config: PUT con sucursal ajena → 422, `null` = todas las que venden. Mockea `upload_image` como en las pruebas existentes de `/image` (`grep -rn "upload_image" tests`).
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suite. **Step 5: Commit** `feat(catalogo): publicar en tienda web, galería y sucursales del canal`.

### Task 4: Pantallas del canal (PR2)

**Files:**
- Create: `frontend/src/hooks/useCanalTienda.ts`, `frontend/src/components/products/DialogoPublicarWeb.tsx`, `frontend/src/components/products/GaleriaProducto.tsx`, `frontend/src/pages/core/TiendaEnLinea.tsx`
- Modify: `frontend/src/api/products.ts`, `components/products/FormularioProducto.tsx`, `pages/inventory/Products.tsx` (casillas por fila + barra de acciones), `pages/core/Brands.tsx`, `pages/core/Departments.tsx`, `pages/pos/Configuracion.tsx`
- Test: `frontend/src/components/products/__tests__/DialogoPublicarWeb.test.tsx`, `frontend/src/pages/inventory/__tests__/productosWeb.test.tsx`

**Interfaces:**
- Consumes: endpoints de T2/T3; `useEnabledModulesStore().enabledModules`; `useAuthStore` rol.
- Produces: `useCanalTienda(): { activo: boolean; puedePublicar: boolean }` (`activo` = `enabledModules.includes('tienda_en_linea')`; `puedePublicar` = activo y rol `ADMINISTRADOR`|`DUEÑO`).

- [ ] **Step 1: Pruebas que fallan (vitest):**
  - Diálogo: tras guardar un alta con `puedePublicar` aparece «¿Lo publicamos también en la tienda web?» con «Sí, publicar» (llama `webPublish({ids:[id], published:true})`) y «Ahora no» (no llama nada). Con cajero o sin módulo no se renderiza.
  - Productos: sin módulo no hay columna «Web» ni casillas; con módulo y admin, seleccionar 2 filas → «Publicar en tienda web (2)» llama `webPublish` con esos ids; «Publicar todo lo filtrado» manda `filtro` con la búsqueda/marca/departamento activos y pide confirmación con el total.
  - Marcas: casilla «Marca premium» solo con módulo. Departamentos: selector «Departamento padre» lista solo raíces.
  - Configuración: pestaña «Tienda en línea» solo para admin/dueño con módulo; casillas por sucursal que vende; «Todas las que venden» manda `null`.
- [ ] **Step 2:** `npx vitest run <archivos>` → FAIL.
- [ ] **Step 3: Implementar.** El diálogo usa `ui/Modal`. `AltaRapidaProducto` (POS) **no** muestra el diálogo. La ficha (`FormularioProducto` en edición) muestra casilla «Publicado en tienda web» y `GaleriaProducto` solo si `activo`. `Configuracion.tsx`: para vista completa con canal activo, dos pestañas «Impresora» | «Tienda en línea»; si no, igual que hoy.
- [ ] **Step 4:** `npx vitest run` completo (incluye `coloresPorTokens`, `overlaysFueraDelKit`, `botonesDelKit`) y `npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(catalogo): publicar en tienda web desde el alta y en bloque, galería y configuración`.

### Task 5: Disponibilidad web (PR2)

**Files:**
- Create: `app/services/canal_disponibilidad.py`, `scripts/recalcular_disponibilidad_web.py`
- Modify: `app/modules/canal/models.py` (`ChannelAvailability`), `app/main.py` (registrar listener en startup), `app/modules/canal/config_router.py` (hook de T3), router de plataforma que enciende módulos (`app/routers/platform/organizations.py` o donde se haga el toggle; `grep -rn "OrganizationModule(" app/routers/platform`) para recalcular al activar
- Test: `tests/test_canal_disponibilidad.py`

**Interfaces:**
- Consumes: `canal_activo` (T1), `config_json.sucursales_web` (T3).
- Produces: modelo `ChannelAvailability` tabla `channel_availability` PK `(organization_id, variant_id)`, columnas `product_id String(36)`, `available bool`, `changed_at timestamptz`, índice `ix_channel_availability_org_changed (organization_id, changed_at)`; `sucursales_web(db, org_id) -> list[int]`; `variante_disponible(db, org_id, variant_id) -> bool`; `registrar_listener() -> None`; `recalcular_disponibilidad(db, org_id) -> int` (filas cambiadas).

- [ ] **Step 1: Pruebas que fallan** (org con módulo, `branch_a` web, `branch_b` no web, producto aprobado con variante y existencias):
  - `test_ultima_pieza_cambia_a_no_disponible`: venta real por `POST /api/sales/` de la última pieza en `branch_a` → fila `available=False`.
  - `test_venta_parcial_no_escribe`: 5 → 4 piezas → sin fila nueva ni `changed_at` movido.
  - `test_sucursal_no_web_no_cuenta`: existencias solo en `branch_b` → `available=False`; vender en `branch_b` no escribe.
  - `test_entrada_vuelve_disponible`: ajuste/compra que sube de 0 a 1 → `available=True`.
  - `test_rollback_no_deja_fila` (cambia `qty_on_hand`, flush, rollback → sin fila).
  - `test_org_sin_modulo_sin_consultas_extra`: contador con `event.listen(engine, "before_cursor_execute")` durante una venta; igual número de statements con y sin listener registrado.
  - `test_variante_borrada_o_producto_inactivo`: borrar variante / desactivar producto / `approval_status='PENDING'` → `available=False`.
  - `test_recalcular_corrige_update_crudo`: `UPDATE stock_on_hand SET qty_on_hand=0` en SQL crudo → `recalcular_disponibilidad` devuelve 1 y deja la fila en False.
  - `test_cambiar_sucursales_recalcula` (PUT `/api/canal/config`).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementar.** Listener `before_flush` en `Session` (global): toma `session.new`/`session.dirty` de tipo `StockOnHand` con historial en `qty_on_hand`, `ProductVariant` con cambio en `deleted_at`/`is_active`, `Product` con cambio en `is_active`/`approval_status`/`deleted_at`; agrupa por org; si `canal_activo` es falso → sale **antes** de consultar nada más (la cache evita la consulta). Para cada variante: calcula con `session.no_autoflush`, compara con la fila actual y solo escribe si cambió. Nunca lanza: captura excepciones y registra `logger.exception` (la venta no debe caer por esto). Script: `--org N [--ejecutar]`, ensayo por omisión.
- [ ] **Step 4:** PASS; suite completa sin fallos nuevos, en especial `tests/test_sales*`, `tests/test_cash*`, `tests/test_conteos*`.
- [ ] **Step 5: Commit** `feat(canal): disponibilidad web materializada sin tocar el cobro`.

### Task 6: API de catálogo del canal (PR3)

**Files:**
- Create: `app/modules/canal/schemas.py`, `app/modules/canal/router.py`, `app/modules/canal/cursor.py`
- Modify: `app/main.py` (`/api/channel/v1`, sin CORS adicional), `docs/API_REFERENCE.md`
- Test: `tests/test_canal_api.py`

**Interfaces:**
- Consumes: `require_channel_key("catalog:read")` (T1), modelos de T2, `ChannelAvailability` (T5).
- Produces: `codificar_cursor(ts: datetime, id: str) -> str` / `decodificar_cursor(s: str) -> tuple[datetime, str]` (base64url de JSON; inválido → 400); schemas `CanalMarca`, `CanalDepartamento`, `CanalImagen`, `CanalVariante`, `CanalProducto`, `CanalBaja`, `CanalDisponibilidad`, `Pagina[T]` — todos `model_config = ConfigDict(extra="forbid")`, campos exactamente los del spec §3.4.

- [ ] **Step 1: Pruebas que fallan:**
  - `test_lista_blanca`: recorre la respuesta JSON de los 5 endpoints y falla si alguna clave casa `price|cost|tax|iva|supplier|proveedor|qty|stock|barcode`.
  - `test_dos_orgs`: llave de org B no ve productos de org A; `GET /products/{id_de_A}` → 404.
  - `test_solo_publicados_en_carga_inicial`: sin `updated_since` no salen bajas ni no publicados.
  - `test_despublicar_da_baja`: publicar, tomar `server_time`, despublicar → `/products?updated_since=` trae `{"id", "updated_at", "deleted": true}`; nunca publicado → no aparece.
  - `test_republicar_tras_baja`: despublicar, borrar (inactivo), reactivar y republicar → aparece completo con `deleted:false`.
  - `test_cursor_estable_con_updated_at_iguales`: 250 productos con el mismo `updated_at`, `limit=100` → 3 páginas, 250 ids distintos, `next_cursor` null al final.
  - `test_limit_fuera_de_rango` (0 y 201) → 422; `test_cursor_basura` → 400.
  - `test_availability_desde`: tras vender la última pieza, `/availability?updated_since=<server_time previo>` trae la variante con `available:false`.
  - `test_marcas_y_departamentos`: `is_premium` y `parent_id` presentes; marca borrada (`deleted_at`) sale `deleted:true` con `updated_since`.
  - `test_server_time_antes_de_consultar` (monkeypatch del reloj: `server_time` ≤ `updated_at` de un cambio hecho durante la consulta no aplica — basta verificar que `server_time` se toma antes del query, con un spy).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementar.** Consultas con `organization_id == ctx.organization_id`, filtro `(updated_at, id) > cursor` como `or_(updated_at > t, and_(updated_at == t, id > i))`, `order_by(updated_at, id)`, `limit+1` para saber si hay siguiente. Productos: `selectinload` de variantes no borradas e imágenes no borradas; `available` de producto = alguna variante con fila `available=True` en `channel_availability` (sin fila = calcula con `variante_disponible`). `server_time` = `datetime.now(timezone.utc)` tomado antes del query. Documentar los 5 endpoints con ejemplos `curl` y respuesta en `docs/API_REFERENCE.md` (sin llaves reales).
- [ ] **Step 4:** PASS + suite completa.
- [ ] **Step 5: Commit** `feat(canal): API de catálogo de solo lectura /api/channel/v1`.

### Task 7: Activación para Eleven y entrega de la llave (PR4, operativa, tras el deploy de PR2 y PR3)

**Files:**
- Modify: `docs/playbooks/altas-de-clientes.md` (sección «Tienda en línea»: encender módulo, sucursales web, emitir llave, scripts SQL deben poner `updated_at = now()`), `.claude/skills/eleven-catalogo/` (o donde viva la skill: `grep -rl "alta_prenda" ~/.claude .claude 2>/dev/null`) — que `alta_prenda.py`/`hoja_plan.py` toquen `updated_at` y llamen `recalcular_disponibilidad` al terminar.

- [ ] **Step 1:** Con permiso del usuario y tras el deploy: correr `init_presets_v2.py` en el contenedor si el módulo no aparece; encender `tienda_en_linea` solo en org 17 desde la plataforma; `recalcular_disponibilidad_web.py --org 17` (ensayo → `--ejecutar`).
- [ ] **Step 2:** Emitir llave `catalog:read` para org 17 desde `/platform` (la ve el usuario, **no** se pega en el chat ni en el repo).
- [ ] **Step 3:** Verificar con `curl` desde el VPS con la llave en variable de entorno: `/brands` 200, `/products` vacío (nada publicado aún), 401 sin llave.
- [ ] **Step 4:** Avisar al dueño de Eleven del diálogo nuevo en el alta y de cómo publicar en bloque.
- [ ] **Step 5: Commit** de docs/skill `docs(canal): playbook de tienda en línea y scripts que mueven updated_at`.

### Task 8: Prospectos y métricas (PR5, fase 2)

**Files:**
- Modify: `app/modules/canal/models.py`, `app/modules/canal/schemas.py`, `app/modules/canal/router.py`, `scripts/railway_init.py` (nada si son tablas nuevas)
- Create: `frontend/src/components/reports/TarjetaTiendaEnLinea.tsx` + endpoint `GET /api/reports/tienda-en-linea?desde&hasta`
- Test: `tests/test_canal_leads.py`, vitest de la tarjeta

**Interfaces:**
- Consumes: `require_channel_key("leads:write")`.
- Produces: tablas `channel_product_metrics(organization_id, product_id, day date, source, count)` PK compuesta; `channel_leads` (campos del spec §3.5, `phone` 10 dígitos); `channel_idempotency(organization_id, key, response_json, created_at)` PK `(organization_id, key)`; `normalizar_telefono(s: str) -> str | None` (quita no-dígitos, toma los últimos 10; <10 → None).

- [ ] **Step 1: Pruebas que fallan:** sin teléfono → 202 `{"recorded":"metric"}` y cero filas en `channel_leads`; con teléfono → 201 `{"lead_id"}` + métrica; teléfono `+52 55 1234 5678` de un cliente existente → `customer_id` ligado; misma `Idempotency-Key` → misma respuesta, sin doble conteo; sin header → 422; `product_ids` ajenos ignorados; llave solo `catalog:read` → 403; reporte con piezas más consultadas solo para admin/dueño de la org.
- [ ] **Step 2:** FAIL. **Step 3:** implementar (purga de idempotencia >7 días al insertar). **Step 4:** PASS + suite + build. **Step 5: Commit** `feat(canal): métricas y prospectos desde la tienda web`.
