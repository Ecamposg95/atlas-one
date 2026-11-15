# Canal «Tienda en línea» — diseño

**Fecha:** 2026-11-14 · **Estado:** borrador para revisión del dueño
**Origen:** task pack escrito desde `eleven_boutique` (2026-11-13) + decisiones del dueño en la sesión del 2026-11-14.
**Primer consumidor:** Eleven Boutique (`eleven.boutique`, org 17 «Eleven Fashion», preset `ATLAS_POS_BOUTIQUE`).

## 1. Qué y por qué

Atlas ONE pasa a ser la **fuente de verdad del catálogo** de una tienda web externa. La web guarda
una copia sincronizada, **nunca escribe productos** y **nunca ve precios, costos ni cantidades**: solo
muestra la pieza y si hay o no hay; la venta se cierra por WhatsApp. Hoy Eleven Boutique importa un
xlsx exportado a mano; con el canal deja de capturarse dos veces.

Todo es **genérico**: cualquier organización que active el módulo puede conectar su web. Nada en el
código menciona a Eleven.

### Decisiones del dueño (2026-11-14)

| # | Tema | Decisión |
|---|------|----------|
| D1 | Publicar al dar de alta | Al crear un producto, si el módulo está activo, **el admin de la organización** ve la pregunta «¿Lo publicamos también en la tienda web?». Cajera y gerente no la ven; su alta queda sin publicar. |
| D2 | Catálogo existente | El admin publica / quita **en bloque desde Productos** (selección o «todo lo filtrado»). |
| D3 | Sucursales que cuentan | El admin elige en la configuración del canal **qué sucursales cuentan para la web**. Por defecto: todas las que venden (`can_sell`). |
| D4 | Clic anónimo a WhatsApp | Es **métrica por pieza**, no prospecto. Solo hay prospecto cuando la persona deja teléfono. La bandeja de seguimiento es el CRM futuro (fuera de este spec). |
| D5 | Señal de «pocas piezas» | No. Solo booleano `available`. |
| D6 | Referencia en el WhatsApp | La decide la web: `model` del producto si existe; si no, SKU de la primera variante. El canal entrega ambos. |
| D7 | Marca premium | Se marca en Atlas ONE (pantalla de marcas); la web la lee. |
| D8 | Nombre/dominio | No afecta el código. Pendiente de confirmar con el dueño de Eleven («Eleven Fashion» vs «Eleven Boutique»). |

### No objetivos

Carrito, pagos, precios o pedidos web · webhooks salientes (la web sondea) · bandeja de prospectos /
CRM · agentes o WhatsApp Business · que la web escriba catálogo o existencias.

### Anti-objetivos (fracaso aunque funcione)

- La API del canal devuelve precio, costo, IVA, proveedor o cantidades.
- Una llave de una org lee datos de otra.
- El tráfico de la web o el cálculo de disponibilidad frena el POS.
- Un tenant existente nota algún cambio sin haber activado el módulo.

## 2. Estado actual (verificado en código 2026-11-14)

- **Llaves:** tabla `api_key` (`app/models/platform.py:126`) ya tiene `organization_id`, `scopes`
  (JSON en Text), `revoked_at`, `last_used_*`. Helpers en `app/modules/platform/api_keys.py`;
  `verify_api_key` existe pero **no está conectado** a ninguna ruta. CRUD de plataforma en
  `app/routers/platform/api_keys.py` y pantalla `frontend/src/pages/platform/PlatformApiKeys.tsx`.
  No hay rate limiting en el proyecto.
- **Catálogo:** `Product`, `ProductVariant`, `Brand`, `Department` usan `UUIDMixin + AuditMixin +
  TenantMixin` (`app/modules/products/models.py`). `AuditMixin.updated_at` tiene `onupdate` en el
  ORM (no en la BD): los `UPDATE` en SQL crudo de los scripts no lo mueven. `Product.image_url` es
  la única foto. `Department` es plano. `Brand` no tiene premium.
- **Existencias:** `stock_on_hand(branch_id, variant_id, qty_on_hand)` (`app/models/inventory.py:52`).
  Se modifica en al menos 8 routers (`sales`, `inventory`, `transfers`, `purchases`, `logistics`,
  `quotes`, devoluciones, conteos) más scripts en prod.
- **Módulos:** catálogo en `capabilities_service.seed_global_modules` / `init_presets_v2.py`;
  `organization_modules(organization_id, module_key, is_enabled, config_json)`; gate
  `require_module(key)` en `app/core/permissions.py`.

