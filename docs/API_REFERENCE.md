# Referencia de API · Atlas BOS

Catálogo de endpoints por dominio. Todos bajo `/api`. Swagger vivo en `/docs`. Fuente: auditoría profunda (julio 2026).

**Convenciones de gating** (ver [`RBAC.md`](RBAC.md)):
- `auth` = requiere `get_current_user` (JWT). `org` = requiere org activa (`get_current_active_organization`).
- Rol entre corchetes = restricción de rol en el endpoint. `[module:x]` = requiere módulo habilitado (`require_module`).
- HQ = ADMINISTRADOR/DUEÑO (org-wide); branch = GERENTE/CAJERO (limitado a su sucursal).

> ⚠️ Solo 3 routers exigen módulo (`sales`→pos, `logistics`→warehouse, `quotes`→quotes). El resto (incluidos los gastro) solo pide auth + tenant scope. ADMIN/DUEÑO hacen bypass del gating por módulo.

---

## Auth · `/api/auth`
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| POST | /login | Login PIN (OAuth2), emite JWT + cookie | público |
| POST | /context/switch | Reemite JWT con otra sucursal/contexto | [ADMIN/SUPERADMIN o org_role=ADMIN] |
| POST | /logout | Borra cookies | público |

## Users · `/api/users`
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| GET | /me/context | **Contexto del frontend**: user, org, branch, preset, `enabled_modules`, templates | auth |
| GET | / · GET /me · GET /{id} | Lista / actual / detalle (`UserRead.has_reprint_pin`, derivado, nunca el hash) | auth+org |
| POST | / · PUT /{id} · DELETE /{id} | Crear / editar / soft-delete; acepta `reprint_pin` (4-8 dígitos, `""` borra, 422 fuera de formato) | [admin/dueño] **(2026-09-19)** — antes sin check de rol admin, cualquier cajero podía tocar `/api/users`; corregido junto con el PIN |

## Organización · `/api/organization` (+ `/api/org/capabilities`, `/api/departments`, `/api/brands`)
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| GET/PUT | /organization/ | Org activa / update (no-admin solo campos de impresora, ticket y comisión — misma whitelist) | auth (admin p/ resto) |
| POST/DELETE | /organization/logo | Logo | [admin] |
| GET | /org/capabilities/ | enabled_modules + nav + default_routes por industria | auth |
| GET | /organization/exchange-rate **(2026-09-17)** | `{mode, rate, source, fix_rate, fix_date, margin, manual_rate}` — tipo de cambio USD resuelto; `rate: null` si `mode='off'` o no se puede resolver | auth (cualquier usuario de la org, lo consume la cajera) |
| POST | /organization/exchange-rate/refresh **(2026-09-17)** | Baja el FIX de Banxico bajo demanda (`{ok, rate_date, rate, source}` o 503 si falta `BANXICO_TOKEN`/falla Banxico) | [admin/dueño] |
| GET | /organization/card-surcharge **(2026-09-17)** | `{"pct": 3.50}` — % de comisión por pago con tarjeta configurado, `SELECT` barato sin red | auth |
| — | /departments, /brands | CRUD de departamentos y marcas | auth+org |

## Setup · `/api/setup`
`POST /initialize` — aplica preset de industria a la org `[ADMINISTRADOR/DUEÑO]`.

---

## Ventas / POS · `/api/sales` `[module:pos]` — motor ATS-crítico
| Método | Ruta | Qué hace |
|---|---|---|
| GET | /stats | KPIs de ventas (branch-scoped salvo HQ) |
| GET · POST | / | Lista paginada · **create_sale** (checkout) |
| GET | /by-folio/{series}/{folio} · /my-last · /{id} · /{id}/print-view | Detalle / última / ticket HTML |
| DELETE | /{id} | **cancel_sale** (revierte stock + deuda) |
| POST | /{id}/refund | Stub (no-op) |
| GET | /export/csv | Export CSV — columnas 2026-09-17 **«Comisión tarjeta»** y **«Total cobrado»** después de «Total» |
| POST/GET/PATCH/DELETE | /parked[/{id}] | Tickets pausados / cuentas de mesa (park, resume, merge cart, soft-delete) |

