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
| GET | /me/context | **Contexto del frontend**: user, org, branch, preset, `enabled_modules`, `plan: {clave, nombre}` (null sin org activa), templates · `modulos_no_disponibles` (objeto `{clave_de_módulo: "en_construccion" | "oculto"}` con los módulos que la interfaz NO debe mostrar aunque estén en `enabled_modules`, porque no están construidos; sale de `app/services/estado_modulos.py::no_disponibles`; es global, igual para toda organización, y solo de interfaz: `enabled_modules` no se recorta y `require_module` sigue permitiendo lo mismo; el frontend guarda un espejo en `frontend/src/utils/estadoModulos.ts`) · `perfil_ui` (`basico`|`completo`; solo plan `FREE` explícito → básico, el resto completo; forzable por la plataforma; ver `docs/modo-basico.md`) · `campos_producto` `{visibles, ocultos}` (en básico además oculta `brand_id, description, unit, image_url, tax_rate, packaging_units, variants`): qué campos del formulario de producto muestra el giro (ficha boutique `gender/model/material` solo en `ATLAS_POS_BOUTIQUE`; `variants` solo con el módulo) | auth |
| GET | / · GET /me · GET /{id} | Lista / actual / detalle (`UserRead.has_reprint_pin`, derivado, nunca el hash) | auth+org |
| POST | / · PUT /{id} · DELETE /{id} | Crear / editar / soft-delete; acepta `reprint_pin` (4-8 dígitos, `""` borra, 422 fuera de formato) | [admin/dueño] **(2026-09-19)** — antes sin check de rol admin, cualquier cajero podía tocar `/api/users`; corregido junto con el PIN |

## Organización · `/api/organization` (+ `/api/org/capabilities`, `/api/departments`, `/api/brands`)
| Método | Ruta | Qué hace | Gating |
|---|---|---|---|
| GET/PUT | /organization/ | Org activa / update (no-admin solo campos de impresora, ticket y comisión — misma whitelist) | auth (admin p/ resto) |
| POST/DELETE | /organization/logo | Logo | [admin] |
| GET | /org/capabilities/ | enabled_modules + `plan: {clave, nombre}` + nav + default_routes por industria | auth |
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
| GET | /stats | **CAJERO → 403** («Los totales del día no están disponibles para la cajera.»). KPIs de ventas: neto de devoluciones aprobadas, sin pendientes ni borradores; trae `gross_sales` (`app/services/metricas_ventas.py`). Una sola fecha = ese día; rango invertido = 422. Ámbito: ADMINISTRADOR/DUEÑO sin `branch_id` = toda la org; GERENTE: siempre su sucursal (ignora `branch_id`, como la lista `GET /`); los demás roles, la suya |
| GET · POST | / | Lista paginada (**CAJERO**: solo las ventas de hoy, día de México, de su sucursal; ignora `start_date`/`end_date`/`branch_id`) · **create_sale** (checkout) |
| GET | /by-folio/{series}/{folio} · /my-last · /{id} · /{id}/print-view | Detalle / última / ticket HTML (**CAJERO**: `/by-folio/...`, `/my-last`, `/{id}` y `/{id}/print-view` dan 404 si la venta no es de hoy y de su sucursal —`/by-folio` con «Venta no encontrada»—; regla en `app/services/ventas_cajero.py`) |
| DELETE | /{id} | **cancel_sale** (revierte stock + deuda) |
| POST | /{id}/refund | Stub (no-op) |
| GET | /export/csv | **CAJERO → 403** («La exportación de ventas no está disponible para la cajera.»). Export CSV — columnas 2026-09-17 **«Comisión tarjeta»** y **«Total cobrado»** después de «Total» |
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
> **Fiado y abonos en el corte (2026-10-31):** la auditoría del corte (`get_session_audit_data`, que consumen `/{id}/ticket` y la pantalla) trae `kpis.credit_sales` (lo fiado en las ventas del turno) y `kpis.customer_payments` (abonos a cuenta recibidos); el ticket imprime los renglones `Fiado` y `Abonos a cuenta` cuando son mayores que cero, y `expected.total_system` = ventas − fiado + fondo + entradas − salidas − reembolsos en efectivo; no suma los abonos del turno. `/branch-summary` repite `credit_sales`/`customer_payments` en `totals` y en cada `cashiers[]`. El efectivo esperado sigue sumando `Payment.amount` (lo que entró al cajón); la única corrección es que el **abono libre** (pago sin ticket) ya entra al esperado y al desglose por método (`filtro_pago_cobrado`).
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
| GET | /revision-fiscal?branch_id=&problema=&limit=&offset= | Productos sin tasa de IVA del SAT (`SIN_CLASIFICACION`) o con discrepancia contra `has_iva`/`tax_rate` (`DISCREPANCIA`), por sucursal: `{resumen, items, total, limit, offset}`. Solo lectura | auth+org (admin/dueño: todas; resto: su sucursal) |
| GET | /export/revision-fiscal.csv?branch_id= | La misma lista completa en CSV (UTF-8 con BOM) | auth+org (mismo alcance) |
| GET | /export/labels.csv?product_id=&only_with_stock= | CSV de etiquetas (UTF-8 con BOM): `SKU,Codigo de barras,Producto,Marca,Talla,Color,Precio,Existencia,Genero,Modelo,Material,Nombre de venta` | auth+org (scope de `query_visible_products`) |

---

## CRM / Clientes · `/api/customers`
`GET /stats · /cobranza · / · /{id}` · `POST / · PUT/DELETE /{id}` · `GET /{id}/statement · /{id}/unpaid-documents · /{id}/pdf-statement` · `POST /{id}/pay` · `POST /{id}/deuda-anterior · DELETE /{id}/deuda-anterior/{entry_id}`. Crédito + estado de cuenta. Tenant-scoped correcto.

Auditoría del crédito (2026-10-28, `docs/AUDITORIA-CRM-CREDITO-2026-10-28.md`): la regla de cuánto debe un ticket vive en `app/modules/customers/services.py`. `POST /{id}/pay` con `sales_document_id` aplica todo a ese ticket y responde 422 si excede lo que **ese ticket** debe; sin ticket (abono libre) reparte del más viejo al más nuevo, un asiento por ticket, cada ticket cubierto pasa a PAID y lo que sobra queda a favor (asiento sin ticket). `/{id}/unpaid-documents` lee el saldo del ledger y excluye cancelados y devueltos por completo. Fiar: `POST /api/sales/` con `customer_id` acepta pagos parciales (lo que falta se carga al cliente y `has_credit` se enciende solo); sin cliente, un pago parcial sigue siendo 422. `DELETE /api/sales/{id}` revierte lo que ese ticket cargó. Una devolución aprobada sobre una venta fiada baja primero la deuda y solo entrega el excedente.

