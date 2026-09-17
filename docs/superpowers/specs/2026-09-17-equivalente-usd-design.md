# Equivalente en dólares (USD) en el POS — diseño

- **Fecha:** 2026-09-17
- **Estado:** diseño aprobado por el dueño en conversación; plan de la Fase A en
  `docs/superpowers/plans/2026-09-17-equivalente-usd-fase-a.md`
- **Alcance de tenencia:** función **general** (todas las organizaciones), no de
  un preset. Neutra por defecto: si la organización no configura tipo de cambio,
  no aparece absolutamente nada nuevo en pantalla ni en el ticket.
- **Auditoría base:** lectura del código del 2026-09-17, resumida en §2

---

## 1. Problema

En la frontera y en las plazas turísticas el cliente pregunta **"¿cuánto es en
dólares?"** antes de pagar, y a veces paga con billetes de dólar. Hoy Atlas One
es 100 % peso mexicano:

- El total del carrito y el ticket salen solo en MXN
  (`frontend/src/components/pos/CartPanel.tsx:882`, `app/pos_printer.py:192`).
- La cajera convierte de cabeza o con la calculadora del celular, con el tipo de
  cambio que recuerde; dos cajeras del mismo turno cotizan distinto.
- Si el cliente paga en dólares, la venta se registra como `CASH` en pesos por el
  equivalente que la cajera calculó, y el corte de caja nunca sabe cuántos
  dólares físicos hay en el cajón.

No hay ninguna noción de moneda en el modelo: `Organization`
(`app/modules/tenants/models.py:154-209`) tiene `timezone` y
`price_includes_tax`, pero ni moneda ni tipo de cambio; `PaymentMethod`
(`app/models/sales.py:28-32`) solo conoce `CASH`, `CARD`, `TRANSFER`, `OTHER`.

## 2. Hallazgos que dictan el diseño

| # | Hallazgo | Evidencia |
|---|---|---|
| 1 | `Organization` no tiene moneda ni tipo de cambio; sí tiene precedente de config fiscal por organización (`price_includes_tax`) | `app/modules/tenants/models.py:183-188` |
| 2 | El router de organización es el punto natural para leer/escribir la config: `GET /` y `PUT /` ya resuelven org activa y roles | `app/modules/tenants/router.py:41`, `:54`, `:29-38` |
| 3 | El `PUT /` ya bloquea a no-admins para cualquier campo fuera de la whitelist `{printer_name, ticket_header, ticket_footer, paper_width_mm}` — los campos nuevos quedan protegidos **sin código extra** | `app/modules/tenants/router.py:66-77` |
| 4 | `app/models/organization.py` y `app/schemas/organization.py` son *reverse-shims* con `import *`; el cuerpo real vive en `app/modules/tenants/` | `app/models/organization.py:8-13`, `app/schemas/organization.py:2` |
| 5 | `create_sale` es el motor ATS-crítico: calcula totales, valida pagos, arma `SalesDocument` y devuelve un dict plano | `app/routers/sales.py:402`, `:715-771`, `:838-851`, `:966-974` |
| 6 | El ticket recibe el objeto `sale` completo, así que cualquier columna nueva del documento está disponible en impresión y reimpresión sin tocar el router de impresión | `app/routers/printer.py:383`, `:451`, `:503`; `app/pos_printer.py:145`, `:370` |
| 7 | El ticket se codifica en **latin-1 con `replace`**: `"≈"` se imprime como `?` | `app/pos_printer.py:325` (`line.encode("latin-1", "replace")`) |
| 8 | Las pruebas de ticket miden ancho máximo por línea (56 cols a 80 mm, 32 a 58 mm) | `tests/test_pos_printer.py:133-160` |
| 9 | `tests/test_pos_printer.py` arma la venta con `MagicMock`: **cualquier atributo no declarado sale truthy** | `tests/test_pos_printer.py:51-74` |
| 10 | Ya existe el patrón de worker de fondo gateado en SQLite (`_IS_SQLITE`), arrancado en el startup | `app/core/outbox.py:33`, `:151-160`; `app/main.py:88-91` |
| 11 | `httpx>=0.27` y `requests==2.32.5` ya están en `requirements.txt`; `tzdata` también (para `ZoneInfo`) | `requirements.txt:38`, `:48`, `:63` |
| 12 | `formatCurrency(value, {currency})` del frontend ya soporta USD; en `es-MX` rinde `"USD 12.34"` | `frontend/src/utils/currency.ts:44-53` |
| 13 | Las pruebas de frontend son solo de funciones puras: `vitest` con `environment: 'node'`, patrón `src/**/*.test.ts` | `frontend/vitest.config.ts` |
| 14 | `PaymentMethod` es un **`Enum` de Postgres** en la columna `payments.method`; agregar un valor exige `ALTER TYPE … ADD VALUE` en AUTOCOMMIT | `app/models/sales.py:28-32`, `:141`; patrón en `scripts/railway_init.py:41-48` |
| 15 | `compute_expected_cash` suma `Payment.amount` de método `CASH` y resta el cambio entregado; no distingue divisas | `app/services/cash_reconciliation.py:215-276` |

