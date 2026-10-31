# Crédito a clientes: cobranza sobre lo que ya existe — diseño

**Fecha:** 2026-10-29 · **Estado:** diseño aprobado en conversación, pendiente de plan ·
**Caso guía:** Eleven Fashion (org 17, una sucursal, ULTRA+): clientas que se llevan prendas y
las van pagando poco a poco. **Quién lo usa:** la cajera desde el POS (fiar, abonar, ver lo
que debe); DUEÑO, ADMINISTRADOR y GERENTE desde el admin (quién debe, cuánto, desde cuándo).
**Antecedente:** `docs/AUDITORIA-CRM-CREDITO-2026-10-28.md` (en `main` 0a5aa594) dejó el
crédito funcionando: fiar con enganche, abonos por ticket o libres (FIFO), cancelación y
devoluciones de ventas fiadas, antigüedad por cargo. Este spec cubre lo que esa auditoría dejó
en su §3.

## 1. Decisiones del dueño

1. **La cajera decide a quién fía.** Cualquier cliente registrado, sin tope de crédito, sin
   PIN ni autorización. `credit_limit` y `credit_days` se quedan en el modelo sin uso.
2. **Abonos libres.** Sin plan de pagos, sin fechas de vencimiento, sin intereses.
3. **Dos interfaces.** Dueño y admin: vista detallada. Cajera: solo acciones, interfaz básica.
4. **"Ventas hoy" cuenta la venta fiada el día que sale la mercancía.** Lo que se cobra
   después es cobranza, no venta. Hoy el sistema hace lo contrario (la venta no cuenta hasta
   liquidarse y ese día cuenta completa).

Fuera de alcance, a propósito: límites de crédito, planes de pago, intereses, envío
automático de mensajes, tablas o columnas nuevas.

## 2. Regla de ventas y corte de caja

### 2.1 Qué es una venta fiada

Un `SalesDocument` con `status = PENDING` y `customer_id IS NOT NULL`. Un PENDING sin cliente
sigue siendo lo que era (una venta que no terminó de cobrarse) y sigue fuera de todo reporte.

La condición se define **una sola vez** en `app/services/cash_reconciliation.py`, junto a
`SALES_REPORT_STATUSES`, como un helper que devuelve la expresión SQL
`status IN SALES_REPORT_STATUSES OR (status = PENDING AND customer_id IS NOT NULL)`. La tupla
`SALES_REPORT_STATUSES` no cambia; cambia quién la usa directo:

| Consumidor | Hoy | Después |
|---|---|---|
| `metricas_ventas.filtros_documentos` | `status.in_(SALES_REPORT_STATUSES)` | helper |
| `cash.get_session_audit_data` (ventas totales, tickets, impuestos) | tupla | helper |
| `cash.get_branch_cash_summary` (`sales_total`, `ticket_count`) | tupla | helper |
| `reports_inicio` (ventas por método, cobros) | tupla | helper |

El comentario de `cash_reconciliation.py` que declara "PENDING fuera de forma PERMANENTE" se
reescribe: su motivo (PENDING no tenía `total_amount` neteado tras una devolución) ya no
aplica, `approve_return` reescribe `total_amount` sea cual sea el estado desde la auditoría.
`CASH_INCLUDED_STATUSES` y el efectivo esperado **no cambian**: ya suman solo `Payment.amount`,
es decir, lo que entró físicamente.

### 2.2 Dos cifras nuevas en la regla de ventas

`metricas_ventas.Resumen` gana `fiado` y `cobranza` (float, 2 decimales), con sus
equivalentes en `SucursalInicio` y en el resumen de `/reports/dashboard`:

- **fiado** del periodo: suma de los cargos del ledger (`CustomerLedgerEntry.amount > 0`)
  cuyo `sales_document_id` apunta a un documento del ámbito creado en el periodo. Es lo que
  quedó a cuenta en esas ventas, neto de lo que la devolución o cancelación ya revirtió
  (la reversión también es un asiento, negativo, ligado al documento; se resta).
- **cobranza** del periodo: suma de abonos (`amount < 0`, sin contar reversiones) hechos en
  el periodo, atribuidos a sucursal por la caja del `Payment` que los acompañó
  (`Payment.cash_session_id → CashSession.branch_id`); un abono sin caja cuenta en "toda la
  organización" y en ninguna sucursal.

Distinguir abono de reversión sin columna nueva: la reversión lleva descripción con prefijo
`Cancelación` o `Devolución` y **siempre** `sales_document_id`; el abono lleva prefijo
`ABONO A TICKET` o `PAGO RECIBIDO`. El helper que clasifica un asiento vive en
`app/modules/customers/services.py` y es el único que conoce los prefijos.

Invariante que se prueba: en un periodo, `neta = cobrado_en_ventas + fiado − devuelto`, donde
`cobrado_en_ventas` es lo pagado al momento de la venta (sin abonos posteriores).