**Cobranza (2026-10-31, spec `docs/superpowers/specs/2026-10-29-crm-cobranza-design.md`).**
- `GET /api/customers/cobranza` (solo `HQ_ROLES` de `metricas_ventas`: ADMINISTRADOR, GERENTE, DUEÑO, y SUPERADMIN; los demás 403) — cuentas por cobrar. Parámetros: `branch_id` (solo lo respetan ADMINISTRADOR, DUEÑO y SUPERADMIN; al GERENTE se le impone la suya —403 sin sucursal—, igual que `/inicio`, para que la tarjeta Por cobrar y esta lista cuadren), `bucket` (`current|31_60|61_90|91_plus`, otro valor 422), `search` (nombre/teléfono), `skip`, `limit` (1..200, default 50), `order` (`saldo` default | `antiguedad`). Responde `{resumen{por_cobrar, vencido_30, clientes, a_favor}, total, items[{id, name, phone, balance, cargo_mas_viejo, dias, ultimo_abono, branch_id, branch_name, tickets_abiertos, antiguedad{current, 31_60, 61_90, 91_plus}}]}`. Solo entran clientes con saldo deudor; el saldo a favor suma aparte en `a_favor` y no resta de `por_cobrar`; `total` es el número de clientes tras filtrar (antes de paginar). La antigüedad aplica los asientos ligados a un ticket (reversiones, `ABONO A TICKET`) al cargo de su propio documento y solo los abonos libres corren FIFO sobre lo que quede; esa misma regla alimenta también `/api/reports/aging-report`, cuyos cubos cambiaron en consecuencia.
- `POST /api/customers/{id}/pay` responde `AbonoResponse`: `entries[]` (asientos), `customer_balance_before/after`, `applied[{sales_document_id, folio, amount, paid_in_full}]` (`paid_in_full` sale de lo que el ticket todavía debe, no del estado del documento), `unapplied` (saldo a favor que quedó sin ticket), `payment_id`, `method`, `reference`, `received_at`. Un abono en efectivo sin sucursal (rol de oficina sin `branch_id`) se rechaza con 422 «Para recibir efectivo elige una sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar»; con sucursal pero sin caja abierta sigue el 409 de siempre. Cada asiento que escribe `aplicar_abono` termina en ` [AB-XXXXXXXX]`, el folio del recibo.
- **Deuda anterior** (2026-11-04): `POST /api/customers/{id}/deuda-anterior` `{amount > 0, fecha (no futura), nota?}` carga lo que la clienta ya debía antes del sistema (la libreta) como asiento **sin ticket** `Deuda anterior[: nota]` fechado el día de la deuda (mediodía de México); responde `{entry, customer_balance}`. No es venta: `fiado`, la venta neta y el corte solo leen asientos ligados a un ticket. El abono libre la cubre **antes** que los tickets (asiento `ABONO A DEUDA ANTERIOR: …`) y `AbonoResponse.deuda_anterior` dice cuánto; `unapplied` ya no lo cuenta como saldo a favor. `DELETE /{id}/deuda-anterior/{entry_id}` la borra (404 si el asiento no es deuda anterior, 409 si después llegó un abono sin ticket). Ambos solo dueño/administrador/SUPERADMIN (`require_admin_or_owner`) y dejan rastro en `platform_audit_log` (`CUSTOMER_DEUDA_ANTERIOR_CREATE/DELETE`).
- `POST /api/printer/print-abono/{payment_id}` — recibo del abono (`RECIBO DE ABONO`, folio `AB-{payment_id[:8].upper()}`): `{status, job_id, content_base64, printer_target}`, mismo contrato que el ticket (el agente local imprime). 404 si el pago no es un abono de cliente o es de otra org; 403 salvo rol de oficina o quien cobró el abono. Reimprimir es volver a llamar (sin PIN) y reproduce el recibo original: saldos reconstruidos deshaciendo los asientos posteriores al abono, «Le atendió» = quien registró el abono y sucursal = la de la caja que lo recibió (cae al usuario/sucursal actual si faltan); solo las marcas «liquidado» de cada ticket reflejan la deuda al momento de imprimir.

## Cotizaciones · `/api/quotes` `[module:quotes]`
`POST / · GET / · GET/PUT/DELETE /{id}` · `GET /{id}/pdf` · **`POST /{id}/convert-to-sale`** (crea venta PAID; ⚠️ **no** emite el evento outbox → no dispara consumo de insumos/mesa) · `GET /stats/kpi`.

## Devoluciones · `/api/returns`
`GET /stats` (⚠️ sin user) · `POST /` crear PENDING (usuarios de sucursal solo sobre ventas de su sucursal, si no 404; **CAJERO/VENDEDOR** (2026-11-24) solo dentro del plazo de la tienda `organization.dias_ventas_caja`, si no 403; reembolso por el método con que se pagó, si no 400; efectivo exige turno abierto, si no 409; `reason_code` de catálogo opcional; se **aprueba sola** si el total ≤ `organization.devolucion_libre_hasta` (`autorizacion=POLITICA`), si no queda PENDING; el GERENTE devuelve cualquier fecha) · `GET /motivos` catálogo · `GET /sale/{id}/piezas` vendido/devuelto/en trámite/disponible por pieza, métodos de reembolso, pendiente y monto libre · `POST /{id}/autorizar` `{pin}` aprueba una pendiente con el PIN de un gerente en la caja (`autorizacion=PIN`; 403 `PIN_INCORRECTO`, 423 tras 3 intentos, mismo contador que la reimpresión) · comprobante: `POST /api/printer/print-return/{id}` · `GET /sale/{id} · / · /{id}` (`/` acepta `start_date`/`end_date` `YYYY-MM-DD` en día de México, una sola fecha = ese día, rango invertido = 422, `branch_id` para roles de oficina y `status`; sin fechas, todo el historial: la pantalla pondrá el rango en la Fase 3) · `POST /{id}/approve` (force p/ refunds >$10k; 409 si caja cerrada) · `POST /{id}/reject`. Approve/reject `[ADMIN/DUEÑO/GERENTE]`. **Vale y cambio (2026-11-24):** `POST /` acepta `destino` = `DINERO` (omisión) \| `VALE` \| `CAMBIO`; con vale/cambio `refund_method` queda en `OTHER`, no sale efectivo y al aprobar se emite un vale (`vale` en la respuesta: `code`, `balance`). Un ticket pagado por completo con vale solo se devuelve a vale desde la caja (400 si pide dinero).