**create_sale** (resumen): gate de caja abierta (branch users); resolución batch de variantes/stock/PBS; validación de stock + techo de descuento (50%); IVA; **propina** (`tip_amount` suma al total y se persiste para reporte por-mesero); validación de pagos + `change_given`; crédito a cliente (→PENDING); `server_user_id` copiado de la mesa; parked→CONVERTED; **`EventBus.enqueue(SalesDocumentCreated)` en la misma txn** + `drain_now`. Commit atómico. Ver [`ARCHITECTURE.md`](ARCHITECTURE.md) §3.

**Añadidos 2026-09-17, ambos con salida temprana neutra si no aplican (no tocan el resto del flujo si `pct=0`/modo `off`):**
- Si `customer_id` llega sin `customer_name`, lo rellena desde el cliente de la misma org (`[:255]`).
- Snapshot de `usd_rate` (envuelto en `try/except → None`: si Banxico o el servicio fallan, la venta se cobra igual) y de `card_surcharge_pct`/`card_surcharge_amount` (la comisión se suma a `cash_needed` y a la validación de cobertura de pagos — **no** a `total_amount` ni a `balance_diff`, que siguen siendo mercancía). `SaleRead` expone ambos snapshots en todas las lecturas (`GET /`, `/{id}`, `/by-folio/...`, `/my-last`).

## Caja · `/api/cash`
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| GET | /status · /history · /summary | Sesión abierta / cortes / audit UI | auth |
| POST | /open · /close · /sessions/{id}/close-guided | Abrir / cerrar / cierre guiado (conteo ciego: el cajero declara lo contado antes de ver el esperado) | dueño de turno (guiado: +GERENTE/ADMIN/DUEÑO) |
| PATCH | /sessions/{id}/opening-balance | Corrige el fondo declarado al abrir — solo si la caja sigue limpia (sin ventas/movimientos); exige `reason` (≥10 caracteres) | dueño de turno o GERENTE/ADMIN/DUEÑO |
| POST | /movements · /inflow · /outflow | Movimientos de efectivo manuales (motivo obligatorio ≥10 caracteres; salidas >$2,000 exigen GERENTE+) | auth |
| GET | /{id}/audit-log · /branch-summary | Timeline / corte consolidado | [ADMIN/DUEÑO/GERENTE] |
| GET | /{id}/pdf · /{id}/ticket | Corte PDF / JSON ESC-POS | acceso a sesión |

> Cerrar bloquea si hay parked tickets sin convertir (409). Reconciliación vía `services/cash_reconciliation`.
> `get_session_audit_data` agrega `card_surcharges` (2026-09-17): suma de `card_surcharge_amount` de las ventas de la sesión, informativo, **no** entra en `Total cobrado` (la comisión ya viaja dentro del pago `CARD`). Lo consumen `/{id}/pdf`, `/{id}/ticket` y la UI del corte.
> **Atribución del efectivo por pago (2026-09-22):** un pago cuenta en el corte de la
> sesión que apunta en `payments.cash_session_id`, no (solo) en la del documento de
> venta — así un abono a crédito cobrado en un turno distinto al de la venta original
> ya no descuadra el corte que sí lo recibió. Regla e idempotencia en
> `app/services/cash_reconciliation.py::session_payments_filter`; detalle en
> `docs/DATA_MODEL.md §Ventas / Caja`. `register_customer_payment` (abono de cliente)
> ahora exige caja abierta para abonos en efectivo (409 si no la hay) — tarjeta y
> transferencia siguen sin exigirla.

## Inventario · `/api/inventory`
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| POST | /adjust | Ajuste IN/OUT (merma = ADJUSTMENT_OUT) — `with_for_update` | non-admin forzado a su branch |
| POST | /transfer | Traspaso inmediato entre sucursales | non-admin solo desde su branch |
| GET | /kardex/{variant_id} | Historial (100 movs) | HQ ve otras branches |

## Logística · `/api/logistics` `[module:warehouse]`
| Método | Ruta | Qué hace |
|---|---|---|
| POST/GET | /containers · /boxes | Tipos de contenedor/caja (⚠️ sin tenant scope; sin user) |
| POST | /calculate | Cálculo de carga + histórico |
| CRUD | /shipments[/{id}[/items]] | Entradas de mercancía |
| POST | /shipments/{id}/receive | Finaliza: StockOnHand + Movement(PURCHASE_IN) |

## Transferencias · `/api/transfers`
`POST /` crear · `GET /` listar · `POST /{id}/fulfill` · `POST /fulfillment/{id}/ship` (Movement TRANSFER_OUT) · `POST /fulfillment/{id}/receive` (TRANSFER_IN). Traspaso formal con fulfillment (distinto de `/inventory/transfer`).