### 2.3 Corte de caja

`get_session_audit_data` añade en `kpis`:

- `credit_sales`: fiado del turno (cargos ligados a documentos del turno, según
  `session_sales_filter`).
- `customer_payments`: abonos cobrados en el turno (`Payment` con ese `cash_session_id` cuyo
  documento no es del turno o es NULL, más los abonos sin documento). Ya están dentro del
  desglose por método; aquí solo se nombran.

El ticket del corte (`pos_printer.build_cash_cut_bytes`) imprime, después de "Ventas
totales", el renglón `Fiado` y, dentro de los cobros, `Abonos a cuenta`, solo si son mayores
que cero. La pantalla de corte (`CashBranchView`, `CashHistory`) muestra los mismos dos
renglones con el mismo criterio. Así la cajera cuadra: ventas = cobrado + fiado.

`get_branch_cash_summary` suma `credit_sales` y `customer_payments` en `totals` para el
dueño que mira el día completo.

**Defecto encontrado al diseñar, se corrige aquí:** el abono libre (sin ticket) nace como
`Payment` con `sales_document_id` NULL, y `compute_expected_cash` y los dos desgloses por
método hacen `join(SalesDocument)` (inner): ese efectivo entra al cajón y **no** entra al
esperado ni al desglose. Los tres queries pasan a `outerjoin` y aceptan el pago sin documento
(`SalesDocument.id IS NULL`) junto a los estados de `CASH_INCLUDED_STATUSES`. La rama (b) de
`session_payments_filter` no cambia: un pago sin documento solo entra por su propio
`cash_session_id`, que el endpoint de abono ya asigna cuando hay caja abierta.

## 3. Cuentas por cobrar (dueño, admin, gerente)

### 3.1 Endpoint

`GET /api/customers/cobranza` en `app/modules/customers/router.py`, gateado por el módulo
`crm` como todo el router y por rol: solo `HQ_ROLES` de `metricas_ventas` (ADMINISTRADOR,
GERENTE, DUEÑO) y SUPERADMIN; los demás reciben 403. Parámetros: `branch_id` (opcional:
sucursal de la última venta fiada del cliente), `bucket` (`current`, `31_60`, `61_90`,
`91_plus`, opcional), `search` (nombre o teléfono), `skip`, `limit` (tope 200), `order`
(`saldo` por defecto, o `antiguedad`).

Respuesta:

```
{
  "resumen": { "por_cobrar": 0.0, "vencido_30": 0.0, "clientes": 0, "a_favor": 0.0 },
  "items": [
    { "id", "name", "phone", "balance", "cargo_mas_viejo": fecha|null, "dias": int,
      "ultimo_abono": fecha|null, "branch_id": int|null, "branch_name": str|null,
      "tickets_abiertos": int,
      "antiguedad": { "current", "31_60", "61_90", "91_plus" } }
  ],
  "total": int
}
```

`antiguedad` sale de `antiguedad_por_cargo(asientos_del_cliente(...))`, que ya existe y ya
cuadra con `current_balance`. `vencido_30` es la suma de `31_60 + 61_90 + 91_plus` de todos
los clientes del filtro. `a_favor` suma los saldos negativos (clientes con saldo a favor) y
se muestra aparte; no se resta de `por_cobrar`. La lista excluye clientes con saldo cero.

El cálculo recorre asientos en Python por cliente, como hoy `/reports/aging-report`. Con el
volumen de las boutiques (decenas de clientes con deuda) alcanza; el `limit` acota el costo.
`/reports/aging-report` se queda como está.

### 3.2 Pantalla

Ruta `/customers/cobranza`, archivo `frontend/src/pages/crm/Cobranza.tsx`, `lazy()` en
`App.tsx`, entrada en `ROLE_ROUTES` de ADMINISTRADOR, DUEÑO y GERENTE, y un enlace
"Cuentas por cobrar" desde la cabecera de `/customers`. No se agrega al menú lateral (es una
vista de Clientes). En modo básico se esconde (`OCULTAS_BASICO_HQ`): las orgs FREE no fían.

Cabecera `CabeceraPagina` con tres cifras: Por cobrar, Vencido a más de 30 días, Clientes con
deuda. `BarraFiltros`: búsqueda, selector de sucursal (solo si hay más de una que vende,
`useSucursalesVendibles`), filtro de antigüedad, orden. Tabla en escritorio; en teléfono
`ListaTarjetas` + `TarjetaFila` (receta 5 de CLAUDE.md). Columnas: cliente, teléfono, saldo,
desde (fecha del cargo más viejo y días), último abono, sucursal, antigüedad como cuatro
chips con color por tramo (`bg-dax-*`, nunca hex sueltos: `coloresPorTokens` lo vigila).