### Vales de tienda — `/api/vales` (`app/routers/vales.py`, 2026-11-24)
`GET /{codigo}` saldo, estado y movimientos de un vale de la organización (404 si no existe; cualquier rol de tienda) · `GET /` lista con `estado`/`customer_id` (CAJERO/VENDEDOR → 403) · `POST /{id}/cancelar` `[ADMIN/DUEÑO]` anula el saldo. **Cobro:** en `POST /api/sales/` el vale viaja como pago `{method: "OTHER", amount, reference: "VALE:<código>"}`; `app/services/vales.py::aplicar_vales_en_venta` le baja el saldo dentro de la transacción de `create_sale` (400 si no existe, está cancelado o no alcanza). Cancelar la venta (`DELETE /api/sales/{id}`) restituye el saldo.

### CRM de clientes — `/api/customers` (`app/modules/customers/router_crm.py`, 2026-11-24; se monta antes del router de clientes)
`GET /campos` campos propios activos · `POST /campos`, `PUT /campos/{id}`, `DELETE /campos/{id}` `[ADMIN/DUEÑO]` (tope 10 activos; tipos TEXTO, NUMERO, FECHA, LISTA, SI_NO) · `GET /seguimiento` (`estado` PENDIENTE\|HECHO\|TODOS, `customer_id`, `hasta`; la caja ve los de su sucursal y los suyos) · `POST /seguimiento` · `POST /seguimiento/{id}/hecho` `{resultado}` · `DELETE /seguimiento/{id}` · `GET /{id}/ficha` ficha 360 (datos, saldo, crédito disponible, compras, lo que más compra, vales, seguimiento; a CAJERO/VENDEDOR sin acumulados y solo compras de su sucursal en el plazo de la tienda). `POST /` y `PUT /{id}` aceptan `tipo` (MENUDEO\|MAYOREO), `birthday`, `company` y `campos`; desde la caja el alta solo toma nombre, teléfono, correo y nota (lo demás se ignora) y editar otra cosa da 403.

## Compras · `/api/purchases`
`GET /stats · / · /{id}` (⚠️ sin user) · `POST /` crear PO · `PATCH /{id}/status` · `POST /{id}/receive` (stock + costo promedio + Movement) · `DELETE /{id}`.

## Gastos · `/api/expenses`
`GET /stats · /categories · /` (⚠️ sin user) · `POST /` · `DELETE /{id}`.

## RRHH · `/api/hr`
`GET/PUT /employees/me` (self-service) · CRUD `/employees[/{id}]` · `POST /employees/{id}/assign` · `POST /attendance/check-in|check-out` · `GET /attendance/report`. (⚠️ sin gate de rol admin.)

