# Comisión por pago con tarjeta — Diseño

**Fecha:** 2026-09-17 · **Base:** `main` @ `959be7d` · **Estado:** diseñado, sin implementar
**Plan de implementación:** [`docs/superpowers/plans/2026-09-17-comision-tarjeta.md`](../plans/2026-09-17-comision-tarjeta.md)

---

## 1. Problema

Cuando un cliente paga con tarjeta, la terminal bancaria le descuenta al negocio entre
2.5 % y 4 % del importe. Hoy Atlas One cobra exactamente el total de la mercancía sin
importar el método, así que ese porcentaje sale íntegro del margen del dueño. Varios
inquilinos ya lo trasladan al cliente **a mano**: la cajera suma el porcentaje con una
calculadora, lo cobra como si fuera parte de la venta y el ticket miente (dice
`TOTAL $1,035.00` sobre mercancía de $1,000.00, sin explicar los $35). Consecuencias
observadas:

- El **corte de caja** no distingue mercancía de comisión: `Ventas Totales` queda inflado
  y el reporte de ingresos del mes también.
- En **pagos mixtos** la cajera calcula mal: aplica el porcentaje al total completo
  aunque el cliente haya dado la mitad en efectivo.
- No hay forma de saber cuánto se recuperó por comisiones en un turno ni en un periodo.

Se necesita que el sistema calcule, cobre, imprima y reporte la comisión, y que la
organización que no la use no note absolutamente nada.

## 2. Decisiones

Tabla concretada **después** de leer el código. La columna «Ajuste» marca dónde el
encargo original cambió porque el código lo contradecía.

