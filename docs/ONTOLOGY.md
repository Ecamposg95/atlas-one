# Ontología de conocimiento · Atlas BOS

Mapa de conceptos, entidades, relaciones y vocabulario del sistema, en un formato
pensado para que un **agente** (o dev) razone sobre el dominio sin leer todo el código.

**Notación**
- Triple de relación: `Sujeto —predicado→ Objeto`.
- Ficha de entidad: bloque `clave: valor` (tipo YAML) con `tabla`, `pk`, `owns`, `emits`, etc.
- Todo concepto enlaza a su detalle en [`DATA_MODEL.md`](DATA_MODEL.md) /
  [`API_REFERENCE.md`](API_REFERENCE.md) / [`RBAC.md`](RBAC.md) / [`ARCHITECTURE.md`](ARCHITECTURE.md).

Índice: [1. Glosario](#1-glosario-canónico) · [2. Dominio](#2-ontología-de-dominio) ·
[3. Entidades](#3-ontología-de-entidades-agregados) · [4. Módulos](#4-ontología-de-módulos) ·
[5. Eventos](#5-ontología-de-eventos) · [6. RBAC](#6-ontología-de-rbac) ·
[7. Presets](#7-ontología-de-presets-y-módulos) · [8. Concepto→código](#8-índice-conceptocódigo)

---

## 1. Glosario canónico

Término → definición (y sinónimos/`identificador`).

| Término | Definición |
|---|---|
| **Atlas One** | La marca comercial / suite todo-en-uno que ve el cliente. |
| **Atlas BOS** | El motor técnico (Business Operating System) detrás de Atlas One. |
| **Organización** (`organization`, "tenant", "org") | Raíz del multi-tenant: la empresa cliente. Todo dato de negocio le pertenece. |
| **Sucursal** (`branch`) | Unidad operativa de una org: tienda, HQ, almacén u oficina (`BranchType`). |
| **HQ** | Headquarters — contexto org-wide; roles ADMINISTRADOR/DUEÑO operan aquí. |
| **Preset de industria** (`industry_type`, `IndustryPreset`) | Plantilla que mapea una vertical → set de módulos. Al aplicarlo se habilitan módulos en la org. |
| **Módulo** (`module`) | Unidad de funcionalidad vendible/activable (pos, inventory, tables, kds…). Vive en el catálogo `modules`; se habilita por org en `organization_modules`. |
| **Capacidad / capability** | Sinónimo operativo de "módulo habilitado" para una org (`capabilities_service`). |
| **Producto** / **Variante** (`product` / `product_variant`, "SKU") | Producto padre y su SKU vendible (precio, costo, IVA). La **variante** es la unidad real de venta/inventario. |
| **Stock on hand** (`stock_on_hand`) | Existencias actuales de una variante en una sucursal. |
| **Movimiento de inventario** (`inventory_movement`, "kardex") | Registro append-only de todo cambio de stock (`MovementType`). |
| **Documento de venta** (`sales_document`) | Encabezado de venta/cotización/pedido/devolución (`DocumentType`, `DocumentStatus`). |
| **Folio** | Identificador secuencial legible de un documento (series A/Q/P/OC…). |
| **Parked ticket** (`parked_ticket`, "ticket pausado", "cuenta abierta") | Buffer de carrito (JSONB) que NO consume folio ni inventario. Doble uso: (a) ticket pausado del POS, (b) **la cuenta abierta de una mesa**. |
| **Sesión de caja** (`cash_session`, "turno", "corte") | Turno de un cajero en una sucursal; agrupa ventas y movimientos de efectivo para el arqueo. |
| **Propina** (`tip_amount`) | Monto de propina; se suma al total y se persiste para el reporte por-mesero. |
| **Mesero / server** (`server_user_id`) | Usuario al que se atribuye una venta de mesa (para propinas/ventas por mesero). |
| **Mesa** (`dining_table`) | Mesa física del salón; su cuenta abierta ES un parked ticket (`current_ticket_id`). |
| **Área** (`dining_area`) | Zona del salón que agrupa mesas. |
| **Comanda** (`kitchen_ticket`, "KDS ticket") | Orden enviada a cocina; se rutea a estaciones y avanza por estados. |
| **Estación** (`kitchen_station`) | Puesto de cocina/barra que prepara ítems de comanda. |
| **Ruta** (`kitchen_route`) | Mapea un departamento de producto → una estación. |
| **Receta / BOM** (`recipe`) | Insumos que consume un platillo/bebida al venderse; permite costeo y descuento automático. |
| **Botella** (`bar_bottle`) | Botella física de barra, controlada por volumen (ml). |
| **Ledger de bar** (`bar_bottle_event`) | Registro inmutable de servidas/merma/reconteo; base del corte de turno y la varianza. |
| **Varianza** (bar) | Delta de un reconteo = merma no registrada / sobre-servido (si todo se registró, un reconteo da 0). |
| **Cita** (`appointment`) | Reserva de un servicio con un profesional/recurso (`AppointmentStatus`). |
| **Evento de dominio** (`event`, ver `SalesDocumentCreated`) | Hecho de negocio publicado al `EventBus`; desacopla módulos. |
| **Outbox** (`event_outbox`) | Cola transaccional que garantiza la entrega de eventos (patrón outbox). |
| **Subscriber** (`app/subscribers/*`) | Handler que reacciona a un evento (idempotente). |
| **Rol de tenant** (`Role`) | Rol de negocio del usuario (ADMINISTRADOR…CLIENTE). |
| **Rol de plataforma** (`PlatformRole`) | Rol de staff SaaS (SUPERADMIN/SUPPORT/NONE). |
| **Impersonación** | Staff de plataforma actuando como una org (vía cookie `support_org_id`; el endpoint es stub). |
| **Feature flag** (`feature_flag`) | Interruptor con rollout determinístico + overrides por org. |
| **Incidente** (`platform_incident`) | Kill-switch masivo que suspende orgs por scope, reversible por snapshot. |

---

## 2. Ontología de dominio

Relaciones de negocio (triples). Los `[N]` marcan cardinalidad (1↔N).

```
Organization —tiene→ Branch [N]
Organization —tiene_preset→ IndustryPreset
IndustryPreset —activa→ Module [N]
Organization —habilita→ Module [N]            (organization_modules)
Organization —emplea→ User [N]                (vía UserOrganization)
User —tiene_rol→ Role
User —tiene_rol_plataforma→ PlatformRole
User —asignado_a→ Branch

Branch —opera→ CashSession [N]
Branch —almacena→ StockOnHand [N]
Branch —vende_en→ SalesDocument [N]

Product —tiene→ ProductVariant [N]
ProductVariant —tiene_existencias→ StockOnHand (por Branch)
ProductVariant —se_vende_en→ SalesLine
ProductVariant —puede_ser→ Recipe (platillo) | RecipeIngredient (insumo) | BarBottle | Service (cita)

SalesDocument —compuesto_de→ SalesLine [N]
SalesDocument —pagado_con→ Payment [N]
SalesDocument —registrado_en→ CashSession
SalesDocument —atribuido_a→ Seller(User) y opcional Server(User=mesero)
SalesLine —descuenta→ StockOnHand  (SALE_OUT)  y  —dispara→ RecipeConsumption

DiningArea —agrupa→ DiningTable [N]
DiningTable —tiene_cuenta→ ParkedTicket (current_ticket_id)
DiningTable —atendida_por→ Server(User)
ParkedTicket —se_convierte_en→ SalesDocument  (al cobrar)
DiningTable —envía→ KitchenTicket [N]
KitchenTicket —compuesto_de→ KitchenTicketItem [N]
KitchenTicketItem —ruteado_a→ KitchenStation (vía KitchenRoute por departamento)

Recipe —pertenece_a→ ProductVariant(platillo)
Recipe —consume→ RecipeIngredient [N] —es→ ProductVariant(insumo)
BarBottle —registra→ BarBottleEvent [N]

Customer —tiene→ CustomerLedgerEntry [N]
Customer —debe/abona→ Payment
Appointment —reserva→ Service [N] con Professional y Resource
```

**Invariantes clave**
- `ParkedTicket` es el puente POS↔Mesas: liberar una mesa sin cobrar **cancela** su parked ticket + comandas KDS; cobrar lo **convierte** a venta y libera la mesa (vía evento).
- Vender un platillo con receta **descuenta insumos** (evento, idempotente). Vender NO descuenta botellas de bar (no integrado aún).
- Toda mutación de negocio ocurre **dentro de una org**; el aislamiento por sucursal NO está garantizado por el framework.

---

## 3. Ontología de entidades (agregados)

Fichas de los **agregados raíz** (la entidad que "posee" a las demás). Detalle de columnas en [`DATA_MODEL.md`](DATA_MODEL.md).

```yaml
Organization:
  tabla: organization         pk: Integer
  es: raíz-tenant
  owns: [Branch, User(via membership), Module-enablement, todo dato de negocio]
  key_fields: [industry_type, plan/status SaaS, slug]

Branch:
  tabla: branches             pk: Integer
  parent: Organization
  tipos: [HQ, STORE, WAREHOUSE, OFFICE]
  owns: [CashSession, StockOnHand, SalesDocument, DiningTable, KitchenStation...]

User:
  tabla: users                pk: Integer
  scoping: via UserOrganization (M2M), NO TenantMixin
  ejes: {role: Role, platform_role: PlatformRole}

ProductVariant:  # agregado del catálogo
  tabla: product_variants     pk: UUID(String36)
  parent: Product
  es_referenciado_por: [StockOnHand, SalesLine, Recipe, RecipeIngredient, BarBottle, Service, InventoryMovement]
  regla: "FKs a este id deben ser String(36)"

SalesDocument:  # agregado transaccional
  tabla: sales_documents      pk: UUID(String36)
  owns: [SalesLine, Payment]
  liga: [CashSession, Customer, Seller, Server, ParkedTicket(convertido)]
  emite: SalesDocumentCreated (vía outbox)

ParkedTicket:   # puente POS ↔ Mesas
  tabla: parked_tickets       pk: UUID(String36)
  doble_uso: [ticket pausado POS, cuenta abierta de mesa]
  raw_cols: [status, converted_to_sale_id]  # en railway_init, NO en el ORM

CashSession:
  tabla: cash_sessions        pk: Integer
  owns: [CashMovement, CashAuditLog]
  agrupa: SalesDocument (para arqueo)
  atribucion: Payment.cash_session_id (2026-09-22) — un pago cuenta en la sesión que lo
    recibió, no (solo) en la del documento de venta; SalesDocument.cash_session_id
    queda como respaldo/índice. Ver session_payments_filter en
    app/services/cash_reconciliation.py y docs/DATA_MODEL.md §Ventas / Caja.

DiningTable:    # agregado gastro-piso
  tabla: dining_tables        pk: Integer
  parent: DiningArea
  cuenta: current_ticket_id -> ParkedTicket
  estados: TableStatus  # máquina de estados validada

KitchenTicket:  # agregado gastro-cocina
  tabla: kitchen_tickets      pk: Integer
  owns: KitchenTicketItem
  estados: KdsStatus (deriva de ItemStatus)

Recipe:
  tabla: recipes              pk: Integer   (unique product_variant_id)
  owns: RecipeIngredient
  efecto: descuenta insumos al vender (subscriber)

BarBottle:
  tabla: bar_bottles          pk: Integer
  owns: BarBottleEvent (ledger inmutable)

Customer:
  tabla: customers            pk: Integer
  owns: CustomerLedgerEntry
  cross_org: el Portal agrega por email a través de orgs

Appointment:
  tabla: appointments         pk: Integer
  liga: [Customer, Professional, Resource, Service(via link), SalesDocument]
  owns: AppointmentEvent (bitácora)
```

---

## 4. Ontología de módulos

Cada módulo: qué es, qué posee (tablas/rutas/eventos), estado. Detalle en [`API_REFERENCE.md`](API_REFERENCE.md).

```yaml
# formato: module: {status, route, owns_tables, publishes, consumes, depends_on}

pos/sales:      {status: REAL, route: /api/sales,    owns: [sales_documents, sales_lines, payments, parked_tickets], publishes: [SalesDocumentCreated], gate: require_module(pos)}
cash:           {status: REAL, route: /api/cash,     owns: [cash_sessions, cash_movements, cash_audit_log]}
inventory:      {status: REAL, route: /api/inventory, owns: [inventory_movements, stock_on_hand]}
products:       {status: REAL, route: /api/products, owns: [products, product_variants, product_prices, packaging_units, product_branch_status, departments, brands, uom]}
customers/crm:  {status: REAL, route: /api/customers, owns: [customers, customer_ledger_entries]}
quotes:         {status: REAL, route: /api/quotes,   owns: [sales_documents(QUOTE/ORDER)], gate: require_module(quotes), gotcha: "convert-to-sale NO emite evento"}
returns:        {status: REAL, route: /api/returns,  owns: [sale_returns, sale_return_items]}
purchases:      {status: REAL, route: /api/purchases, owns: [purchase_orders, purchase_order_lines]}
expenses:       {status: REAL, route: /api/expenses, owns: [expenses]}
logistics:      {status: REAL, route: /api/logistics + /api/transfers, owns: [container_types, box_types, inbound_shipments, transfer_orders, transfer_fulfillments...], gate: require_module(warehouse)}
hr:             {status: REAL, route: /api/hr,       owns: [employees, branch_assignments, attendances]}
reports:        {status: REAL, route: /api/reports,  owns: [] (solo lee)}
printer:        {status: REAL, route: /api/printer,  owns: [print_jobs]}
tenants/org:    {status: REAL, route: /api/organization, owns: [organization, branches (self-service)]}
users:          {status: REAL, route: /api/users,    owns: [users, user_organizations], key: "/me/context da enabled_modules"}
auth:           {status: REAL, route: /api/auth,     owns: [] (JWT/login)}
portal:         {status: REAL, route: /api/portal,   owns: [], scope: CROSS-ORG por email}

# --- Gastro ---
tables:         {status: REAL, route: /api/tables,   owns: [dining_areas, dining_tables], consumes: SalesDocumentCreated (libera mesa), depends_on: [kitchen, sales/ParkedTicket]}
kitchen/kds:    {status: REAL, route: /api/kitchen,  owns: [kitchen_stations, kitchen_routes, kitchen_tickets, kitchen_ticket_items]}
recipes:        {status: REAL, route: /api/recipes,  owns: [recipes, recipe_ingredients], consumes: SalesDocumentCreated (descuenta insumos)}
bar:            {status: REAL(MVP), route: /api/bar,  owns: [bar_bottles, bar_bottle_events], gotcha: "sin subscriber de ventas"}
appointments:   {status: REAL, route: /api/appointments + /api/portal/booking, owns: [appointments_* (8 tablas)]}

# --- Platform (SUPERADMIN) ---
platform.*:     {status: REAL, route: /api/platform/*, owns: [platform_audit_log, platform_alert, platform_announcement, feature_flag, org_feature_override, platform_incident, api_key, + modules/presets], sub_routers: 16}

# --- Stubs (solo /health) ---
commissions|memberships|ai|purchasing: {status: STUB, route: /api/<x>, owns: []}

# --- Infra transversal ---
events/outbox:  {owns: [event_outbox], provee: EventBus + worker; ver ARCHITECTURE §3}
```

---

## 5. Ontología de eventos

```
SalesDocumentCreated
  —publicado_por→ sales.create_sale   (vía EventBus.enqueue en la MISMA txn)
  —entregado_por→ outbox (drain_now inmediato + worker con reintento/backoff)
  —consumido_por→ recipes.consume_ingredients_on_sale   ⇒ descuenta insumos (idempotente por reference=sale.id)
  —consumido_por→ tables.free_table_on_sale             ⇒ libera la mesa cuyo parked ticket se convirtió
  —consumido_por→ abasto.check_reorder_levels           ⇒ genera recomendaciones de reorden

Reglas:
  - Publicar SIEMPRE con enqueue(db, event) antes del commit (atómico con el negocio).
  - Todo subscriber DEBE ser idempotente (puede re-ejecutarse tras fallo parcial).
  - En SQLite el worker está gateado off (dev local no despacha solo).
  - Huecos: quotes.convert-to-sale NO publica; bar no consume ventas.
```

---

## 6. Ontología de RBAC

```
# Roles de tenant (Role) —puede_operar_en→ Contexto —landing→ Home
ADMINISTRADOR —opera→ HQ         (bypass module-gating; máximo alcance)
DUEÑO         —opera→ HQ         (bypass module-gating; alcance reducido)
GERENTE       —opera→ Branch     (POS + reportes de sucursal)
CAJERO        —opera→ Branch     (solo POS)
VENDEDOR      —opera→ Mobile     (ventas de campo)
SOPORTE_OPERATIVO —opera→ Mobile (solo consulta)
CLIENTE       —opera→ Portal     (estado de cuenta cross-org)

# Roles de plataforma (PlatformRole)
SUPERADMIN —accede→ /api/platform/* (ops destructivas)
SUPPORT    —accede→ /api/platform/* (read-only por convención)

# Mecánica de gating (DUAL, ver RBAC.md)
Route —gated_por→ require_module(key)      # solo pos/warehouse/quotes lo aplican a nivel router
Module —habilitado_si→ organization_modules.is_enabled
User(ADMIN|DUEÑO) —bypass→ require_module
View(frontend) —gated_por→ ATLAS_POS_ROLE_VIEWS (role_permissions.py)

# Aislamiento
Query —debe_filtrar→ organization_id        (helpers: get_tenant_scoped/scoped_query)
branch_id —NO_enforced_por→ framework       (ad-hoc por router → riesgo cross-sucursal)
```
⚠️ El RBAC es un control **débil** (12 huecos en [`RBAC.md §5`](RBAC.md)); no lo trates como candado de seguridad.

---

## 7. Ontología de presets y módulos

```
IndustryType(vertical) —tiene→ IndustryPreset —lista→ [module_key]
apply_industry_preset(org, industry) ⇒ upsert organization_modules(is_enabled=True) por cada key válida
  fuente_de_verdad: tabla industry_presets   (fallback: dict INDUSTRY_PRESETS en capabilities_service)
  filtro: keys deben existir en el catálogo `modules` (seed_global_modules)

Presets gastro:
  ATLAS_ONE_RESTAURANT —activa→ [pos, kitchen, tables, bar, recipes, menu, commissions, ...]  # superset
  ATLAS_ONE_CAFE       —activa→ [pos, kitchen, recipes, menu, ...]     # sin mesas/bar
  ATLAS_ONE_BAR        —activa→ [pos, tables, bar, recipes, menu, ...] # sin cocina

Frontend: /api/users/me/context —devuelve→ enabled_modules —consumido_por→ Sidebar (gating de nav)
```

---

## 8. Índice concepto→código

| Concepto | Dónde vive |
|---|---|
| Resolver org activa | `app/core/tenant_context.py::get_current_active_organization` |
| Filtrar por org | `app/core/tenant_query.py::{get_tenant_scoped, scoped_query, _resolve_org_id}` |
| Gating por módulo | `app/core/permissions.py::require_module` |
| Aplicar preset / capabilities | `app/services/capabilities_service.py` |
| Publicar evento | `app/core/events.py::EventBus.enqueue` |
| Despachar/outbox | `app/core/outbox.py` · tabla `event_outbox` |
| Reaccionar a evento | `app/subscribers/{recipes,tables,abasto}.py` |
| Checkout (motor ATS) | `app/routers/sales.py::create_sale` |
| Máquina de estados de mesa | `app/modules/tables/services.py::{set_status, free_table}` |
| Rutear comanda a estación | `app/modules/kitchen/services.py::resolve_station` |
| Costear/descontar receta | `app/modules/recipes/services.py::{compute_cost, consume_for_variant}` |
| Corte de bar / varianza | `app/modules/bar/services.py::bar_report` |
| Migraciones idempotentes | `scripts/railway_init.py` |
| Seed de módulos/presets | `scripts/init_presets_v2.py` · `capabilities_service.seed_global_modules` |
| Auth/JWT | `app/core/security/*` · `app/modules/auth/router.py` |

> Mantén esta ontología sincronizada al añadir conceptos/módulos/eventos. Es la capa que
> permite a un agente ubicarse sin re-derivar el sistema. Detalle exhaustivo en los demás `docs/`.