## Reportes · `/api/reports`
| Ruta | Qué hace |
|---|---|
| /daily-summary · /dashboard · /sales-by-hour | **CAJERO → 403** («Los totales del día no están disponibles para la cajera.»; ninguna pantalla suya los llama). Ventas del día / KPIs+charts+alerts / por hora. `low_stock` de `/dashboard` marca existencia ≤ `organization.umbral_poca_existencia` (3 si no está capturado; antes 5 fijo, SP6). `/daily-summary`: `total_revenue` es venta **neta** (cobradas − devoluciones aprobadas del día, `app/services/metricas_ventas.py`); trae `gross_revenue`, `returns_total`, `returns_count`; `payments` resta el vuelto y lo devuelto por método. Ámbito: roles de oficina sin `branch_id` = toda la org. Desde 2026-10-23 `/dashboard` y `/sales-by-hour` también usan `metricas_ventas.py`: `kpis.sales` es venta **neta**, nuevos `kpis.returns`/`returns_count`/`prev_returns`/`gross_sales`; `charts.trend` agrupa por día de México; `charts.hourly` y `sales-by-hour.hourly` traen las 24 horas; `charts.payments` es `{método: {total, count}}` neto de vuelto y devoluciones. Ámbito de `/dashboard`: ADMINISTRADOR/DUEÑO sin `branch_id` = toda la org (antes, la del usuario); GERENTE: siempre su sucursal (ignora `branch_id`, como la lista de ventas); una sola fecha = ese día y rango invertido = 422. `/sales-by-hour`: roles de oficina sin `branch_id` = toda la org. Fase 2 (2026-10-24): `kpis.gross_profit`/`prev_gross_profit`/`sales_without_cost`/`sales_with_cost` (**ojo:** `gross_profit` de `/dashboard` es solo sobre renglones con costo, mientras que el de `/daily-summary` es el contrato A-8 que suma lo sin costo con costo 0; no son comparables. `sales_with_cost` = importe bruto de los renglones con costo, la base de la utilidad; utilidad bruta solo sobre renglones con costo y neta de devoluciones por el costo de la variante; `null` para roles sin costos, p. ej. GERENTE) y `top_products[]` trae hasta 10 con `total` (importe). |
| /command-center/stats | **CAJERO → 403** (mismo detail). Desde 2026-11-17: ADMINISTRADOR, DUEÑO y SUPERADMIN ven toda la org; **GERENTE solo su sucursal** (totales, canceladas, `branches`); VENDEDOR, SOPORTE_OPERATIVO y demás roles de piso → 403. Mission control multi-sucursal (agregado, sin N+1). `branches[].critical_stock` y `alerts` usan el mismo umbral de la empresa (`app/services/existencias.py::umbral_poca_existencia`). Desde 2026-10-23 `global.total_sales` y `branches[].total_sales` son venta **neta** (cobradas − devoluciones aprobadas), `returns_total` es lo devuelto y `hourly_distribution` trae las 24 horas (`metricas_ventas.py`) |
| (cajera, 2026-11-17) | Fugas cerradas (`fix/fugas-cajera`). **Todo este renglón rige solo con `organization.conteo_ciego` encendido** (`app/services/ventas_cajero.py::cajera_a_ciegas`); con el conteo ciego apagado la cajera recibe lo mismo que antes. `/api/branch/dashboard` con el turno abierto manda `null` en `sales_total`, `avg_ticket`, `returns_total`, `goal_progress_pct` y `payment_methods` (se queda el conteo de tickets), su respaldo "cerrado hoy" es solo su propio turno y sin alerta `cash_variance`; `/api/cash/summary` con su turno abierto manda `null` en esperado, ventas totales, efectivo, reembolsos, totales de entradas/salidas y conciliación (tarjeta, transferencia y las listas se quedan), y con `session_id` solo sus turnos de hoy (si no, 404); `/api/cash/history` solo sus turnos de hoy; `/api/cash/{id}/pdf`, `/api/cash/{id}/ticket` y `POST /api/printer/print-cash-cut` solo sus turnos de hoy (si no, 404) y con el turno abierto 409 (el corte se imprime al cerrar); `/api/cash/{id}/audit-log` ya era 403 para ella. |
| (regla de venta, 2026-10-31) | Desde la cobranza, `metricas_ventas.py` reconoce como venta lo **cobrado y lo fiado**: `filtro_venta_reconocida` (`app/services/cash_reconciliation.py`) = PAID/REFUNDED_* **o** ticket (`INVOICE`) PENDING con cliente; un PENDING sin cliente y las cotizaciones/pedidos PENDING no cuentan. La fiada cuenta el día que sale la mercancía y los abonos posteriores son cobranza, no venta: `neta = cobrado_en_ventas + fiado − devuelto_de_ventas_no_fiadas`. `/dashboard` suma `kpis.credit_sales` (lo que quedó fiado en el periodo), `kpis.collections` (abonos recibidos) y `kpis.prev_credit_sales`. |
| **/by-waiter** | Ventas + **propinas** por mesero (`coalesce(server_user_id, seller_id)`) |
| /audit/discrepancies · /aging-report · /product/{id} · /export/csv | `/export/csv`: **CAJERO → 403** (mismo detail que `/daily-summary`). Arqueos / antigüedad de saldos (desde 2026-10-28 FIFO: los cubos suman lo que el cliente debe hoy, no todos sus cargos históricos) / analítica de producto / CSV (su sección "Alertas Stock Bajo" usa el umbral de la empresa, SP6; igual que `products/stats/catalog-kpis.threshold`, `branch-kpis.low_stock` y el filtro `stock_status` de `products/hq-inventory`) |
| **/valor-inventario** `?branch_id=&agrupar=sucursal\|departamento\|marca&department_id=` | Valor de la tienda (2026-10): `totales {piezas, skus, valor_venta, valor_costo, piezas_sin_costo, skus_sin_costo}` + `grupos[]` ordenados por `valor_venta`. Σ existencia × precio (completo) y Σ existencia × costo **solo de variantes con costo > 0**; costo NULL/0 cuenta como "sin costo". Sin borrados (`deleted_at`), sin existencias ≤ 0; sin `branch_id` el alcance por defecto son las sucursales con `is_active AND can_sell`; un `branch_id` explícito mira esa sucursal aunque esté cerrada, y uno de otra org devuelve 404. ADMIN/DUEÑO/SUPERADMIN ven todo; GERENTE recibe siempre su sucursal (ignora `branch_id`) con `valor_costo: null` (`ve_costo: false`) y sin sucursal asignada da 403; demás roles (CAJERO) 403. Vive en `app/routers/reports_valuacion.py`. Sin instantánea diaria (v1 calcula en vivo). `department_id` (UUID) acota totales y grupos a un departamento (la pantalla lo usa para repartir las marcas de un departamento); de otra org → 404; la respuesta lo devuelve en `department_id` (null si no se pidió). |
| **/inicio** `?branch_id=&completo=false&dias_sin_movimiento=30` (alias `/inicio-basico`) | Inicio del dueño (modo básico 2026-10 + SP6), una sola llamada: `hoy`/`ayer`/`semana` `{desde, hasta, total, devuelto, tickets}` (`total` neto de devoluciones aprobadas; 7 días incluido hoy), `por_metodo_hoy` (sin vuelto, netos de devoluciones), `top_semana[]` (máx. 5 por piezas), `poca_existencia {umbral, productos[]}` (existencia por variante ≤ `organization.umbral_poca_existencia` o 3, máx. 10, activos y no borrados; sin `branch_id` solo sucursales activas que venden) y `corte {estado: abierto\|cerrado\|sin_turno, cajera, abierto_en, cerrado_en, efectivo_esperado, efectivo_contado}`. Con **`completo=true`** suma: `sin_movimiento {dias, productos[{variant_id, nombre, sku, existencia, importe_venta}]}` (existencia > 0 y sin renglón de venta válida en `dias` días, 1..365, máx. 10 por importe), `pendientes {devoluciones (PENDING), turnos_abiertos (OPEN > 24 h), diferencias_caja[] (cortes de 7 días con diferencia recalculada ≠ 0, máx. 10)}`, `sucursales[]` (`null` con una sola que vende o al pedir `branch_id`; `{branch_id, nombre, ventas_hoy, devuelto_hoy, tickets_hoy, corte, poca_existencia}`) y `utilidad_bruta_hoy` (solo renglones con costo; `null` para el gerente) `venta_sin_costo_hoy` (lo vendido hoy sin costo) y `venta_con_costo_hoy` (importe bruto de los renglones con costo: la base de `utilidad_bruta_hoy`, la misma de `kpis.sales_with_cost` de Reportes; `null` para el gerente). Fase 2 (2026-10-24), también solo con `completo=true`: `tendencia {dias[7]{fecha, neta, tickets}, anterior[7]}` (hoy y 6 anteriores / los 7 previos, netos, día de México), `por_hora_hoy[24]{hora, neta, tickets}` (hora de México, el frontend recorta la ventana) y `utilidad_bruta_ayer` (`null` para el gerente). Sin `completo` esos nueve campos (`sin_movimiento`, `pendientes`, `sucursales`, `utilidad_bruta_hoy`, `venta_sin_costo_hoy`, `venta_con_costo_hoy`, `tendencia`, `por_hora_hoy`, `utilidad_bruta_ayer`) van en `null` y no se consultan. Cobranza (2026-10-31): `hoy`/`ayer`/`semana` traen además `fiado` (lo que quedó a cuenta en esas ventas) y `cobranza` (abonos recibidos), y cada `sucursales[]` trae `fiado_hoy`. Solo con `completo=true`, rol de oficina (ADMIN/GERENTE/DUEÑO/SUPERADMIN) y módulo `crm` encendido, suma `por_cobrar {total, vencido_30, clientes}` (cuentas por cobrar de la sucursal pedida o de la org; `vencido_30` = cubos 31_60 + 61_90 + 91_plus); si no, `null`. ADMIN/DUEÑO/SUPERADMIN: org o sucursal pedida (404 si es de otra org); GERENTE: siempre la suya; demás 403. Vive en `app/routers/reports_inicio.py`. |

## Impresora · `/api/printer`
`POST /test-print · /print-ticket · /reprint-ticket/{id} · /reprint-refunded/{id} · /print-cash-cut · /print-abono/{payment_id}` · `GET /printers · /download-agent`. Genera ESC/POS base64 (el agente local imprime, no el server). Registra `PrintJob`. `reprint-ticket`/`reprint-refunded` aceptan `pin` (2026-09-19): si la venta no es propia-y-reciente, primero prueban el PIN de reimpresión de un supervisor (`users.reprint_pin_hash`) y si no, su contraseña.