| # | Decisión | Ajuste |
|---|---|---|
| 1 | El porcentaje es **por organización**, columna `organization.card_surcharge_pct`. `0` = apagado, y es el DEFAULT para todas las organizaciones vivas. | — |
| 2 | Tipo de la columna: **`NUMERIC(5,2)`**, no `NUMERIC(6,3)`. | **Sí.** `app/pos_printer.py::_total_line` da `label_w = cols - 12 = 20` en papel de 58 mm y **no trunca** la etiqueta: se desborda. La etiqueta más larga posible con 2 decimales es `COM. TARJETA 19.99%:` = 20 caracteres exactos; con 3 decimales (`19.999`) serían 21 y el renglón rompería el ancho del papel. Dos decimales también evitan mostrar en el ticket un porcentaje redondeado distinto del guardado. |
| 3 | Rango válido: `0 ≤ pct ≤ 20`. Fuera de rango → **422** con `detail` en español. | — |
| 4 | Solo ADMINISTRADOR/DUEÑO pueden cambiarla. **No hace falta guardia nueva**: `app/modules/tenants/router.py:75-85` bloquea cualquier campo fuera de la whitelist `{printer_name, ticket_header, ticket_footer, paper_width_mm}` llamando a `require_admin`. Mismo mecanismo que usaron las tres columnas `usd_rate_*`. | — |
| 5 | Aplica **solo al método `CARD`**. `PaymentMethod` (`app/models/sales.py:29-33`) tiene `CASH`, `CARD`, `TRANSFER`, `OTHER`: todo lo que no es `CARD` es base sin comisión. | — |
| 6 | **`total_amount` sigue siendo el total de mercancía (+IVA +propina).** La comisión vive en `sales_documents.card_surcharge_amount`, columna aparte. Así `Ventas Totales` del corte, los KPIs de `/api/sales/stats` y el histórico de ingresos no se mueven. | — |
| 7 | El `Payment` de `CARD` se guarda **con la comisión incluida** (`amount = base + comisión`). Es el importe que realmente pasó por la terminal, es lo que el banco depositará, y hace que `COBRADO POR METODO` del corte cuadre sin tocar `compute_expected_cash`. | — |
| 8 | **`compute_expected_cash` NO se toca.** La comisión nunca es efectivo: entra por el renglón `CARD`, que ese servicio ya ignora. | — |
| 9 | La regla de cálculo vive en un servicio puro, `app/services/card_surcharge.py`, única fuente de la comisión — igual que `app/services/tax.py` lo es del IVA y `app/services/exchange_rate.py` del tipo de cambio. `Decimal`, `ROUND_HALF_UP`, a centavos. | — |
| 10 | La venta **congela** `card_surcharge_pct` y `card_surcharge_amount`. Reimpresión y reenvío idempotente leen el documento; **nunca** recalculan. | — |
| 11 | El **cajero no puede quitar la comisión**: no hay interruptor en el POS y la validación del backend exige que los pagos cubran `total + comisión`. | — |
| 12 | **Las devoluciones NO reintegran la comisión** (ver §7). | — |
| 13 | El porcentaje llega al POS por un **endpoint propio y barato**, `GET /api/organization/card-surcharge`, con su store de Zustand — el mismo patrón que `GET /api/organization/exchange-rate` + `exchangeRateStore`. **No** se amplía `/api/users/me/context`. | **Sí.** El encargo dejaba abiertas las dos opciones. `/me/context` lo consumen seis componentes a través de `useEnabledModulesStore` y se carga en `App.tsx`, `Sidebar.tsx` y `MobileLayout.tsx` con una bandera `loaded` que el POS no controla: meter ahí un número que decide cuánto se cobra abre una carrera (POS montado antes de que `loaded` sea `true` ⇒ comisión 0 en pantalla). El endpoint dedicado es un `SELECT` y no tiene esa ventana. |
| 14 | La columna del CSV de ventas va en **`app/routers/sales.py::export_sales_csv`** (`GET /api/sales/export/csv`), no en `app/routers/reports.py::export_dashboard_csv`. | **Sí.** El `/export/csv` de `reports.py` (línea 979) es un volcado de KPIs, top de productos, distribución horaria y alertas de stock: **no tiene renglón por venta**, así que no hay dónde poner una columna. El CSV que sí lista ventas una por renglón es el de `sales.py:1454`. |
| 15 | En el corte impreso la comisión es un renglón **informativo** bajo `Tarjeta (n)` (etiqueta `incl. comision`, misma convención que el `en efectivo` del bloque de devoluciones; `_rline` alinea todo a la derecha, así que la sangría es solo del texto), y **no** se suma a `Total cobrado`. | **Sí (refuerzo).** `_total_cobrado` se acumula en la misma pasada que imprime los renglones (`app/pos_printer.py`, bloque `COBRADO POR METODO`) y la comisión ya está dentro de `payments['card']['total']`. Sumarla otra vez rompería la invariante documentada en ese bloque: el desglose tiene que sumar exactamente el total. |
| 16 | En `MixedPaymentModal` el monto de tarjeta se completa con un botón explícito **«Completar con tarjeta»**, no con un `useEffect` que reescriba lo que el cajero teclea. En `CardPaymentModal` (100 % tarjeta) es automático. | **Sí.** El modal mixto deja editar cada renglón libremente; un efecto que pisara el campo de tarjeta cada vez que cambia otro renglón pelearía con el cursor del cajero. El botón es determinista y la validación (§5) impide cobrar de menos igual. |

## 3. Modelo de datos