## Productos / Catálogo · `/api/products` (11 sub-routers)
CRUD productos + aprobar/rechazar/restore/duplicate/imagen; `search` (variants/pos search — ⚠️ inalcanzable, ver gotchas); `stats` (catalog-kpis, branch-kpis); `packaging`; `branch_status` (habilitación de catálogo por sucursal); `bulk` (batch-action); `import_export` (excel upload/export, ⚠️ no conoce `gender/model/material`); `reports` (hq-inventory); `audit` ({id}/audit-log); `barcodes` (2026-09-19). Todo tenant-scoped.

**Variantes color/talla (módulo `variants`, 2026-09-17):**

| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| POST | /{product_id}/variants | Crea una o más variantes (matriz color×talla) del producto | [module:variants] |
| PUT | /variants/{variant_id} | Edita una variante existente | [module:variants] |
| DELETE | /variants/{variant_id} | Soft-delete de una variante | [module:variants] |
| GET | /sku-suggest?brand=&name=&model=&color=&size=&gender= **(2026-09-21)** | `{"sku": "...", "available": bool}` — SKU sugerido (`MARCA-PRENDA[-INICIALES]-MODELO[-MUJ\|NIN]-COLOR-TALLA`); es una sugerencia, no se aplica sola | auth+org |

**Códigos de barras y etiquetas (2026-09-19, ver [`presets/BOUTIQUE.md §2.4`](presets/BOUTIQUE.md)):**

| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| GET | /barcodes/missing-count | `{"missing": n}` de variantes visibles sin código | auth+org |
| POST | /barcodes/assign-missing | Genera EAN-13 interno (`2`+org+secuencia+verificador) a las variantes sin código; body opcional `{product_id}` | [admin/dueño] |
| GET | /export/labels.csv?product_id=&only_with_stock= | CSV de etiquetas (UTF-8 con BOM): `SKU,Codigo de barras,Producto,Marca,Talla,Color,Precio,Existencia,Genero,Modelo,Material,Nombre de venta` | auth+org (scope de `query_visible_products`) |

---

## CRM / Clientes · `/api/customers`
`GET /stats · / · /{id}` · `POST / · PUT/DELETE /{id}` · `GET /{id}/statement · /{id}/unpaid-documents · /{id}/pdf-statement` · `POST /{id}/pay`. Crédito + estado de cuenta. Tenant-scoped correcto.

## Cotizaciones · `/api/quotes` `[module:quotes]`
`POST / · GET / · GET/PUT/DELETE /{id}` · `GET /{id}/pdf` · **`POST /{id}/convert-to-sale`** (crea venta PAID; ⚠️ **no** emite el evento outbox → no dispara consumo de insumos/mesa) · `GET /stats/kpi`.

## Devoluciones · `/api/returns`
`GET /stats` (⚠️ sin user) · `POST /` crear PENDING · `GET /sale/{id} · / · /{id}` · `POST /{id}/approve` (force p/ refunds >$10k; 409 si caja cerrada) · `POST /{id}/reject`. Approve/reject `[ADMIN/DUEÑO/GERENTE]`.

## Compras · `/api/purchases`
`GET /stats · / · /{id}` (⚠️ sin user) · `POST /` crear PO · `PATCH /{id}/status` · `POST /{id}/receive` (stock + costo promedio + Movement) · `DELETE /{id}`.

## Gastos · `/api/expenses`
`GET /stats · /categories · /` (⚠️ sin user) · `POST /` · `DELETE /{id}`.

## RRHH · `/api/hr`
`GET/PUT /employees/me` (self-service) · CRUD `/employees[/{id}]` · `POST /employees/{id}/assign` · `POST /attendance/check-in|check-out` · `GET /attendance/report`. (⚠️ sin gate de rol admin.)

## Reportes · `/api/reports`
| Ruta | Qué hace |
|---|---|
| /daily-summary · /dashboard · /sales-by-hour | Ventas del día / KPIs+charts+alerts / por hora |
| /command-center/stats | Mission control multi-sucursal (agregado, sin N+1) |
| **/by-waiter** | Ventas + **propinas** por mesero (`coalesce(server_user_id, seller_id)`) |
| /audit/discrepancies · /aging-report · /product/{id} · /export/csv | Arqueos / antigüedad de saldos / analítica de producto / CSV |