`POST /print-cash-cut` acepta `open_drawer` (por omisión `false`): solo el cierre de turno lo manda, y `branch.open_drawer_on_print` manda sobre él. `POST /drawer-opened` `{printer_name?}` → 204: registra `DRAWER_OPENED_MANUAL` en `cash_audit_log` con la caja abierta del usuario; la apertura la hace el agente local (2026-11-06).

`GET /download-agent?platform=windows|linux|mac` — redirige (302) al repositorio del
agente, <https://github.com/Ecamposg95/Atlas-Print-Agent> (ZIP de `main`; dentro,
`legacy/print_agent/` trae los launchers e instaladores de autoarranque). El agente ya no
vive en este repo (2026-09-22). `ATLAS_PRINT_AGENT_URL` sobreescribe el destino y admite
`{platform}` para cuando el repo publique un ZIP por plataforma. Runbook de
autoarranque en `docs/superpowers/runbooks/print-agent-autostart.md`.

## Canal Tienda en línea (`/api/channel/v1`) `[module:tienda_en_linea]`

API de **solo lectura** para que una tienda web externa (eleven.boutique) sincronice el catálogo
publicado de una organización. No usa JWT: autentica con una llave de servidor con scope
`catalog:read` (`Authorization: Bearer atlas_xxxxxxxx_...` o `X-Api-Key`). Sin llave válida 401, sin
scope 403, módulo apagado 404, más de 120 llamadas/min por llave 429. Sin CORS: se llama desde el
servidor de la web, nunca desde el navegador. Nunca expone precios, costos, existencias, códigos de
barras ni proveedores.

Paginación común: `?updated_since=<ISO8601>&cursor=<opaco>&limit=<1..200, def 100>`. Orden
`(updated_at, id)`. Respuesta `{ "items": [...], "next_cursor": str|null, "server_time": ISO8601 }`;
`server_time` se toma **antes** de consultar. Siguiente `updated_since` = último `server_time` **− 10
minutos** (deduplica por id): `updated_at`/`changed_at` se sellan en Python antes del commit, y una
transacción larga (publicación masiva, recálculo al activar el módulo, un cobro esperando un lock)
puede confirmar filas con sello anterior a tu último `server_time`. Además, una carga completa
nocturna (sin `updated_since`). `updated_since` va en UTC con `Z` (`2026-11-14T10:00:00Z`) o con el
`+` codificado (`%2B00:00`): un `+` sin codificar llega como espacio → 422. `limit` fuera de
rango → 422; `cursor` inválido → 400.

| Endpoint | Item |
|---|---|
| `GET /brands` | `{id, name, logo_url, is_premium, updated_at, deleted}` |
| `GET /departments` | `{id, name, parent_id, updated_at, deleted}` |
| `GET /products` | publicado: `{id, name, description, brand_id, department_id, gender, model, material, available, images:[{url, alt, position, is_primary}], variants:[{id, sku, color, size, available}], updated_at, web_published_at, deleted:false}` |
| `GET /products/{id}` | mismo shape; 404 si no es de la org o nunca se publicó |
| `GET /availability` | `{product_id, variant_id, available, changed_at}` (orden `changed_at, variant_id`; solo productos alguna vez publicados) |

**Bajas:** sin `updated_since` (carga inicial) solo salen publicados. Con `updated_since`, un
producto que alguna vez se publicó y ya no (despublicado, inactivo, borrado o no aprobado) llega
como `{id, updated_at, deleted: true}`. Nunca publicados no existen para el canal.

**Marcas y departamentos:** se borran en duro, así que `/brands` y `/departments` nunca devuelven
`deleted: true`. Son catálogos chicos: en cada sincronización bájalos completos (sin
`updated_since`) y descarta los ids que ya no vengan.

```bash
KEY=atlas_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxx   # placeholder: la llave real se entrega por canal seguro
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/brands"
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/departments"
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/products?limit=100"
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/products?updated_since=2026-11-14T10:00:00Z&cursor=<next_cursor>"
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/products/<uuid>"
curl -H "Authorization: Bearer $KEY" "https://app.atlasone.com.mx/api/channel/v1/availability?updated_since=2026-11-14T10:00:00Z"
```

```json
{ "items": [
    { "id": "b1f0…", "name": "Bolsa hobo", "description": null, "brand_id": "9c2e…",
      "department_id": "41aa…", "gender": "MUJER", "model": null, "material": "Piel",
      "available": true,
      "images": [{ "url": "https://…/1.jpg", "alt": null, "position": 0, "is_primary": true }],
      "variants": [{ "id": "7d3c…", "sku": "BOL-001", "color": "Negro", "size": null, "available": true }],
      "updated_at": "2026-11-14T10:05:00Z", "web_published_at": "2026-11-13T18:00:00Z", "deleted": false },
    { "id": "c0de…", "updated_at": "2026-11-14T10:06:00Z", "deleted": true } ],
  "next_cursor": null, "server_time": "2026-11-14T10:07:00Z" }
```

## Etiquetas · `/api/labels` `[module:labels]`
`GET /candidates` (filtros `search`, `department_id`, `brand_id`, `gender`, `only_with_stock`, `product_id`, `created_after` ISO 8601 = solo tallas dadas de alta desde ese instante; la pantalla manda la medianoche local; `carga_id` = solo las variantes que recibieron piezas de esa carga —movimientos con `reference="carga:<id>"`— y `copies_default` y `piezas_carga` salen de lo que entró, no de la existencia) devuelve una fila por variante visible con sus campos de etiqueta, `created_at` (alta de la talla, UTC) y `copies_default` = existencia (admin/dueño suman la organización, el resto su sucursal; tope 99). Las no imprimibles NO se esconden: llegan con `printable:false` y su `reason`. `POST /preview` (`{variant_id}` o datos sueltos) devuelve el layout en dots sobre un lienzo 408×200 —`elements` con textos y el código de barras en `bits`— más el ZPL crudo, para que la pantalla dibuje exactamente lo que va a salir. `POST /jobs` (`{items:[{variant_id, copies}]}`, copias 1..99, tope de 500 etiquetas por lote) devuelve `{content_base64, labels, skipped}`; un renglón sin código de barras cae en `skipped` sin tumbar el trabajo. `GET /test` da la etiqueta de calibración. **El server no imprime**: entrega ZPL en base64 y el navegador lo manda al agente local (`POST https://localhost:9100/print`), igual que el ticket. El layout está portado byte a byte de `atlas_labels/` del repositorio del agente (51 × 25 mm a 203 dpi, Zebra GX420t) y un test lo congela contra un literal.