Sin Alembic (regla de oro #3): columnas nuevas = `ALTER TABLE … ADD COLUMN` idempotente
en la lista `migrations` de `scripts/railway_init.py` (tuplas `(tabla, columna, ddl)`,
líneas 51-112) **más** el atributo en el modelo para que `create_all` las cree en bases
nuevas y en la SQLite de las pruebas.

### `organization` (`app/modules/tenants/models.py`, clase `Organization`)

```
card_surcharge_pct   NUMERIC(5,2)  NOT NULL DEFAULT 0
```

Porcentaje que se suma a la parte cobrada con tarjeta. `0` = función apagada. Va justo
después del bloque `usd_rate_*` (línea 201), que es el precedente de «columna de
configuración por inquilino».

### `sales_documents` (`app/models/sales.py`, clase `SalesDocument`)

```
card_surcharge_pct     NUMERIC(5,2)   NULL           -- snapshot; NULL = no aplicó
card_surcharge_amount  NUMERIC(10,2)  NOT NULL DEFAULT 0
```

`card_surcharge_pct` se guarda **solo cuando la comisión fue mayor que cero**; si no,
queda `NULL`. Así una venta en efectivo de una organización con 3.5 % configurado no
arrastra un porcentaje que nunca se aplicó, y el ticket sabe si imprimir el renglón sin
consultar nada más.

`card_surcharge_amount` es `NOT NULL DEFAULT 0`: toda venta histórica queda en `0.00`
sin necesidad de backfill. En PostgreSQL ≥ 11 un `ADD COLUMN … NOT NULL DEFAULT` con
constante no reescribe la tabla, así que el `ALTER` es instantáneo aun con el histórico
de Kaory.

**Lo que NO cambia:** `total_amount`, `subtotal`, `tax_amount`, `tip_amount`,
`change_given`, `Payment.amount` como concepto, `cash_sessions`, ni ninguna tabla de
inventario. La comisión no toca el IVA: se aplica sobre el total ya con impuestos y no
genera impuesto propio (es un cargo por servicio de la terminal, decisión del dueño;
si algún día debe causar IVA, será otro diseño).

## 4. Regla de cálculo

Servicio puro `app/services/card_surcharge.py`. Sin base de datos, sin FastAPI.

```
base_tarjeta  = max(0, total − Σ(pagos cuyo método ≠ CARD))
comision      = redondear(base_tarjeta × pct / 100)
pago_tarjeta  = base_tarjeta + comision
total_a_pagar = total + comision
```

Todo en `Decimal`, cuantizado a centavos con `ROUND_HALF_UP` (el mismo redondeo fiscal
mexicano de `app/services/tax.py`). `total` y la suma de pagos no-tarjeta se cuantizan
**antes** de restar, para que la base sea un importe en centavos exacto y el POS y el
backend nunca discrepen.

Nota: el encargo describía la base como «total menos los pagos no-CARD *limitados al
total*». El límite es redundante — `max(0, total − nc)` ya lo hace —, así que la
implementación usa la forma corta.

Interfaz:

```python
@dataclass(frozen=True)
class ComisionTarjeta:
    base: Decimal           # importe sobre el que se cobra la comisión
    pct: Decimal            # porcentaje aplicado (0 si no aplicó)
    monto: Decimal          # la comisión, a centavos
    pago_tarjeta: Decimal   # base + monto: lo que debe pasar por la terminal
    total_a_pagar: Decimal  # total + monto

def calcular_comision(total, pagos, pct) -> ComisionTarjeta: ...
def pct_de_organizacion(org) -> Decimal: ...   # lectura defensiva de la columna
def validar_pct(pct) -> None: ...              # lanza ValueError; el router lo vuelve 422
```

`pagos` va *duck-typed*: cualquier objeto con `.method` y `.amount` sirve
(`PaymentCreate` en producción, `SimpleNamespace` en las pruebas).

### Ejemplos numéricos

Organización con `card_surcharge_pct = 3.50`.

**A · 100 % tarjeta.** Mercancía $1,000.00.

| concepto | valor |
|---|---|
| base | 1,000.00 |
| comisión | 35.00 |
| pago CARD | 1,035.00 |
| total a pagar | 1,035.00 |
| `sales_documents.total_amount` | **1,000.00** |
| `sales_documents.card_surcharge_amount` | 35.00 |
| `sales_documents.card_surcharge_pct` | 3.50 |

**B · Mixto exacto.** Mercancía $1,000.00, el cliente da $400.00 en efectivo.

| concepto | valor |
|---|---|
| pagos no-tarjeta | 400.00 |
| base | 600.00 |
| comisión | 21.00 |
| pago CARD | 621.00 |
| total a pagar | 1,021.00 |
| pagos registrados | CASH 400.00 + CARD 621.00 = 1,021.00 |
| `change_given` | 0.00 |

**C · Mixto con cambio en efectivo.** Mercancía $1,000.00. El cajero teclea CASH
$500.00, pulsa «Completar con tarjeta» (CARD $517.50) y entonces el cliente entrega un
billete de $600.00, así que el cajero corrige el renglón de efectivo a $600.00 **sin**
volver a pulsar el botón.

| concepto | valor |
|---|---|
| pagos no-tarjeta | 600.00 |
| base (recalculada) | 400.00 |
| comisión | 14.00 |
| total a pagar | 1,014.00 |
| pagos registrados | CASH 600.00 + CARD 517.50 = 1,117.50 |
| `cash_needed` = 1,014.00 − 517.50 | 496.50 |
| `change_given` = 600.00 − 496.50 | **103.50** |

Comprobación: 1,117.50 − 103.50 = 1,014.00 = 1,000.00 de mercancía + 14.00 de comisión. ✔
El cajón queda cuadrado y el cliente paga exactamente lo debido.

Aquí se ve el borde documentado en la decisión 16: como el cajero subió el efectivo
declarado sin re-completar la tarjeta, la comisión bajó de $17.50 a $14.00 mientras la
terminal cobró $517.50. El negocio recupera $3.50 de menos. El modal muestra en vivo
`Total a pagar $1,014.00`, así que el desajuste es visible; re-pulsar «Completar con
tarjeta» lo corrige. Se acepta: la alternativa (recalcular el renglón de tarjeta cada
tecla) pelea con el cursor del cajero.

**D · Neutralidad (`pct = 0`).** Comisión `0.00`, `total_a_pagar = total`,
`card_surcharge_pct = NULL`, ni un renglón nuevo en el ticket, ni en el corte, ni en el
CSV. Idéntico a hoy.

**E · Sin tarjeta.** `pct = 3.50`, el cliente paga $1,000.00 en efectivo: base `0.00`,
comisión `0.00`. La comisión solo existe si hay al menos un pago `CARD`.

**F · Redondeo.** Mercancía $333.33, 100 % tarjeta: 333.33 × 0.035 = 11.66655 →
**11.67** (HALF_UP). Total a pagar $345.00.

## 5. Efecto en `create_sale` (el motor de cobro)

`app/routers/sales.py::create_sale` es el motor ATS-crítico (regla de oro #8). El cambio
se concentra en **cuatro puntos**, todos neutros cuando la comisión es cero:

1. **Línea 513-515.** La organización ya se consulta ahí para `resolve_org_tax_mode`,
   pero el resultado se descarta. Se guarda en una variable y se reutiliza para leer
   `card_surcharge_pct`. **Cero consultas nuevas.**
2. **Después de `total_paid` (línea 717), antes de `cash_paid`.** Se calcula la comisión
   y se define `total_a_cobrar = total_sale + comision`. Con `pct = 0` o sin pago `CARD`,
   `comision = Decimal("0.00")` y `total_a_cobrar is total_sale` — el resto del flujo no
   distingue.
3. **`cash_needed` (línea 732) y la validación H-1 (líneas 741-772)** pasan a usar
   `total_a_cobrar`. Esto es indispensable, no cosmético: si `cash_needed` siguiera
   usando `total_sale`, en el ejemplo B el sistema le devolvería al cliente $21.00 de
   cambio — justo la comisión que acaba de cobrarle. La tolerancia (`Decimal("0.01")`),
   el guard de sobrepago ×10 y el aviso `PAYMENT_DISCREPANCY` quedan tal cual.
4. **Después del `if existing_sale / else` (línea 851)**, junto al snapshot de `usd_rate`:
   se asignan `card_surcharge_amount` y `card_surcharge_pct` al documento. Vale para las
   dos ramas (venta nueva y venta a crédito que se termina de pagar).

`balance_diff = total_sale - total_paid` (línea 773, la que decide si queda deuda a
crédito) **sigue usando `total_sale`**: la deuda del cliente es por la mercancía. Con los
pagos cubriendo `total_a_cobrar`, `balance_diff` sale negativo y `doc_status` es `PAID`,
que es lo correcto.

**Prueba de neutralidad exigible en la revisión:** con `card_surcharge_pct = 0`, o con
una venta sin pago `CARD`, la respuesta del checkout, el documento persistido, los
`Payment`, el `change_given`, el ticket y el corte tienen que ser idénticos a los de hoy.
El plan incluye pruebas explícitas para cada uno.

## 6. API

### Configuración (organización)

| Endpoint | Cambio |
|---|---|
| `GET /api/organization/` → `OrganizationRead` | expone `card_surcharge_pct` |
| `PUT /api/organization/` ← `OrganizationUpdate` | acepta `card_surcharge_pct`; valida `0 ≤ pct ≤ 20` → **422** `"La comisión por pago con tarjeta debe estar entre 0 y 20 %."`. Solo ADMIN/DUEÑO por la whitelist existente |
| `GET /api/organization/card-surcharge` **(nuevo)** | `{"pct": 3.50}`. Cualquier usuario de la organización (lo consume la cajera). Un `SELECT`, cero red |

### Venta

| Endpoint | Cambio |
|---|---|
| `POST /api/sales/` | la validación de cobertura compara contra `total + comisión`. La respuesta agrega `card_surcharge_amount` y `card_surcharge_pct` (misma forma en el alta y en el reenvío idempotente de `_respuesta_de_venta_existente`) |
| `GET /api/sales/`, `GET /api/sales/{id}`, `GET /api/sales/by-folio/...`, `GET /api/sales/my-last` | `SaleRead` agrega `card_surcharge_amount` y `card_surcharge_pct` |
| `GET /api/sales/export/csv` | columnas nuevas **«Comisión tarjeta»** y **«Total cobrado»** después de «Total» |

El payload de entrada **no cambia**: el POS nunca manda el porcentaje ni la comisión.
Los calcula el servidor, que es el único que puede hacerlo sin que el cajero lo altere.

### Corte de caja

`get_session_audit_data` (`app/routers/cash.py:591`) agrega al diccionario que devuelve
una clave de primer nivel:

```json
"card_surcharges": 245.00
```

Suma de `sales_documents.card_surcharge_amount` de las ventas de la sesión con
`status in CASH_INCLUDED_STATUSES` — exactamente los mismos estatus con los que se
agrupa `payment_stats`, porque la comisión viaja dentro de esos mismos `Payment` de
tarjeta. La consumen `GET /api/cash/{id}/pdf`, `GET /api/cash/{id}/ticket` y la UI del
corte sin cambios de contrato (clave nueva, nadie la exigía antes).

## 7. Devoluciones: la comisión **no** se reintegra

Decisión: **por omisión la comisión no se devuelve.**

Motivo: el banco ya se la quedó. `approve_return` (`app/crud/returns.py`) reescribe
`sale.total_amount` al neto y saca el reembolso como `CashMovement` OUT; si además
devolviéramos la comisión, el negocio pagaría dos veces el mismo cargo del adquirente.

Consecuencias que el diseño acepta y documenta:

- `sales_documents.card_surcharge_amount` **no se modifica** al aprobar una devolución.
- El ticket reemitido (`build_reissued_ticket_bytes`) recalcula el `TOTAL` neto pero
  sigue mostrando la comisión original y un `TOTAL A PAGAR` = neto + comisión. En una
  devolución total eso imprime `TOTAL $0.00` y `COM. TARJETA 3.5% $35.00`. Es feo, y es
  verdad: esos $35 no vuelven.
- El corte del día de la devolución sigue contando la comisión original en
  `card_surcharges`, porque la venta sigue en `CASH_INCLUDED_STATUSES`
  (`REFUNDED_PARTIAL`/`REFUNDED_TOTAL` están incluidos).

Si un inquilino pide devolverla, es una función aparte: haría falta un
`SaleReturn.card_surcharge_refunded` y un `CashMovement` propio. **Fuera de alcance.**

## 8. Alcance

### Dentro

- Columna de configuración por organización + validación + pantalla **Empresa**.
- Servicio puro `app/services/card_surcharge.py` con pruebas.
- Dos columnas en `sales_documents` + migración idempotente.
- `create_sale`: cálculo, validación de cobertura, persistencia y respuesta.
- Ticket (`build_ticket_bytes` y `build_reissued_ticket_bytes`): renglones
  `COM. TARJETA X%` y `TOTAL A PAGAR`, con la línea USD recolocada después y calculada
  sobre el total a pagar.
- Corte de caja: `card_surcharges` en `get_session_audit_data` y renglón informativo en
  el corte impreso.
- Reportes: `SaleRead`, CSV de ventas, detalle en `SalesHistory` y `HQSalesLog`.
- POS: util pura `cardSurcharge.ts` con pruebas, store del porcentaje,
  `CardPaymentModal` y `MixedPaymentModal`.

### Fuera

- **Devolver la comisión** (§7).
- **Comisión por método distinto de `CARD`** (transferencia, cheque, crédito de tienda).
- **Comisión por terminal o por banco** (una sola tasa por organización).
- **Comisión por sucursal** (`branches` no lleva la columna).
- **IVA sobre la comisión** y su reflejo en CFDI.
- **Cambiar `/api/sales/stats`** ni ningún KPI de periodo: `total_sales` sigue siendo
  mercancía. Sumar ahí la comisión movería un número que los dueños ya leen todos los
  días. Si se quiere un KPI de comisiones recuperadas, es trabajo aparte.
- **`quotes convert-to-sale`**: esa ruta no pasa por `create_sale` y hoy ya tiene huecos
  conocidos (no emite el evento del outbox, CLAUDE.md §6). No se le agrega la comisión.
- **Cotizaciones, apartados y estado de cuenta de clientes.**
- **Interruptor por venta para que el cajero la quite** (decisión del dueño).

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Tocar el motor de cobro.** `create_sale` cobra dinero real de Kaory, Ginebra, Imaltzin y Eleven. | Cuatro puntos de cambio, todos con salida temprana cuando `pct = 0`. Pruebas de neutralidad byte a byte: respuesta del checkout, `change_given`, documento, pagos, ticket y corte. |
| **Cambio entregado de más.** Si `cash_needed` no incluyera la comisión, en un mixto la cajera devolvería justo el importe de la comisión. | Ejemplos B y C de §4 convertidos en pruebas; `change_given` verificado en los tres escenarios. |
| **Doble conteo en el corte.** La comisión ya está dentro de `payments['card']['total']`. | El renglón impreso es informativo y **no** entra en `_total_cobrado`. Prueba que comprueba que `Total cobrado` sigue siendo la suma exacta de los métodos. |
| **Idempotencia.** Un reenvío del mismo `client_uuid` no debe recalcular ni duplicar la comisión. | `_respuesta_de_venta_existente` lee el documento; la prueba de idempotencia comprueba que el segundo POST devuelve el mismo `card_surcharge_amount` y no crea `Payment` extra. |
| **Ancho del ticket.** `_total_line` no trunca la etiqueta; una etiqueta larga desborda el papel de 58 mm. | `NUMERIC(5,2)` + etiqueta `COM. TARJETA {pct}%` (≤ 20 caracteres) + pruebas de ancho a 58 y 80 mm, como en `tests/test_ticket_usd.py`. |
| **`MagicMock` en `tests/test_pos_printer.py`.** Cualquier atributo no declarado sale *truthy* e imprimiría un renglón de comisión con un `MagicMock` de importe en las 12 pruebas de ticket existentes. | `_make_sale` declara `card_surcharge_amount = Decimal("0")` y `card_surcharge_pct = None`, igual que se hizo con `usd_rate`. |
| **Deploy a medias.** Si el frontend sale antes que la migración, el POS pediría un endpoint que no existe. | El store falla cerrado (`pct = 0` ante cualquier error) y el backend no depende del frontend: si el POS manda el importe sin comisión, el 422 de cobertura lo dice en español. Aun así, el orden de despliegue es backend → frontend. |
| **Un dueño teclea 35 en vez de 3.5.** | Tope duro de 20 % con 422 y texto en español; el POS enseña el importe en pesos antes de cobrar. |
| **`with_for_update` es no-op en SQLite** (regla de oro #7): la concurrencia real no se ejercita en pruebas. | La comisión no introduce ningún lock nuevo ni ninguna escritura fuera de la transacción del checkout. |

## 10. Estimación

| Tarea | Alcance | Tiempo |
|---|---|---|
| C1 | Columnas, servicio puro, validación y endpoint de configuración | ~3 h |
| C2 | `create_sale` + respuesta + pruebas de neutralidad, mixto e idempotencia | ~4 h |
| C3 | Ticket, corte de caja, `SaleRead` y CSV | ~4 h |
| C4 | Frontend: util pura, store, dos modales, Empresa, historial | ~4 h |
| — | Verificación cruzada, despliegue y validación en staging | ~2 h |

**Total: ~2 jornadas de trabajo**, en una sola rama `feat/comision-tarjeta`, cuatro
commits con la suite verde en cada uno.