## 3. Decisiones

1. **Tipo de cambio automático (Banxico FIX) + ajuste manual por organización.**
   El FIX (serie `SF43718`) es la referencia pública y auditable en México. Se
   baja una vez al día a una tabla **global** `exchange_rates` y cada
   organización decide cómo usarla con tres modos:
   - `off` (**default**): no hay tipo de cambio; nada se muestra. Es lo que
     verán hoy las ~16 organizaciones vivas sin que nadie toque nada.
   - `auto`: `tipo efectivo = FIX del día + usd_rate_margin` (p. ej. `+0.30`,
     el spread de ventanilla que el negocio cobra). Sin FIX del día → `None`.
   - `manual`: `tipo efectivo = usd_rate_manual`, capturado por el admin.
2. **El FIX es global, la política es por organización.** La tabla
   `exchange_rates` **no** lleva `organization_id`: es un dato público, uno por
   día, compartido por todos los inquilinos. La regla de oro #5 (filtrar por
   `organization_id`) no aplica porque no hay dato de negocio de nadie ahí —
   igual que la tabla `modules`. Bonus: al no tener FK a `organization`, no
   entra en el cascade manual de `platform/organizations.py delete ?force=true`.
3. **Tres columnas en `organization`, no una tabla de configuración.** Es
   exactamente el precedente de `price_includes_tax` (`models.py:188`): config
   fiscal del inquilino, columna simple, migración idempotente. Una tabla aparte
   costaría un JOIN en el camino del POS a cambio de nada.
4. **`usd_rate_mode` es `VARCHAR(10)` con constantes Python, no un enum de DB.**
   Regla de `CLAUDE.md §5`: un enum nuevo de Postgres obliga a
   `ALTER TYPE … ADD VALUE` en AUTOCOMMIT cada vez que se agrega un modo (y ya
   se prevé un cuarto modo, `fix_puro`, si alguien quiere el FIX sin margen).
5. **Servicio puro para resolver y convertir.** `app/services/exchange_rate.py`
   con `resolve_usd_rate(org, latest_fix)` y `to_usd(amount_mxn, rate)`. Es la
   **única** fuente de la conversión: la usan el endpoint, el snapshot de la
   venta y el ticket, igual que `app/services/tax.py` es la única fuente del
   IVA. Redondeo `ROUND_HALF_UP` a dos decimales, el mismo de `tax.py`.
6. **El tipo de cambio se congela en la venta.** `sales_documents.usd_rate
   NUMERIC(10,4) NULL`. Sin el snapshot, un ticket reimpreso mañana mostraría
   otro equivalente que el original, y en un cobro en dólares (Fase B) eso sería
   un descuadre real. `NULL` = venta anterior a la función o de una organización
   en modo `off`; el ticket simplemente no imprime la línea.
