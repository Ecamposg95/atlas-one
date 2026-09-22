# Modelo de Datos · Atlas BOS (74 tablas)

Catálogo de la base de datos por dominio. Fuente: auditoría profunda (julio 2026). Modelos en `app/models/*.py` y `app/modules/*/models.py`.

## Mixins base (`app/models/mixins.py`)

| Mixin | Aporta | Notas |
|---|---|---|
| `UUIDMixin` | `id = String(36)` PK (uuid4) | PK **UUID**. Catálogo (products) y ventas. |
| `AuditMixin` | `created_at`, `updated_at`, `deleted_at` (tz-aware) | `deleted_at` = soft-delete. |
| `TenantMixin` | `organization_id = Integer FK→organization.id` (**nullable**, index) | Scoping multi-tenant. |

**Dos convenciones de PK conviven:** catálogo/ventas usan `id UUID String(36)`; tenancy/usuarios/caja/RRHH/logística/gastro/appointments usan `id Integer`. **Las FKs a IDs UUID (`product_variants.id`, `sales_documents.id`, `parked_tickets.id`, `departments.id`) deben declararse `String(36)`, nunca Integer** (SQLite no lo valida, Postgres crashea en `create_all`).

---

## Organización / Tenancy
| Tabla | PK | Propósito | Enums |
|---|---|---|---|
| `organization` | Int | Tenant root (fiscal, branding, plan SaaS) | `industry_type`=IndustryType |
| `branches` | Int | Sucursal (tienda/HQ/almacén/oficina) | `branch_type`=BranchType |
| `modules` | **String (key)** | Catálogo global de módulos SaaS | `scope`=ModuleScope, `status`=ModuleStatus |
| `organization_modules` | (org_id, module_key) | Habilitación de módulo por org | — |
| `industry_presets` | Int | Preset de módulos por vertical | `industry_type` (String) |
| `exchange_rates` | Int | FIX de Banxico diario, **global** (sin `organization_id`/`TenantMixin` a propósito — dato público) | `source`=String (`banxico`\|`manual`); UNIQUE `(currency, rate_date)` |

`BranchType`{HQ,STORE,WAREHOUSE,OFFICE} · `ModuleScope`{HQ,BRANCH,WAREHOUSE,GLOBAL} · `ModuleStatus`{BETA,STABLE} · `IndustryType` (~19 valores: ATLAS_POS, **ATLAS_POS_BOUTIQUE** (2026-09-16, ver [`presets/BOUTIQUE.md`](presets/BOUTIQUE.md)), DISTRIBUTOR_POS, RETAIL_CHAIN, RESTAURANT_QSR/FULL, CAFE_BAKERY, AUTO_REPAIR_SHOP, WAREHOUSE_LOGISTICS, CUSTOM, familia ATLAS_ONE_* incl. RESTAURANT/CAFE/BAR, varios legacy).

**Columnas boutique/2026-09 en `organization`** (`app/modules/tenants/models.py`, todas
con `ALTER` idempotente en `railway_init.py`, todas opcionales/apagadas por default —
ninguna organización existente cambia de comportamiento sin configurarlas):

| Columna | Tipo | Default | Propósito |
|---|---|---|---|
| `ticket_terms` | `Text` | `NULL` | Términos y condiciones impresos al pie del ticket |
| `ticket_terms_url` | `String` | `NULL` | URL de términos; si está capturada, el ticket emite un QR nativo ESC/POS |
| `ticket_instagram`/`ticket_facebook`/`ticket_tiktok`/`ticket_whatsapp` | `String` | `NULL` | Redes sociales del bloque "SIGUENOS" del ticket |
| `ticket_show_vendor` | `Boolean` | `false` | Imprime "Sistema: Atlas One \| Atlas Tech" + dominio al pie |
| `ticket_line_style` | `String(12)` | `'compact'` | `compact` (una línea por producto, formato de hoy) \| `detailed` (marca/nombre/talla en 2-4 líneas, ver [`presets/BOUTIQUE.md §3.3`](presets/BOUTIQUE.md)) |
| `card_surcharge_pct` | `Numeric(5,2)` | `0` | % de comisión por pago con tarjeta, `0`=apagado. `NUMERIC(5,2)` y no `(6,3)`: con 3 decimales la etiqueta del ticket desborda el papel de 58 mm |
| `usd_rate_mode` | `String(10)` | `'off'` | `off`\|`auto`(FIX+margen)\|`manual`. String con constantes Python, no enum de Postgres (regla de oro §5) |
| `usd_rate_manual` | `Numeric(10,4)` | `NULL` | Tipo fijo si `mode='manual'` |
| `usd_rate_margin` | `Numeric(10,4)` | `0` | Se suma al FIX en modo `auto` |