Al pulsar un renglón se abre el detalle del cliente en `ui/Modal` tamaño grande (en
teléfono ocupa toda la pantalla, como el resto del kit) con: saldo, tickets abiertos (`/unpaid-documents`), últimos 30
asientos (`/statement`), y cuatro botones: Registrar abono (mismo modal de `Customers.tsx`,
extraído a `components/crm/AbonoModal.tsx`), Estado de cuenta PDF (`/pdf-statement`),
Recordar por WhatsApp (§5) y Ver ticket (enlace a `/sales?folio=`).

### 3.3 Inicio

`InicioResponse` gana `por_cobrar: Optional[PorCobrar]` con `{ total, vencido_30, clientes }`,
solo con `completo=true`, solo para roles HQ y solo si el módulo `crm` está encendido; en
otro caso `None`. El Inicio del admin (`pages/hq/Inicio.tsx`) pinta una tarjeta "Por cobrar"
junto a las de pendientes, con el total, el vencido en rojo si es mayor que cero, y enlace a
`/customers/cobranza`. Si `por_cobrar` es `None` o el total es cero, la tarjeta no se
renderiza (render condicional, no `hidden`).

## 4. Abonar desde el POS (cajera)

### 4.1 Interfaz

En `CustomerModal.tsx`, cuando el cliente ya elegido tiene `current_balance > 0`, aparece el
botón "Abonar" junto a "Quitar cliente". Abre `components/crm/AbonoModal.tsx` (el mismo que
usa el admin, modo `basico`): monto, método (efectivo, tarjeta, transferencia), referencia
(obligatoria si no es efectivo), y un selector opcional "Aplicar a ticket" que lista
`/unpaid-documents` con folio, fecha y saldo; por defecto "Al más viejo primero". Al
confirmar llama `POST /customers/{id}/pay`, cierra, refresca el saldo del carrito
(`CartPanel` ya lo consulta) y muestra toast "Abono de $X · Saldo: $Y". Después ofrece
imprimir el recibo con la misma casilla "Imprimir" que el cobro.

La cajera no ve antigüedad, lista de deudores ni estado de cuenta. En el POS no se agrega
nada más.

Errores: 422 del backend se muestran tal cual en el modal (ya traen `detail` accionable:
caja cerrada para efectivo, monto mayor que el ticket, cliente inactivo).

### 4.2 Respuesta del endpoint de pago

`POST /customers/{id}/pay` deja de devolver un solo `LedgerEntryResponse` y devuelve:

```
{
  "entries": [LedgerEntryResponse, ...],       # lo que ya devuelve aplicar_abono
  "customer_balance_before": Decimal,
  "customer_balance_after": Decimal,
  "applied": [ { "sales_document_id", "folio", "amount", "paid_in_full": bool } ],
  "unapplied": Decimal,                         # saldo a favor que quedó sin ticket
  "payment_id": str,                            # UUID del Payment
  "method": str, "reference": str|null, "received_at": datetime
}
```

`Customers.tsx` (único consumidor de hoy) se ajusta a `entries[0]` donde usaba el asiento.

### 4.3 Recibo de abono

`POST /api/printer/print-abono/{payment_id}` en `app/routers/printer.py`. Busca el `Payment`,
verifica org y sucursal como `print_ticket_endpoint`, y arma los bytes con un método nuevo
`pos_printer.build_abono_bytes(...)`: encabezado del negocio (como el ticket), "RECIBO DE
ABONO", fecha y hora de México, cliente, monto, método y referencia, tickets a los que se
aplicó (folio y monto), "Saldo anterior" y "Saldo actual", cajera, y pie con el folio
`AB-{payment_id}`. Sin apertura de cajón. Responde el mismo `ready_to_print` con base64 que
el ticket, y el POS lo manda al agente con `printerApi` como hoy. La reimpresión se hace
llamando el mismo endpoint otra vez; no requiere PIN.

Los datos de "aplicado" se reconstruyen desde el ledger: los asientos negativos creados en la
misma transacción que el `Payment` (mismo `customer_id`, `created_at` igual al del pago con
tolerancia de 2 segundos) con `sales_document_id`. "Saldo anterior" = saldo actual − suma de
esos asientos. Sin columna nueva.

## 5. Recordatorio por WhatsApp

Botón "Recordar por WhatsApp" en el panel de cobranza (§3.2) y en el renglón de la tabla.
Abre en pestaña nueva `https://wa.me/{telefono}?text={mensaje}` con el teléfono normalizado
a E.164 de México con `toWaPhone` y el mensaje:

> Hola {nombre}, te saludamos de {negocio}. Tienes un saldo pendiente de {saldo}. Puedes
> pasar a abonar cuando gustes. ¡Gracias!