## Impresora · `/api/printer`
`POST /test-print · /print-ticket · /reprint-ticket/{id} · /reprint-refunded/{id} · /print-cash-cut` · `GET /printers · /download-agent`. Genera ESC/POS base64 (el agente local imprime, no el server). Registra `PrintJob`. `reprint-ticket`/`reprint-refunded` aceptan `pin` (2026-09-19): si la venta no es propia-y-reciente, primero prueban el PIN de reimpresión de un supervisor (`users.reprint_pin_hash`) y si no, su contraseña.

`GET /download-agent?platform=windows|linux|mac` — redirige (302) al repositorio del
agente, <https://github.com/Ecamposg95/Atlas-Print-Agent> (ZIP de `main`; dentro,
`legacy/print_agent/` trae los launchers e instaladores de autoarranque). El agente ya no
vive en este repo (2026-09-22). `ATLAS_PRINT_AGENT_URL` sobreescribe el destino y admite
`{platform}` para cuando el repo publique un ZIP por plataforma. Runbook de
autoarranque en `docs/superpowers/runbooks/print-agent-autostart.md`.

## Etiquetas · `/api/labels` `[module:labels]`
`GET /candidates` (filtros `search`, `department_id`, `brand_id`, `gender`, `only_with_stock`, `product_id`) devuelve una fila por variante visible con sus campos de etiqueta y `copies_default` = existencia (admin/dueño suman la organización, el resto su sucursal; tope 99). Las no imprimibles NO se esconden: llegan con `printable:false` y su `reason`. `POST /preview` (`{variant_id}` o datos sueltos) devuelve el layout en dots sobre un lienzo 408×200 —`elements` con textos y el código de barras en `bits`— más el ZPL crudo, para que la pantalla dibuje exactamente lo que va a salir. `POST /jobs` (`{items:[{variant_id, copies}]}`, copias 1..99, tope de 500 etiquetas por lote) devuelve `{content_base64, labels, skipped}`; un renglón sin código de barras cae en `skipped` sin tumbar el trabajo. `GET /test` da la etiqueta de calibración. **El server no imprime**: entrega ZPL en base64 y el navegador lo manda al agente local (`POST https://localhost:9100/print`), igual que el ticket. El layout está portado byte a byte de `atlas_labels/` del repositorio del agente (51 × 25 mm a 203 dpi, Zebra GX420t) y un test lo congela contra un literal.

## Portal cliente · `/api/portal`
`GET /accounts · /my-account/balance · /quotes · /my-account/transactions`. **Sin tenant scope** (cross-org por email del usuario). ⚠️ Contiene fallbacks demo y accesos a atributos posiblemente inexistentes.

## Branch dashboard · `/api/branch`
`GET /dashboard` — dashboard de una sucursal (branch de `current_user.branch_id` o header `X-Branch-ID`).

---

## Gastro

### Mesas · `/api/tables`
CRUD `/areas` y `/` (mesas) · `POST /{id}/open` (crea ParkedTicket, lock anti doble-apertura) · `POST /{id}/free` (abandona cuenta + cancela KDS) · `POST /{id}/transfer` · `POST /{id}/assign-server` · `PATCH /{id}/status` (máquina de estados validada). Subscriber libera la mesa al cobrar.

### Cocina / KDS · `/api/kitchen`
CRUD `/stations`, `/routes` (dept→estación) · `POST /tickets` (fire) · `GET /tickets[/{id}]` (feed) · `POST /tickets/{id}/bump?station_id=` (avance por estación) · `/recall` · `/cancel` · `POST /items/{id}/bump|void` · `GET /stats` (ventana 24h).

### Recetas · `/api/recipes`
`GET / · GET/POST/PUT/DELETE /{id}` · `GET /{id}/cost` (costeo + margen). Subscriber descuenta insumos al vender (idempotente).

### Bar · `/api/bar`
`GET/POST /bottles` · `GET /report` (**corte de turno**: servido/merma/varianza) · `POST /bottles/{id}/pour|waste|refill` · `DELETE /bottles/{id}` (archiva). Ledger inmutable `bar_bottle_events`.