## Usuarios / Auth
| Tabla | PK | Propósito | Enums |
|---|---|---|---|
| `users` | Int | Cuenta login (perfil, FaceID, roles) | `role`=Role, `platform_role`=PlatformRole |
| `user_organizations` | (user_id, org_id) | Membresía M2M user↔org | `org_role` String (ADMIN/MEMBER/OWNER) |

`Role`{ADMINISTRADOR,GERENTE,CAJERO,DUEÑO,VENDEDOR,SOPORTE_OPERATIVO,CLIENTE} · `PlatformRole`{SUPERADMIN,SUPPORT,NONE}. `users` **no** usa TenantMixin (scoping vía `user_organizations`). Ver [`RBAC.md`](RBAC.md).

`users.reprint_pin_hash` (`String`, nullable, 2026-09-19) — PIN de reimpresión de 4-8
dígitos, hasheado igual que la contraseña, **independiente de ella**; solo tiene efecto
en roles gerenciales (ADMINISTRADOR/DUEÑO/GERENTE). Nunca se expone: `UserRead` solo
trae el derivado `has_reprint_pin: bool` (propiedad `User.has_reprint_pin`). El POS
prueba primero el PIN de los supervisores de la sucursal y luego su contraseña —
mismo orden que ya existía, con el PIN como primer intento.

## Productos / Catálogo (`modules/products/models.py`, PK UUID)
| Tabla | Propósito |
|---|---|
| `departments` | Departamento/categoría |
| `brands` | Marca |
| `uom` | Unidad de medida |
| `products` | Producto padre (approval_status) |
| `product_variants` | SKU vendible (precio, costo, IVA) — UNIQUE `(org, sku) WHERE deleted_at IS NULL` |
| `product_prices` | Precios escalonados por cantidad |
| `packaging_units` | Jerarquía de empaque (caja/pack) |
| `product_branch_status` | Matriz habilitación producto×sucursal — UNIQUE `(variant_id, branch_id)` |

**Columnas boutique/2026-09 (preset `ATLAS_POS_BOUTIQUE`, ver [`presets/BOUTIQUE.md`](presets/BOUTIQUE.md)):**

- `products.gender` `String(10)` nullable — `HOMBRE|MUJER|UNISEX|NINO`. String con
  constantes Python (`app/modules/products/sale_name.py::GENDERS`), no enum de Postgres.
- `products.model` `String(80)` nullable — nombre comercial del modelo ("Air Force 1").
- `products.material` `String(80)` nullable — informativo; no entra en `sale_name` ni SKU.
- `product_variants.color` `String(60)` nullable, `product_variants.size` `String(30)`
  nullable (2026-09-17, módulo `variants`) — la unidad de venta real de una prenda con
  variaciones; conviven con la `variant_name` heredada (etiqueta libre, sigue en uso en
  el catálogo viejo 1:1). **`barcode` sigue sin UNIQUE a nivel de base** (§Gotchas E más
  abajo y CLAUDE.md §6): la unicidad de código por talla/color es solo aplicativa.
- `sale_name` (producto y variante) **no es columna**: es un campo calculado y aplanado
  en la respuesta por `app/modules/products/sale_name.py` + `_compute_product_read`
  (`app/modules/products/router/_shared.py`). Ver la fórmula en `presets/BOUTIQUE.md §2.2`.