## Cargar mercancía · `/api/cargas` `[module:ai]` (gate estricto: ni ADMIN/DUEÑO lo saltan)
Subir, leer, contestar dudas y descartar: roles de oficina; **autorizar solo ADMINISTRADOR/DUEÑO**. Decimales viajan como string (`"1500.00"`); errores `{"detail": "<frase en español>"}`. Todo filtra `organization_id`; una carga de otra org da 404. Guía de operación: [`ai/cargar-mercancia.md`](ai/cargar-mercancia.md).

| Método y ruta | Entrada | Respuesta |
|---|---|---|
| `POST /api/cargas` | multipart: `archivo`, `proposito` (`entrada`\|`migracion`), `sucursal_id?` | 202 `{id, folio, estado}`; 413 si pasa de 20 MB; 415 tipo no soportado (pdf, xlsx, csv); 503 sin `ANTHROPIC_API_KEY` (no se crea la carga) |
| `GET /api/cargas` | — | `[CargaResumen]`, la más reciente primero |
| `GET /api/cargas/{id}` | — | `CargaDetalle`: `carga`, `contadores` por clase, `dudas`, `grupos` (renglones del plan, cada uno con `descripcion` original y `origen`), `cambios`, `ultimos_conteos`, `puede_autorizar` |
| `POST /api/cargas/{id}/respuestas` | `{texto}` (≤ 4000) | `{cambio, rechazos}`: la IA traduce el texto a operaciones, el código las valida y recalcula; `rechazos` = lo que no entendió (también un precio, costo o cantidad que no escribió); 422 si la respuesta del modelo se cortó ("contesta en partes") |
| `POST /api/cargas/{id}/dudas/{numero}` | `{opcion, valor?}` | `{cambio, rechazos}`; botón = clave de la opción; respuesta escrita (solo dudas con `acepta_texto`) = `{opcion: "", valor}` |
| `POST /api/cargas/{id}/cambios/{cambio_id}/deshacer` | — | `CargaDetalle` |
| `POST /api/cargas/{id}/reintentar` | — | `{id, folio, estado}`; relee si falló la lectura (con un intento nuevo), regresa al plan si falló la aplicación; **409** si la carga ya se aplicó alguna vez (`aplicada_at`) |
| `POST /api/cargas/{id}/autorizar` | — | `ResumenAplicacion` (`productos_nuevos`, `variantes_nuevas`, `piezas`, `valor_costo`, `etiquetas`); **403** si no es ADMINISTRADOR/DUEÑO, **409** con dudas abiertas |
| `POST /api/cargas/{id}/descartar` | — | `{id, folio, estado}` |
| `GET /api/cargas/{id}/etiquetas` | — | `[Etiqueta]` (marca, producto, sku, talla, barcode, piezas, precio) |

Estados: `leyendo` → `plan` → `aplicando` → `aplicada`; también `error` y `descartada`. Clases de renglón: `EXISTE`, `SUMA`, `NUEVO`, `YA_CARGADO`, `IGNORADO`; los `YA_CARGADO` siempre traen una duda `ya_cargado` (saltar \| cargar) por carga previa. Dudas que aceptan texto (`acepta_texto`): `tipo_cambio`, `precio_faltante`, `sin_costo`, `marca_nueva`, `precio_fuera_familia`, `sin_tipo`, `sin_marca`; además `moneda` (PDF con costo sin moneda) y `departamento`. La lectura corre en un hilo de fondo: la pantalla consulta `GET /api/cargas/{id}` hasta que sale de `leyendo`. `autorizar` aplica todo en una transacción (kardex `reference="carga:<id>"`, auditoría `CARGA_APLICADA`); si falla, revierte y deja la carga en `error`. Tope diario de tokens por org (`AI_TOKENS_DIA_ORG`): 429. Cada llamada al proveedor tiene tope de `AI_TIMEOUT_SEG` segundos (300) y un reintento; la lectura marca su avance tras cada bloque y descarta lo leído si la carga cambió de intento o de estado mientras leía.

## Agente · `/api/ai` `[module:ai]` (gate estricto: ni ADMIN/DUEÑO lo saltan)

Fase A1: consultas por rol, sin escrituras y sin streaming. Roles con agente: CAJERO, VENDEDOR, GERENTE, ADMINISTRADOR, DUEÑO (`app/modules/ai/matriz.py`); cualquier otro rol, y SUPERADMIN/SUPPORT (fase A4), reciben **403**. Una conversación es de una persona en una organización: la de otro usuario o de otra empresa responde **404**. Guía: `docs/ai/README.md`.

| Endpoint | Body | Respuesta |
|---|---|---|
| `POST /api/ai/conversaciones` | `{titulo?}` | 201 `{id, titulo, created_at, updated_at}` |
| `GET /api/ai/conversaciones` | — | las propias, la más reciente primero (máx. 50) |
| `GET /api/ai/conversaciones/{id}` | — | `{…, mensajes: [{id, rol, contenido, tablas, created_at}]}`: solo lo que escribió la persona y lo que contestó el agente (los pasos de herramientas no viajan) |
| `POST /api/ai/conversaciones/{id}/mensajes` | `{texto}` (1 a 4000) | `{mensaje}` con la respuesta y `tablas: [{titulo, columnas, filas, mas}]` (las arma el servidor con el resultado de las herramientas, máx. 3 tablas de 12 filas). **429** cupo diario de la organización o de la persona agotado; **503** sin llave del proveedor (`IA no configurada: falta …`) o proveedor caído (el turno no se guarda; lo gastado sí se cuenta) |
| `DELETE /api/ai/conversaciones/{id}` | — | 204; borra la conversación y sus mensajes |
| `GET /api/ai/health` | — | `{module, status, ready}` (solo sesión) |

El modelo solo recibe las herramientas del rol y el servidor rechaza cualquier otra. Organización y sucursal salen de la sesión; solo ADMINISTRADOR y DUEÑO pueden nombrar una sucursal. Cada llamada al modelo deja fila en `ai_llamadas` (rol, tarea `consulta`, modelo, tokens).

## Conteos — `/api/inventory/counts`
Conteo físico de una sucursal (y opcionalmente un departamento) con escáner. Solo ADMINISTRADOR/DUEÑO (403 al resto); el módulo `inventory` solo decide si el ítem Conteo aparece en el menú. Todo se filtra por organización: un conteo o línea de otra org da **404**. El conteo **nunca toca `stock_on_hand`**: lee la existencia y la congela al cerrar. Tablas en [`DATA_MODEL.md`](DATA_MODEL.md). Diseño: `docs/superpowers/specs/2026-10-22-conteo-inventario-design.md`.