## 3. Diseño

### 3.1 Llaves de canal (paso 1)

- **Dependencia** `require_channel_key(scope)` en `app/core/security/channel_keys.py`:
  - Lee `Authorization: Bearer atlas_…` o `X-Api-Key`. Formato distinto de un JWT: si el bearer no
    empieza con `atlas_`, 401 (un JWT de usuario nunca entra al canal).
  - `verify_api_key` → fila no revocada; si no, 401. Scope ausente en `scopes` → 403.
  - Módulo `tienda_en_linea` apagado en la org de la llave → 404 (no revela que existe).
  - Devuelve un contexto `ChannelContext(organization_id, key_id, scopes)`; las rutas de canal
    filtran **siempre** por ese `organization_id` (nunca por parámetro).
  - `last_used_at` se actualiza como mucho una vez por minuto por llave (no un commit por request).
- **Las rutas de usuario no aceptan llaves**: `get_current_user` no cambia; una llave enviada ahí
  falla la decodificación JWT como hoy.
- **Rate limit** en memoria del proceso: ventana deslizante por `key_id`, 120 req/min → 429 con
  `Retry-After`. Suficiente con un solo contenedor en el VPS; si un día hay varios, se mueve a la BD.
- **Scopes válidos:** `catalog:read`, `leads:write`. La creación rechaza scopes desconocidos.
- **Emisión:** la pantalla de plataforma existente (`PlatformApiKeys`) ya emite/lista/revoca y
  muestra la llave una sola vez; se añade el selector de scopes y validación. El admin de la org no
  emite llaves (las entrega la plataforma por canal seguro).

### 3.2 Módulo y campos nuevos (paso 2)

**Módulo** `tienda_en_linea` («Tienda en línea») en el catálogo global, **fuera de todos los presets**
y fuera de los planes por ahora: lo enciende la plataforma por organización. Su `config_json`:

```json
{ "sucursales_web": [20, 36] }    // null o ausente = todas las sucursales con can_sell
```

**Esquema** (todo en `scripts/railway_init.py`, `ADD COLUMN IF NOT EXISTS`, defaults que no cambian nada):

| Cambio | Tipo / default | Nota |
|---|---|---|
| `products.web_published` | `BOOLEAN NOT NULL DEFAULT false` | |
| `products.web_published_at` | `TIMESTAMPTZ NULL` | se fija al publicar, se conserva al despublicar |
| `brands.is_premium` | `BOOLEAN NOT NULL DEFAULT false` | |
| `departments.parent_id` | `VARCHAR(36) NULL` FK `departments.id` | máx. 2 niveles, misma org (validado en el servicio) |
| tabla `product_images` | nueva (UUID, `TenantMixin`, `AuditMixin`): `product_id` (String 36), `url`, `alt`, `position`, `is_primary` | `create_all` la crea |
| backfill | `INSERT … SELECT` de `products.image_url` no vacíos como imagen primaria, solo si el producto no tiene imágenes | idempotente |
| índices | `(organization_id, updated_at)` en `products`, `product_variants`, `brands`, `departments`, `product_images` | `CREATE INDEX IF NOT EXISTS` |

**`image_url` se conserva** y queda sincronizada con la imagen primaria (el POS, el ticket y las
etiquetas la siguen leyendo).

**`updated_at` del producto como reloj de la sincronización.** Sube cuando cambia el producto, su
galería, sus variantes (alta, edición, borrado) o se publica/despublica. Se centraliza en un helper
`tocar_producto(db, product_id)` que llaman los servicios de variantes e imágenes. Los cambios de
marca/departamento no tocan los productos: tienen su propio endpoint y la web los cruza por id.
Los scripts que editan en SQL crudo deben poner `updated_at = now()`; se anota en
`docs/playbooks/altas-de-clientes.md` y en la skill `eleven-catalogo`.

**Pantallas** (solo si el módulo está activo para la org; render condicional, sin `hidden`):

- **Alta de producto** (`FormularioProducto` / `AltaRapidaProducto`): al guardar, si el usuario es
  admin/dueño, diálogo «¿Lo publicamos también en la tienda web?» Sí / Ahora no. No se pregunta en
  el POS a la cajera.