## Inventario (`app/models/inventory.py`)
| Tabla | PK | Propósito | Enums |
|---|---|---|---|
| `inventory_movements` | Int | Kardex de stock | `movement_type`=MovementType |
| `stock_on_hand` | Int | Existencias por sucursal+variante — UNIQUE `(branch, variant)` | — |

`MovementType`{PURCHASE_IN,SALE_OUT,ADJUSTMENT_IN/OUT,TRANSFER_IN/OUT,SALE_RETURN,RECIPE_CONSUMPTION}.

## Ventas / Caja
| Tabla | PK | Propósito | Enums |
|---|---|---|---|
| `sales_documents` | UUID | Venta/cotización/pedido (tip_amount, server_user_id) | `doc_type`=DocumentType, `status`=DocumentStatus |
| `sales_lines` | UUID | Detalle de venta | — |
| `payments` | UUID | Pagos (o abono si doc NULL) | `method`=PaymentMethod |
| `parked_tickets` | UUID | Tickets pausados / cuentas de mesa (cart_json JSONB) | — |
| `cash_sessions` | Int | Turno de caja | `status`=CashSessionStatus |
| `cash_movements` | Int | Entradas/salidas manuales | `type` String (IN/OUT) |
| `cash_audit_log` | Int | Log append-only monetario | `event_type` String |

`DocumentType`{QUOTE,ORDER,INVOICE,RETURN} · `DocumentStatus`{DRAFT,PENDING,PAID,CANCELLED,REFUNDED_PARTIAL,REFUNDED_TOTAL} · `PaymentMethod`{CASH,CARD,TRANSFER,OTHER} · `CashSessionStatus`{OPEN,CLOSED}.

**Columnas 2026-09 en `sales_documents`** (`app/models/sales.py`), ambas snapshot —
se congelan al cobrar y una reimpresión/reenvío idempotente NUNCA las recalcula:

- `usd_rate` `Numeric(10,4)` nullable — tipo de cambio efectivo aplicado a esta venta
  (`NULL` = sin equivalente mostrado, venta anterior a la función, u organización en
  modo `off`). Ver `app/services/exchange_rate.py`.
- `card_surcharge_pct` `Numeric(5,2)` nullable (`NULL` = no aplicó comisión, distinto
  de `0`) y `card_surcharge_amount` `Numeric(10,2)` NOT NULL default `0`. `total_amount`
  **sigue siendo la mercancía**; la comisión vive aparte para no mover ningún KPI
  histórico. Ver `app/services/card_surcharge.py`.

**Columnas 2026-09-22 — atribución del efectivo por pago** (fusión
`feat/pago-atribuido-a-caja`, `63ee8a2`; reporte de la fusión en
`.superpowers/sdd/audit-funcional/pago-merge-report.md`, no versionado):

- `payments.cash_session_id` `Integer` nullable, FK → `cash_sessions.id`, con índice
  `ix_payments_cash_session_id`. **Un pago cuenta en el corte de la sesión que lo
  recibió** (nueva regla primaria), no en la del documento de venta —
  `sales_documents.cash_session_id` se queda como respaldo/índice, no como criterio
  primario (sigue alimentando `_compute_change_given` y `branch_dashboard.py`, que
  mantiene su propia copia del filtro por documento — inconsistencia conocida, ver
  `pago-merge-report.md §5.3`). Regla completa e idempotente en
  `app/services/cash_reconciliation.py::session_payments_filter` — un pago cuenta si
  `cash_session_id` apunta a la sesión, **o** es `NULL` y su documento cae en el filtro
  por documento (mutuamente excluyentes, sin doble conteo). Escritores:
  `app/routers/sales.py::create_sale`, `app/modules/customers/router.py::register_customer_payment`,
  `app/routers/quotes.py::convert_quote_to_sale`. Pagos históricos: backfill automático
  en cada deploy (`rellenar_payments_cash_session()` en `railway_init.py`) — copia
  `sales_documents.cash_session_id` a los pagos huérfanos, no inventa sesión para los
  que tampoco tenían una en el documento.