`{negocio}` es el nombre de la organización que ya trae `/me/context`. Si el cliente no tiene
teléfono marcable, el botón se deshabilita con tooltip "Sin teléfono". No se registra nada en la
base: el dueño ve en WhatsApp cuándo escribió. La normalización ya existe: `toWaPhone` en
`frontend/src/utils/phone.ts` (10 dígitos → `52` + dígitos; 12 con `52` o 13 con `521` se
respetan; otra longitud → `null`); se reutiliza y se le añade prueba unitaria si no la tiene.

## 6. Cabos de la auditoría

1. **Abono en efectivo de un rol sin sucursal.** `POST /customers/{id}/pay` con método
   efectivo y `current_user.branch_id` nulo responde 422 "Para recibir efectivo elige una
   sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar". Tarjeta y
   transferencia siguen pasando con `cash_session_id` NULL.
2. **Conciliación de abonos viejos sin ticket.** `scripts/conciliar_abonos_fifo.py --org N
   [--dry-run]`: por cliente con asientos negativos sin `sales_document_id` anteriores al
   2026-10-28 y tickets PENDING con cliente, recorre los tickets del más viejo al más nuevo y,
   sin crear asientos nuevos, marca PAID los que esos abonos cubren por completo (`saldo_documento`
   ya los calcula con el respaldo legado). Imprime qué haría y, sin `--dry-run`, lo hace. No
   toca `current_balance`.
3. **Colores del portal.** `pages/portal/Portal.tsx` pinta saldo deudor (`> 0`) en rojo y a
   favor (`< 0`) en verde, igual que el CRM, con tokens `text-dax-danger` / `text-dax-success`.

## 7. Esquema, permisos y riesgos

- **Sin ALTER.** Ninguna tabla ni columna nueva; `railway_init.py` no se toca.
- **Permisos.** Cobranza e Inicio "Por cobrar": roles HQ. Abonar: cualquier rol con el módulo
  `crm` (hoy ya es así). Recibo: cualquier usuario con acceso a la sucursal del pago.
- **Riesgo principal:** la regla de ventas y el corte (`cash.py`) tienen pruebas que fijan
  que PENDING no cuenta. Esas pruebas cambian de sentido: PENDING **con cliente** cuenta,
  PENDING sin cliente no. `tests/test_cash_*`, `tests/test_metricas_ventas*`,
  `tests/test_reports_inicio*` se revisan una por una; ninguna se borra, se reescribe la
  expectativa.
- **Eleven hoy no fía** por sistema (fiaba en libreta): no hay datos que migrar; el script
  del §6.2 queda para cuando se migre a otra org.

## 8. Pruebas

**pytest**

- Regla: venta fiada con enganche cuenta completa en `resumen` del día; el abono del día
  siguiente no suma venta y sí `cobranza`; `fiado` del día es el total menos el enganche;
  cancelarla la saca; devolverla parcialmente resta `devuelto` y ajusta `fiado`; un PENDING
  sin cliente sigue sin contar. Invariante del §2.2.
- Corte: turno con una venta fiada y un abono a un ticket de otro turno: `kpis.total_sales`
  incluye la fiada, `credit_sales` y `customer_payments` correctos, `expected.cash_physical`
  igual que antes del cambio.
- Cobranza: 403 a cajera; resumen y antigüedad cuadran con `current_balance`; filtros por
  sucursal, bucket y búsqueda; orden; saldo a favor aparte; cliente en cero no aparece.
- Pago: respuesta nueva con `applied`, `unapplied` y saldos; 422 efectivo sin sucursal.
- Recibo: bytes contienen "RECIBO DE ABONO", folio, tickets aplicados y saldos; 403 de otra
  org; 404 de pago inexistente.
- Script de conciliación: con `--dry-run` no cambia nada; sin él marca PAID lo cubierto.
- Inicio: `por_cobrar` solo con `completo`, solo HQ, `None` sin módulo.

**vitest**

- `Cobranza.tsx`: pinta cifras y renglones, chips de antigüedad, botón de WhatsApp
  deshabilitado sin teléfono, versión de teléfono con tarjetas.
- `AbonoModal.tsx`: referencia obligatoria fuera de efectivo, selector de ticket, muestra el
  422 del backend, llama a imprimir al confirmar.
- `CustomerModal.tsx`: "Abonar" solo con saldo mayor que cero.
- `Inicio.tsx`: tarjeta "Por cobrar" solo cuando viene y es mayor que cero.
- `utils/whatsapp.ts`: normalización de teléfonos.
- Guardias existentes: `coloresPorTokens` (la pantalla nueva entra limpia), `overlaysFueraDelKit`,
  `botonesDelKit`, `responsivoOla2` (añadir `Cobranza.tsx`).

Presupuesto del bundle: la pantalla va en `lazy()`; el POS solo crece por `AbonoModal`, que
también se carga perezoso desde `CustomerModal`.