### Appointments · `/api/appointments` (staff) + `/api/portal/booking` (cliente)
**Staff** (27): CRUD `/resources`, `/professionals` (+ `/schedule`, `/blocks`), `/services` (`/from-variant`); `GET /availability` (slots); `GET/POST/PUT /appointments`; transiciones `/confirm · /start · /complete · /cancel · /no-show`. **Portal público** (9): `/register` (crea CLIENTE+JWT), `/me`, `/branches`, `/services`, `/professionals`, `/availability`, `POST/GET /appointments`, `/appointments/{id}/cancel` (política 24h). Anti double-booking con `pg_advisory_xact_lock`.

---

## Platform (SaaS) · `/api/platform/*` — todo `[SUPERADMIN o SUPPORT]`
16 sub-routers (`app/routers/platform/`), montados con guard `require_platform_admin` a nivel router. Ops destructivas revalidan SUPERADMIN en el handler.

| Sub-router | Prefijo | Qué gestiona |
|---|---|---|
| stats | /stats/* | KPIs cross-tenant (global, trends, top-tenants, cohort, heatmap…) — caché TTL |
| control_tower | /control-tower/* | Dashboard tiempo-real (sales-now, active-sessions, deltas) |
| organizations | /organizations | **CRUD de tenants** + módulos/preset por org; `apply-preset`, `modules/{key}` toggle, `industry`, `bootstrap`, `reset-preset`, delete `?force=` (cascade ~30 tablas) `[SUPERADMIN]` |
| branches | /branches | Sucursales cross-tenant (CRUD, archive) |
| users | /users | Usuarios cross-tenant (CRUD, reset-password, `role` `[SUPERADMIN]`) |
| admins | /admins | Platform-admins (invite, manual, role, revoke) `[SUPERADMIN]` |
| modules | /modules | Catálogo global (catalog, counts, dependencies; CRUD `[SUPERADMIN]`) |
| presets | /presets | CRUD de industry presets (system presets protegidos) |
| feature_flags | /flags | Flags con rollout determinístico (crc32) + overrides por org; resolved/preview |
| incidents | /incidents | Incident mode (suspensión masiva por scope; restaura por snapshot) `[SUPERADMIN]` |
| alerts | /alerts | Inbox de anomalías (scan, ack, resolve) |
| announcements | /announcements | Broadcast a tenants (targeting, publish) |
| api_keys | /api-keys | API keys server-to-server (SHA-256, secreto una vez) |
| health | /health/matrix | Salud por tenant (score, última venta, revenue) |
| reports | /reports/* | Reportería cross-tenant + export CSV streaming |
| audit | /audit/logs | Bitácora de acciones del superadmin |
| impersonation | /impersonate[/exit] | ⚠️ **Stub**: audita pero no emite JWT scoped |

---

## Stubs / Beta (solo `GET /health`, `ready:false`)
`/api/commissions`, `/api/memberships`, `/api/ai`, `/api/purchasing`. (Nota: compras REAL vive en `/api/purchases`; `/api/purchasing` es el placeholder del rediseño modular.)

---

## Gotchas transversales (para quien consume la API)
- **`convert-to-sale` de quotes NO dispara el evento outbox** (a diferencia de `create_sale`): no descuenta insumos ni libera mesa. Tampoco congela `usd_rate` ni comisión de tarjeta (ambos son exclusivos de `create_sale`).
- **`GET /api/products/search` es inalcanzable** (preexistente, hallado 2026-09-21): `core.router` monta `/{product_id}` antes que `search.router` en `app/modules/products/router/__init__.py`, así que cualquier ruta declarada en `search.py` queda tapada por el match de `/{product_id}`.
- **Las mutaciones de `/products/{id}/variants` y `/products/variants/{id}`** exigen `require_module("variants")`; los endpoints de `barcodes.py` no lo exigen (solo rol donde aplica). Recuerda que ADMIN/DUEÑO hacen bypass de `require_module` en general (RBAC.md §5): un admin de una org sin el módulo `variants` activo puede llamar el endpoint de variantes a mano aunque la UI no se lo muestre.
- **Endpoints sin `get_current_user`** (solo `org_id`, menor atribución de auditoría): `returns:/stats`, `purchases:/stats,/,/{id}`, `expenses:/stats,/categories,/`, `transfers:/,/{id}/fulfill`. Logistics `/containers`,`/boxes` no tienen ni org (sin tenant scope).
- **Debug prints en prod**: `sales.py` (export CSV), `quotes.py` (create).
- **Definición de "HQ" divergente**: `reports/dashboard` y `command-center` excluyen GERENTE; pero `sales-by-hour`/`by-waiter`/`export-csv` lo incluyen como HQ.