- `cash_movements.created_by_user_id` `Integer` nullable, FK → `users.id`, con índice
  `ix_cash_movements_created_by`. Autoría de una entrada/salida de efectivo manual —
  el modelo ya existía en `main`, pero su DDL solo vivía en un script manual
  (`scripts/migrate_add_cash_movement_author.py`); desde el 2026-09-22 es automática
  (`railway_init.py`), ver `CLAUDE.md §6`.

Consecuencia de negocio (no de esquema): `CASH_INCLUDED_STATUSES` volvió a incluir
`DocumentStatus.PENDING` — con atribución por pago, liquidar una venta a crédito ya
no reatribuye retroactivamente el abono viejo a la sesión de hoy (antes vaciaba un
corte ya cerrado). `SALES_REPORT_STATUSES` sigue **sin** `PENDING` — una venta a
crédito con abono parcial no debe inflar "ventas totales" con la deuda aún no cobrada.

## CRM / Finanzas
| Tabla | PK | Propósito | Enums |
|---|---|---|---|
| `customers` | Int | Cliente (crédito, lealtad) | — |
| `customer_ledger_entries` | Int | Kardex financiero del cliente | — |
| `account_transactions` | Int | Movimientos de cuenta (cargo/pago) | `tx_type`=TransactionType |
| `expenses` | Int | Egresos operativos | `category` String |
| `purchase_orders` | Int | OC a proveedor | `status`=PurchaseOrderStatus |
| `purchase_order_lines` | Int | Línea de OC | — |
| `purchase_recommendations` | UUID | Reorden por bajo stock (abasto) | `status`=RecommendationStatus |

## Devoluciones (`app/models/returns.py`, PK UUID)
`sale_returns` (refund_method=PaymentMethod, status String), `sale_return_items` (reentrada a stock o merma).

## Logística (`app/models/logistics.py`, PK Int)
`container_types`, `box_types`, `product_packagings`, `container_load_calcs`, `inbound_shipments` (status String), `shipment_items`, `transfer_orders` (`TransferStatus`), `transfer_order_lines`, `transfer_fulfillments` (`FulfillmentStatus`), `transfer_fulfillment_lines`.

`TransferStatus`{DRAFT,REQUESTED,PARTIALLY_FULFILLED,COMPLETED,CANCELLED} · `FulfillmentStatus`{PREPARED,SHIPPED,RECEIVED,CANCELLED}.

## RRHH (`app/models/hr.py`, PK Int)
`employees` (fiscal MX, `employee_type`=EmployeeType), `branch_assignments`, `attendances` (`verification_method`=VerificationMethod, `incident_type`=IncidentType).

## Impresión
`print_jobs` (UUID, cola ESC/POS base64, `status`=PrintJobStatus).

## Platform / SaaS (`app/models/platform.py`, PK Int)
`platform_audit_log`, `platform_alert`, `platform_announcement`, `feature_flag`, `org_feature_override` (UNIQUE org+flag), `platform_incident`, `api_key` (SHA-256 hash + prefix). Ver [`API_REFERENCE.md`](API_REFERENCE.md) §platform.

## Outbox / Eventos
`event_outbox` (UUID, `status` String OutboxStatus{PENDING,PROCESSED,FAILED}, ml de reintento/backoff). Índice `ix_event_outbox_due (status, available_at)`. Ver [`ARCHITECTURE.md`](ARCHITECTURE.md) §3.

## Gastro
| Módulo | Tablas | Enums |
|---|---|---|
| **tables** | `dining_areas`, `dining_tables` (current_ticket_id→parked_tickets, server_user_id) | `TableStatus`{AVAILABLE,OCCUPIED,BILL_REQUESTED,CLEANING,RESERVED} |
| **kitchen** | `kitchen_stations`, `kitchen_routes` (dept→estación, UNIQUE branch+dept), `kitchen_tickets`, `kitchen_ticket_items` | `KdsStatus`{NEW,IN_PROGRESS,READY,SERVED,CANCELED}, `ItemStatus`{PENDING,PREPARING,READY,SERVED,VOIDED} |
| **recipes** | `recipes` (product_variant_id UNIQUE), `recipe_ingredients` | — |
| **bar** | `bar_bottles` (`BottleStatus`{OPEN,EMPTY,ARCHIVED}), `bar_bottle_events` (ledger: ml_change firmado) | `BarEventType`{OPEN,POUR,WASTE,REFILL} |

