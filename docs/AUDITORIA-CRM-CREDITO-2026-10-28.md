# Auditoría del módulo de crédito / clientes — 2026-10-28

**Motivo.** El dueño de Eleven: "muchos se llevan cosas y no las pagan y las van pagando
poco a poco. Es un módulo muy importante." Decisiones tomadas con él antes de auditar:
la cajera decide a quién fía (cualquier cliente registrado, sin tope ni PIN); los pagos
son abonos libres (sin plan ni fechas); dueño/admin quieren una vista detallada y la
cajera solo acciones con interfaz básica.

**Alcance.** Todo el camino del dinero fiado: checkout con cliente
(`app/routers/sales.py::create_sale`), cancelación de venta, abonos y estado de cuenta
(`app/modules/customers/`), devoluciones (`app/crud/returns.py`), antigüedad de saldos
(`app/routers/reports.py`), y las pantallas `pages/crm/Customers.tsx`,
`components/pos/modals/MixedPaymentModal.tsx`, `CustomerModal.tsx`, `CartPanel.tsx`.

**Resultado.** 9 hallazgos corregidos en la rama `fix/crm-credito-auditoria` con 11 pruebas
nuevas (`tests/test_crm_credito_auditoria.py`) y 4 de vitest
(`MixedPaymentModalCredito.test.tsx`); 7 quedan anotados para el diseño del módulo
(§3). Ningún cambio de esquema: no hay ALTER en `railway_init.py`.

---

## 1. Hallazgos corregidos

| # | Severidad | Dónde | Qué pasaba | Qué hace ahora |
|---|---|---|---|---|
| C-1 | **Crítica** | `sales.py::create_sale` guard H-1 | "Se lleva $3,000 y deja $500" devolvía **422 Pagos insuficientes**. La única forma de fiar era `payments: []` (sin enganche), y el POS ni siquiera lo permitía (ver F-1). | Con `customer_id`, un pago parcial es válido: lo que falta queda a la cuenta del cliente. Sin cliente sigue el 422 (no hay a quién cargarle). |
| C-2 | **Crítica** | `sales.py::cancel_sale` | Cancelar una venta fiada tronaba con **500**: el asiento se construía con `entry_type="CANCELLATION"`, campo que `CustomerLedgerEntry` no tiene. La venta no se podía cancelar. Además la reversión usaba `total − pagos`, que para un pedido de cotizaciones (nunca cargó nada) regalaba saldo a favor. | `services.revertir_cargo_de_documento`: revierte lo que ESE documento le carga según el ledger. |
| C-3 | **Crítica** | `sales.py::create_sale` bloque "Crédito Cliente" | El cargo solo se asentaba si `customer.has_credit`. Un cliente sin la casilla se llevaba la mercancía con la venta PENDING y **la deuda no existía en ningún lado** (ni saldo, ni estado de cuenta, ni antigüedad). | Se asienta siempre que la venta deje saldo; la casilla `has_credit` se enciende sola (la cajera decidió fiarle). |
| C-4 | **Crítica** | `crud/returns.py::approve_return` | Devolución **en efectivo** de una venta fiada: salían billetes del cajón para un cliente que no había pagado, y su deuda seguía intacta. | `services.aplicar_devolucion_a_saldo`: lo devuelto baja primero la deuda del cliente; solo el excedente sale por el método elegido (sin excedente, no se crea `CashMovement` ni se exige caja). Si sigue debiendo, la venta queda PENDING; cubierta por completo, REFUNDED_TOTAL. |
| I-1 | Importante | `/reports/aging-report` | Sumaba **todos los cargos históricos** sin restar abonos: un cliente que compró $10,000 en el año y debe $100 reportaba $10,000 repartidos por antigüedad. Los cubos no cuadraban con `total_balance`. | `services.antiguedad_por_cargo`: FIFO (cada abono paga el cargo más viejo); los cubos suman lo que debe hoy. |
| I-2 | Importante | `POST /customers/{id}/pay` | Abono libre (sin ticket) bajaba el saldo pero **dejaba todos los tickets PENDING para siempre**; abono a ticket se marcaba PAID solo cuando el saldo TOTAL del cliente llegaba a cero (con dos tickets fiados, liquidar el primero no lo cerraba); el guard de sobrepago comparaba contra el saldo total, así que se podía abonar a un ticket de $100 un monto de $150. | `services.aplicar_abono`: con ticket, todo a ese ticket (422 si excede lo que ese ticket debe); sin ticket, se reparte del más viejo al más nuevo con un asiento por ticket, cada ticket cubierto pasa a PAID y lo que sobra queda como saldo a favor. |
| I-3 | Importante | `GET /customers/{id}/unpaid-documents` | `total − pagos` sobre cualquier documento: mostraba tickets cancelados, devueltos y pedidos que nunca cargaron nada. | `services.documentos_abiertos`: saldo por ledger, excluye CANCELLED/REFUNDED_TOTAL, respaldo `total − pagos` solo para PENDING sin asientos (ventas anteriores a que el checkout escribiera el ledger). |
| F-1 | Importante | POS `MixedPaymentModal` | `isValid = remaining <= 0.005`: **imposible dejar saldo** desde el POS. El módulo de crédito no tenía entrada. | Con cliente del CRM en el carrito: lo que no se cobre "Queda a crédito", botón "Cobrar y fiar", acceso "Todo a crédito"; el toast dice cuánto quedó fiado (`credit_debt`). Sin cliente, igual que antes. |
| F-2 | Menor | CRM `Customers.tsx` | El modal de abono solo pedía monto: todo entraba como **efectivo** (una transferencia caía al cajón y descuadraba el corte; la cajera sin caja abierta recibía 409 aunque fuera tarjeta). | Selector Efectivo/Tarjeta/Transferencia + referencia. Filtro "Con deuda" (`balance_filter=debt`, que el backend ya tenía). El POS muestra "Debe $X" en los resultados de búsqueda y en el chip del carrito. |