- **Productos (lista)**: columna/insignia «Web»; en la selección múltiple, acciones «Publicar en
  tienda web» / «Quitar de la tienda web», también sobre «todo lo filtrado». Endpoint
  `POST /api/products/web-publish {product_ids | filtro, published: bool}` — admin/dueño, filtra org,
  en lotes, devuelve conteo.
- **Ficha del producto**: casilla «Publicado en tienda web» y galería ordenable (subir a Cloudinary
  con `app/utils/image_storage.py`, ordenar, marcar principal, borrar).
- **Marcas**: casilla «Marca premium».
- **Departamentos**: selector «Departamento padre» (solo departamentos raíz).
- **Configuración → Tienda en línea** (pestaña nueva en `/configuracion`, admin/dueño): sucursales
  que cuentan para la web.

### 3.3 Disponibilidad (paso 3)

- **Regla:** variante disponible ⇔ suma de `qty_on_hand > 0` en las sucursales web, variante no
  borrada, producto activo, `approval_status = 'APPROVED'`. Producto disponible ⇔ alguna variante
  disponible.
- **Tabla** `channel_availability(organization_id, variant_id PK compuesta, product_id, available,
  changed_at)` con índice `(organization_id, changed_at)`. Solo se escribe **cuando el booleano
  cambia**.
- **Cómo se entera sin tocar los 8 routers ni `create_sale`:** un listener de sesión SQLAlchemy
  (`before_flush`) en `app/services/canal_disponibilidad.py` junta las `StockOnHand` nuevas o con
  `qty_on_hand` modificado y las variantes/productos cuyo estado de venta cambió; en el mismo flush
  recalcula solo esas variantes y escribe la fila si el booleano cambió. Atajos:
  - si la org no tiene el módulo activo → no hace nada (consulta cacheada por org, 60 s);
  - si la sucursal no cuenta para la web → no hace nada;
  - una venta que deja 3 piezas de 5 no cambia el booleano → cero escrituras.
  Corre dentro de la transacción del negocio: si la venta hace rollback, la disponibilidad también.
- **Red de seguridad** para lo que el listener no ve (SQL crudo de scripts, cambio de sucursales web,
  activar el módulo): `recalcular_disponibilidad(db, org_id)` recorre la org y corrige diferencias.
  Se llama al activar el módulo, al guardar las sucursales web y desde un comando
  `scripts/recalcular_disponibilidad_web.py --org N`.
- **Riesgo aceptado:** el listener corre en el flush de `create_sale`. Se prueba explícitamente que
  una venta en una org **sin** el módulo no hace consultas extra, y que con el módulo hace a lo más
  una consulta por variante tocada.

### 3.4 API del canal (paso 4)

Router `app/modules/canal/router.py`, prefijo `/api/channel/v1`, scope `catalog:read`, sin CORS.

**Paginación común:** `?updated_since=<ISO8601>&cursor=<opaco>&limit=<1..200, def 100>`, orden
`(updated_at, id)`, respuesta `{ "items": [...], "next_cursor": str|null, "server_time": ISO8601 }`.
`server_time` se toma **antes** de la consulta; la web usa como siguiente `updated_since` el último
`server_time` **− 10 minutos** (deduplica por id) —los sellos `updated_at`/`changed_at` se ponen en
Python antes del commit y una transacción larga puede confirmar filas con sello anterior— y hace una
carga completa nocturna. `updated_since` va con `Z` o con el `+` codificado (un `+` crudo → 422).
Marcas y departamentos se borran en duro: nunca llegan con `deleted:true`; la web los baja completos
en cada sincronización y descarta los ids que desaparecieron.

```
GET /brands        { id, name, logo_url, is_premium, updated_at, deleted }
GET /departments   { id, name, parent_id, updated_at, deleted }
GET /products      publicado:  { id, name, description, brand_id, department_id, gender, model,
                                 material, available, images:[{url, alt, position, is_primary}],
                                 variants:[{id, sku, color, size, available}],
                                 updated_at, web_published_at, deleted:false }
                   despublicado/inactivo/borrado/no aprobado: { id, updated_at, deleted:true }
GET /products/{id} mismo shape; 404 si no es de la org o nunca se publicó
GET /availability  { product_id, variant_id, available, changed_at }  (orden por changed_at, id)
```

- **Nombre:** `products.name` tal cual (el «nombre de venta» de la ficha boutique ya se guarda ahí).
- **Lista de campos cerrada:** schemas propios en `app/modules/canal/schemas.py` con
  `extra="forbid"`; ninguno hereda de los schemas internos. Prueba que serializa respuestas reales y
  falla si aparece cualquier clave con `price|cost|tax|iva|supplier|proveedor|qty|stock|barcode`.