7. **El snapshot NO participa de ningún cálculo en Fase A.** En `create_sale`
   solo se asigna la columna, envuelta en `try/except` que devuelve `None`: si
   Banxico, la tabla o el servicio fallan, **la venta se cobra igual**. Ninguna
   ruta de cobro, stock, folio o caja cambia. Es la única forma aceptable de
   tocar `app/routers/sales.py` (regla de oro #8).
8. **En el ticket se imprime `USD (T.C. 18.5000): 12.34`, no `≈ USD`.** El
   hallazgo 7: la codificación latin-1 convierte `≈` en `?`. El tipo de cambio
   viaja **en la etiqueta** de `_total_line`, que ya pagina a 56/32 columnas; la
   etiqueta mide 19 caracteres y cabe hasta en el papel de 58 mm (`label_w=20`).
   En pantalla (HTML, UTF-8) sí se usa `≈`.
9. **El job diario es un `asyncio.Task` como el worker del outbox**, arrancado
   en el startup de `app/main.py` y **doblemente apagado**: si el backend corre
   sobre SQLite (tests y dev local) y si no hay `BANXICO_TOKEN`. Corre al
   arrancar (si falta la fila de hoy) y luego despierta a las **12:30
   America/Mexico_City**, un margen cómodo sobre la publicación del FIX (~12:00).
10. **La escritura del FIX es idempotente por `(currency, rate_date)`.** El job
    puede correr N veces al día, y N réplicas del backend pueden arrancar a la
    vez; la fila del día es una sola. Se consulta antes de insertar y el
    `UniqueConstraint` es la red.
11. **Nunca se toca la red en pruebas.** El cliente `fetch_fix` se parchea con
    `monkeypatch`. No hay una sola prueba que dependa de que Banxico responda.
12. **El frontend pide el tipo de cambio a un endpoint propio**, no a
    `GET /api/organization/`. Lo consume la cajera, que **no** es admin y no
    debe poder leer RFC ni configuración fiscal para pintar un número. Se cachea
    en un store de Zustand y se refresca cada 30 min (el FIX cambia una vez al
    día; media hora es un compromiso holgado).
13. **La conversión del frontend es una función pura en `src/utils/usd.ts`**,
    con prueba `vitest`, por el hallazgo 13. Ningún componente calcula.

## 4. Alcance

### Fase A — quick win (dentro)

- Tabla `exchange_rates` + tres columnas en `organization`.
- Servicio puro `resolve_usd_rate` / `to_usd` / `validar_config_usd`.
- Cliente Banxico + job diario gateado.
- `GET /api/organization/exchange-rate`, `PUT /api/organization/` con los tres
  campos, `POST /api/organization/exchange-rate/refresh`.
- `sales_documents.usd_rate` llenado en `create_sale`.
- Ticket y ticket reemitido: línea `USD (T.C. …)` cuando hay snapshot.
- POS: total en USD bajo el total del carrito; precio en USD en cada tarjeta.
- `Organization.tsx`: sección "Tipo de cambio USD" (modo, manual, margen, FIX del
  día, botón "Actualizar ahora").

### Fase B — cobrar en dólares (fuera de la Fase A, §7)

Método de pago `USD_CASH`, `Payment.amount_foreign` + `Payment.exchange_rate`,
cambio en pesos, corte de caja con "dólares recibidos", reportes por divisa.

### Fuera de ambas fases

- Monedas distintas del dólar (EUR, CAD). El modelo lo admite (`exchange_rates`
  ya tiene `currency`), la UI no.
- **Precios de catálogo en USD.** El precio se sigue capturando y cobrando en
  MXN; el USD es siempre derivado. Cambiar eso tocaría el motor de precios.
- Conversión en cotizaciones, devoluciones y estado de cuenta de clientes.
- Facturación (CFDI) en moneda extranjera.
- Histórico del FIX más allá de la fila diaria que el job va acumulando (no se
  hace backfill de años anteriores).

## 5. Modelo de datos

### Tabla nueva: `exchange_rates`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `Integer` PK autoincrement | convención de PK entera (hay dos en el repo, `CLAUDE.md` regla 4) |
| `currency` | `String(3)`, not null, default `'USD'` | deja la puerta abierta a EUR/CAD |
| `rate_date` | `Date`, not null, index | día del FIX según Banxico (no del fetch) |
| `rate` | `Numeric(10,4)`, not null | 4 decimales: el FIX se publica con 4 |
| `source` | `String(16)`, not null, default `'banxico'` | `'banxico'` \| `'manual'` |
| `fetched_at` | `DateTime(timezone=True)`, default `now()` | cuándo se bajó |

`UniqueConstraint('currency', 'rate_date', name='uq_exchange_rate_day')`.
Sin `organization_id` (decisión 2). Sin `TenantMixin`. La crea `create_all` al
registrar el modelo en `app/models/__init__.py`.

### Columnas nuevas en `organization`

| Columna | Tipo | Default | Notas |
|---|---|---|---|
| `usd_rate_mode` | `VARCHAR(10)` NOT NULL | `'off'` | `off` \| `auto` \| `manual` |
| `usd_rate_manual` | `NUMERIC(10,4)` NULL | — | obligatorio y > 0 si `mode='manual'` |
| `usd_rate_margin` | `NUMERIC(10,4)` NOT NULL | `0` | se suma al FIX en modo `auto`; puede ser negativo |

### Columna nueva en `sales_documents`

| Columna | Tipo | Notas |
|---|---|---|
| `usd_rate` | `NUMERIC(10,4)` NULL | tipo de cambio efectivo congelado al cobrar. `NULL` = sin equivalente |

Los tres `ALTER TABLE … ADD COLUMN` son idempotentes y viven en la lista
`migrations` de `scripts/railway_init.py` (regla de oro #3, sin Alembic).

### Contrato del servicio

```
ResolvedRate(rate: Decimal, source: str, fix_rate: Decimal|None, fix_date: date|None)

resolve_usd_rate(org, latest_fix) -> ResolvedRate | None
    mode 'off'                       -> None
    mode 'manual', manual > 0        -> ResolvedRate(manual, 'manual', fix?, fix_date?)
    mode 'manual', manual None/<=0   -> None     (config a medias ≠ error de cobro)
    mode 'auto', hay FIX             -> ResolvedRate(fix + margin, 'banxico', fix, fix_date)
    mode 'auto', sin FIX             -> None
    resultado <= 0                   -> None     (un margen absurdo no imprime basura)

to_usd(amount_mxn, rate) -> Decimal   # ROUND_HALF_UP a 2 decimales; rate<=0 -> Decimal('0.00')
validar_config_usd(mode, manual, margin) -> None | raise ValueError
```

## 6. API

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/api/organization/exchange-rate` | cualquier usuario autenticado de la org | `{mode, rate, source, fix_rate, fix_date, margin, manual_rate}`; `rate: null` si `off` o si no se puede resolver |
| `PUT` | `/api/organization/` | ADMIN/DUEÑO (por la whitelist existente, hallazgo 3) | `OrganizationRead` con los tres campos nuevos |
| `POST` | `/api/organization/exchange-rate/refresh` | ADMIN/DUEÑO (`require_admin`) | `{ok, rate_date, rate, source}` o 503 si falta token / falla Banxico |

`GET` es deliberadamente barato: dos SELECT (organización + FIX del día) y cero
llamadas de red. `POST …/refresh` es el único que sale a internet a demanda, y
existe para que el dueño no tenga que esperar hasta mañana al configurar.

`PUT /api/organization/` no necesita guardia nueva: por el hallazgo 3, un cajero
que mande `usd_rate_mode` recibe 403 desde el código que ya está. Lo que sí se
agrega es la validación de coherencia (`validar_config_usd`) sobre los valores
**resultantes** —no sobre el payload parcial—, de modo que un `PUT` que solo
cambia el margen no pueda dejar la organización en modo `manual` sin tipo.

## 7. Fase B — cobrar en dólares

Todo lo de abajo queda **fuera** del plan de la Fase A; se escribe aquí para que
la Fase B se planee sobre decisiones ya tomadas, no desde cero.

### 7.1 Modelo

- **Método de pago nuevo `USD_CASH`** en `PaymentMethod`
  (`app/models/sales.py:28-32`). Por el hallazgo 14 la columna es un `Enum` de
  Postgres: hace falta un `ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS
  'USD_CASH'` en AUTOCOMMIT en `scripts/railway_init.py`, igual que el bloque
  que ya sincroniza `industrytype` (`railway_init.py:41-48`). **Este ALTER debe
  desplegarse antes que el código que emite el valor**, o el primer cobro en
  dólares revienta con `InvalidTextRepresentation`.
- **`payments.amount_foreign NUMERIC(12,2) NULL`** — los dólares físicos que
  entregó el cliente.
- **`payments.exchange_rate NUMERIC(10,4) NULL`** — el tipo aplicado a ESE pago.
  Se duplica respecto a `sales_documents.usd_rate` a propósito: un pago mixto
  puede convivir con una venta cuyo snapshot cambió por reintento, y el corte
  necesita el tipo del pago, no el del documento.
- **`payments.amount` sigue siendo MXN.** Invariante dura:
  `amount == quantize(amount_foreign * exchange_rate)`. Así ningún reporte, ni
  el crédito de clientes, ni `compute_expected_cash` cambian de unidad.

### 7.2 Flujo de cobro

1. El POS abre un modal "Pago en dólares" con el total en USD ya calculado.
2. La cajera captura **dólares recibidos** (no pesos).
3. El backend recalcula `amount = amount_foreign * rate` con el tipo resuelto en
   el servidor (nunca el que mande el cliente) y sigue el camino normal de
   validación de pagos de `create_sale:715-771`.
4. **El cambio se entrega en pesos**, siempre. Es la decisión que evita tener que
   modelar un cajón bimonetario: el `change_given` existente
   (`app/models/sales.py:69`) sigue siendo MXN y `compute_expected_cash` sigue
   restándolo sin saber de divisas.

### 7.3 Corte de caja

- `compute_expected_cash` (`app/services/cash_reconciliation.py:215-276`) filtra
  hoy `Payment.method == PaymentMethod.CASH`. **Un pago `USD_CASH` quedaría
  fuera del esperado y el cajón saldría sobrado en pesos.** Hay dos opciones y
  la decisión es la segunda:
  - (a) incluir `USD_CASH` en el `expected` en pesos — simple, pero la cajera
    contaría dólares y pesos revueltos.
  - (b) **dos líneas separadas**: el `expected` en pesos **no** incluye
    `USD_CASH` (sí resta el cambio en pesos que se dio por esos pagos), y el
    corte muestra un bloque aparte "Dólares recibidos: USD 120.00 (≈ $2,220.00)"
    que se cuenta y se cuadra por separado.
- Eso obliga a: un campo `counted_usd` en el cierre de caja, una línea en el
  ticket de corte (`app/pos_printer.py:444+`, `build_cash_cut_bytes`) y una
  entrada nueva en `ExpectedCashBreakdown`.
- **Riesgo alto:** `change_given` de un pago en dólares es cambio en pesos que
  sale del cajón de pesos sin que haya entrado un peso. Si el `expected` en
  pesos no lo resta, el corte marca faltante todos los días. `_compute_change_given`
  debe seguir contando ese cambio aunque el pago que lo originó no sume al
  `expected` en pesos — es exactamente la inversión de la lógica actual y es el
  punto donde la Fase B se rompe si se implementa a la ligera.

### 7.4 Reportes

- Cortes y reportes de ventas por método de pago ganan una fila `USD_CASH`.
- Reporte nuevo "Dólares del período": suma de `amount_foreign` y tipo promedio
  ponderado, para conciliar con la casa de cambio donde el negocio los vende.

### 7.5 Riesgos propios de la Fase B

| Riesgo | Mitigación |
|---|---|
| El `ALTER TYPE` no alcanza a correr antes del código que usa `USD_CASH` | Desplegar el ALTER solo, verificarlo en prod, y **después** habilitar el modal |
| Cajera captura pesos donde el campo pide dólares (un billete de 20 USD registrado como $20) | El modal muestra el equivalente en pesos **en vivo** y bloquea el cobro si el peso resultante queda a más de 25 % del total |
| Cortes históricos: `expected` cambia de fórmula | La fórmula nueva solo aplica a sesiones abiertas después del deploy; `counted_usd IS NULL` ⇒ comportamiento viejo |
| Doble conversión (el POS convierte y el backend vuelve a convertir) | El POST manda `amount_foreign` y **nunca** `amount`; el servidor es el único que multiplica |

**Estimación Fase B: ~3 días** (1 modelo + enum + `create_sale`, 1 corte de caja
y ticket de corte, 1 modal del POS y reportes), más un día de observación en la
primera tienda antes de ofrecerlo.

## 8. Riesgos (Fase A)

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | **Tocar `create_sale`** (regla de oro #8) | Una sola asignación de columna, envuelta en `try/except → None`, después del `if/else` que arma el documento y antes del `flush`. Sin ramas nuevas, sin cambiar totales ni validación de pagos. Prueba explícita de que una venta se cobra igual con el servicio reventando |
| 2 | **`MagicMock` truthy en `tests/test_pos_printer.py`** (hallazgo 9): `sale.usd_rate` saldría truthy y ensuciaría los tickets de todas las pruebas existentes | Declarar `sale.usd_rate = kwargs.get("usd_rate", None)` en `_make_sale`. Es el mismo bug que ya documenta el comentario de `org.price_includes_tax` en ese archivo (`tests/test_pos_printer.py:19-22`) |
| 3 | Banxico caído o token vencido | El job y el endpoint fallan en silencio salvo log; el POS muestra el último FIX disponible. Si no hay ninguno y el modo es `auto`, `rate = null` y no se muestra nada. **Nunca** se cae una venta por esto |
| 4 | El FIX del día no es el del día de la venta (feriados, fin de semana: Banxico publica `N/E`) | `fetch_fix` descarta datos no numéricos; en fin de semana la fila más reciente es la del viernes. El endpoint devuelve `fix_date` para que la UI diga de qué día es el tipo |
| 5 | Ancho del ticket: una línea larga rompe la prueba de 32 columnas | La etiqueta `USD (T.C. 18.5000):` mide 19 y el `label_w` de 58 mm es 20. Hay prueba de ancho en ambos papeles |
| 6 | Job de fondo por réplica: 2 réplicas de Railway = 2 jobs | La escritura es idempotente por `(currency, rate_date)` y consulta antes de insertar |
| 7 | El número en USD se lee como precio oficial y el cliente reclama el centavo | La UI dice siempre "≈" y muestra el T.C. usado; el ticket imprime el T.C. en la etiqueta |
| 8 | Precisión: `Decimal` en el backend, `number` en el frontend | El frontend solo pinta; el único valor que se persiste (`usd_rate`) y el que se imprime los calcula el backend con `Decimal` |

## 9. Fases y estimación

| Fase | Contenido | Tareas del plan | Estimación |
|---|---|---|---|
| A1 | Modelo `ExchangeRate`, columnas de `organization`, servicio puro | Task 1 | 0.5 día |
| A2 | Cliente Banxico, job diario, tres endpoints | Task 2 | 0.5 día |
| A3 | Snapshot en la venta, línea del ticket y del reemitido | Task 3 | 0.5 día |
| A4 | Store, utilidades puras, CartPanel, ProductSearch, Organization.tsx | Task 4 | 0.5 día |
| **A** | **Total Fase A** | **1–4** | **~2 días** |
| B | Cobro en USD (§7) | por planear | ~3 días |

La Fase A se despliega sola y es invisible hasta que un dueño entra a
**Empresa → Tipo de cambio USD** y elige un modo distinto de `off`.