| Método | Ruta | Body | Respuesta | Reglas |
|---|---|---|---|---|
| POST | `/` | `{branch_id?, department_id?, notes?}` | 201 `ConteoRead` (con `avance`) | Sin `branch_id` usa la del usuario; 422 si no hay ninguna. **409** si ya hay un conteo ABIERTO de esa sucursal+departamento (uno CERRADO o CANCELADO no cuenta). 404 si sucursal/departamento no son de la org |
| GET | `/` | query `status?`, `branch_id?` | lista `ConteoRead`, más reciente primero | — |
| GET | `/{id}` | — | `ConteoDetalle` (`ConteoRead` + `lineas`) | 404 cross-org |
| POST | `/{id}/scan` | `{code}` | `{resultado: contado\|ambiguo\|desconocido, linea?, producto?, qty_sistema?, fuera_de_alcance, candidatos}` | +1 a la línea de la variante; varias coincidencias → `ambiguo` sin contar; sin coincidencia → línea por código (`desconocido`). 422 código vacío; 409 si está cerrado o cancelado |
| POST | `/{id}/lines` | `{variant_id, qty=1}` (qty > 0) | `LineaRead` | Suma `qty` a la línea (la crea si no existe). 404 variante ajena; 409 cerrado o cancelado |
| PATCH | `/{id}/lines/{line_id}` | `{qty_contada?, corregida?}` (al menos uno; qty >= 0) | `LineaRead`, o `null` si quedó en 0 | **0 borra la línea.** `corregida` marca que la ficha de la pieza se corrigió durante el conteo. 422 si no manda ninguno; 409 cerrado o cancelado |
| DELETE | `/{id}/lines/{line_id}` | — | 204 | Equivale a fijar 0 |
| GET | `/{id}/lista` | — | `{filas: [{producto, sistema, contado, estado: pendiente\|revisado\|diferencia, corregida, line_id}], totales: {total, revisados, pendientes, con_diferencia, corregidas}}` | Lista completa del alcance (departamento o tienda) con su estado de paloma, para la sesión "lista primero". 404 cross-org |
| POST | `/{id}/close` | — | `ConteoDetalle` | **Congela**: guarda `qty_sistema` en cada línea, `status=CERRADO`, `closed_at` y el reporte en `resumen`. Cerrado ya no admite escaneos ni ediciones (409) |
| POST | `/{id}/cancel` | — | `ConteoRead` | **Descarta** un conteo ABIERTO: `status=CANCELADO` y `closed_at`; no congela `qty_sistema` ni `resumen` y **nunca toca `stock_on_hand`**. Los ajustes ya hechos en piso se conservan (son movimientos de kardex reales) y las líneas quedan como rastro. Un cancelado se comporta como cerrado para escanear/editar/ajustar/aplicar (409) y libera la sucursal+departamento para abrir otro conteo. **409** si ya estaba CERRADO o CANCELADO; 403 a quien no sea admin/dueño; 404 cross-org |
| POST | `/{id}/lines/{line_id}/ajustar` | — | `{linea, qty_sistema, movimiento_id}` | Ajuste en piso (conteo ABIERTO): `delta = qty_contada − existencia actual`; mueve el kardex (ADJUSTMENT_IN/OUT, `reference="Conteo"`) y marca `ajustada_at`. **409** si ya cuadra, o si el conteo está cerrado o cancelado |
| POST | `/{id}/apply` | `{variant_ids: [...]}` | `Reporte` (con `ajustes[]`, `aplicado_en`) | Aplica al kardex las tallas elegidas de un conteo CERRADO (**409** "Primero cierra el conteo." si sigue abierto; "Este conteo fue cancelado." si está cancelado). **El delta está congelado** (`qty_contada − qty_sistema` al cierre), no la existencia de hoy; una salida mayor a la existencia se recorta a 0 (`recortado`). Ya ajustadas se omiten |
| GET | `/{id}/report` | — | `{estado, generado_en, alcance, totales, faltantes, sobrantes, fuera_de_alcance, desconocidos}` | Abierto: se calcula con la existencia actual; cerrado: sobre las líneas congeladas; cancelado: también se calcula en vivo (no hay `resumen` congelado). Filas ordenadas por diferencia absoluta |

Reporte: `faltantes` (sistema > contado), `sobrantes` (contado > sistema), `fuera_de_alcance` (variantes contadas fuera del departamento) y `desconocidos` (códigos sin variante). `totales` trae `esperadas_/contadas_variantes|piezas`, `cuadradas_variantes`, `faltantes_piezas`, `sobrantes_piezas`, `fuera_de_alcance_piezas` y `desconocidos`.

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
| organizations | /organizations | **CRUD de tenants** + plan (cambio vía selector); módulos/preset por org; `apply-preset`, `modules/{key}` toggle, `industry`, `bootstrap`, `reset-preset`, `{id}/plan-uso`, delete `?force=` (cascade ~30 tablas) `[SUPERADMIN]` |
| suscripciones | /suscripciones, /organizations/{id}/suscripcion | Cobro de la mensualidad a cada tienda (suscripción, cargos, pagos manuales). Ver abajo |
| plans | /plans | Catálogo de planes (FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS); topes y módulos por plan |
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

- `PUT /api/platform/organizations/{id}` acepta `perfil_ui` (`auto`\|`basico`\|`completo`, 422 si es otro); el `PUT /api/organization/` de tenant lo descarta como a `plan`. `OrganizationRead` expone `perfil_ui` y `umbral_poca_existencia` (este sí lo guarda la dueña).

### Suscripciones · `/api/platform/suscripciones` y `/api/suscripcion` (megaplan F3)
Lo que **Atlas le cobra a cada tienda**. No es CRM Cobranza (`/api/customers/…`, crédito de la tienda a sus clientes). Módulo `app/modules/suscripciones/`, montado aparte en `app/main.py` con `require_platform_admin`. Primera versión de **registro manual**: sin pasarela, sin CFDI y sin suspensión automática; `suspendida` es informativa y **no bloquea ningún acceso**. Importes como cadena decimal (`"499.00"`). Toda escritura deja fila en `platform_audit_log` (`entity_type = SUSCRIPCION`, `entity_id` = id de la organización; acciones `SUSCRIPCION_ALTA`, `_EDICION`, `_CAMBIO_PLAN`, `_CARGO`, `_PAGO`, `_CARGO_CANCELADO`). Tablas en [`DATA_MODEL.md`](DATA_MODEL.md). Plan: `docs/superpowers/plans/2026-11-24-f3-cobro-de-suscripciones.md`.