Regla única: `app/modules/customers/services.py` es ahora el único lugar que sabe cuánto
debe un documento (`deuda_cargada_por_documento`, `saldo_documento`) y cómo se aplica un
abono o una devolución. `sales.py::_deuda_cargada_por_documento` quedó como alias.

## 2. Verificado y sin cambios

- Atribución del abono en efectivo a la caja de quien lo cobra (`Payment.cash_session_id`) y
  guard de caja abierta: correctos (`tests/test_abono_*`).
- Liquidación de una venta a crédito por el mismo documento (`existing_sale`): ajusta por la
  diferencia del ledger, no vuelve a cargar (`test_credito_liquidar_documento.py`).
- Estado de cuenta, PDF y WhatsApp: funcionan; el PDF compacta lo anterior a `start_date` en
  saldo anterior.
- Multi-tenancy: todas las consultas del módulo filtran `organization_id`; `require_module("crm")`
  en todo el router.
- `credit_limit` y `credit_days` no se imponen en ningún lado. Por decisión del dueño (sin tope)
  se quedan como dato informativo.

## 3. Pendiente para el diseño del módulo (no son bugs)

1. **Qué cuenta como "Ventas hoy"** con una venta fiada: hoy no cuenta hasta liquidarse y ese
   día cuenta completa (`SALES_REPORT_STATUSES` excluye PENDING). Opciones: contar la venta el
   día que sale la mercancía (recomendada: es lo que descuenta inventario; los abonos son
   cobranza) o contar solo el dinero que entra. Decisión del dueño pendiente.
2. **Vista detallada del dueño**: quién debe, cuánto, desde cuándo (la antigüedad ya cuadra),
   historial por cliente y por sucursal, cuentas por cobrar en Inicio/Reportes. Hoy
   `/reports/aging-report` no tiene pantalla.
3. **Abonos desde el POS** (hoy solo desde Clientes) y recibo/ticket del abono.
4. **Recordatorios por WhatsApp** (hoy solo el estado de cuenta manual).
5. **Abono en efectivo de un rol de oficina sin sucursal**: queda sin caja (`cash_session_id`
   NULL) y, si trae ticket, cae al respaldo por documento del corte original. Decidir si se
   bloquea o se pide sucursal.
6. **Abonos libres anteriores a esta auditoría** no tienen enlace a ticket: esos tickets siguen
   PENDING aunque el saldo esté en cero. Un script de conciliación FIFO es trivial con
   `aplicar_abono`; correrlo cuando se migre a producción si hay datos (Eleven hoy no fía).
7. Portal del cliente (`pages/portal/Portal.tsx`) pinta el saldo deudor en verde y el saldo a
   favor en rojo: colores invertidos respecto al CRM.