## Appointments (`modules/appointments/models.py`, PK Int)
`appointments_resources` (`ResourceType`), `appointments_professionals` (1:1 user), `appointments_schedules` (UNIQUE prof+weekday), `appointments_blocks`, `appointments_services` (1:1 variant), `appointments` (`AppointmentStatus`, `BookingChannel`), `appointments_services_link`, `appointments_events` (`AppointmentEventType`).

`ResourceType`{CHAIR,CABIN,CONSULTORY,BAY,TABLE} · `AppointmentStatus`{PENDING,CONFIRMED,IN_PROGRESS,COMPLETED,CANCELED,NO_SHOW} · `BookingChannel`{STAFF,PORTAL}.

---

## ⚠️ Gotchas de esquema

**A) FKs a IDs UUID = `String(36)`.** Cualquier tabla con `id` Integer que referencie `product_variants.id`, `sales_documents.id`, `parked_tickets.id` o `departments.id` (todos UUID) **debe** usar `String(36)`. Verificado correcto en todo el esquema actual; respetarlo en tablas nuevas.

**B) Columnas RAW añadidas por `scripts/railway_init.py` — NO están en el ORM** (se leen defensivamente vía `setattr`/SQL crudo). Documentarlas aunque no aparezcan en los modelos:
- `parked_tickets.status VARCHAR(16) DEFAULT 'ACTIVE'` (ACTIVE→CONVERTED/CANCELLED) — usada por tables/services y el subscriber.
- `parked_tickets.converted_to_sale_id VARCHAR(36) → sales_documents.id` — seteada en checkout.
- `sales_documents.global_discount_pct NUMERIC(5,2)` — descuento global.
- `branches.printer_cols INTEGER` — en DDL raw (creada también por
  `scripts/migrate_add_printer_cols.py`), no en el modelo `Branch`. La auditoría de
  esquema de 2026-09-19 confirmó **cero lectores** en todo `app/` (ni el impresor la
  lee ni ningún endpoint la escribe) — candidata a `DROP COLUMN`, verificando antes
  que ninguna integración externa la consulte.

**C) Tablas SIN tenant scoping** (ni TenantMixin ni FK org): `cash_movements`, `event_outbox`, `branch_assignments`, `attendances`, `purchase_order_lines`. `cash_audit_log` tiene `organization_id` Integer manual **sin FK**. El scoping depende de joins con la tabla padre.

**D) `organization_id` inconsistente:** TenantMixin lo hace nullable; los módulos gastro/appointments/tables lo declaran FK manual **NOT NULL** (más estricto). No hay patrón único.

**E) Enums-como-String sin validación DB:** `inbound_shipments.status`, `sale_returns.status`, `cash_movements.type`, `bar_bottle_events.event_type`, `event_outbox.status` son columnas `String` con valores tipo-enum (elegido a propósito para evitar migraciones de enum Postgres).

**F) Divergencias ORM↔DB:** `payments.sales_document_id` es `nullable=True` en el ORM pero railway_init lo fuerza a NOT NULL en prod. `CashSessionStatus` está definido dos veces (sales.py y cash.py). `event_outbox` usa `datetime.utcnow` **naive** (el resto usa tz-aware). `IndustryPreset` existe en el ORM pero no se exporta en `app/models/__init__.py` (se crea vía create_all porque comparte metadata).

**Conteo:** 74 tablas registradas en `Base.metadata` (corregido por la auditoría de
esquema de 2026-09-19, `.superpowers/sdd/db-audit/schema-findings.md` §resumen, que
introspeccionó `Base.metadata` directamente; el conteo previo de 73 estaba desactualizado).
Incluye `exchange_rates` (§Organización) y las columnas nuevas de esta sección — ningún
módulo nuevo (`app/modules/`) se agregó por el preset boutique, solo columnas y una
tabla global.