| Método | Ruta | Quién | Qué hace |
|---|---|---|---|
| GET | `/api/platform/suscripciones?estado=&q=` | SUPERADMIN, SUPPORT | `{totales, items}`. `totales`: `cartera_vencida` (saldo de cargos pendientes ya vencidos), `por_vencer` (saldo de pendientes que aún no vencen), `ingreso_mensual_recurrente` (precios pactados llevados a mes de las `al_corriente` y `por_vencer`), `por_estado`, `sin_suscripcion`. Los filtros recortan `items`, no los totales. `estado` desconocido → 400 |
| GET | `/api/platform/organizations/{org_id}/suscripcion` | SUPERADMIN, SUPPORT | `{organizacion, plan_organizacion, suscripcion \| null, cargos[]}` con los pagos de cada cargo (incluye notas internas y quién registró) |
| PUT | `/api/platform/organizations/{org_id}/suscripcion` | SUPERADMIN | Alta o edición (solo aplica lo que viene): `plan`, `precio_mxn`, `periodicidad` (`mensual`\|`anual`), `dia_corte` (1–28), `fecha_inicio`, `proxima_renovacion`, `estado`, `notas`, `rfc`, `razon_social`, `correo_facturacion`. En el alta el precio por omisión es el de lista del plan. **Cambiar `plan` cambia también `organization.plan`** (`plans.asignar_plan`); plan desconocido → 400. `estado` solo se guarda si es manual (`suspendida`, `cortesia`); mandar uno automático quita el manual y se recalcula |
| POST | `/api/platform/organizations/{org_id}/suscripcion/cargos` | SUPERADMIN | Cargo del periodo. Body opcional `{periodo_desde, importe, vence_el}`; por omisión el periodo que empieza en `proxima_renovacion`, importe = precio pactado, vence el primer día. **Idempotente**: 201 `{creado: true}` la primera vez, 200 `{creado: false}` con el mismo cargo si ya existía. Sin suscripción → 409; precio 0 → 422 |
| POST | `/api/platform/suscripciones/cargos/{cargo_id}/pagos` | SUPERADMIN | `{importe, metodo, fecha_pago?, referencia?, notas?}`; `metodo` ∈ `transferencia`, `deposito`, `efectivo`, `tarjeta`, `otro`. Parcial o total; mayor al saldo, cero, método desconocido o fecha futura → 422; cargo pagado o cancelado → 409. Al cubrir el importe el cargo queda `pagado` y `proxima_renovacion` avanza al día siguiente del fin del periodo (nunca retrocede). Devuelve el detalle |
| POST | `/api/platform/suscripciones/cargos/{cargo_id}/cancelar` | SUPERADMIN | `{motivo?}`. Solo cargos sin pagos (409 si los tiene). Generar de nuevo ese periodo lo reabre |
| GET | `/api/suscripcion/mia` | ADMINISTRADOR, DUEÑO | Solo lectura, de la organización activa: `{plan (nombre, precio de lista, topes), uso (usuarios activos, sucursales que venden), suscripcion \| null, cargos[]}`. Sin notas internas ni quién registró. Cajera, gerente y demás roles → 403 |

- **Estado** (`services.calcular_estado`, día de México): se calcula al leer. Manual gana → precio 0 es `al_corriente` → cargo pendiente vencido es `vencida` → cargo pendiente que vence en ≤ 7 días es `por_vencer` → sin cargos pendientes manda `proxima_renovacion` (pasada = `vencida`, en ≤ 7 días = `por_vencer`).
- `PUT /api/platform/organizations/{id}` con `plan` refleja el plan en la suscripción (el precio pactado no se toca).

---

## Stubs / Beta (solo `GET /health`, `ready:false`)
`/api/commissions`, `/api/memberships`, `/api/purchasing`. (Nota: compras REAL vive en `/api/purchases`; `/api/purchasing` es el placeholder del rediseño modular.)

---

## Gotchas transversales (para quien consume la API)
- **Códigos de error por plan** (2026-09-30): `PUT /api/platform/organizations/{id}` → 400 plan desconocido (el `detail` lista las claves válidas); `PATCH /api/platform/organizations/{id}/modules/{key}?enable=` → 403 módulo fuera de plan (el `detail` nombra el plan mínimo o "fuera del preset"); `POST /api/users/`, `PUT /api/users/{id}` (reactivar), `POST /api/branches/` (que vende), `PUT /api/branches/{id}` (pasar a vender) → 403 tope de plan.
- **Campos nuevos** (2026-09-30): `GET /api/platform/organizations/{id}/modules` devuelve por módulo `plan_minimo` (clave del plan que lo incluye, o `null` si es base o del preset) y `permitido_por_plan` (bool: base ∪ preset ∪ plan actual); `GET /api/platform/organizations/{id}/upsell-recommendations` devuelve `plan_minimo` por recomendación.
- **`convert-to-sale` de quotes NO dispara el evento outbox** (a diferencia de `create_sale`): no descuenta insumos ni libera mesa. Tampoco congela `usd_rate` ni comisión de tarjeta (ambos son exclusivos de `create_sale`).
- **`GET /api/products/search` es inalcanzable** (preexistente, hallado 2026-09-21): `core.router` monta `/{product_id}` antes que `search.router` en `app/modules/products/router/__init__.py`, así que cualquier ruta declarada en `search.py` queda tapada por el match de `/{product_id}`.
- **Las mutaciones de `/products/{id}/variants` y `/products/variants/{id}`** exigen `require_module("variants")`; los endpoints de `barcodes.py` no lo exigen (solo rol donde aplica). Recuerda que ADMIN/DUEÑO hacen bypass de `require_module` en general (RBAC.md §5): un admin de una org sin el módulo `variants` activo puede llamar el endpoint de variantes a mano aunque la UI no se lo muestre.
- **Endpoints sin `get_current_user`** (solo `org_id`, menor atribución de auditoría): `returns:/stats`, `purchases:/stats,/,/{id}`, `expenses:/stats,/categories,/`, `transfers:/,/{id}/fulfill`. Logistics `/containers`,`/boxes` no tienen ni org (sin tenant scope).
- **Debug prints en prod**: `sales.py` (export CSV), `quotes.py` (create).
- **Definición de "HQ" divergente**: `reports/dashboard` y `command-center` excluyen GERENTE; pero `sales-by-hour`/`by-waiter`/`export-csv` lo incluyen como HQ.