- **«Se despublicó desde X»**: `/products?updated_since` incluye los productos con
  `web_published = false` cuyo `updated_at` es posterior **y** que alguna vez se publicaron
  (`web_published_at IS NOT NULL`), como `deleted: true`. Nunca publicados → no existen para el canal.
- **Carga inicial** sin `updated_since`: solo publicados (no manda tombstones).
- Documentación en `docs/API_REFERENCE.md` con ejemplos `curl`.

### 3.5 Prospectos y métricas (paso 5, fase 2)

`POST /api/channel/v1/leads`, scope `leads:write`, header `Idempotency-Key` obligatorio.

```json
{ "source": "web_whatsapp_click" | "web_selection" | "web_form",
  "product_ids": ["uuid"], "line": "general" | "boutique",
  "name": "?", "phone": "?", "email": "?",
  "utm": {"source": "?", "medium": "?", "campaign": "?"}, "occurred_at": "ISO8601" }
```

- **Sin teléfono** (D4): incrementa `channel_product_metrics(organization_id, product_id, day,
  source, count)` → `202 {"recorded": "metric"}`. No guarda datos personales.
- **Con teléfono:** crea `channel_leads` (id UUID, org, source, line, name, phone normalizado a 10
  dígitos, email, utm, product_ids JSON, `customer_id` si el teléfono ya es cliente de la org,
  `status='nuevo'`, `occurred_at`) → `201 {"lead_id"}`. Además cuenta la métrica.
- `channel_idempotency(organization_id, key, response_json, created_at)`: repetir la clave devuelve
  la misma respuesta; purga a los 7 días.
- Productos de otra org o inexistentes en `product_ids` → se ignoran (no 4xx: la web no debe
  reintentar por eso).
- **Lectura mínima en Atlas ONE:** en Reportes, tarjeta «Tienda en línea»: piezas más consultadas por
  periodo y número de prospectos. La bandeja con seguimiento es el CRM futuro.

## 4. Pruebas (por paso)

1. **Llaves:** válida, revocada (401), de otra org (ve solo lo suyo), sin scope (403), ausente (401),
   JWT de usuario en ruta de canal (401), llave en ruta de usuario (401), módulo apagado (404),
   rate limit (429).
2. **Campos:** defaults no cambian respuestas existentes de `/api/products`; backfill idempotente;
   `parent_id` rechaza 3 niveles y otra org; publicar en bloque solo admin/dueño y solo su org; el
   diálogo no aparece sin módulo ni para cajera (vitest).
3. **Disponibilidad:** vender la última pieza → `available=false` y fila nueva; vender una de varias
   → sin fila; sucursal no web no cuenta; rollback no deja fila; org sin módulo no hace consultas
   extra (contador de statements); `recalcular_disponibilidad` corrige un `UPDATE` crudo.
4. **API:** lista blanca; dos orgs; paginación por cursor estable con `updated_at` iguales;
   despublicar → `deleted:true`; nunca publicado no aparece; `is_premium` y `parent_id` presentes.
5. **Leads:** sin teléfono → métrica, sin fila de lead; con teléfono existente → liga cliente;
   idempotencia; `product_ids` ajenos ignorados.

`with_for_update` y concurrencia no se prueban en SQLite (regla #7); el listener no depende de locks.

## 5. Entrega

Rama `feat/canal-tienda-en-linea`, un PR por paso: **1 llaves → 2 módulo y campos → 3 disponibilidad
→ 4 API** (fase 1) y **5 leads** (fase 2) aparte. Nada a `main` sin permiso. Tras desplegar el paso 2:
correr `init_presets_v2.py`/seed de módulos si hace falta y encender el módulo solo en la org 17.
Tras el paso 4: emitir la llave `catalog:read` de la org 17 y entregarla por canal seguro (nunca en
chat, repo ni docs). Avisar al dueño de Eleven antes de que vea el diálogo nuevo en el alta.

## 6. Preguntas abiertas

- D8: nombre comercial y dominio oficiales (no bloquea).
- ¿La foto de la galería se sube desde Atlas ONE o se siguen subiendo en el panel de la web? Este
  diseño asume **Atlas ONE** (fuente de verdad); el panel de Eleven dejaría de subir fotos de producto
  y conservaría solo las editoriales.
