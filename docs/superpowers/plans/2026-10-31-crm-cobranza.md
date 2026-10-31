# Crédito a clientes: cobranza — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una venta fiada cuente como venta el día que sale la mercancía, que el corte y los reportes separen fiado y cobranza, que el dueño vea quién debe y desde cuándo, y que la cajera abone desde el POS con recibo.

**Architecture:** Sin tablas nuevas. Una sola expresión SQL define "venta reconocida" (cobrada o fiada) y la consumen la regla de ventas, el corte y el Inicio. El ledger de clientes que dejó la auditoría 2026-10-28 (`app/modules/customers/services.py`) es la fuente de fiado, cobranza y antigüedad. Una pantalla nueva de cuentas por cobrar, un modal de abono compartido entre admin y POS, y un recibo ESC/POS que viaja por el agente de impresión como el ticket.

**Tech Stack:** FastAPI + SQLAlchemy (pytest en SQLite), React 18 + Vite + TS + Tailwind (vitest + testing-library), ESC/POS vía `app/pos_printer.py`.

**Spec:** `docs/superpowers/specs/2026-10-29-crm-cobranza-design.md` (léelo antes de cada tarea; el plan argumenta desde él).

## Global Constraints

- **Sin ALTER.** Ninguna tabla ni columna nueva; `scripts/railway_init.py` no se toca.
- **Venta fiada = `doc_type = INVOICE AND status = PENDING AND customer_id IS NOT NULL`.** Un PENDING sin cliente sigue fuera de todo reporte, y las cotizaciones y pedidos (QUOTE/ORDER) PENDING tampoco cuentan.
- **`CASH_INCLUDED_STATUSES` y el efectivo esperado no cambian de criterio**: suman `Payment.amount`, lo que entró físicamente. La única corrección es que el abono libre (pago sin documento) ya entre.
- **Prefijos de reversión del ledger:** `Cancelación` y `Devolución`; solo `app/modules/customers/services.py` los conoce.
- **Copy exacto:** renglones del corte `Fiado` y `Abonos a cuenta`; título del recibo `RECIBO DE ABONO`; folio del recibo `AB-{payment_id[:8].upper()}`; botón del POS `Abonar`; pantalla `Cuentas por cobrar` en `/customers/cobranza`; 422 del efectivo sin sucursal: `Para recibir efectivo elige una sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar`.
- **Mensaje de WhatsApp:** `Hola {nombre}, te saludamos de {negocio}. Tienes un saldo pendiente de {saldo}. Puedes pasar a abonar cuando gustes. ¡Gracias!`
- **Roles:** cuentas por cobrar e Inicio "Por cobrar" solo `HQ_ROLES` de `metricas_ventas` (ADMINISTRADOR, GERENTE, DUEÑO) y SUPERADMIN. Abonar: cualquier rol con el módulo `crm`.
- **Frontend:** colores por tokens (`text-dax-*`, `bg-dax-*`), kit `ui/` (`Modal`, `CabeceraPagina`, `BarraFiltros`, `ListaTarjetas`, `TarjetaFila`, `KpiCard`), botones `dax-btn-*`, render condicional (nunca `hidden`), rejillas con prefijo (`grid-cols-1 sm:grid-cols-2`), pantalla nueva en `lazy()`.
- **Pruebas:** backend `python3 -m pytest -q --ignore=tests/test_cash_complete.py <archivo>`; un solo proceso de pytest por worktree. Frontend `cd frontend && npx vitest run <archivo>`; `npx tsc --noEmit` antes de cada commit que toque `.ts/.tsx`.
- **Commits:** mensajes `feat(crm): …` / `fix(cash): …` / `test: …`, terminados con las dos líneas de atribución que exige el harness. Nunca `git stash` a secas (el stash es compartido entre worktrees). Nunca push.
- **No dejes `print()` de debug.** Comentarios en español, como el código circundante.

## Review Focus

1. **Abono libre en efectivo sin ticket** debe sumar al efectivo esperado y al desglose del corte (hoy el `join` interno lo deja fuera). Prueba en Tarea 2: `test_el_abono_libre_en_efectivo_entra_al_esperado_y_al_desglose`.
2. **Venta fiada cancelada el mismo día** no debe contar como venta ni dejar fiado. Pruebas en Tarea 2 (`test_la_venta_fiada_cancelada_no_deja_fiado`) y Tarea 4 (`test_fiado_del_dia_ignora_la_venta_cancelada`).
3. **Devolución parcial de una venta fiada** baja la venta neta y el fiado del día, y no saca efectivo. Prueba en Tarea 4: `test_la_devolucion_de_una_fiada_baja_neta_y_fiado`.
4. **Cliente con saldo a favor** no aparece como deudor en cuentas por cobrar, pero sí suma en `a_favor`. Prueba en Tarea 7: `test_el_saldo_a_favor_va_aparte_y_el_cero_no_aparece`.
5. **Teléfono con espacios, guiones o `+52`** debe abrir WhatsApp; sin teléfono marcable el botón se deshabilita con "Sin teléfono". Pruebas en Tarea 11: `phone.test.ts` y `Cobranza.test.tsx`.

## Desviaciones del spec (resueltas aquí)

- §3.2 nombraba un botón "Ver ticket" con enlace a `/sales?folio=`; `SalesHistory.tsx` no lee parámetros de búsqueda, así que el detalle muestra el folio como texto y no enlaza. Si se quiere el enlace, es otra tarea sobre `SalesHistory`.
- §6.1 cambia una prueba vigente: `tests/test_abono_en_efectivo_exige_caja.py::test_el_rol_de_oficina_sin_sucursal_sigue_exento` fijaba la exención que el dueño decidió quitar. Se reescribe (Tarea 5), no se borra.

## Hallazgo fuera de alcance (decisión del usuario pendiente)

Al verificar la Tarea 4 se comprobó en SQLite (venta cobrada de $200, devolución aprobada de
una pieza) que `approve_return` reescribe `total_amount` al neto ($100) **y** `metricas_ventas`
vuelve a restar `SaleReturn.total_refunded` ($100): la venta neta del día sale en $0 cuando
debería ser $100. Afecta Inicio, Reportes y `/sales/stats` en producción desde que ambas
reglas conviven; no lo introduce esta rama ni lo corrige. Ninguna prueba de reportes aprueba
una devolución por la API (`tests/test_metricas_ventas.py` siembra `SaleReturn` sin reescribir
el total). Corrección candidata, aparte de este plan: que `metricas_ventas` tome la venta bruta
como `total_amount + devoluciones aprobadas del documento` (o deje de restar), con una prueba
end-to-end vía `approve_return`.

## Mapa de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `app/services/cash_reconciliation.py` | `filtro_venta_reconocida()`, `filtro_pago_cobrado()`, `fiado_de_sesion()`, `abonos_de_sesion()`; `compute_expected_cash` con `outerjoin` |
| `app/services/metricas_ventas.py` | `filtros_documentos` usa el filtro; `Resumen.fiado` / `Resumen.cobranza`; `fiado()`, `cobranza()`, `por_sucursal` |
| `app/modules/customers/services.py` | clasificación de asientos (`es_abono`, `es_reversion`, filtros SQL), `cargos_pendientes`, `detalle_del_abono`, `cuentas_por_cobrar` |
| `app/modules/customers/schemas.py` | `AbonoAplicado`, `AbonoResponse`, `ClienteCobranza`, `ResumenCobranza`, `CobranzaResponse` |
| `app/modules/customers/router.py` | `GET /cobranza`, `POST /{id}/pay` (respuesta nueva, 422 efectivo sin sucursal) |
| `app/routers/cash.py` | corte de sesión y resumen de sucursal: venta reconocida, `credit_sales`, `customer_payments` |
| `app/routers/reports.py`, `app/routers/reports_inicio.py`, `app/schemas/reports.py` | `credit_sales`/`collections` en el dashboard; `fiado`/`cobranza` en `PeriodoVentas`; `por_cobrar` en el Inicio |
| `app/routers/printer.py`, `app/pos_printer.py` | `POST /printer/print-abono/{payment_id}`, `build_abono_bytes`, renglones del corte |
| `scripts/conciliar_abonos_fifo.py` | conciliación de abonos viejos sin ticket |
| `frontend/src/api/customers.ts`, `cash.ts`, `printer.ts`, `reports.ts` | tipos y llamadas nuevas |
| `frontend/src/components/crm/AbonoModal.tsx` | modal de abono compartido (admin y POS) |
| `frontend/src/pages/crm/Cobranza.tsx` | pantalla de cuentas por cobrar |
| `frontend/src/pages/crm/Customers.tsx`, `components/pos/modals/CustomerModal.tsx`, `components/pos/CartPanel.tsx`, `store/posStore.ts` | usar el modal; botón Abonar; refresco del saldo |
| `frontend/src/pages/hq/Inicio.tsx`, `pages/finance/CashHistory.tsx`, `components/branch/CashBranchView.tsx`, `pages/portal/Portal.tsx` | tarjeta Por cobrar; renglones Fiado/Abonos; colores del portal |
| `frontend/src/App.tsx`, `components/layout/navConfig.ts`, `navPerfilBasico.ts`, `pages/__tests__/responsivoOla2.test.ts` | ruta, roles, modo básico, guardia responsiva |
| `docs/API_REFERENCE.md`, `docs/FRONTEND_VIEWS.md`, `docs/AUDITORIA-CRM-CREDITO-2026-10-28.md`, `CLAUDE.md` | documentación |

---

### Task 1: La venta fiada cuenta como venta (regla única)

**Files:**
- Modify: `app/services/cash_reconciliation.py` (bloque de `SALES_REPORT_STATUSES`, ~líneas 86-122)
- Modify: `app/services/metricas_ventas.py:1-11` (docstring), `:28` (import), `:131-140` (`filtros_documentos`)
- Modify: `app/routers/reports_inicio.py:44` (import), `:196-210` (`_sin_movimiento`)
- Modify: `CLAUDE.md` §6 viñeta "Una sola regla de venta en reportes"
- Test: `tests/test_metricas_ventas.py`

**Interfaces:**
- Produces: `app.services.cash_reconciliation.filtro_venta_reconocida() -> sqlalchemy expression` (sobre `SalesDocument`). Las tareas 2, 4 y 7 la usan.

- [ ] **Step 1: Escribe la prueba que falla**

En `tests/test_metricas_ventas.py`, amplía `_venta` (líneas 28-48) con dos kwargs al final de la firma, `customer_id=None, pagado=None`, y usa ambos:

```python
def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID,
           metodo=PaymentMethod.CASH, entregado=None, costo="40", customer_id=None, pagado=None):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"), total_amount=Decimal(total),
        status=status, doc_type="ORDER", customer_id=customer_id,
        change_given=(Decimal(entregado) - Decimal(total)) if entregado else None,
    )
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description=f"Producto {doc.folio}", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal(costo)))
    # `pagado="0"` = venta fiada sin enganche: ningún Payment.
    if pagado is None or Decimal(pagado) > 0:
        pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo,
                       amount=Decimal(entregado or pagado or total))
        pago.created_at = doc.created_at
        db.add(pago)
    db.commit()
    return doc
```

Añade después de `_devolucion` un helper y, en la sección `# --- Resumen ---`, la prueba:

```python
def _cliente(db, org, nombre="Clienta"):
    from app.modules.customers.models import Customer
    c = Customer(name=nombre, organization_id=org.id, current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def test_resumen_cuenta_la_venta_fiada_el_dia_que_nace(db, org, branch_a, cajero_a, products_setup):
    """Spec 2026-10-29 §2.1: PENDING con cliente es venta fiada y cuenta completa
    el día que sale la mercancía; PENDING sin cliente sigue fuera."""
    cliente = _cliente(db, org)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "300", status=DocumentStatus.PENDING,
           customer_id=cliente.id, pagado="50")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "999", status=DocumentStatus.PENDING)
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (r.bruta, r.tickets) == (400.0, 2)
    assert mv.por_sucursal(db, org.id, mv.periodo_preset("hoy"))[branch_a.id].bruta == 400.0
```

- [ ] **Step 2: Córrela y confirma que falla**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_metricas_ventas.py -k fiada`
Expected: FAIL con `assert (100.0, 1) == (400.0, 2)`.

- [ ] **Step 3: Define `filtro_venta_reconocida` y reescribe el comentario**

En `app/services/cash_reconciliation.py`, el comentario que precede a `SALES_REPORT_STATUSES` termina con el párrafo que empieza en `#     PENDING NO tiene ese ajuste:` y acaba en `#     motivo.` Sustituye ese párrafo (solo ese) por:

```python
#     PENDING: desde 2026-10-31 (spec crm-cobranza §2.1) la tupla sigue sin
#     PENDING, pero quien pregunta "¿cuenta como venta?" ya no usa la tupla
#     directo: usa `filtro_venta_reconocida()`, que suma la venta FIADA
#     (PENDING con cliente). El motivo histórico para excluir PENDING —su
#     `total_amount` no se neteaba tras una devolución— ya no existe:
#     `approve_return` reescribe `total_amount` sea cual sea el estado. Un
#     PENDING sin cliente (venta que no terminó de cobrarse) sigue fuera.
```

Y justo después de la tupla `SALES_REPORT_STATUSES = (...)` añade:

```python
def filtro_venta_reconocida():
    """Expresión SQL de "este documento cuenta como venta" (spec 2026-10-29 §2.1).

    Cobrada (PAID / REFUNDED_*) o **fiada**: PENDING con cliente del CRM. La
    venta fiada cuenta el día que sale la mercancía; los abonos que lleguen
    después son cobranza, no venta. Un PENDING sin cliente sigue fuera.
    """
    return or_(
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
        and_(SalesDocument.status == DocumentStatus.PENDING, SalesDocument.customer_id.isnot(None)),
    )
```

(`or_`, `and_`, `SalesDocument` y `DocumentStatus` ya están importados en ese archivo.)

- [ ] **Step 4: Úsala en la regla de ventas y en el Inicio**

`app/services/metricas_ventas.py`:
- Línea 28: `from app.services.cash_reconciliation import filtro_venta_reconocida` (quita `SALES_REPORT_STATUSES` del import si ya no lo usa nadie en el archivo).
- En `filtros_documentos`, sustituye `SalesDocument.status.in_(SALES_REPORT_STATUSES),` por `filtro_venta_reconocida(),`.
- En el docstring del módulo, cambia la frase `Venta neta = documentos en \`SALES_REPORT_STATUSES\` a su \`total_amount\` original` por `Venta neta = documentos cobrados o fiados (\`filtro_venta_reconocida\`) a su \`total_amount\``.

`app/routers/reports_inicio.py`:
- Línea 44: importa también `filtro_venta_reconocida`.
- En `_sin_movimiento`, sustituye `SalesDocument.status.in_(SALES_REPORT_STATUSES),` por `filtro_venta_reconocida(),` y en el docstring `Solo cuentan ventas en \`SALES_REPORT_STATUSES\`` por `Solo cuentan ventas reconocidas (cobradas o fiadas)`. Si `SALES_REPORT_STATUSES` queda sin uso en el archivo, quítalo del import.

`CLAUDE.md` §6, viñeta **Una sola regla de venta en reportes**: cambia `(cobradas − devoluciones aprobadas, día de México)` por `(cobradas o fiadas a cliente − devoluciones aprobadas, día de México; `filtro_venta_reconocida` de `cash_reconciliation.py`)`.

- [ ] **Step 5: Corre las pruebas afectadas**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_metricas_ventas.py tests/test_reports_inicio.py tests/test_reports_dashboard.py tests/test_reports_daily_summary.py tests/test_cash_credito_y_abonos.py tests/test_crm_credito_auditoria.py`
Expected: todo PASS (las dos pruebas de `test_cash_credito_y_abonos` que fijan "PENDING no cuenta" siguen verdes porque su `_venta_pendiente` no tiene cliente).

- [ ] **Step 6: Commit**

```bash
git add app/services/cash_reconciliation.py app/services/metricas_ventas.py app/routers/reports_inicio.py CLAUDE.md tests/test_metricas_ventas.py
git commit -m "feat(reportes): la venta fiada cuenta como venta el día que sale la mercancía"
```

---

### Task 2: El corte separa fiado y abonos, y el abono libre entra al esperado

**Files:**
- Modify: `app/modules/customers/services.py` (imports línea 23; nuevas funciones antes de `# Cancelación y devolución`; `__all__`)
- Modify: `app/services/cash_reconciliation.py` (`compute_expected_cash` ~líneas 278-289; nuevas funciones al final)
- Modify: `app/routers/cash.py` (`get_session_audit_data` ~660-1000; `get_branch_cash_summary` ~1300-1470)
- Create: `tests/cobranza_helpers.py` (helpers que comparten las pruebas de las tareas 2, 5 y 6; `tests/` no es paquete y `pytest.ini` tiene `pythonpath = .`, así que se importa como `from tests.cobranza_helpers import …`)
- Test: `tests/test_cobranza_corte.py` (nuevo)

**Interfaces:**
- Consumes: `filtro_venta_reconocida()` (Tarea 1).
- Produces: en `app.modules.customers.services`: `PREFIJOS_REVERSION`, `es_reversion(asiento) -> bool`, `es_abono(asiento) -> bool`, `filtro_sql_reversion()`, `filtro_sql_cargo_o_reversion()`, `filtro_sql_abono()`. En `cash_reconciliation`: `filtro_pago_cobrado()`, `fiado_de_sesion(db, session) -> Decimal`, `abonos_de_sesion(db, session) -> Decimal`. En el JSON del corte: `kpis.credit_sales`, `kpis.customer_payments`; en el resumen de sucursal: `cashiers[].credit_sales`, `cashiers[].customer_payments`, `totals.credit_sales`, `totals.customer_payments`.

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `tests/cobranza_helpers.py` (sin prefijo `test_`: pytest no lo colecta):

```python
"""Helpers de las pruebas de cobranza (spec 2026-10-29): caja abierta,
cliente, venta fiada por la API y abono por la API."""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.modules.customers.models import Customer


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _cliente(db, org, nombre="Clienta"):
    c = Customer(name=nombre, organization_id=org.id, has_credit=False,
                 credit_limit=Decimal("0"), current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _fiar(client, h, cliente, sku, pagos=None):
    """Venta con cliente dejando saldo (el producto A vale 100)."""
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER", "customer_id": cliente.id,
        "items": [{"sku": sku, "quantity": 1}], "payments": pagos or [],
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _abonar(client, h, cliente, monto, metodo="CASH", documento=None):
    body = {"amount": str(monto), "method": metodo}
    if documento:
        body["sales_document_id"] = documento
    r = client.post(f"/api/customers/{cliente.id}/pay", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Módulos pos+crm, caja abierta de la cajera A; devuelve (headers, variante A, sesión)."""
    _habilitar(db, org, "pos", "crm")
    _, variant = products_setup["product_a"]
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    return h, variant, sesion
```

Crea `tests/test_cobranza_corte.py`:

```python
"""Corte de caja con ventas fiadas (spec 2026-10-29 §2.3).

La venta fiada cuenta en "Ventas totales" del turno; lo que quedó a cuenta se
reporta como `credit_sales` y los abonos cobrados en el turno como
`customer_payments`. El efectivo esperado no cambia de criterio, pero el abono
LIBRE (pago sin documento) por fin entra: el `join` interno a `SalesDocument`
lo dejaba fuera del cajón aunque los billetes estuvieran ahí.
"""
from app.modules.customers.models import CustomerLedgerEntry
from app.modules.customers.services import es_abono, es_reversion
from app.routers.cash import get_session_audit_data
from tests.cobranza_helpers import _abonar, _cliente, _escenario, _fiar


def test_la_venta_fiada_cuenta_en_el_corte_y_el_fiado_se_reporta(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "40.00"}])

    audit = get_session_audit_data(db, sesion.id)
    assert audit["kpis"]["total_sales"] == 100.0
    assert audit["kpis"]["total_tickets"] == 1
    assert audit["kpis"]["credit_sales"] == 60.0
    assert audit["kpis"]["customer_payments"] == 0.0
    assert audit["payments"]["cash"]["total"] == 40.0
    assert audit["expected"]["cash_physical"] == 40.0, "el esperado solo suma lo que entró"


def test_el_abono_libre_en_efectivo_entra_al_esperado_y_al_desglose(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Review Focus 1: el abono sin ticket nace como Payment sin documento y el
    join interno lo dejaba fuera del cajón."""
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    _abonar(client, h, cliente, "30")

    audit = get_session_audit_data(db, sesion.id)
    assert audit["payments"]["cash"] == {"total": 30.0, "count": 1}
    assert audit["expected"]["cash_physical"] == 30.0
    assert audit["kpis"]["customer_payments"] == 30.0
    assert audit["kpis"]["total_sales"] == 100.0
    assert audit["kpis"]["credit_sales"] == 100.0, "el abono es cobranza: no baja el fiado del turno"


def test_la_venta_fiada_cancelada_no_deja_fiado(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku)
    r = client.delete(f"/api/sales/{venta['sale_id']}", params={"reason": "Se arrepintió"}, headers=h)
    assert r.status_code == 200, r.text

    audit = get_session_audit_data(db, sesion.id)
    assert audit["kpis"]["total_sales"] == 0.0
    assert audit["kpis"]["total_tickets"] == 0
    assert audit["kpis"]["credit_sales"] == 0.0


def test_el_resumen_de_sucursal_suma_fiado_y_abonos(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a, auth_gerente_a, products_setup
):
    h, variant, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "40.00"}])
    _abonar(client, h, cliente, "30")

    r = client.get(f"/api/cash/branch-summary?branch_id={branch_a.id}",
                   headers={**auth_gerente_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totals"]["sales"] == 100.0
    assert data["totals"]["tickets"] == 1
    assert data["totals"]["credit_sales"] == 60.0
    assert data["totals"]["customer_payments"] == 30.0
    assert data["totals"]["cash"] == 70.0
    fila = next(c for c in data["cashiers"] if c["session_id"] == sesion.id)
    assert (fila["credit_sales"], fila["customer_payments"], fila["cash"]) == (60.0, 30.0, 70.0)


def test_las_reversiones_se_distinguen_de_los_abonos(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """La clasificación por prefijo es la única forma de separar un abono de
    una cancelación en el ledger; si alguien cambia el texto, esto truena."""
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    a = _fiar(client, h, cliente, variant.sku)
    _abonar(client, h, cliente, "20", documento=a["sale_id"])
    b = _fiar(client, h, cliente, variant.sku)
    assert client.delete(f"/api/sales/{b['sale_id']}", params={"reason": "x"}, headers=h).status_code == 200

    asientos = db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == cliente.id).order_by(CustomerLedgerEntry.id).all()
    assert [float(x.amount) for x in asientos] == [100.0, -20.0, 100.0, -100.0]
    assert [es_abono(x) for x in asientos] == [False, True, False, False]
    assert [es_reversion(x) for x in asientos] == [False, False, False, True]
```

- [ ] **Step 2: Córrelas y confirma que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_cobranza_corte.py`
Expected: FAIL/ERROR (`ImportError: cannot import name 'es_abono'`).

- [ ] **Step 3: Clasificación de asientos en el servicio de clientes**

En `app/modules/customers/services.py`, cambia la línea 23 a `from sqlalchemy import and_, case, func, or_` y añade, justo antes del bloque `# Cancelación y devolución`:

```python
# --------------------------------------------------------------------------
# Qué es cada asiento
# --------------------------------------------------------------------------
# Un asiento negativo es abono salvo que lo haya escrito una cancelación o una
# devolución (`revertir_cargo_de_documento` desde sales.py::cancel_sale y
# `aplicar_devolucion_a_saldo` desde crud/returns.py::approve_return). Este es
# el ÚNICO lugar que conoce los prefijos; `tests/test_cobranza_corte.py` los
# fija contra los textos reales.
PREFIJOS_REVERSION = ("Cancelación", "Devolución")


def es_reversion(asiento) -> bool:
    return _dec(asiento.amount) < 0 and (asiento.description or "").startswith(PREFIJOS_REVERSION)


def es_abono(asiento) -> bool:
    return _dec(asiento.amount) < 0 and not es_reversion(asiento)


def filtro_sql_reversion():
    return or_(*[CustomerLedgerEntry.description.like(f"{p}%") for p in PREFIJOS_REVERSION])


def filtro_sql_cargo_o_reversion():
    """Cargos (+) y sus reversiones (−): lo que suma al "fiado". Deja fuera los abonos."""
    return or_(CustomerLedgerEntry.amount > 0, filtro_sql_reversion())


def filtro_sql_abono():
    return and_(CustomerLedgerEntry.amount < 0, ~filtro_sql_reversion())
```

Agrega a `__all__`: `"PREFIJOS_REVERSION", "es_reversion", "es_abono", "filtro_sql_reversion", "filtro_sql_cargo_o_reversion", "filtro_sql_abono"`.

- [ ] **Step 4: El pago sin documento entra al esperado; fiado y abonos por sesión**

En `app/services/cash_reconciliation.py`:

(a) Después de `filtro_venta_reconocida` (Tarea 1) añade:

```python
def filtro_pago_cobrado():
    """Para queries sobre `Payment` con `.outerjoin(SalesDocument)`: el pago
    cuenta si su documento está en CASH_INCLUDED_STATUSES o si no tiene
    documento —abono libre a la cuenta del cliente (spec 2026-10-29 §2.3)—.
    Antes el `join` interno dejaba ese efectivo fuera del esperado aunque
    estuviera en el cajón."""
    return or_(SalesDocument.status.in_(CASH_INCLUDED_STATUSES), SalesDocument.id.is_(None))
```

(b) En `compute_expected_cash`, el query `cash_payments`: cambia `.join(SalesDocument)` por `.outerjoin(SalesDocument)` y la línea `SalesDocument.status.in_(CASH_INCLUDED_STATUSES),` por `filtro_pago_cobrado(),`. Añade al comentario de arriba: `# Outerjoin: el abono libre (Payment sin documento) también es efectivo que entró.`

(c) Al final del archivo:

```python
def fiado_de_sesion(db: Session, session: CashSession) -> Decimal:
    """Lo que quedó a cuenta en las ventas fiadas de este turno: cargos del
    ledger ligados a documentos del turno, netos de cancelación/devolución
    (spec 2026-10-29 §2.3). Los abonos no restan: son cobranza."""
    from app.modules.customers.models import CustomerLedgerEntry
    from app.modules.customers.services import filtro_sql_cargo_o_reversion
    total = (
        db.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0))
        .join(SalesDocument, SalesDocument.id == CustomerLedgerEntry.sales_document_id)
        .filter(session_sales_filter(session), filtro_venta_reconocida(), filtro_sql_cargo_o_reversion())
        .scalar()
    )
    return Decimal(str(total or 0))


def abonos_de_sesion(db: Session, session: CashSession) -> Decimal:
    """Abonos a cuenta cobrados en este turno. Son los `Payment` con
    `customer_id`: solo los crea `POST /customers/{id}/pay`; el checkout no
    pone cliente en el pago."""
    total = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.cash_session_id == session.id, Payment.customer_id.isnot(None))
        .scalar()
    )
    return Decimal(str(total or 0))
```

- [ ] **Step 5: El corte de sesión**

En `app/routers/cash.py::get_session_audit_data`:

1. En el `from app.services.cash_reconciliation import (...)` local añade `filtro_venta_reconocida, filtro_pago_cobrado, fiado_de_sesion, abonos_de_sesion,` y quita `SALES_REPORT_STATUSES` si queda sin uso en la función.
2. `payment_stats`: `.join(SalesDocument)` → `.outerjoin(SalesDocument)`; `SalesDocument.status.in_(CASH_INCLUDED_STATUSES),` → `filtro_pago_cobrado(),`. Al final del comentario de ese bloque añade: `# Outerjoin + filtro_pago_cobrado: el abono libre (sin documento) también entró por caja.`
3. `invoice_stats`: `SalesDocument.status.in_(SALES_REPORT_STATUSES),` → `filtro_venta_reconocida(),`. Sustituye el comentario `# 2. Impuestos y Subtotal (NETOS post-refund). ... con impuestos de dinero que todavía no se cobra.` por:
   ```python
   # 2. Impuestos y Subtotal (NETOS post-refund) de las ventas reconocidas:
   # cobradas o fiadas (spec 2026-10-29 §2.1). `approve_return` reescribe
   # estos campos al neto sea cual sea el estado, así que la fiada entra
   # completa el día que nace, igual que en "Ventas totales".
   ```
4. `total_sales_query` y `total_tickets`: `SalesDocument.status.in_(SALES_REPORT_STATUSES),` → `filtro_venta_reconocida(),`. Reescribe los dos comentarios que dicen que PENDING no cuenta: `# Ventas reconocidas (cobradas o fiadas): la fiada cuenta el día que sale la mercancía; lo que quedó a cuenta va aparte en kpis.credit_sales.` y, en tickets, `# La fiada es un ticket cerrado en mostrador aunque se liquide después.`
5. Antes del `return`, calcula:
   ```python
   fiado_turno = fiado_de_sesion(db, session)
   abonos_turno = abonos_de_sesion(db, session)
   ```
6. En `"kpis"` añade `"credit_sales": float(fiado_turno), "customer_payments": float(abonos_turno),`.
7. En `"expected"]["total_system"]` resta el fiado para que siga siendo dinero: `Decimal(str(grand_total_sales)) - fiado_turno + Decimal(str(session.opening_balance or 0)) + ...` con el comentario `# total_system es dinero: las ventas menos lo que quedó fiado.`

- [ ] **Step 6: El resumen de sucursal**

En `get_branch_cash_summary`:

1. Import local: añade `filtro_venta_reconocida, filtro_pago_cobrado, fiado_de_sesion, abonos_de_sesion` (quita `SALES_REPORT_STATUSES` si queda sin uso).
2. En el `return` temprano (sin sesiones) y en el diccionario `totals` inicial añade `"credit_sales": 0` / `Decimal(0)` y `"customer_payments": 0` / `Decimal(0)`.
3. `sales_total` y `ticket_count`: `SalesDocument.status.in_(SALES_REPORT_STATUSES),` → `filtro_venta_reconocida(),`.
4. `payment_stats`: `.join(SalesDocument)` → `.outerjoin(SalesDocument)`; `SalesDocument.status.in_(CASH_INCLUDED_STATUSES),` → `filtro_pago_cobrado(),`.
5. Dentro del loop, después de `live_difference`: `fiado_s = fiado_de_sesion(db, s)` y `abonos_s = abonos_de_sesion(db, s)`. En `cashier_data` añade `"credit_sales": float(fiado_s), "customer_payments": float(abonos_s),` y en los acumuladores `totals["credit_sales"] += fiado_s` y `totals["customer_payments"] += abonos_s`.
6. Actualiza el comentario largo de arriba del loop: sustituye la frase `sales_total/ticket_count (SALES_REPORT_STATUSES, a nivel DOCUMENTO vía session_sales_filter)` por `sales_total/ticket_count (filtro_venta_reconocida: cobradas o fiadas, a nivel DOCUMENTO vía session_sales_filter)`.

- [ ] **Step 7: Corre las pruebas**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_cobranza_corte.py tests/test_cash_credito_y_abonos.py tests/test_cash_reportes_atribucion_por_pago.py tests/test_abono_cliente_atribuye_caja.py tests/test_abono_en_efectivo_exige_caja.py tests/test_cash_math.py tests/test_cash_invariants.py tests/test_cash_audit.py tests/test_cash_opening_balance.py tests/test_abono_a_cuenta_sin_venta.py`
Expected: todo PASS.

- [ ] **Step 8: Commit**

```bash
git add app/modules/customers/services.py app/services/cash_reconciliation.py app/routers/cash.py tests/cobranza_helpers.py tests/test_cobranza_corte.py
git commit -m "feat(cash): el corte separa fiado y abonos; el abono libre entra al esperado"
```

---

### Task 3: Renglones "Fiado" y "Abonos a cuenta" en el ticket y en las pantallas del corte

**Files:**
- Modify: `app/pos_printer.py::build_cash_cut_bytes` (bloque `== COBRADO POR METODO ==` tras `Total cobrado`; bloque `== VENTAS NETAS ==` tras `Ventas Totales`)
- Modify: `frontend/src/api/cash.ts` (`CashSummary`, `getSummary`)
- Modify: `frontend/src/pages/finance/CashHistory.tsx:234-250`, `frontend/src/components/branch/CashBranchView.tsx:691-705`
- Test: `tests/test_corte_fiado_ticket.py` (nuevo), `frontend/src/api/__tests__/cashSummary.test.ts` (nuevo)

**Interfaces:**
- Consumes: `kpis.credit_sales`, `kpis.customer_payments` (Tarea 2).
- Produces: `CashSummary.credit_sales: number`, `CashSummary.customer_payments: number`.

- [ ] **Step 1: Prueba del ticket que falla**

Crea `tests/test_corte_fiado_ticket.py`:

```python
"""El ticket del corte imprime "Fiado" y "Abonos a cuenta" solo cuando son > 0
(spec 2026-10-29 §2.3). Así ventas = cobrado + fiado y la cajera cuadra."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.pos_printer import PosPrinter

MX = ZoneInfo("America/Mexico_City")


def _texto(raw: bytes, p: PosPrinter) -> str:
    out = raw
    for k, c in sorted(p.CMD.items(), key=lambda kv: len(kv[1]), reverse=True):
        if k != "LF" and c:
            out = out.replace(c, b"")
    return out.decode("latin-1", "replace")


def _audit(credit_sales=0.0, customer_payments=0.0):
    return {
        "session": {"id": 1, "opened_at": datetime(2026, 10, 30, 9, 0, tzinfo=MX), "closed_at": None,
                    "opening_balance": 0.0, "closing_balance": 0.0, "last_activity": None,
                    "user_name": "MIRNA", "branch_name": "ROMA", "organization_name": "ELEVEN"},
        "payments": {k: {"total": 0.0, "count": 0} for k in ("cash", "card", "transfer", "store_credit", "check", "others")}
        | {"cash": {"total": 70.0, "count": 2}},
        "movements": {"inflows": 0.0, "outflows": 0.0, "list": []},
        "returns": {"count": 0, "total": 0.0, "cash_refunds": 0.0, "list": [], "by_method": {}},
        "kpis": {"total_sales": 100.0, "total_tickets": 1, "avg_ticket": 100.0, "total_taxes": 0.0,
                 "subtotal": 100.0, "credit_sales": credit_sales, "customer_payments": customer_payments},
        "expected": {"cash_physical": 70.0, "total_system": 40.0},
        "reconciliation": {"reported": 0.0, "difference": 0.0, "diff_percent": 0.0},
    }


def test_imprime_fiado_y_abonos_cuando_los_hay():
    p = PosPrinter("x", paper_width_mm=80)
    lineas = _texto(p.build_cash_cut_bytes(_audit(credit_sales=60.0, customer_payments=30.0)), p).split("\n")
    fiado = next(l for l in lineas if l.strip().startswith("Fiado"))
    abonos = next(l for l in lineas if "Abonos a cuenta" in l)
    assert fiado.rstrip().endswith("$60.00")
    assert abonos.rstrip().endswith("$30.00")
    assert lineas.index(fiado) > lineas.index(next(l for l in lineas if "Ventas Totales" in l))
    assert lineas.index(abonos) < lineas.index(next(l for l in lineas if "Total cobrado" in l))


def test_sin_fiado_ni_abonos_el_ticket_es_el_de_siempre():
    p = PosPrinter("x", paper_width_mm=58)
    t = _texto(p.build_cash_cut_bytes(_audit()), p)
    assert "Fiado" not in t and "Abonos a cuenta" not in t


def test_un_corte_viejo_sin_las_claves_no_truena():
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit()
    del a["kpis"]["credit_sales"]; del a["kpis"]["customer_payments"]
    assert b"CORTE DE CAJA" in p.build_cash_cut_bytes(a)
```

- [ ] **Step 2: Córrela y confirma que falla**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_corte_fiado_ticket.py`
Expected: la primera FAIL con `StopIteration` (no hay renglón Fiado); las otras dos PASS.

- [ ] **Step 3: Los dos renglones en `build_cash_cut_bytes`**

En `app/pos_printer.py`, dentro del bloque `== COBRADO POR METODO ==`, **antes** de `raw += self._rline("Total cobrado", _total_cobrado)`:

```python
        # Abonos a cuenta cobrados en el turno. Informativo: YA están dentro
        # de los renglones por método (son Payment como cualquier otro); se
        # nombran para que la cajera sepa que parte de lo cobrado no es venta
        # de hoy sino cobranza de ventas fiadas (spec 2026-10-29 §2.3).
        _abonos = (kpis.get('customer_payments') or 0)
        if _abonos > 0:
            raw += self._rline("  Abonos a cuenta", _abonos)
```

Y en `== VENTAS NETAS ==`, **justo después** de `raw += self._rline("Ventas Totales", kpis['total_sales'])`:

```python
        # Lo que de esas ventas quedó fiado a clientes: ventas = cobrado + fiado.
        _fiado = (kpis.get('credit_sales') or 0)
        if _fiado > 0:
            raw += self._rline("Fiado", _fiado)
```

- [ ] **Step 4: Corre las pruebas del ticket**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_corte_fiado_ticket.py tests/test_cash_cut_detalle.py tests/test_cash_cut_historia.py tests/test_corte_comision_tarjeta.py`
Expected: todo PASS.

- [ ] **Step 5: Prueba del cliente de caja que falla**

Crea `frontend/src/api/__tests__/cashSummary.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../client', () => ({ default: { get } }))

import { cashApi } from '../cash'

describe('cashApi.getSummary', () => {
  it('aplana fiado y abonos del corte (0 si el backend no los manda)', async () => {
    get.mockResolvedValueOnce({ data: { session: { id: 3 }, kpis: { total_sales: 100, credit_sales: 60, customer_payments: 30 }, payments: {}, movements: {}, returns: {}, expected: {} } })
    const s = await cashApi.getSummary(3)
    expect(s.total_sales).toBe(100)
    expect(s.credit_sales).toBe(60)
    expect(s.customer_payments).toBe(30)
    get.mockResolvedValueOnce({ data: { session: { id: 4 }, kpis: { total_sales: 10 } } })
    const viejo = await cashApi.getSummary(4)
    expect(viejo.credit_sales).toBe(0)
    expect(viejo.customer_payments).toBe(0)
  })
})
```

Run: `cd frontend && npx vitest run src/api/__tests__/cashSummary.test.ts`
Expected: FAIL (`credit_sales` es `undefined`).

- [ ] **Step 6: Tipo y aplanado**

En `frontend/src/api/cash.ts`, en `CashSummary` añade tras `total_sales: number`:

```ts
  /** Lo que quedó fiado a clientes en las ventas del turno (spec 2026-10-29 §2.3). */
  credit_sales: number
  /** Abonos a cuenta cobrados en el turno; ya están dentro de los totales por método. */
  customer_payments: number
```

y en `getSummary`, tras `total_sales: data?.kpis?.total_sales ?? 0,`:

```ts
      credit_sales: data?.kpis?.credit_sales ?? 0,
      customer_payments: data?.kpis?.customer_payments ?? 0,
```

- [ ] **Step 7: Las pantallas del corte**

`frontend/src/pages/finance/CashHistory.tsx`, en el arreglo de KPIs (líneas 236-241), después del objeto `Transferencia` añade dos entradas condicionales (el arreglo pasa a construirse con spread):

```tsx
              {[
                { label: 'Ventas totales', value: formatCurrency(summary.total_sales), icon: 'fa-coins', color: 'text-emerald-400' },
                { label: 'Efectivo', value: formatCurrency(summary.total_cash), icon: 'fa-money-bill', color: 'text-white' },
                { label: 'Tarjeta', value: formatCurrency(summary.total_card), icon: 'fa-credit-card', color: 'text-indigo-400' },
                { label: 'Transferencia', value: formatCurrency(summary.total_transfer), icon: 'fa-mobile-screen', color: 'text-blue-400' },
                ...(summary.credit_sales > 0 ? [{ label: 'Fiado', value: formatCurrency(summary.credit_sales), icon: 'fa-hand-holding-dollar', color: 'text-amber-400' }] : []),
                ...(summary.customer_payments > 0 ? [{ label: 'Abonos a cuenta', value: formatCurrency(summary.customer_payments), icon: 'fa-piggy-bank', color: 'text-emerald-400' }] : []),
              ].map((k) => (
```

(`CashHistory.tsx` está en `pages/finance`, dentro del alcance de `coloresPorTokens`; si la prueba se queja de `text-white`/`text-amber-400` nuevos, usa `text-dax-text` y `text-dax-warning` en las dos entradas nuevas y no toques las existentes, que ya están en `PENDIENTES`.)

`frontend/src/components/branch/CashBranchView.tsx`, después del `<KpiCard icon="fa-coins" … />` de ventas totales (líneas 693-700), añade:

```tsx
          {summary && summary.credit_sales > 0 && (
            <KpiCard
              icon="fa-hand-holding-dollar"
              label="Fiado"
              value={fmtMoney(String(summary.credit_sales))}
              iconBg="rgba(245,158,11,0.12)"
              iconColor="#f59e0b"
              valueClass="text-amber-600 dark:text-amber-400"
            />
          )}
          {summary && summary.customer_payments > 0 && (
            <KpiCard
              icon="fa-piggy-bank"
              label="Abonos a cuenta"
              value={fmtMoney(String(summary.customer_payments))}
              iconBg="rgba(16,185,129,0.12)"
              iconColor="#10b981"
              valueClass="text-emerald-600 dark:text-emerald-400"
            />
          )}
```

(`KpiCard` aquí es el componente local de `CashBranchView`, con las mismas props que la tarjeta de ventas totales que está justo arriba; copia su firma exacta.)

- [ ] **Step 8: Verifica**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/api/__tests__/cashSummary.test.ts src/__tests__/coloresPorTokens.test.ts`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/pos_printer.py tests/test_corte_fiado_ticket.py frontend/src/api/cash.ts frontend/src/api/__tests__/cashSummary.test.ts frontend/src/pages/finance/CashHistory.tsx frontend/src/components/branch/CashBranchView.tsx
git commit -m "feat(cash): Fiado y Abonos a cuenta en el ticket del corte y en las pantallas de caja"
```

---

### Task 4: `fiado` y `cobranza` en la regla de ventas, el dashboard y el Inicio

**Files:**
- Modify: `app/services/metricas_ventas.py` (imports; `Resumen`; `_armar_resumen`; `resumen`; `por_sucursal`; funciones nuevas `fiado`, `cobranza`)
- Modify: `app/routers/reports.py` (`kpis` del dashboard, ~línea 304)
- Modify: `app/schemas/reports.py` (`PeriodoVentas`, `SucursalInicio`)
- Modify: `app/routers/reports_inicio.py` (`_periodo`, `_sucursales`)
- Test: `tests/test_metricas_ventas.py`, `tests/test_reports_dashboard.py`

**Interfaces:**
- Consumes: `filtro_sql_cargo_o_reversion()` (Tarea 2), `filtros_documentos` (Tarea 1).
- Produces: `Resumen.fiado: float`, `Resumen.cobranza: float`; `mv.fiado(db, ambito, periodo) -> float`; `mv.cobranza(db, ambito, periodo) -> float`; dashboard `kpis.credit_sales`, `kpis.collections`, `kpis.prev_credit_sales`; `PeriodoVentas.fiado`, `PeriodoVentas.cobranza`; `SucursalInicio.fiado_hoy`.

- [ ] **Step 1: Pruebas que fallan**

En `tests/test_metricas_ventas.py`, después de `_cliente` (Tarea 1) añade:

```python
def _fiada(db, org, branch, user, variante, cliente, total, enganche="0", dia=None):
    """Venta fiada como la deja el checkout: PENDING con cliente, Payment solo
    por el enganche y un cargo en el ledger por lo que quedó a cuenta."""
    from app.modules.customers.models import CustomerLedgerEntry
    doc = _venta(db, org, branch, user, variante, total, dia=dia, status=DocumentStatus.PENDING,
                 customer_id=cliente.id, pagado=enganche)
    cargo = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=doc.id, organization_id=org.id,
                                amount=Decimal(total) - Decimal(enganche), description=f"Venta a crédito #{doc.folio}")
    cargo.created_at = doc.created_at
    cliente.current_balance = Decimal(str(cliente.current_balance)) + cargo.amount
    db.add(cargo); db.commit()
    return doc


def _abono(db, org, cliente, monto, dia=None, sesion=None, doc=None):
    """Abono como lo deja POST /customers/{id}/pay: Payment con cliente (y la
    caja que lo cobró) más el asiento negativo."""
    from app.modules.customers.models import CustomerLedgerEntry
    cuando = _instante(dia or mv.hoy_mx())
    pago = Payment(organization_id=org.id, customer_id=cliente.id, method=PaymentMethod.CASH,
                   amount=Decimal(monto), cash_session_id=sesion.id if sesion else None)
    pago.created_at = cuando
    asiento = CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id, amount=-Decimal(monto),
                                  sales_document_id=doc.id if doc else None, description="PAGO RECIBIDO: CASH")
    asiento.created_at = cuando
    cliente.current_balance = Decimal(str(cliente.current_balance)) - Decimal(monto)
    db.add_all([pago, asiento]); db.commit()


def _reversion(db, org, cliente, doc, monto, descripcion):
    from app.modules.customers.models import CustomerLedgerEntry
    a = CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id, amount=-Decimal(monto),
                            sales_document_id=doc.id, description=descripcion)
    a.created_at = doc.created_at
    db.add(a); db.commit()


def _caja(db, org, branch, user):
    from app.models.cash import CashSession
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


# --- Fiado y cobranza (spec 2026-10-29 §2.2) ---------------------------------

def test_fiado_y_cobranza_del_periodo(db, org, branch_a, branch_b, cajero_a, products_setup):
    hoy, ayer = mv.hoy_mx(), mv.hoy_mx() - timedelta(days=1)
    cliente = _cliente(db, org)
    sesion = _caja(db, org, branch_a, cajero_a)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")                    # cobrada hoy
    _fiada(db, org, branch_a, cajero_a, _v(products_setup), cliente, "300", "50")      # fiada hoy, enganche 50
    _fiada(db, org, branch_a, cajero_a, _v(products_setup), cliente, "200", dia=ayer)  # fiada ayer
    _abono(db, org, cliente, "80", sesion=sesion)                                      # abono hoy

    todo = mv.Ambito(org.id, None, True)
    r_hoy = mv.resumen(db, todo, mv.Periodo(hoy, hoy))
    assert (r_hoy.bruta, r_hoy.neta, r_hoy.tickets) == (400.0, 400.0, 2)
    assert (r_hoy.fiado, r_hoy.cobranza) == (250.0, 80.0)
    # Invariante: neta = cobrado en las ventas + fiado − devuelto de ventas NO fiadas (100 + 50 + 250 − 0);
    # la devolución de una fiada ya va neteada dentro de `fiado`. Ver test_la_invariante_separa_….
    assert r_hoy.neta == 150.0 + r_hoy.fiado - 0.0
    r_ayer = mv.resumen(db, todo, mv.Periodo(ayer, ayer))
    assert (r_ayer.bruta, r_ayer.fiado, r_ayer.cobranza) == (200.0, 200.0, 0.0)

    # Por sucursal: el abono se atribuye a la caja que lo cobró (sucursal A).
    por_suc = mv.por_sucursal(db, org.id, mv.Periodo(hoy, hoy))
    assert (por_suc[branch_a.id].fiado, por_suc[branch_a.id].cobranza) == (250.0, 80.0)
    assert branch_b.id not in por_suc
    solo_b = mv.resumen(db, mv.Ambito(org.id, branch_b.id, False), mv.Periodo(hoy, hoy))
    assert (solo_b.fiado, solo_b.cobranza) == (0.0, 0.0)


def test_un_abono_sin_caja_cuenta_en_la_org_y_en_ninguna_sucursal(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    cliente = _cliente(db, org)
    _fiada(db, org, branch_a, cajero_a, _v(products_setup), cliente, "100")
    _abono(db, org, cliente, "40")   # transferencia registrada desde oficina, sin caja
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy)).cobranza == 40.0
    assert mv.resumen(db, mv.Ambito(org.id, branch_a.id, False), mv.Periodo(hoy, hoy)).cobranza == 0.0


def test_fiado_del_dia_ignora_la_venta_cancelada(db, org, branch_a, cajero_a, products_setup):
    """Review Focus 2."""
    hoy = mv.hoy_mx()
    cliente = _cliente(db, org)
    doc = _fiada(db, org, branch_a, cajero_a, _v(products_setup), cliente, "100")
    _reversion(db, org, cliente, doc, "100", f"Cancelación Venta #{doc.folio}")
    doc.status = DocumentStatus.CANCELLED
    db.commit()
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy))
    assert (r.bruta, r.tickets, r.fiado) == (0.0, 0, 0.0)


def test_la_devolucion_de_una_fiada_baja_neta_y_fiado(db, org, branch_a, cajero_a, products_setup):
    """Review Focus 3: la devolución aprobada resta en `devuelto` y su asiento
    "Devolución …" resta del fiado; el abono, en cambio, no toca el fiado."""
    hoy = mv.hoy_mx()
    cliente = _cliente(db, org)
    doc = _fiada(db, org, branch_a, cajero_a, _v(products_setup), cliente, "100")
    _devolucion(db, org, branch_a, cajero_a, doc, "30")
    _reversion(db, org, cliente, doc, "30", "Devolución #ABCD1234 aplicada al saldo")
    _abono(db, org, cliente, "20", doc=doc)
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy))
    assert (r.bruta, r.devuelto, r.neta) == (100.0, 30.0, 70.0)
    assert (r.fiado, r.cobranza) == (70.0, 20.0)
```

Y en `tests/test_reports_dashboard.py`, después de `test_dashboard_kpis_netos_y_comparativo`:

```python
def test_dashboard_trae_fiado_y_cobranza(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    from app.modules.customers.models import Customer, CustomerLedgerEntry
    hoy = mv.hoy_mx()
    cliente = Customer(name="Fiada", organization_id=org.id, current_balance=Decimal("0"))
    db.add(cliente); db.commit()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "300", status=DocumentStatus.PENDING)
    v.customer_id = cliente.id
    db.add(CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=v.id, organization_id=org.id,
                               amount=Decimal("300"), description="Venta a crédito"))
    db.add(Payment(organization_id=org.id, customer_id=cliente.id, method=PaymentMethod.CASH, amount=Decimal("45")))
    db.commit()
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    assert d["kpis"]["sales"] == 300.0
    assert d["kpis"]["credit_sales"] == 300.0
    assert d["kpis"]["collections"] == 45.0
    assert d["kpis"]["prev_credit_sales"] == 0.0
```

(Revisa los imports del archivo: necesita `date`, `Decimal`, `Payment`, `PaymentMethod`, `DocumentStatus`; añade los que falten. Si `_venta` de ese archivo crea un `Payment` por el total, la venta "PENDING" tendrá un pago de 300 — para este KPI no importa.)

- [ ] **Step 2: Córrelas y confirma que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_metricas_ventas.py -k "fiado or cobranza or devolucion_de_una_fiada or sin_caja" ; python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_reports_dashboard.py -k fiado`
Expected: FAIL (`Resumen` no tiene `fiado`; `KeyError: 'credit_sales'`).

- [ ] **Step 3: `fiado` y `cobranza` en `metricas_ventas`**

En `app/services/metricas_ventas.py`:

Imports (junto a los de modelos):
```python
from app.models.cash import CashSession
from app.modules.customers.models import CustomerLedgerEntry
from app.modules.customers.services import filtro_sql_cargo_o_reversion
```

`Resumen` gana dos campos con default al final:
```python
    fiado: float = 0.0      # lo que quedó a cuenta en las ventas del periodo (spec 2026-10-29 §2.2)
    cobranza: float = 0.0   # abonos recibidos en el periodo; no son venta
```

`_armar_resumen`:
```python
def _armar_resumen(bruta, devuelto, tickets, devoluciones, fiado=0, cobranza=0) -> Resumen:
    bruta, devuelto, tickets, devoluciones = _f(bruta), _f(devuelto), int(tickets or 0), int(devoluciones or 0)
    neta = round(bruta - devuelto, 2)
    return Resumen(bruta=bruta, devuelto=devuelto, neta=neta, tickets=tickets, devoluciones=devoluciones,
                   ticket_promedio=round(neta / tickets, 2) if tickets else 0.0,
                   fiado=_f(fiado), cobranza=_f(cobranza))
```

Antes de `resumen`, las dos funciones y el filtro de abonos:
```python
def _filtros_abonos(ambito: Ambito, periodo: Periodo) -> list:
    """Abonos a cuenta del periodo: `Payment` con cliente (solo los crea
    POST /customers/{id}/pay). La sucursal es la de la caja que los recibió
    (`Payment.cash_session_id`); sin caja, el abono cuenta en toda la
    organización y en ninguna sucursal."""
    f = [
        Payment.organization_id == ambito.organization_id,
        Payment.customer_id.isnot(None),
        dia_mx(Payment.created_at) >= periodo.inicio,
        dia_mx(Payment.created_at) <= periodo.fin,
    ]
    if not ambito.toda_la_org:
        f.append(CashSession.branch_id == ambito.branch_id)
    return f


def fiado(db: Session, ambito: Ambito, periodo: Periodo) -> float:
    """Lo que quedó a cuenta en las ventas del periodo: cargos del ledger ligados
    a documentos del ámbito creados en el periodo, menos lo que una cancelación
    o devolución ya revirtió. Los abonos no restan: son cobranza."""
    total = (
        db.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0))
        .join(SalesDocument, SalesDocument.id == CustomerLedgerEntry.sales_document_id)
        .filter(*filtros_documentos(ambito, periodo), filtro_sql_cargo_o_reversion())
        .scalar()
    )
    return _f(total)


def cobranza(db: Session, ambito: Ambito, periodo: Periodo) -> float:
    total = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .outerjoin(CashSession, CashSession.id == Payment.cash_session_id)
        .filter(*_filtros_abonos(ambito, periodo))
        .scalar()
    )
    return _f(total)
```

`resumen` devuelve `_armar_resumen(docs[0], devs[0], docs[1], devs[1], fiado=fiado(db, ambito, periodo), cobranza=cobranza(db, ambito, periodo))`.

`por_sucursal`: después del diccionario `devs` añade
```python
    fiados = {
        r.branch_id: r.total
        for r in db.query(SalesDocument.branch_id, func.coalesce(func.sum(CustomerLedgerEntry.amount), 0).label("total"))
        .select_from(CustomerLedgerEntry)
        .join(SalesDocument, SalesDocument.id == CustomerLedgerEntry.sales_document_id)
        .filter(*filtros_documentos(ambito, periodo), filtro_sql_cargo_o_reversion())
        .group_by(SalesDocument.branch_id).all()
    }
    cobranzas = {
        r.branch_id: r.total
        for r in db.query(CashSession.branch_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
        .select_from(Payment)
        .join(CashSession, CashSession.id == Payment.cash_session_id)
        .filter(*_filtros_abonos(ambito, periodo))
        .group_by(CashSession.branch_id).all()
    }
```
y el loop pasa a `for b in set(docs) | set(devs) | set(fiados) | set(cobranzas):` con `salida[b] = _armar_resumen(bruta, devuelto, n, nd, fiado=fiados.get(b, 0), cobranza=cobranzas.get(b, 0))`.

- [ ] **Step 4: Exponerlo**

`app/routers/reports.py`, en el diccionario `"kpis"` del dashboard, después de `"prev_returns": anterior.devuelto,`:
```python
            # Spec 2026-10-29 §2.2: lo que quedó fiado en las ventas del periodo y los abonos recibidos.
            "credit_sales": actual.fiado,
            "collections": actual.cobranza,
            "prev_credit_sales": anterior.fiado,
```

`app/schemas/reports.py`: en `PeriodoVentas` añade `fiado: float = 0.0   # lo que quedó a cuenta en esas ventas` y `cobranza: float = 0.0   # abonos recibidos en el periodo`; en `SucursalInicio` añade `fiado_hoy: float = 0.0`.

`app/routers/reports_inicio.py`: `_periodo` devuelve `PeriodoVentas(desde=desde, hasta=hasta, total=r.neta, devuelto=r.devuelto, tickets=r.tickets, fiado=r.fiado, cobranza=r.cobranza)`; en `_sucursales` añade `fiado_hoy=r.fiado,` al `SucursalInicio(...)`.

- [ ] **Step 5: Corre**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_metricas_ventas.py tests/test_reports_dashboard.py tests/test_reports_inicio.py tests/test_reports_daily_summary.py tests/test_regresion_reportes.py tests/test_platform_reports_money.py`
Expected: todo PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/metricas_ventas.py app/routers/reports.py app/schemas/reports.py app/routers/reports_inicio.py tests/test_metricas_ventas.py tests/test_reports_dashboard.py
git commit -m "feat(reportes): fiado y cobranza del periodo en la regla de ventas, el dashboard y el Inicio"
```

---

### Task 5: El abono responde qué cubrió; efectivo sin sucursal se rechaza

**Files:**
- Modify: `app/modules/customers/schemas.py` (nuevas clases después de `LedgerEntryResponse`)
- Modify: `app/modules/customers/router.py::register_customer_payment` (~459-535)
- Modify: `tests/test_abono_en_efectivo_exige_caja.py:135-155`
- Modify: `frontend/src/api/customers.ts`
- Test: `tests/test_crm_cobranza_abonos.py` (nuevo)

**Interfaces:**
- Produces: `POST /api/customers/{id}/pay` → `AbonoResponse {entries, customer_balance_before, customer_balance_after, applied[{sales_document_id, folio, amount, paid_in_full}], unapplied, payment_id (UUID str), method, reference, received_at}`. Frontend: `customersApi.pay(id, {amount, method?, reference?, sales_document_id?}) → AbonoResponse`; `customersApi.getUnpaidDocuments(id) → UnpaidDocument[]`.

- [ ] **Step 1: Pruebas que fallan**

Crea `tests/test_crm_cobranza_abonos.py`:

```python
"""POST /customers/{id}/pay: respuesta con lo aplicado (spec 2026-10-29 §4.2)
y el efectivo sin sucursal se rechaza (§6.1)."""
from app.models.sales import Payment
from tests.cobranza_helpers import _cliente, _escenario, _fiar


def test_el_abono_libre_dice_que_tickets_cubrio(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    a = _fiar(client, h, cliente, variant.sku)
    b = _fiar(client, h, cliente, variant.sku)

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "150", "method": "CASH"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["sales_document_id"], float(x["amount"]), x["paid_in_full"]) for x in d["applied"]] == [
        (a["sale_id"], 100.0, True), (b["sale_id"], 50.0, False)]
    assert all(x["folio"].startswith("A-") for x in d["applied"])
    assert float(d["unapplied"]) == 0.0
    assert (float(d["customer_balance_before"]), float(d["customer_balance_after"])) == (200.0, 50.0)
    assert d["method"] == "CASH" and d["received_at"]
    assert len(d["entries"]) == 2 and float(d["entries"][0]["amount"]) == -100.0
    assert db.query(Payment).filter(Payment.id == d["payment_id"]).one().customer_id == cliente.id


def test_lo_que_sobra_queda_a_favor(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    d = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "120", "method": "CARD", "reference": "1234"}, headers=h).json()
    assert float(d["unapplied"]) == 20.0
    assert float(d["customer_balance_after"]) == -20.0
    assert d["reference"] == "1234"


def test_efectivo_sin_sucursal_se_rechaza_y_tarjeta_pasa(
    client, db, org, branch_a, cajero_a, auth_cajero_a, admin_sin_sucursal, auth_admin_sin_sucursal, products_setup
):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    ho = {**auth_admin_sin_sucursal, "X-Organization-ID": str(org.id)}

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "CASH"}, headers=ho)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Para recibir efectivo elige una sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar"

    r = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "TRANSFER", "reference": "SPEI 1"}, headers=ho)
    assert r.status_code == 200, r.text
    assert db.query(Payment).filter(Payment.id == r.json()["payment_id"]).one().cash_session_id is None
```

Y en `tests/test_abono_en_efectivo_exige_caja.py` sustituye entera la función `test_el_rol_de_oficina_sin_sucursal_sigue_exento` por:

```python
def test_el_rol_de_oficina_sin_sucursal_no_puede_recibir_efectivo(
    client, db, org, branch_a, cajero_a, admin_user, auth_admin
):
    """Spec 2026-10-29 §6.1: sin `branch_id` no hay cajón que responda por los
    billetes, así que el efectivo se rechaza con 422; transferencia y tarjeta
    se siguen registrando sin caja (no tocan el cajón)."""
    sesion_1 = _abrir_caja(db, org, branch_a, cajero_a)
    cliente, venta = _cliente_con_venta_a_credito(
        db, org, branch_a, cajero_a, sesion_1, folio=3004)
    admin_user.branch_id = None
    db.commit()
    h = {**auth_admin, "X-Organization-ID": str(org.id)}

    resp = client.post(f"/api/customers/{cliente.id}/pay",
                       json={"amount": "400", "method": "CASH", "sales_document_id": venta.id}, headers=h)
    assert resp.status_code == 422, resp.text
    assert "sucursal" in resp.json()["detail"]
    assert db.query(Payment).filter(Payment.organization_id == org.id).count() == 0

    resp = client.post(f"/api/customers/{cliente.id}/pay",
                       json={"amount": "400", "method": "TRANSFER", "sales_document_id": venta.id}, headers=h)
    assert resp.status_code == 200, resp.text
    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id is None
```

- [ ] **Step 2: Córrelas y confirma que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_crm_cobranza_abonos.py tests/test_abono_en_efectivo_exige_caja.py`
Expected: FAIL (`KeyError: 'applied'`; el efectivo sin sucursal responde 200).

- [ ] **Step 3: Esquemas**

En `app/modules/customers/schemas.py`, asegúrate de tener `from typing import List, Optional` y `from datetime import datetime`, y añade después de `LedgerEntryResponse`:

```python
class AbonoAplicado(BaseModel):
    sales_document_id: str
    folio: str
    amount: Decimal
    paid_in_full: bool


class AbonoResponse(BaseModel):
    """Respuesta de POST /customers/{id}/pay (spec 2026-10-29 §4.2): qué
    tickets cubrió el abono y cómo quedó el saldo, para que el POS lo diga y
    el recibo lo imprima."""
    entries: List[LedgerEntryResponse]
    customer_balance_before: Decimal
    customer_balance_after: Decimal
    applied: List[AbonoAplicado]
    unapplied: Decimal          # saldo a favor que quedó sin ticket
    payment_id: str             # UUID del Payment
    method: str
    reference: Optional[str] = None
    received_at: datetime
```

- [ ] **Step 4: El endpoint**

En `app/modules/customers/router.py::register_customer_payment`:

1. Decorador: `response_model=AbonoResponse` (importa `AbonoResponse, AbonoAplicado` junto a los demás esquemas). Actualiza el docstring: quita "Solo administrador/dueño" (cualquier rol con `crm` abona) y añade "Devuelve qué tickets cubrió y el saldo antes/después (spec 2026-10-29 §4.2)".
2. Después de `cobra_efectivo = method_enum == SalesPaymentMethod.CASH`, sustituye `requiere_caja = cobra_efectivo and bool(current_user.branch_id)` y el comentario de la exención (`(b) la exencion de oficina central …`) por:
   ```python
    # Spec 2026-10-29 §6.1: sin sucursal no hay cajón que responda por los
    # billetes. Antes el rol de oficina quedaba exento y el efectivo nacía
    # sin caja (caía al respaldo por documento del corte original); ahora
    # solo tarjeta y transferencia pasan sin sucursal.
    if cobra_efectivo and not current_user.branch_id:
        raise HTTPException(
            status_code=422,
            detail="Para recibir efectivo elige una sucursal con caja abierta; tarjeta y transferencia sí se pueden registrar",
        )
    requiere_caja = cobra_efectivo
   ```
3. Justo antes de `asientos = aplicar_abono(`: `saldo_antes = Decimal(str(customer.current_balance or 0))`.
4. Sustituye el final (`db.add(payment_record)` … `return new_entry`) por:
   ```python
    db.add(payment_record)
    db.flush()

    from app.modules.customers.services import CERO, DocumentoAbierto
    ids = [a.sales_document_id for a in asientos if a.sales_document_id]
    docs = {d.id: d for d in db.query(SalesDocument).filter(SalesDocument.id.in_(ids)).all()} if ids else {}
    applied = [
        AbonoAplicado(
            sales_document_id=a.sales_document_id,
            folio=DocumentoAbierto(documento=docs[a.sales_document_id], saldo=CERO).folio,
            amount=-Decimal(str(a.amount)),
            paid_in_full=docs[a.sales_document_id].status == DocumentStatus.PAID,
        )
        for a in asientos if a.sales_document_id in docs
    ]
    unapplied = sum((-Decimal(str(a.amount)) for a in asientos if not a.sales_document_id), Decimal("0"))

    db.commit()
    for a in asientos:
        db.refresh(a)
    db.refresh(payment_record)
    return AbonoResponse(
        entries=[LedgerEntryResponse.model_validate(a) for a in asientos],
        customer_balance_before=saldo_antes,
        customer_balance_after=Decimal(str(customer.current_balance)),
        applied=applied,
        unapplied=unapplied,
        payment_id=payment_record.id,
        method=method_enum.value,
        reference=payment_in.reference,
        received_at=payment_record.created_at,
    )
   ```
   y borra la línea `new_entry = asientos[0]`. Si `LedgerEntryResponse` usa `class Config: from_attributes = True` (Pydantic v2 lo acepta), `model_validate` funciona.

- [ ] **Step 5: Corre**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_crm_cobranza_abonos.py tests/test_abono_en_efectivo_exige_caja.py tests/test_abono_a_cuenta_sin_venta.py tests/test_abono_cliente_atribuye_caja.py tests/test_cash_reportes_atribucion_por_pago.py tests/test_crm_credito_auditoria.py tests/test_customers_statement_api.py tests/test_cobranza_corte.py`
Expected: todo PASS. (`test_abono_a_cuenta_sin_venta` solo lee `status_code` y la tabla; sigue verde.)

- [ ] **Step 6: Tipos del frontend**

En `frontend/src/api/customers.ts`, después de `LedgerEntry` añade:

```ts
export interface UnpaidDocument {
  id: string
  folio: string
  created_at: string
  total_amount: number
  paid_amount: number
  balance: number
  doc_type: string
}

export interface AbonoAplicado {
  sales_document_id: string
  folio: string
  amount: number
  paid_in_full: boolean
}

/** Respuesta de POST /customers/{id}/pay (spec 2026-10-29 §4.2). */
export interface AbonoResponse {
  entries: LedgerEntry[]
  customer_balance_before: number
  customer_balance_after: number
  applied: AbonoAplicado[]
  unapplied: number
  payment_id: string
  method: string
  reference: string | null
  received_at: string
}
```

Sustituye `pay` por:

```ts
  pay: async (id: number, payload: { amount: number; method?: string; reference?: string; sales_document_id?: string }): Promise<AbonoResponse> => {
    const { data } = await client.post<AbonoResponse>(`/customers/${id}/pay`, payload)
    return data
  },

  getUnpaidDocuments: async (id: number): Promise<UnpaidDocument[]> => {
    const { data } = await client.get<UnpaidDocument[]>(`/customers/${id}/unpaid-documents`)
    return Array.isArray(data) ? data : []
  },
```

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores (`Customers.tsx` ignora el valor de retorno de `pay`).

- [ ] **Step 7: Commit**

```bash
git add app/modules/customers/schemas.py app/modules/customers/router.py tests/test_crm_cobranza_abonos.py tests/test_abono_en_efectivo_exige_caja.py frontend/src/api/customers.ts
git commit -m "feat(crm): el abono responde qué tickets cubrió; efectivo sin sucursal se rechaza"
```

---

### Task 6: Recibo de abono (ESC/POS) y su endpoint

**Files:**
- Modify: `app/modules/customers/services.py` (`detalle_del_abono`)
- Modify: `app/pos_printer.py` (`build_abono_bytes`, después de `build_cash_cut_bytes`)
- Modify: `app/routers/printer.py` (nuevo endpoint después de `reprint_refunded_endpoint`)
- Modify: `frontend/src/api/printer.ts` (`getAbonoBase64`)
- Test: `tests/test_recibo_abono.py` (nuevo)

**Interfaces:**
- Consumes: `AbonoResponse.payment_id` (Tarea 5), `es_abono`, `asientos_del_cliente`, `DocumentoAbierto` (servicio).
- Produces: `detalle_del_abono(db, *, org_id, pago) -> dict{customer, applied: list[dict], unapplied: Decimal, balance_before: Decimal, balance_after: Decimal}`; `PosPrinter.build_abono_bytes(...) -> bytes`; `POST /api/printer/print-abono/{payment_id}` → `{status, job_id, content_base64, printer_target}`; `printerApi.getAbonoBase64(paymentId) -> Promise<string>`.

- [ ] **Step 1: Pruebas que fallan**

Crea `tests/test_recibo_abono.py`:

```python
"""Recibo de abono (spec 2026-10-29 §4.3): bytes ESC/POS con cliente, monto,
tickets aplicados y saldo antes/después; reimprimir es volver a llamar."""
import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.pos_printer import PosPrinter
from tests.cobranza_helpers import _cliente, _escenario, _fiar


def _texto(raw: bytes, p: PosPrinter) -> str:
    out = raw
    for k, c in sorted(p.CMD.items(), key=lambda kv: len(kv[1]), reverse=True):
        if k != "LF" and c:
            out = out.replace(c, b"")
    return out.decode("latin-1", "replace")


class _Org:
    name = "ELEVEN FASHION"; legal_name = None; logo_url = None; phone = None


class _Branch:
    name = "Roma"; logo_url = None; phone = None; city = None


def test_los_bytes_del_recibo_traen_todo_lo_que_la_clienta_necesita():
    p = PosPrinter("x", paper_width_mm=58)
    raw = p.build_abono_bytes(
        organization=_Org(), branch=_Branch(), cashier="mirna", customer_name="Ana Pérez",
        amount=150.0, method="CASH", reference=None,
        applied=[{"folio": "A-12", "amount": Decimal("100.00"), "paid_in_full": True},
                 {"folio": "A-15", "amount": Decimal("50.00"), "paid_in_full": False}],
        unapplied=0.0, balance_before=200.0, balance_after=50.0,
        received_at=datetime(2026, 10, 31, 18, 5, tzinfo=timezone.utc), folio="AB-1A2B3C4D",
    )
    t = _texto(raw, p)
    for esperado in ("ELEVEN FASHION", "RECIBO DE ABONO", "AB-1A2B3C4D", "Ana P", "Efectivo",
                     "Ticket A-12 (liquidado)", "Ticket A-15", "Saldo anterior", "Saldo actual"):
        assert esperado in t, f"falta {esperado!r} en:\n{t}"
    lineas = t.split("\n")
    assert next(l for l in lineas if "Saldo actual" in l).rstrip().endswith("$50.00")
    assert "12:05" in t, "la hora se imprime en hora de México"
    assert p.CMD["DRAWER"] not in raw, "un abono no abre el cajón"


def test_el_endpoint_devuelve_el_recibo_en_base64(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org, nombre="Lupita")
    venta = _fiar(client, h, cliente, variant.sku)
    abono = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "40", "method": "CASH"}, headers=h).json()

    r = client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready_to_print"
    t = base64.b64decode(r.json()["content_base64"]).decode("latin-1", "replace")
    assert "RECIBO DE ABONO" in t and "LUPITA" in t.upper()
    assert abono["applied"][0]["folio"] in t
    assert f"AB-{abono['payment_id'][:8].upper()}" in t
    assert "$40.00" in t and "$100.00" in t and "$60.00" in t   # abono, saldo anterior, saldo actual

    # Reimprimir es volver a llamar; no pide PIN.
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=h).status_code == 200


def test_un_pago_que_no_es_abono_o_no_existe_da_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, pagos=[{"method": "CASH", "amount": "30.00"}])
    assert client.post(f"/api/printer/print-abono/{uuid.uuid4()}", headers=h).status_code == 404
    from app.models.sales import Payment
    pago_venta = db.query(Payment).filter(Payment.sales_document_id == venta["sale_id"]).one()
    assert client.post(f"/api/printer/print-abono/{pago_venta.id}", headers=h).status_code == 404


def test_el_gerente_puede_imprimir_el_recibo_de_otra_cajera(
    client, db, org, branch_a, cajero_a, auth_cajero_a, gerente_a, auth_gerente_a, products_setup
):
    h, variant, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    _fiar(client, h, cliente, variant.sku)
    abono = client.post(f"/api/customers/{cliente.id}/pay", json={"amount": "10", "method": "CARD", "reference": "77"}, headers=h).json()
    hg = {**auth_gerente_a, "X-Organization-ID": str(org.id)}
    assert client.post(f"/api/printer/print-abono/{abono['payment_id']}", headers=hg).status_code == 200
```

- [ ] **Step 2: Córrelas y confirma que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_recibo_abono.py`
Expected: FAIL (`AttributeError: 'PosPrinter' object has no attribute 'build_abono_bytes'`; 404 en el endpoint).

- [ ] **Step 3: `detalle_del_abono` en el servicio**

En `app/modules/customers/services.py`, después de `asientos_del_cliente`:

```python
def detalle_del_abono(db: Session, *, org_id: int, pago) -> dict:
    """Reconstruye qué cubrió un abono a partir del ledger (spec 2026-10-29 §4.3).

    Sin columna nueva: los asientos de abono del mismo cliente nacidos en la
    misma transacción que el `Payment` (misma marca de tiempo, ±2 s) son los
    suyos. "Saldo anterior" = saldo actual + lo abonado: exacto al imprimir en
    el momento; en una reimpresión posterior parte del saldo de hoy.
    """
    from datetime import timedelta
    from app.models.sales import DocumentStatus, SalesDocument

    customer = db.query(Customer).filter(
        Customer.id == pago.customer_id, Customer.organization_id == org_id).one()

    def _utc(t):
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t

    cuando = _utc(pago.created_at)
    asientos = [
        a for a in asientos_del_cliente(db, org_id=org_id, customer_id=customer.id)
        if es_abono(a) and a.created_at is not None
        and abs(_utc(a.created_at) - cuando) <= timedelta(seconds=2)
    ]
    ids = [a.sales_document_id for a in asientos if a.sales_document_id]
    docs = {d.id: d for d in db.query(SalesDocument).filter(SalesDocument.id.in_(ids)).all()} if ids else {}
    applied = [
        {
            "sales_document_id": a.sales_document_id,
            "folio": DocumentoAbierto(documento=docs[a.sales_document_id], saldo=CERO).folio,
            "amount": -_dec(a.amount),
            "paid_in_full": docs[a.sales_document_id].status == DocumentStatus.PAID,
        }
        for a in asientos if a.sales_document_id in docs
    ]
    unapplied = sum((-_dec(a.amount) for a in asientos if not a.sales_document_id), CERO)
    abonado = sum((-_dec(a.amount) for a in asientos), CERO)
    despues = _dec(customer.current_balance)
    return {"customer": customer, "applied": applied, "unapplied": unapplied,
            "balance_after": despues, "balance_before": despues + abonado}
```

Añade `"detalle_del_abono"` a `__all__`.

- [ ] **Step 4: `build_abono_bytes`**

En `app/pos_printer.py`, después de `build_cash_cut_bytes` (mismo nivel de indentación de método):

```python
    def build_abono_bytes(self, *, organization, branch, cashier: str, customer_name: str,
                          amount: float, method: str, reference, applied: list, unapplied: float,
                          balance_before: float, balance_after: float, received_at: datetime,
                          folio: str) -> bytes:
        """Recibo de abono a cuenta (spec 2026-10-29 §4.3). Sin apertura de cajón:
        el efectivo ya entró con el abono, el recibo solo lo documenta."""
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")

        def linea(texto: str) -> bytes:
            return (self._truncate(texto, self.cols) + "\n").encode("latin-1", "replace")

        raw = self.CMD["RESET"] + self._default_font + self.CMD["SIZE_NORMAL"] + self.CMD["CENTER"]
        raw += self.CMD["BOLD_ON"] + linea((organization.name if organization else None) or "ATLAS POS") + self.CMD["BOLD_OFF"]
        if branch is not None and getattr(branch, "name", None):
            raw += linea(branch.name)
        raw += self.CMD["SIZE_LARGE"] + self.CMD["BOLD_ON"] + b"RECIBO DE ABONO\n" + self.CMD["BOLD_OFF"] + self.CMD["SIZE_NORMAL"]
        dt = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
        raw += linea(f"{dt.astimezone(MX_TZ).strftime('%d/%m/%y %H:%M')} | {folio}")
        raw += self.CMD["LEFT"] + sep
        raw += linea(f"CLIENTE: {customer_name}")
        raw += self._rline("Abono", amount)
        metodo = {"CASH": "Efectivo", "CARD": "Tarjeta", "TRANSFER": "Transferencia"}.get(str(method).upper(), str(method))
        raw += linea(f"Metodo: {metodo}" + (f" ({reference})" if reference else ""))
        if applied:
            raw += sep + linea("APLICADO A:")
            for a in applied:
                etiqueta = f"Ticket {a['folio']}" + (" (liquidado)" if a.get("paid_in_full") else "")
                raw += self._rline(etiqueta, float(a["amount"]))
        if unapplied and unapplied > 0:
            raw += self._rline("Queda a favor", float(unapplied))
        raw += sep
        raw += self._rline("Saldo anterior", balance_before)
        raw += self.CMD["BOLD_ON"] + self._rline("Saldo actual", balance_after) + self.CMD["BOLD_OFF"]
        raw += sep + linea(f"Le atendio: {cashier}")
        raw += self.CMD["LF"] * 3 + self.CMD["CUT"]
        return raw
```

(`datetime`, `timezone` y `MX_TZ` ya están importados al inicio del archivo; `_truncate` y `_rline` existen.)

- [ ] **Step 5: El endpoint**

En `app/routers/printer.py`, después de `reprint_refunded_endpoint`:

```python
@router.post("/print-abono/{payment_id}")
def print_abono_endpoint(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Recibo de un abono a cuenta (spec 2026-10-29 §4.3). Mismo contrato que
    el ticket: bytes ESC/POS en base64 que el agente local manda a la
    impresora. Reimprimir es volver a llamar; no pide PIN. Lo imprime quien
    cobró el abono o un rol de oficina."""
    from app.models.sales import Payment
    from app.modules.customers.services import detalle_del_abono
    from app.services.metricas_ventas import HQ_ROLES

    pago = db.query(Payment).filter(Payment.id == payment_id, Payment.organization_id == org_id).first()
    if not pago or pago.customer_id is None:
        raise HTTPException(status_code=404, detail="Abono no encontrado")
    rol = str(getattr(current_user.role, "value", current_user.role))
    if rol not in HQ_ROLES and pago.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo quien cobró el abono o un rol de oficina puede imprimir este recibo")

    detalle = detalle_del_abono(db, org_id=org_id, pago=pago)
    from app.models.organization import Organization
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    printer, target_printer_name = _resolve_printer(current_user, organization)
    try:
        raw_bytes = printer.build_abono_bytes(
            organization=organization, branch=current_user.branch, cashier=current_user.username,
            customer_name=detalle["customer"].name, amount=float(pago.amount),
            method=str(getattr(pago.method, "value", pago.method)), reference=pago.reference,
            applied=detalle["applied"], unapplied=float(detalle["unapplied"]),
            balance_before=float(detalle["balance_before"]), balance_after=float(detalle["balance_after"]),
            received_at=pago.created_at, folio=f"AB-{pago.id[:8].upper()}",
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    job = _record_print_job(db, raw_bytes=raw_bytes, printer_name=printer.printer_name,
                            org_id=org_id, request=request)
    return {
        "status": "ready_to_print",
        "job_id": job.id,
        "content_base64": base64.b64encode(raw_bytes).decode("utf-8"),
        "printer_target": target_printer_name,
    }
```

- [ ] **Step 6: Corre**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_recibo_abono.py tests/test_crm_cobranza_abonos.py`
Expected: todo PASS.

- [ ] **Step 7: Cliente del frontend**

En `frontend/src/api/printer.ts`, dentro de `printerApi`, después de `reprintTicket`:

```ts
  /** Recibo de abono a cuenta en base64 (spec 2026-10-29 §4.3); reimprimir es volver a llamar. */
  getAbonoBase64: async (paymentId: string): Promise<string> => {
    const { data } = await client.post<{ content_base64?: string; base64?: string }>(
      `/printer/print-abono/${paymentId}`, {}
    )
    return data.content_base64 ?? data.base64 ?? ''
  },
```

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 8: Commit**

```bash
git add app/modules/customers/services.py app/pos_printer.py app/routers/printer.py tests/test_recibo_abono.py frontend/src/api/printer.ts
git commit -m "feat(printer): recibo de abono a cuenta por el agente de impresión"
```

---

### Task 7: Endpoint de cuentas por cobrar

**Files:**
- Modify: `app/modules/customers/services.py` (`_utc`, `cargos_pendientes`, `antiguedad_por_cargo` refactor, `ClienteCobranza`, `cuentas_por_cobrar`, `__all__`)
- Modify: `app/modules/customers/schemas.py` (`ClienteCobranzaOut`, `ResumenCobranza`, `CobranzaResponse`)
- Modify: `app/modules/customers/router.py` (nueva ruta `GET /cobranza` entre `/stats` y `GET /`)
- Test: `tests/test_crm_cobranza_endpoint.py` (nuevo)

**Interfaces:**
- Consumes: `antiguedad_por_cargo`, `asientos_del_cliente`, `documentos_abiertos`, `es_abono`, `BUCKETS` (servicio).
- Produces: `cuentas_por_cobrar(db, *, org_id, branch_id=None, bucket=None, search=None, order="saldo", ahora=None) -> tuple[dict, list[ClienteCobranza]]`; `GET /api/customers/cobranza?branch_id&bucket&search&skip&limit&order` → `{resumen:{por_cobrar, vencido_30, clientes, a_favor}, items:[{id,name,phone,balance,cargo_mas_viejo,dias,ultimo_abono,branch_id,branch_name,tickets_abiertos,antiguedad:{current,31_60,61_90,91_plus}}], total}`. La ruta DEBE declararse antes de `GET /{customer_id}` o FastAPI intenta convertir "cobranza" a entero.

- [ ] **Step 1: Pruebas que fallan**

Crea `tests/test_crm_cobranza_endpoint.py`:

```python
"""GET /customers/cobranza (spec 2026-10-29 §3.1): quién debe, cuánto, desde
cuándo. Roles de oficina; antigüedad por cargo FIFO; saldo a favor aparte."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, SalesDocument
from app.modules.customers.models import Customer, CustomerLedgerEntry

_folios = count(500)


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _hace(dias: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=dias)


def _cliente(db, org, nombre, telefono=None):
    c = Customer(name=nombre, phone=telefono, organization_id=org.id, current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _cargo(db, org, branch, user, cliente, monto, dias_atras):
    """Venta fiada completa (PENDING con cliente) y su cargo, con `dias_atras` de edad."""
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, customer_id=cliente.id,
        folio=next(_folios), series="A", subtotal=Decimal(monto), tax_amount=Decimal("0"),
        total_amount=Decimal(monto), status=DocumentStatus.PENDING, doc_type="ORDER",
    )
    doc.created_at = _hace(dias_atras)
    db.add(doc); db.flush()
    a = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=doc.id, organization_id=org.id,
                            amount=Decimal(monto), description=f"Venta a crédito #{doc.folio}")
    a.created_at = doc.created_at
    cliente.current_balance = Decimal(str(cliente.current_balance)) + Decimal(monto)
    db.add(a); db.commit()
    return doc


def _abono(db, org, cliente, monto, dias_atras):
    a = CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id, amount=-Decimal(monto),
                            description="PAGO RECIBIDO: CASH")
    a.created_at = _hace(dias_atras)
    cliente.current_balance = Decimal(str(cliente.current_balance)) - Decimal(monto)
    db.add(a); db.commit()


def _escenario(db, org, branch_a, branch_b, cajero_a):
    """Ana: 100 hace 45 días, abonó 30 hace 10 → debe 70 (31_60). Beto: 80 hoy
    en la sucursal B. Carla: solo un abono de 20 → a favor. Dora: 10 y lo pagó."""
    _habilitar(db, org, "crm")
    ana = _cliente(db, org, "Ana Pérez", "55 1234 5678")
    _cargo(db, org, branch_a, cajero_a, ana, "100", 45)
    _abono(db, org, ana, "30", 10)
    beto = _cliente(db, org, "Beto")
    _cargo(db, org, branch_b, cajero_a, beto, "80", 0)
    carla = _cliente(db, org, "Carla")
    _abono(db, org, carla, "20", 1)
    dora = _cliente(db, org, "Dora")
    _cargo(db, org, branch_a, cajero_a, dora, "10", 3)
    _abono(db, org, dora, "10", 2)
    return ana, beto, carla, dora


def test_la_cajera_no_ve_las_cuentas_por_cobrar(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a):
    _escenario(db, org, branch_a, branch_b, cajero_a)
    r = client.get("/api/customers/cobranza", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 403, r.text


def test_resumen_y_antiguedad_cuadran_con_el_saldo(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    ana, beto, carla, dora = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    d = client.get("/api/customers/cobranza", headers=h).json()

    # Los Decimal viajan como cadenas; se comparan como números.
    assert {k: float(v) for k, v in d["resumen"].items()} == {"por_cobrar": 150.0, "vencido_30": 70.0, "clientes": 2, "a_favor": 20.0}
    assert d["total"] == 2
    assert [i["id"] for i in d["items"]] == [beto.id, ana.id], "orden por saldo"
    fila = next(i for i in d["items"] if i["id"] == ana.id)
    assert float(fila["balance"]) == 70.0
    assert fila["dias"] == 45 and fila["cargo_mas_viejo"] is not None and fila["ultimo_abono"] is not None
    assert {k: float(v) for k, v in fila["antiguedad"].items()} == {"current": 0.0, "31_60": 70.0, "61_90": 0.0, "91_plus": 0.0}
    assert fila["tickets_abiertos"] == 1
    assert (fila["branch_id"], fila["branch_name"], fila["phone"]) == (branch_a.id, branch_a.name, "55 1234 5678")


def test_el_saldo_a_favor_va_aparte_y_el_cero_no_aparece(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    """Review Focus 4."""
    ana, beto, carla, dora = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    d = client.get("/api/customers/cobranza", headers=h).json()
    ids = [i["id"] for i in d["items"]]
    assert carla.id not in ids and dora.id not in ids
    assert float(d["resumen"]["a_favor"]) == 20.0


def test_filtros_y_orden(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    ana, beto, _, _ = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    g = lambda qs: client.get(f"/api/customers/cobranza?{qs}", headers=h).json()
    assert [i["id"] for i in g("order=antiguedad")["items"]] == [ana.id, beto.id]
    assert [i["id"] for i in g("bucket=31_60")["items"]] == [ana.id]
    assert [i["id"] for i in g(f"branch_id={branch_b.id}")["items"]] == [beto.id]
    assert [i["id"] for i in g("search=ana")["items"]] == [ana.id]
    assert [i["id"] for i in g("search=1234")["items"]] == [ana.id], "también busca por teléfono"
    assert float(g("bucket=31_60")["resumen"]["por_cobrar"]) == 70.0, "el resumen sigue al filtro"
    pagina = g("limit=1&skip=1")
    assert pagina["total"] == 2 and [i["id"] for i in pagina["items"]] == [ana.id]
    assert client.get("/api/customers/cobranza?bucket=viejo", headers=h).status_code == 422
```

- [ ] **Step 2: Córrelas y confirma que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_crm_cobranza_endpoint.py`
Expected: FAIL con 422 (FastAPI intenta convertir "cobranza" en `customer_id`).

- [ ] **Step 3: El servicio**

En `app/modules/customers/services.py`:

(a) Junto a `_dec`, un `_utc` de módulo (si la Tarea 6 dejó uno local dentro de `detalle_del_abono`, bórralo y usa este):
```python
def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
```

(b) Sustituye `antiguedad_por_cargo` por la pareja:

```python
def cargos_pendientes(asientos: Iterable[CustomerLedgerEntry]) -> list[list]:
    """Los cargos que todavía deben algo, del más viejo al más nuevo, como
    `[created_at, restante]`. Los abonos se aplican al cargo más viejo primero
    (FIFO); un abono anterior a cualquier cargo queda como crédito que consume
    el siguiente cargo. Las reversiones (cancelación/devolución) también restan
    del cargo más viejo: es la mejor aproximación sin enlace asiento↔asiento."""
    pendientes: list[list] = []
    credito = CERO
    for e in sorted(asientos, key=lambda x: (x.created_at or datetime.min.replace(tzinfo=timezone.utc), x.id or 0)):
        monto = _dec(e.amount)
        if monto > 0:
            if credito > 0:
                usado = min(credito, monto)
                credito -= usado
                monto -= usado
            if monto > 0:
                pendientes.append([e.created_at, monto])
        elif monto < 0:
            abono = -monto
            while abono > 0 and pendientes:
                cargo = pendientes[0]
                usado = min(abono, cargo[1])
                cargo[1] -= usado
                abono -= usado
                if cargo[1] <= CERO:
                    pendientes.pop(0)
            if abono > 0:
                credito += abono
    return pendientes


def antiguedad_por_cargo(
    asientos: Iterable[CustomerLedgerEntry], *, ahora: Optional[datetime] = None
) -> dict[str, Decimal]:
    """Reparte lo que el cliente debe HOY por la edad del cargo que lo originó
    (ver `cargos_pendientes`). Un cliente que compró $10,000 en el año y debe
    $100 reporta $100, no $10,000."""
    ahora = ahora or datetime.now(timezone.utc)
    buckets = {k: CERO for k in BUCKETS}
    for creado, restante in cargos_pendientes(asientos):
        if creado is None:
            buckets["current"] += restante
            continue
        buckets[_bucket((ahora - _utc(creado)).days)] += restante
    return buckets
```

(c) Después de `detalle_del_abono`:

```python
# --------------------------------------------------------------------------
# Cuentas por cobrar (spec 2026-10-29 §3.1)
# --------------------------------------------------------------------------
@dataclass
class ClienteCobranza:
    customer: Customer
    balance: Decimal
    cargo_mas_viejo: Optional[datetime]
    dias: int
    ultimo_abono: Optional[datetime]
    branch_id: Optional[int]
    branch_name: Optional[str]
    tickets_abiertos: int
    antiguedad: dict[str, Decimal]


def cuentas_por_cobrar(
    db: Session, *, org_id: int, branch_id: Optional[int] = None, bucket: Optional[str] = None,
    search: Optional[str] = None, order: str = "saldo", ahora: Optional[datetime] = None,
) -> tuple[dict, list[ClienteCobranza]]:
    """Quién debe, cuánto y desde cuándo. Recorre asientos en Python por
    cliente (decenas en una boutique); `limit` lo acota el router. La sucursal
    de un cliente es la de su última venta. `a_favor` suma los saldos negativos
    del mismo filtro de búsqueda y va aparte: no se resta de `por_cobrar`."""
    from app.models.organization import Branch
    from app.models.sales import SalesDocument

    ahora = ahora or datetime.now(timezone.utc)
    q = db.query(Customer).filter(Customer.organization_id == org_id, Customer.current_balance != 0)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    clientes = q.all()
    a_favor = sum((-_dec(c.current_balance) for c in clientes if _dec(c.current_balance) < 0), CERO)

    filas: list[ClienteCobranza] = []
    for c in clientes:
        saldo = _dec(c.current_balance)
        if saldo <= 0:
            continue
        ultima = (
            db.query(SalesDocument.branch_id, Branch.name)
            .join(Branch, Branch.id == SalesDocument.branch_id)
            .filter(SalesDocument.customer_id == c.id, SalesDocument.organization_id == org_id)
            .order_by(SalesDocument.created_at.desc()).first()
        )
        b_id, b_name = (ultima[0], ultima[1]) if ultima else (None, None)
        if branch_id is not None and b_id != branch_id:
            continue
        asientos = asientos_del_cliente(db, org_id=org_id, customer_id=c.id)
        antig = antiguedad_por_cargo(asientos, ahora=ahora)
        if bucket and antig.get(bucket, CERO) <= 0:
            continue
        pendientes = cargos_pendientes(asientos)
        mas_viejo = next((creado for creado, _ in pendientes if creado is not None), None)
        abonos = [_utc(a.created_at) for a in asientos if es_abono(a) and a.created_at is not None]
        filas.append(ClienteCobranza(
            customer=c, balance=saldo, cargo_mas_viejo=mas_viejo,
            dias=(ahora - _utc(mas_viejo)).days if mas_viejo else 0,
            ultimo_abono=max(abonos) if abonos else None,
            branch_id=b_id, branch_name=b_name,
            tickets_abiertos=len(documentos_abiertos(db, org_id=org_id, customer=c)),
            antiguedad=antig,
        ))
    if order == "antiguedad":
        filas.sort(key=lambda f: (-f.dias, -f.balance, f.customer.name))
    else:
        filas.sort(key=lambda f: (-f.balance, f.customer.name))
    vencido = sum((f.antiguedad["31_60"] + f.antiguedad["61_90"] + f.antiguedad["91_plus"] for f in filas), CERO)
    resumen = {
        "por_cobrar": sum((f.balance for f in filas), CERO),
        "vencido_30": vencido,
        "clientes": len(filas),
        "a_favor": a_favor,
    }
    return resumen, filas
```

Añade a `__all__`: `"cargos_pendientes", "ClienteCobranza", "cuentas_por_cobrar"`.

- [ ] **Step 4: Esquemas y ruta**

`app/modules/customers/schemas.py` (asegura `from typing import Dict, List, Optional`):

```python
class ClienteCobranzaOut(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    balance: Decimal
    cargo_mas_viejo: Optional[datetime] = None
    dias: int
    ultimo_abono: Optional[datetime] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    tickets_abiertos: int
    antiguedad: Dict[str, Decimal]   # current, 31_60, 61_90, 91_plus


class ResumenCobranza(BaseModel):
    por_cobrar: Decimal
    vencido_30: Decimal
    clientes: int
    a_favor: Decimal


class CobranzaResponse(BaseModel):
    resumen: ResumenCobranza
    items: List[ClienteCobranzaOut]
    total: int
```

`app/modules/customers/router.py`, justo después de `get_customer_stats` y ANTES del bloque `# 1. LISTAR CLIENTES` (importa `Query` de fastapi si no está, y `CobranzaResponse, ClienteCobranzaOut, ResumenCobranza` de los esquemas):

```python
@router.get("/cobranza", response_model=CobranzaResponse)
def cuentas_por_cobrar_endpoint(
    branch_id: Optional[int] = None,
    bucket: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    order: str = Query("saldo", pattern="^(saldo|antiguedad)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Cuentas por cobrar (spec 2026-10-29 §3.1): quién debe, cuánto, desde
    cuándo. Solo roles de oficina. Va antes de `GET /{customer_id}` para que
    "cobranza" no se intente leer como id."""
    from app.models.users import PlatformRole
    from app.services.metricas_ventas import HQ_ROLES
    from app.modules.customers.services import BUCKETS, cuentas_por_cobrar

    rol = str(getattr(current_user.role, "value", current_user.role))
    if rol not in HQ_ROLES and getattr(current_user, "platform_role", None) != PlatformRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Solo administración puede ver las cuentas por cobrar")
    if bucket and bucket not in BUCKETS:
        raise HTTPException(status_code=422, detail=f"bucket debe ser uno de: {', '.join(BUCKETS)}")

    resumen, filas = cuentas_por_cobrar(
        db, org_id=org_id, branch_id=branch_id, bucket=bucket, search=search, order=order)
    pagina = filas[skip: skip + limit]
    return CobranzaResponse(
        resumen=ResumenCobranza(**resumen),
        total=len(filas),
        items=[
            ClienteCobranzaOut(
                id=f.customer.id, name=f.customer.name, phone=f.customer.phone, balance=f.balance,
                cargo_mas_viejo=f.cargo_mas_viejo, dias=f.dias, ultimo_abono=f.ultimo_abono,
                branch_id=f.branch_id, branch_name=f.branch_name,
                tickets_abiertos=f.tickets_abiertos, antiguedad=f.antiguedad,
            )
            for f in pagina
        ],
    )
```

- [ ] **Step 5: Corre**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_crm_cobranza_endpoint.py tests/test_crm_credito_auditoria.py tests/test_regresion_reportes.py tests/test_customers_statement_api.py`
Expected: todo PASS (la refactorización de `antiguedad_por_cargo` no cambia sus resultados: lo fijan las pruebas de la auditoría y `test_a9`).

- [ ] **Step 6: Commit**

```bash
git add app/modules/customers/services.py app/modules/customers/schemas.py app/modules/customers/router.py tests/test_crm_cobranza_endpoint.py
git commit -m "feat(crm): endpoint de cuentas por cobrar con antigüedad por cargo"
```

---

### Task 8: Tarjeta "Por cobrar" en el Inicio

**Files:**
- Modify: `app/schemas/reports.py` (`PorCobrar`, `InicioResponse.por_cobrar`)
- Modify: `app/routers/reports_inicio.py` (`_por_cobrar`, uso en `inicio`)
- Modify: `frontend/src/api/reports.ts` (`Inicio.por_cobrar`, `PeriodoVentas.fiado/cobranza`)
- Modify: `frontend/src/pages/hq/Inicio.tsx` (componente `PorCobrar`, render tras Pendientes)
- Test: `tests/test_reports_inicio.py`, `frontend/src/pages/hq/__tests__/Inicio.test.tsx`

**Interfaces:**
- Consumes: `cuentas_por_cobrar` (Tarea 7).
- Produces: `InicioResponse.por_cobrar: Optional[{total: float, vencido_30: float, clientes: int}]` (solo `completo=true`, rol HQ y módulo `crm` encendido).

- [ ] **Step 1: Prueba backend que falla**

En `tests/test_reports_inicio.py` (sección SP6, después de `test_sin_completo_las_secciones_nuevas_son_null`):

```python
def test_por_cobrar_solo_con_completo_rol_de_oficina_y_crm(client, db, org, branch_a, admin_user, auth_admin, cajero_a, auth_cajero_a):
    from app.models.modules import Module, OrganizationModule
    from app.modules.customers.models import Customer, CustomerLedgerEntry
    cliente = Customer(name="Fiada", organization_id=org.id, current_balance=Decimal("0"))
    db.add(cliente); db.commit()
    doc = _venta(db, org, branch_a, cajero_a, _variante(db, org, branch_a, "Blusa", "BL-1", 5), "300",
                 status=DocumentStatus.PENDING, dias_atras=40)
    doc.customer_id = cliente.id
    cargo = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=doc.id, organization_id=org.id,
                                amount=Decimal("300"), description="Venta a crédito")
    cargo.created_at = doc.created_at
    cliente.current_balance = Decimal("300")
    db.add(cargo); db.commit()

    assert client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["por_cobrar"] is None, "sin módulo crm"

    if db.query(Module).filter(Module.key == "crm").first() is None:
        db.add(Module(key="crm", name="crm")); db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="crm", is_enabled=True)); db.commit()

    assert client.get(INICIO, headers=auth_admin).json()["por_cobrar"] is None, "sin completo"
    pc = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["por_cobrar"]
    assert pc == {"total": 300.0, "vencido_30": 300.0, "clientes": 1}
```

(Si `_venta` de ese archivo no acepta `status`/`dias_atras` con esos nombres, usa los que tenga: su firma está en las líneas 46-47. `INICIO` es la constante del archivo con la URL del endpoint. Un cajero no llega al Inicio del dueño; el 403 de rol ya lo cubre `tests/test_crm_cobranza_endpoint.py`.)

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_reports_inicio.py -k por_cobrar`
Expected: FAIL (`KeyError: 'por_cobrar'`).

- [ ] **Step 2: Backend**

`app/schemas/reports.py`, antes de `InicioResponse`:
```python
class PorCobrar(BaseModel):
    """Spec 2026-10-29 §3.3: solo con `completo`, rol de oficina y módulo crm."""
    total: float
    vencido_30: float   # suma de los cubos 31_60 + 61_90 + 91_plus
    clientes: int
```
y en `InicioResponse`: `por_cobrar: Optional[PorCobrar] = None`.

`app/routers/reports_inicio.py`: importa `PorCobrar` con los demás esquemas y `from app.models.modules import OrganizationModule`; añade antes de la ruta:

```python
def _por_cobrar(db: Session, org_id: int, sucursal: Optional[int], current_user: User) -> Optional[PorCobrar]:
    """Cuentas por cobrar para la tarjeta del Inicio: solo roles de oficina y
    solo con el módulo `crm` encendido; si no, None y la tarjeta no se pinta."""
    rol = str(getattr(current_user.role, "value", current_user.role))
    if rol not in mv.HQ_ROLES:
        return None
    activo = db.query(OrganizationModule.id).filter(
        OrganizationModule.organization_id == org_id, OrganizationModule.module_key == "crm",
        OrganizationModule.is_enabled == True,  # noqa: E712
    ).first()
    if activo is None:
        return None
    from app.modules.customers.services import cuentas_por_cobrar
    resumen, _ = cuentas_por_cobrar(db, org_id=org_id, branch_id=sucursal)
    return PorCobrar(total=float(resumen["por_cobrar"]), vencido_30=float(resumen["vencido_30"]),
                     clientes=int(resumen["clientes"]))
```

y en `inicio`, dentro del bloque `completo`, después de `respuesta.pendientes = ...`: `respuesta.por_cobrar = _por_cobrar(db, org_id, sucursal, current_user)`.

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_reports_inicio.py`
Expected: PASS.

- [ ] **Step 3: Prueba del Inicio que falla**

En `frontend/src/pages/hq/__tests__/Inicio.test.tsx`: añade `por_cobrar: null,` a `DATOS` (junto a `pendientes: null`) y `por_cobrar: { total: 4500, vencido_30: 1200, clientes: 3 },` a `COMPLETO`. Añade al final del `describe` principal (usa los helpers `pintar`, `perfil` y los mocks del archivo):

```tsx
  it('pinta "Por cobrar" solo cuando viene y es mayor que cero', async () => {
    perfil('completo')
    inicio.mockResolvedValueOnce(COMPLETO); valorInventario.mockResolvedValue(VALUACION)
    pintar()
    const tarjeta = await screen.findByTestId('por-cobrar')
    expect(within(tarjeta).getByText('$4,500.00')).toBeTruthy()
    expect(within(tarjeta).getByText('$1,200.00')).toBeTruthy()
    expect(within(tarjeta).getByText('3 clientes')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Ver cuentas por cobrar/ }).getAttribute('href')).toBe('/customers/cobranza')
    cleanup()
    inicio.mockResolvedValueOnce({ ...COMPLETO, por_cobrar: { total: 0, vencido_30: 0, clientes: 0 } })
    pintar()
    await screen.findByTestId('pendientes')
    expect(screen.queryByTestId('por-cobrar')).toBeNull()
  })
```

(`formatCurrency` del proyecto pinta `$4,500.00`; si la prueba muestra otro formato, ajusta el texto esperado al de `formatCurrency(4500)`.)

Run: `cd frontend && npx vitest run src/pages/hq/__tests__/Inicio.test.tsx`
Expected: FAIL (no existe `por-cobrar`).

- [ ] **Step 4: Frontend**

`frontend/src/api/reports.ts`: en `PeriodoVentas` añade `fiado?: number` y `cobranza?: number`; en `Inicio`, después de `pendientes`: 
```ts
  /** Cuentas por cobrar (spec 2026-10-29 §3.3): solo con `completo`, rol de oficina y módulo crm; null si no aplica. */
  por_cobrar: { total: number; vencido_30: number; clientes: number } | null
```

`frontend/src/pages/hq/Inicio.tsx`: después de la función `Pendientes` añade:

```tsx
function PorCobrar({ datos }: { datos: NonNullable<DatosInicio['por_cobrar']> }) {
  const clientes = datos.clientes === 1 ? '1 cliente' : `${datos.clientes} clientes`
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/customers/cobranza', texto: 'Ver cuentas por cobrar →' }}>Por cobrar</Titulo>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="por-cobrar">
        <KpiCard etiqueta="Total por cobrar" valor={formatCurrency(datos.total)} detalle={clientes} />
        <KpiCard etiqueta="Vencido a más de 30 días" valor={formatCurrency(datos.vencido_30)}
          tono={datos.vencido_30 > 0 ? 'danger' : undefined} />
      </div>
    </DaxCard>
  )
}
```

y en el render, justo después de la línea `{datos.pendientes && <Pendientes … />}`:
```tsx
          {/* 4b · Por cobrar: solo si hay deuda (render condicional, no hidden) */}
          {datos.por_cobrar && datos.por_cobrar.total > 0 && <PorCobrar datos={datos.por_cobrar} />}
```

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/hq/__tests__/Inicio.test.tsx src/pages/__tests__/responsivoOla2.test.ts src/__tests__/coloresPorTokens.test.ts`
Expected: PASS. (Si otro test del archivo construye su propio objeto `Inicio` sin `por_cobrar`, `tsc` lo dirá: añádele `por_cobrar: null`.)

- [ ] **Step 5: Commit**

```bash
git add app/schemas/reports.py app/routers/reports_inicio.py tests/test_reports_inicio.py frontend/src/api/reports.ts frontend/src/pages/hq/Inicio.tsx frontend/src/pages/hq/__tests__/Inicio.test.tsx
git commit -m "feat(inicio): tarjeta Por cobrar para roles de oficina"
```

---

### Task 9: `AbonoModal` compartido (admin) con selector de ticket e impresión

**Files:**
- Create: `frontend/src/components/crm/AbonoModal.tsx`
- Modify: `frontend/src/pages/crm/Customers.tsx` (estado del pago, modal)
- Modify: `frontend/src/pages/crm/__tests__/Customers.test.tsx` (mock)
- Test: `frontend/src/components/crm/__tests__/AbonoModal.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `customersApi.pay` → `AbonoResponse`, `customersApi.getUnpaidDocuments` (Tarea 5).
- Produces: `AbonoModal({ customerId, customerName, onClose, onDone?, imprimir? })`. `imprimir(paymentId)` es opcional: con ella aparece la casilla "Imprimir recibo" (marcada) y se llama tras abonar. La Tarea 10 la usa desde el POS; la Tarea 11 desde Cobranza.

- [ ] **Step 1: Prueba que falla**

Crea `frontend/src/components/crm/__tests__/AbonoModal.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { pay, getUnpaidDocuments } = vi.hoisted(() => ({ pay: vi.fn(), getUnpaidDocuments: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { pay, getUnpaidDocuments } }))

import { AbonoModal } from '../AbonoModal'

const RESPUESTA = {
  entries: [], customer_balance_before: 200, customer_balance_after: 50, unapplied: 0,
  applied: [{ sales_document_id: 'd1', folio: 'A-12', amount: 150, paid_in_full: true }],
  payment_id: 'pago-1', method: 'CASH', reference: null, received_at: '2026-10-31T18:00:00Z',
}
const TICKETS = [
  { id: 'd1', folio: 'A-12', created_at: '2026-10-01T18:00:00Z', total_amount: 100, paid_amount: 0, balance: 100, doc_type: 'ORDER' },
  { id: 'd2', folio: 'A-15', created_at: '2026-10-20T18:00:00Z', total_amount: 100, paid_amount: 0, balance: 100, doc_type: 'ORDER' },
]
const confirmar = () => screen.getByRole('button', { name: /Confirmar/ }) as HTMLButtonElement
const monto = () => screen.getByPlaceholderText('0.00')

beforeEach(() => { pay.mockReset().mockResolvedValue(RESPUESTA); getUnpaidDocuments.mockReset().mockResolvedValue(TICKETS) })
afterEach(cleanup)

describe('AbonoModal', () => {
  it('fuera de efectivo la referencia es obligatoria', async () => {
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(monto(), { target: { value: '100' } })
    expect(confirmar().disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('Método'), { target: { value: 'CARD' } })
    expect(confirmar().disabled).toBe(true)
    fireEvent.change(screen.getByLabelText(/Referencia/), { target: { value: '4421' } })
    expect(confirmar().disabled).toBe(false)
  })

  it('lista los tickets abiertos y manda el elegido; sin elegir, va del más viejo al más nuevo', async () => {
    const onDone = vi.fn(); const onClose = vi.fn()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={onClose} onDone={onDone} />)
    const selector = await screen.findByLabelText('Aplicar a ticket')
    expect(screen.getByText(/A-15/)).toBeTruthy()
    fireEvent.change(monto(), { target: { value: '50' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenCalledWith(1, { amount: 50, method: 'CASH', reference: undefined, sales_document_id: undefined }))
    expect(onDone).toHaveBeenCalledWith(RESPUESTA)
    expect(onClose).toHaveBeenCalled()
    cleanup()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Aplicar a ticket'), { target: { value: 'd2' } })
    fireEvent.change(monto(), { target: { value: '20' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenLastCalledWith(1, expect.objectContaining({ sales_document_id: 'd2' })))
    void selector
  })

  it('muestra el detalle del backend cuando el abono se rechaza', async () => {
    pay.mockRejectedValueOnce({ response: { data: { detail: 'Debes abrir caja antes de cobrar en efectivo' } } })
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    expect(await screen.findByText('Debes abrir caja antes de cobrar en efectivo')).toBeTruthy()
  })

  it('imprime el recibo al confirmar si la casilla está marcada', async () => {
    const imprimir = vi.fn(async () => {})
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} imprimir={imprimir} />)
    const casilla = screen.getByLabelText('Imprimir recibo') as HTMLInputElement
    expect(casilla.checked).toBe(true)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(imprimir).toHaveBeenCalledWith('pago-1'))
    cleanup()
    imprimir.mockClear()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} imprimir={imprimir} />)
    fireEvent.click(screen.getByLabelText('Imprimir recibo'))
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenCalled())
    expect(imprimir).not.toHaveBeenCalled()
  })
})
```

Run: `cd frontend && npx vitest run src/components/crm/__tests__/AbonoModal.test.tsx`
Expected: FAIL (el módulo no existe).

- [ ] **Step 2: El componente**

Crea `frontend/src/components/crm/AbonoModal.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { customersApi, type AbonoResponse, type UnpaidDocument } from '../../api/customers'
import { Modal } from '../ui/Modal'
import { formatCurrency } from '../../utils/currency'

type Metodo = 'CASH' | 'CARD' | 'TRANSFER'

interface Props {
  customerId: number
  customerName: string
  onClose: () => void
  /** Recibe la respuesta del backend; el padre refresca saldo y listas. */
  onDone?: (r: AbonoResponse) => void
  /** Con ella aparece la casilla "Imprimir recibo" (marcada) y se llama tras abonar. */
  imprimir?: (paymentId: string) => Promise<void>
}

const apiErrorMessage = (err: unknown, fallback: string) => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/**
 * Registrar un abono a la cuenta de un cliente (spec 2026-10-29 §4.1). Lo
 * usan Clientes, Cuentas por cobrar y el POS. Sin ticket elegido el backend
 * reparte del más viejo al más nuevo; lo que sobre queda a favor.
 */
export function AbonoModal({ customerId, customerName, onClose, onDone, imprimir }: Props) {
  const [monto, setMonto] = useState('')
  const [metodo, setMetodo] = useState<Metodo>('CASH')
  const [referencia, setReferencia] = useState('')
  const [ticket, setTicket] = useState('')
  const [tickets, setTickets] = useState<UnpaidDocument[]>([])
  const [imprimirRecibo, setImprimirRecibo] = useState(true)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const montoRef = useRef<HTMLInputElement>(null)

  // El Modal del kit enfoca su primer control (cerrar) al montar; este efecto corre después y devuelve el foco al monto.
  useEffect(() => { montoRef.current?.focus() }, [])
  useEffect(() => {
    let vivo = true
    customersApi.getUnpaidDocuments(customerId).then((d) => { if (vivo) setTickets(d) }).catch(() => {})
    return () => { vivo = false }
  }, [customerId])

  const importe = parseFloat(monto)
  const referenciaOk = metodo === 'CASH' || referencia.trim().length > 0
  const valido = Number.isFinite(importe) && importe > 0 && referenciaOk && !guardando

  const confirmar = async () => {
    if (!valido) return
    setGuardando(true)
    setError(null)
    try {
      const r = await customersApi.pay(customerId, {
        amount: importe,
        method: metodo,
        reference: referencia.trim() || undefined,
        sales_document_id: ticket || undefined,
      })
      onDone?.(r)
      if (imprimir && imprimirRecibo) {
        try {
          await imprimir(r.payment_id)
        } catch {
          setError('El abono quedó registrado, pero el recibo no se imprimió')
          setGuardando(false)
          return
        }
      }
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo registrar el abono'))
      setGuardando(false)
    }
  }

  const fecha = (iso: string) => new Date(iso).toLocaleDateString('es-MX')

  return (
    <Modal open onClose={onClose} size="sm" title="Registrar abono"
      footer={<>
        <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
        <button onClick={confirmar} disabled={!valido} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
        </button>
      </>}>
      <p className="text-dax-muted text-sm mb-4">{customerName}</p>
      <div className="space-y-3">
        <div>
          <label htmlFor="abono-monto" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Monto</label>
          <input id="abono-monto" type="number" step="0.01" min="0" value={monto} onChange={(e) => setMonto(e.target.value)}
            placeholder="0.00" className="dax-input w-full text-lg font-bold" ref={montoRef} />
        </div>
        <div>
          <label htmlFor="abono-metodo" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Método</label>
          <select id="abono-metodo" value={metodo} onChange={(e) => setMetodo(e.target.value as Metodo)} className="dax-input w-full text-sm">
            <option value="CASH">Efectivo</option>
            <option value="CARD">Tarjeta</option>
            <option value="TRANSFER">Transferencia</option>
          </select>
        </div>
        {metodo !== 'CASH' && (
          <div>
            <label htmlFor="abono-referencia" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Referencia (obligatoria)</label>
            <input id="abono-referencia" type="text" value={referencia} onChange={(e) => setReferencia(e.target.value)}
              placeholder={metodo === 'TRANSFER' ? 'Folio de la transferencia' : 'Últimos dígitos / autorización'} className="dax-input w-full text-sm" />
          </div>
        )}
        {tickets.length > 0 && (
          <div>
            <label htmlFor="abono-ticket" className="text-[10px] font-bold text-dax-muted uppercase tracking-wider block mb-1">Aplicar a ticket</label>
            <select id="abono-ticket" value={ticket} onChange={(e) => setTicket(e.target.value)} className="dax-input w-full text-sm">
              <option value="">Del más viejo al más nuevo</option>
              {tickets.map((t) => (
                <option key={t.id} value={t.id}>{t.folio} · {fecha(t.created_at)} · debe {formatCurrency(t.balance)}</option>
              ))}
            </select>
          </div>
        )}
        {imprimir && (
          <label className="flex items-center gap-2 text-sm text-dax-text min-h-[44px]">
            <input type="checkbox" checked={imprimirRecibo} onChange={(e) => setImprimirRecibo(e.target.checked)} />
            Imprimir recibo
          </label>
        )}
        <p className="text-xs text-dax-muted">Sin ticket elegido, el abono se aplica del ticket más viejo al más nuevo; lo que sobre queda a favor.</p>
        {error && <p className="text-dax-danger text-xs" role="alert">{error}</p>}
      </div>
    </Modal>
  )
}
```

Run: `cd frontend && npx vitest run src/components/crm/__tests__/AbonoModal.test.tsx`
Expected: PASS.

- [ ] **Step 3: `Customers.tsx` usa el modal**

En `frontend/src/pages/crm/Customers.tsx`:
1. Import: `import { AbonoModal } from '../../components/crm/AbonoModal'`. Quita el import de `Modal` si queda sin uso.
2. Borra los estados `payAmount`, `payMethod`, `payReference`, `payLoading`, `payInputRef`, la constante `payAbierto` y su `useEffect`, y la función `handlePay`. Deja `payModal`/`setPayModal` y `cerrarPago = () => setPayModal(null)`.
3. Sustituye todo el bloque `{/* Modal pago */} {payModal && (<Modal …>…</Modal>)}` por:
   ```tsx
      {payModal && (
        <AbonoModal
          customerId={payModal.id}
          customerName={payModal.name}
          onClose={cerrarPago}
          onDone={() => {
            customersApi.getStats().then(setStats).catch(() => {})
            load(search, page)
            if (selected?.id === payModal.id) openDetail({ ...selected })
          }}
        />
      )}
   ```
4. En `frontend/src/pages/crm/__tests__/Customers.test.tsx`, el mock de `customersApi` gana `getUnpaidDocuments: vi.fn().mockResolvedValue([])` (el modal lo llama al montar).

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/crm src/components/crm`
Expected: PASS (`Customers.test.tsx` sigue encontrando el `placeholder="0.00"` enfocado; `customersEscape.test.ts` sigue viendo `querySelector('[role="dialog"]')`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/crm/AbonoModal.tsx frontend/src/components/crm/__tests__/AbonoModal.test.tsx frontend/src/pages/crm/Customers.tsx frontend/src/pages/crm/__tests__/Customers.test.tsx
git commit -m "feat(crm): AbonoModal compartido con selector de ticket e impresión del recibo"
```

---

### Task 10: "Abonar" desde el POS

**Files:**
- Modify: `frontend/src/store/posStore.ts` (`saldoVersion`, `tocarSaldo`)
- Modify: `frontend/src/components/pos/CartPanel.tsx:45-54` (refresco del saldo)
- Modify: `frontend/src/components/pos/modals/CustomerModal.tsx`
- Test: `frontend/src/components/pos/__tests__/CustomerModalAbonar.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `AbonoModal` (Tarea 9), `printerApi.getAbonoBase64` / `printerApi.printViaAgent` (Tarea 6), `customersApi.getById`.
- Produces: `usePOSStore().saldoVersion: number`, `usePOSStore().tocarSaldo(): void` (el carrito vuelve a pedir el saldo cuando cambia).

- [ ] **Step 1: Prueba que falla**

Crea `frontend/src/components/pos/__tests__/CustomerModalAbonar.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { getById, search } = vi.hoisted(() => ({ getById: vi.fn(), search: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { getById, search, create: vi.fn() } }))
vi.mock('../../../api/printer', () => ({ printerApi: { getAbonoBase64: vi.fn(), printViaAgent: vi.fn() } }))
vi.mock('../../crm/AbonoModal', () => ({ AbonoModal: () => <div data-testid="abono-modal" /> }))

import { CustomerModal } from '../modals/CustomerModal'
import { usePOSStore } from '../../../store/posStore'

beforeEach(() => {
  search.mockReset().mockResolvedValue([])
  getById.mockReset()
  usePOSStore.setState({ customerId: 7, customerName: 'Ana Pérez' })
})
afterEach(cleanup)

describe('CustomerModal: Abonar', () => {
  it('ofrece Abonar solo cuando el cliente elegido debe', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 250 })
    render(<CustomerModal onClose={() => {}} />)
    const boton = await screen.findByRole('button', { name: /Abonar/ })
    expect(screen.getByText(/Debe \$250\.00/)).toBeTruthy()
    fireEvent.click(boton)
    expect(await screen.findByTestId('abono-modal')).toBeTruthy()
  })

  it('sin deuda no hay botón', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 0 })
    render(<CustomerModal onClose={() => {}} />)
    await waitFor(() => expect(getById).toHaveBeenCalledWith(7))
    expect(screen.queryByRole('button', { name: /Abonar/ })).toBeNull()
  })

  it('con nombre libre (sin ficha) ni consulta ni botón', () => {
    usePOSStore.setState({ customerId: null, customerName: 'Cliente de paso' })
    render(<CustomerModal onClose={() => {}} />)
    expect(getById).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /Abonar/ })).toBeNull()
  })

  it('tocarSaldo sube la versión que el carrito observa', () => {
    const antes = usePOSStore.getState().saldoVersion
    usePOSStore.getState().tocarSaldo()
    expect(usePOSStore.getState().saldoVersion).toBe(antes + 1)
  })
})
```

Run: `cd frontend && npx vitest run src/components/pos/__tests__/CustomerModalAbonar.test.tsx`
Expected: FAIL (no hay botón Abonar; `tocarSaldo` no existe).

- [ ] **Step 2: Store y carrito**

`frontend/src/store/posStore.ts`:
- En la interfaz, debajo de `customerId: number | null`: `/** Sube cuando el cliente abona desde el POS: el carrito vuelve a pedir el saldo. */ saldoVersion: number` y, junto a `setCustomer`, `tocarSaldo: () => void`.
- En el estado inicial, junto a `customerId: null,`: `saldoVersion: 0,`.
- Junto a la implementación de `setCustomer`: `tocarSaldo: () => set((s) => ({ saldoVersion: s.saldoVersion + 1 })),`.

`frontend/src/components/pos/CartPanel.tsx`: después de `const customerId = usePOSStore((s) => s.customerId)` añade `const saldoVersion = usePOSStore((s) => s.saldoVersion)` y cambia las dependencias del efecto del saldo a `[customerId, saldoVersion]`.

- [ ] **Step 3: El botón en `CustomerModal`**

En `frontend/src/components/pos/modals/CustomerModal.tsx`:

Imports:
```tsx
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { printerApi } from '../../../api/printer'
import { toast } from '../../../store/toastStore'

// Perezoso: el POS no paga el modal de abono hasta que alguien abona.
const AbonoModal = lazy(() => import('../../crm/AbonoModal').then((m) => ({ default: m.AbonoModal })))
```

Dentro del componente, después de `const setCustomer = …`:
```tsx
  const printerName = usePOSStore((s) => s.printerName)
  const tocarSaldo = usePOSStore((s) => s.tocarSaldo)
  // Saldo del cliente con ficha: habilita "Abonar" (spec 2026-10-29 §4.1).
  // Un nombre libre no tiene ficha ni saldo; si el CRM falla, no hay botón.
  const [saldo, setSaldo] = useState<number | null>(null)
  const [abonando, setAbonando] = useState(false)
  useEffect(() => {
    if (customerId == null) { setSaldo(null); return }
    let vivo = true
    customersApi.getById(customerId)
      .then((c) => { if (vivo) setSaldo(c.current_balance ?? 0) })
      .catch(() => { if (vivo) setSaldo(null) })
    return () => { vivo = false }
  }, [customerId])

  const imprimirRecibo = async (paymentId: string) => {
    const b64 = await printerApi.getAbonoBase64(paymentId)
    if (printerName && b64) await printerApi.printViaAgent(printerName, b64)
  }
```

El manejador de Escape pasa a respetar el modal de abono (su `Modal` del kit ya cierra con Escape):
```tsx
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !abonando) onClose() }
```
y sus dependencias a `[onClose, abonando]`.

En el subtítulo (`<p className="text-xs mb-4" …>Búscalo en clientes, guárdalo o usa solo el nombre.</p>`) añade, debajo:
```tsx
        {customerId != null && saldo != null && saldo > 0 && (
          <p className="text-xs mb-3 font-semibold text-dax-danger">Debe {formatCurrency(saldo)}</p>
        )}
```

En el pie (`dax-modal-footer`), antes del botón "Quitar cliente":
```tsx
          {customerId != null && saldo != null && saldo > 0 && (
            <button onClick={() => setAbonando(true)} className="dax-btn-primary text-sm min-h-[44px]">
              <i className="fa-solid fa-hand-holding-dollar" /> Abonar
            </button>
          )}
```

Antes del cierre del `div` raíz (después del `dax-card dax-modal`):
```tsx
      {abonando && customerId != null && (
        <Suspense fallback={null}>
          <AbonoModal
            customerId={customerId}
            customerName={customerName ?? ''}
            onClose={() => setAbonando(false)}
            onDone={(r) => {
              toast.success(`Abono de ${formatCurrency(r.customer_balance_before - r.customer_balance_after)} · Saldo: ${formatCurrency(r.customer_balance_after)}`)
              setSaldo(r.customer_balance_after)
              tocarSaldo()
            }}
            imprimir={imprimirRecibo}
          />
        </Suspense>
      )}
```

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/components/pos src/__tests__/overlaysFueraDelKit.test.ts src/__tests__/botonesDelKit.test.ts src/__tests__/rutasPerezosas.test.ts`
Expected: PASS (el `rutasPerezosas > MobileLayout` de 5 s es un flake conocido; si solo falla ese, vuelve a correr).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/posStore.ts frontend/src/components/pos/CartPanel.tsx frontend/src/components/pos/modals/CustomerModal.tsx frontend/src/components/pos/__tests__/CustomerModalAbonar.test.tsx
git commit -m "feat(pos): Abonar desde el botón Cliente con recibo impreso"
```

---

### Task 11: Pantalla "Cuentas por cobrar" con recordatorio por WhatsApp

**Files:**
- Modify: `frontend/src/api/customers.ts` (tipos y `cobranza`)
- Create: `frontend/src/pages/crm/Cobranza.tsx`
- Modify: `frontend/src/App.tsx` (lazy + ruta), `frontend/src/components/layout/navConfig.ts:144-146` (`ROLE_ROUTES`), `frontend/src/components/layout/navPerfilBasico.ts:24-31` (`OCULTAS_BASICO_HQ`), `frontend/src/pages/__tests__/responsivoOla2.test.ts:6-10` (`PAGINAS`), `frontend/src/pages/crm/Customers.tsx` (enlace en la cabecera)
- Test: `frontend/src/utils/__tests__/phone.test.ts` (nuevo), `frontend/src/pages/crm/__tests__/Cobranza.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `GET /api/customers/cobranza` (Tarea 7), `AbonoModal` (Tarea 9), `customersApi.getUnpaidDocuments`, `customersApi.getStatement`, `customersApi.getStatementPdf`, `toWaPhone` (`utils/phone.ts`), `useSucursalesVendibles`, `useAuthStore().org?.name`.
- Produces: ruta `/customers/cobranza`; `customersApi.cobranza(params) -> CobranzaResponse`.

- [ ] **Step 1: Pruebas que fallan**

`frontend/src/utils/__tests__/phone.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { toWaPhone } from '../phone'

describe('toWaPhone (Review Focus 5)', () => {
  it('normaliza a E.164 de México', () => {
    expect(toWaPhone('55 1234 5678')).toBe('525512345678')
    expect(toWaPhone('(55) 1234-5678')).toBe('525512345678')
    expect(toWaPhone('+52 55 1234 5678')).toBe('525512345678')
    expect(toWaPhone('5215512345678')).toBe('5215512345678')
  })
  it('lo que no es marcable da null', () => {
    expect(toWaPhone(null)).toBeNull()
    expect(toWaPhone('')).toBeNull()
    expect(toWaPhone('1234')).toBeNull()
  })
})
```

`frontend/src/pages/crm/__tests__/Cobranza.test.tsx`:
```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { cobranza, modo } = vi.hoisted(() => ({ cobranza: vi.fn(), modo: { telefono: false } }))
vi.mock('../../../api/customers', () => ({
  customersApi: {
    cobranza,
    getUnpaidDocuments: vi.fn().mockResolvedValue([]),
    getStatement: vi.fn().mockResolvedValue([]),
    getStatementPdf: vi.fn(),
  },
}))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => modo.telefono }))
vi.mock('../../../hooks/useSucursalesVendibles', () => ({ useSucursalesVendibles: () => [] }))
vi.mock('../../../components/crm/AbonoModal', () => ({ AbonoModal: () => <div data-testid="abono-modal" /> }))

import { Cobranza } from '../Cobranza'
import { useAuthStore } from '../../../store/authStore'

const DATOS = {
  resumen: { por_cobrar: 150, vencido_30: 70, clientes: 2, a_favor: 20 },
  total: 2,
  items: [
    { id: 1, name: 'Ana Pérez', phone: '55 1234 5678', balance: 70, cargo_mas_viejo: '2026-09-16T18:00:00Z', dias: 45,
      ultimo_abono: '2026-10-21T18:00:00Z', branch_id: 1, branch_name: 'Roma', tickets_abiertos: 1,
      antiguedad: { current: 0, '31_60': 70, '61_90': 0, '91_plus': 0 } },
    { id: 2, name: 'Beto', phone: null, balance: 80, cargo_mas_viejo: '2026-10-31T18:00:00Z', dias: 0,
      ultimo_abono: null, branch_id: 2, branch_name: 'Condesa', tickets_abiertos: 1,
      antiguedad: { current: 80, '31_60': 0, '61_90': 0, '91_plus': 0 } },
  ],
}
const pintar = () => render(<MemoryRouter><Cobranza /></MemoryRouter>)

beforeEach(() => {
  cobranza.mockReset().mockResolvedValue(DATOS)
  modo.telefono = false
  useAuthStore.setState({ user: { id: 1, role: 'ADMINISTRADOR' } as never, org: { id: 17, name: 'Eleven Fashion' } as never })
})
afterEach(cleanup)

describe('Cuentas por cobrar', () => {
  it('pinta las cifras, los renglones y la antigüedad', async () => {
    pintar()
    expect(await screen.findByText('Ana Pérez')).toBeTruthy()
    const kpis = screen.getByTestId('kpis-cobranza')
    expect(within(kpis).getByText('$150.00')).toBeTruthy()
    expect(within(kpis).getByText('$70.00')).toBeTruthy()
    expect(within(kpis).getByText('2')).toBeTruthy()
    expect(screen.getByText(/45 días/)).toBeTruthy()
    expect(screen.getAllByText(/31-60/).length).toBeGreaterThan(0)
  })

  it('WhatsApp abre el chat con el mensaje y se deshabilita sin teléfono (Review Focus 5)', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    pintar()
    await screen.findByText('Ana Pérez')
    const botones = screen.getAllByRole('button', { name: /WhatsApp/ }) as HTMLButtonElement[]
    expect(botones.length).toBe(2)
    const [ana, beto] = botones
    expect(beto.disabled).toBe(true)
    expect(beto.title).toBe('Sin teléfono')
    fireEvent.click(ana)
    const url = open.mock.calls[0][0] as string
    expect(url.startsWith('https://wa.me/525512345678?text=')).toBe(true)
    expect(decodeURIComponent(url.split('text=')[1])).toBe(
      'Hola Ana Pérez, te saludamos de Eleven Fashion. Tienes un saldo pendiente de $70.00. Puedes pasar a abonar cuando gustes. ¡Gracias!')
    open.mockRestore()
  })

  it('al abrir un renglón muestra el detalle y Registrar abono', async () => {
    pintar()
    fireEvent.click(await screen.findByText('Ana Pérez'))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Registrar abono/ }))
    expect(await screen.findByTestId('abono-modal')).toBeTruthy()
  })

  it('en teléfono usa tarjetas, no tabla', async () => {
    modo.telefono = true
    pintar()
    await screen.findByText('Ana Pérez')
    expect(document.querySelector('table')).toBeNull()
  })

  it('cambiar filtros vuelve a pedir con esos parámetros', async () => {
    pintar()
    await screen.findByText('Ana Pérez')
    fireEvent.change(screen.getByLabelText('Antigüedad'), { target: { value: '91_plus' } })
    expect(cobranza).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: '91_plus' }))
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'antiguedad' } })
    expect(cobranza).toHaveBeenLastCalledWith(expect.objectContaining({ order: 'antiguedad' }))
  })
})
```

Run: `cd frontend && npx vitest run src/utils/__tests__/phone.test.ts src/pages/crm/__tests__/Cobranza.test.tsx`
Expected: `phone.test.ts` PASS (la función ya existe); `Cobranza.test.tsx` FAIL (no existe la página).

- [ ] **Step 2: Cliente de la API**

En `frontend/src/api/customers.ts` añade los tipos:

```ts
export interface CobranzaItem {
  id: number
  name: string
  phone: string | null
  balance: number
  cargo_mas_viejo: string | null
  dias: number
  ultimo_abono: string | null
  branch_id: number | null
  branch_name: string | null
  tickets_abiertos: number
  antiguedad: Record<'current' | '31_60' | '61_90' | '91_plus', number>
}

export interface CobranzaResumen { por_cobrar: number; vencido_30: number; clientes: number; a_favor: number }

export interface CobranzaResponse { resumen: CobranzaResumen; items: CobranzaItem[]; total: number }
```

y en `customersApi`:

```ts
  /** GET /customers/cobranza (spec 2026-10-29 §3.1): solo roles de oficina. */
  cobranza: async (params?: { branch_id?: number; bucket?: string; search?: string; order?: 'saldo' | 'antiguedad'; skip?: number; limit?: number }): Promise<CobranzaResponse> => {
    const { data } = await client.get<CobranzaResponse>('/customers/cobranza', { params })
    const num = (v: unknown) => Number(v ?? 0)
    return {
      total: data.total,
      resumen: { por_cobrar: num(data.resumen.por_cobrar), vencido_30: num(data.resumen.vencido_30), clientes: data.resumen.clientes, a_favor: num(data.resumen.a_favor) },
      items: data.items.map((i) => ({
        ...i, balance: num(i.balance),
        antiguedad: { current: num(i.antiguedad.current), '31_60': num(i.antiguedad['31_60']), '61_90': num(i.antiguedad['61_90']), '91_plus': num(i.antiguedad['91_plus']) },
      })),
    }
  },
```

(Los `Decimal` del backend llegan como cadenas; se convierten aquí para que la pantalla no lo haga.)

- [ ] **Step 3: La pantalla**

Crea `frontend/src/pages/crm/Cobranza.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { customersApi, type CobranzaItem, type CobranzaResponse, type LedgerEntry, type UnpaidDocument } from '../../api/customers'
import { AbonoModal } from '../../components/crm/AbonoModal'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ErrorState } from '../../components/ui/ErrorState'
import { KpiCard } from '../../components/ui/KpiCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { Modal } from '../../components/ui/Modal'
import { Spinner } from '../../components/ui/Spinner'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'
import { toWaPhone } from '../../utils/phone'

type Bucket = 'current' | '31_60' | '61_90' | '91_plus'
const BUCKETS: { clave: Bucket; etiqueta: string; tono: string }[] = [
  { clave: 'current', etiqueta: '0-30', tono: 'text-dax-success' },
  { clave: '31_60', etiqueta: '31-60', tono: 'text-dax-warning' },
  { clave: '61_90', etiqueta: '61-90', tono: 'text-dax-warning' },
  { clave: '91_plus', etiqueta: '+90', tono: 'text-dax-danger' },
]
const fecha = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('es-MX') : '—')
const dias = (n: number) => (n === 1 ? '1 día' : `${n} días`)

/** Mensaje del recordatorio (spec 2026-10-29 §5): texto fijo, sin API ni registro. */
export const mensajeRecordatorio = (nombre: string, negocio: string, saldo: number) =>
  `Hola ${nombre}, te saludamos de ${negocio}. Tienes un saldo pendiente de ${formatCurrency(saldo)}. Puedes pasar a abonar cuando gustes. ¡Gracias!`

function Antiguedad({ a }: { a: CobranzaItem['antiguedad'] }) {
  return (
    <span className="inline-flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] font-semibold tabular-nums">
      {BUCKETS.filter((b) => a[b.clave] > 0).map((b) => (
        <span key={b.clave} className={b.tono}>{b.etiqueta}: {formatCurrency(a[b.clave])}</span>
      ))}
    </span>
  )
}

/**
 * Cuentas por cobrar (spec 2026-10-29 §3.2): quién debe, cuánto y desde
 * cuándo. Solo roles de oficina; se entra desde Clientes y desde el Inicio.
 */
export function Cobranza() {
  const esTelefono = useEsTelefono()
  const negocio = useAuthStore((s) => s.org?.name) ?? 'la tienda'
  const sucursales = useSucursalesVendibles(true)
  const [datos, setDatos] = useState<CobranzaResponse | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [branchId, setBranchId] = useState('')
  const [bucket, setBucket] = useState('')
  const [order, setOrder] = useState<'saldo' | 'antiguedad'>('saldo')
  const [detalle, setDetalle] = useState<CobranzaItem | null>(null)
  const [tickets, setTickets] = useState<UnpaidDocument[]>([])
  const [asientos, setAsientos] = useState<LedgerEntry[]>([])
  const [abonando, setAbonando] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cargar = useCallback(async (q: string) => {
    setCargando(true); setError(false)
    try {
      setDatos(await customersApi.cobranza({
        search: q.trim() || undefined,
        branch_id: branchId ? Number(branchId) : undefined,
        bucket: bucket || undefined,
        order, limit: 200,
      }))
    } catch { setError(true) } finally { setCargando(false) }
  }, [branchId, bucket, order])

  useEffect(() => { cargar(search) /* eslint-disable-line react-hooks/exhaustive-deps */ }, [cargar])

  const onSearch = (v: string) => {
    setSearch(v)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => cargar(v), 400)
  }

  const abrir = async (c: CobranzaItem) => {
    setDetalle(c)
    try {
      const [t, a] = await Promise.all([customersApi.getUnpaidDocuments(c.id), customersApi.getStatement(c.id, { limit: 30 })])
      setTickets(t); setAsientos(a)
    } catch { setTickets([]); setAsientos([]) }
  }

  const whatsapp = (c: CobranzaItem) => {
    const tel = toWaPhone(c.phone)
    if (!tel) return
    window.open(`https://wa.me/${tel}?text=${encodeURIComponent(mensajeRecordatorio(c.name, negocio, c.balance))}`, '_blank')
  }

  const pdf = async (c: CobranzaItem) => {
    try {
      const blob = await customersApi.getStatementPdf(c.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `EdoCuenta_${c.name.replace(/[^\w-]+/g, '_')}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch { toast.error('No se pudo generar el PDF del estado de cuenta') }
  }

  const botonWa = (c: CobranzaItem, compacto = false) => {
    const tel = toWaPhone(c.phone)
    return (
      <button type="button" onClick={() => whatsapp(c)} disabled={!tel} title={tel ? 'Recordar por WhatsApp' : 'Sin teléfono'}
        aria-label="Recordar por WhatsApp"
        className={`${compacto ? 'dax-btn-icon' : 'dax-btn-secondary text-xs'} disabled:opacity-40`}>
        <i className="fa-brands fa-whatsapp" aria-hidden="true" />{!compacto && ' WhatsApp'}
      </button>
    )
  }

  const items = datos?.items ?? []
  const r = datos?.resumen

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-dax-text">Cuentas por cobrar</h1>}
        descripcion="Quién debe, cuánto y desde cuándo. El abono se aplica del ticket más viejo al más nuevo."
        acciones={<Link to="/customers" className="dax-btn-secondary text-xs"><i className="fa-solid fa-address-book" aria-hidden="true" /> Clientes</Link>}
      />

      {r && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="kpis-cobranza">
          <KpiCard etiqueta="Por cobrar" valor={formatCurrency(r.por_cobrar)} detalle={r.a_favor > 0 ? `A favor de clientes: ${formatCurrency(r.a_favor)}` : undefined} />
          <KpiCard etiqueta="Vencido a más de 30 días" valor={formatCurrency(r.vencido_30)} tono={r.vencido_30 > 0 ? 'danger' : undefined} />
          <KpiCard etiqueta="Clientes con deuda" valor={String(r.clientes)} />
        </div>
      )}

      <BarraFiltros>
        <input type="search" value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Nombre o teléfono" aria-label="Buscar" className="dax-input flex-1 min-w-[160px] text-sm" />
        {sucursales.length > 1 && (
          <select aria-label="Sucursal" value={branchId} onChange={(e) => setBranchId(e.target.value)} className="dax-input text-sm">
            <option value="">Todas las sucursales</option>
            {sucursales.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        <select aria-label="Antigüedad" value={bucket} onChange={(e) => setBucket(e.target.value)} className="dax-input text-sm">
          <option value="">Toda antigüedad</option>
          {BUCKETS.map((b) => <option key={b.clave} value={b.clave}>{b.etiqueta} días</option>)}
        </select>
        <select aria-label="Orden" value={order} onChange={(e) => setOrder(e.target.value as 'saldo' | 'antiguedad')} className="dax-input text-sm">
          <option value="saldo">Mayor saldo primero</option>
          <option value="antiguedad">Más viejo primero</option>
        </select>
      </BarraFiltros>

      {error ? (
        <ErrorState message="No se pudieron cargar las cuentas por cobrar" onRetry={() => cargar(search)} />
      ) : esTelefono ? (
        <ListaTarjetas vacio={!cargando && items.length === 0} textoVacio="Nadie debe" cargando={cargando}>
          {items.map((c) => (
            <TarjetaFila key={c.id} titulo={c.name} subtitulo={c.branch_name ?? undefined}
              importe={<span className="text-dax-danger font-bold">{formatCurrency(c.balance)}</span>}
              estado={<Antiguedad a={c.antiguedad} />}
              datos={[{ etiqueta: 'Desde', valor: `${fecha(c.cargo_mas_viejo)} · ${dias(c.dias)}` }, { etiqueta: 'Último abono', valor: fecha(c.ultimo_abono) }]}
              onClick={() => abrir(c)}
              acciones={<>{botonWa(c)}<button type="button" onClick={() => abrir(c)} className="dax-btn-primary text-xs">Ver</button></>} />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard>
          {cargando && !datos ? <div className="flex justify-center py-10"><Spinner /></div> : items.length === 0 ? (
            <p className="text-center text-dax-muted py-10">Nadie debe</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-dax-muted">
                  <th className="py-2">Cliente</th><th>Teléfono</th><th className="text-right">Saldo</th><th>Desde</th><th>Último abono</th><th>Sucursal</th><th>Antigüedad</th><th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-t border-dax-border-dim cursor-pointer hover:brightness-110" onClick={() => abrir(c)}>
                    <td className="py-2 font-medium text-dax-text">{c.name}</td>
                    <td className="text-dax-muted">{c.phone ?? '—'}</td>
                    <td className="text-right tabular-nums font-bold text-dax-danger">{formatCurrency(c.balance)}</td>
                    <td className="text-dax-muted">{fecha(c.cargo_mas_viejo)} · {dias(c.dias)}</td>
                    <td className="text-dax-muted">{fecha(c.ultimo_abono)}</td>
                    <td className="text-dax-muted">{c.branch_name ?? '—'}</td>
                    <td><Antiguedad a={c.antiguedad} /></td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>{botonWa(c, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </DaxCard>
      )}

      {detalle && (
        <Modal open onClose={() => { setDetalle(null); setTickets([]); setAsientos([]) }} size="lg" title={detalle.name}
          footer={<>
            {botonWa(detalle)}
            <button type="button" onClick={() => pdf(detalle)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-file-pdf" aria-hidden="true" /> Estado de cuenta</button>
            <button type="button" onClick={() => setAbonando(true)} className="dax-btn-primary text-xs flex-1 justify-center"><i className="fa-solid fa-money-bill-wave" aria-hidden="true" /> Registrar abono</button>
          </>}>
          <p className="text-sm text-dax-muted mb-3">Debe <span className="font-bold text-dax-danger">{formatCurrency(detalle.balance)}</span> · <Antiguedad a={detalle.antiguedad} /></p>
          <p className="dax-section-title mb-1">Tickets abiertos</p>
          {tickets.length === 0 ? <p className="text-xs text-dax-muted mb-3">Sin tickets abiertos</p> : (
            <ul className="mb-3 space-y-1">
              {tickets.map((t) => (
                <li key={t.id} className="flex justify-between text-sm"><span className="text-dax-text">{t.folio} · {fecha(t.created_at)}</span><span className="tabular-nums text-dax-danger">{formatCurrency(t.balance)}</span></li>
              ))}
            </ul>
          )}
          <p className="dax-section-title mb-1">Movimientos</p>
          <ul className="space-y-1 max-h-64 overflow-y-auto">
            {asientos.map((e) => (
              <li key={e.id} className="flex justify-between text-xs">
                <span className="text-dax-muted">{fecha(e.created_at)} · {e.description ?? '—'}</span>
                <span className={`tabular-nums font-semibold ${e.amount >= 0 ? 'text-dax-danger' : 'text-dax-success'}`}>{e.amount >= 0 ? '+' : ''}{formatCurrency(e.amount)}</span>
              </li>
            ))}
          </ul>
        </Modal>
      )}

      {abonando && detalle && (
        <AbonoModal customerId={detalle.id} customerName={detalle.name} onClose={() => setAbonando(false)}
          onDone={() => { cargar(search); abrir(detalle) }} />
      )}
    </div>
  )
}
```

Props del kit ya verificadas: `ErrorState { message?, onRetry?, compact? }`, `ListaTarjetas { vacio?, textoVacio?, cargando? }`, `KpiCard { etiqueta, valor, detalle?, tono? }`, `TarjetaFila { titulo, subtitulo?, importe?, estado?, datos?, acciones?, onClick? }`; tokens `border-dax-border-dim`, `text-dax-muted/-text/-success/-warning/-danger` existen en `tailwind.config.js`.

- [ ] **Step 4: Ruta, roles, modo básico, guardias y enlace**

- `frontend/src/App.tsx`: junto al `lazy` de `Customers`: `const Cobranza = lazy(() => import('./pages/crm/Cobranza').then(m => ({ default: m.Cobranza })))`, y después de la ruta `customers`:
  ```tsx
          <Route path="customers/cobranza" element={<RutaPorRol url="/customers/cobranza"><Suspense fallback={<PageLoader />}><Cobranza /></Suspense></RutaPorRol>} />
  ```
- `frontend/src/components/layout/navConfig.ts`: en `ROLE_ROUTES`, añade `'/customers/cobranza'` justo después de `'/customers'` en las listas de `ADMINISTRADOR`, `DUEÑO` y `GERENTE` (no en `CAJERO`). El menú no cambia: `urlActiva` deja "Clientes" encendido en `/customers/cobranza` porque empieza por `/customers/`.
- `frontend/src/components/layout/navPerfilBasico.ts`: en `OCULTAS_BASICO_HQ`, `'/customers', '/customers/cobranza', '/hq/branches', …`.
- `frontend/src/pages/__tests__/responsivoOla2.test.ts`: añade `'crm/Cobranza.tsx'` a `PAGINAS` después de `'crm/Customers.tsx'`.
- `frontend/src/pages/crm/Customers.tsx`: importa `Link` de `react-router-dom` y `esRolHq` de `../../utils/rolesHq`; la `CabeceraPagina` gana
  ```tsx
        acciones={(esRolHq(user?.role) || user?.role === 'GERENTE') ? (
          <Link to="/customers/cobranza" className="dax-btn-secondary text-xs"><i className="fa-solid fa-hand-holding-dollar" aria-hidden="true" /> Cuentas por cobrar</Link>
        ) : undefined}
  ```

- [ ] **Step 5: Verifica**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/pages/crm src/utils/__tests__/phone.test.ts src/pages/__tests__/responsivoOla2.test.ts src/components/layout src/__tests__/fusionesAdmin.test.ts src/__tests__/coloresPorTokens.test.ts src/__tests__/overlaysFueraDelKit.test.ts src/__tests__/botonesDelKit.test.ts && npm run build && python3 ../scripts/presupuesto_bundle.py`
Expected: todo PASS; el presupuesto de la ruta crítica no sube (la pantalla va en `lazy()` y `AbonoModal` solo entra al POS perezoso). Si `presupuesto_bundle.py` se invoca distinto, mira `docs/DEPLOY.md`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/customers.ts frontend/src/pages/crm/Cobranza.tsx frontend/src/pages/crm/__tests__/Cobranza.test.tsx frontend/src/utils/__tests__/phone.test.ts frontend/src/App.tsx frontend/src/components/layout/navConfig.ts frontend/src/components/layout/navPerfilBasico.ts frontend/src/pages/__tests__/responsivoOla2.test.ts frontend/src/pages/crm/Customers.tsx
git commit -m "feat(crm): pantalla Cuentas por cobrar con antigüedad, abono y recordatorio por WhatsApp"
```

---

### Task 12: Conciliación de abonos viejos, colores del portal y documentación

**Files:**
- Create: `scripts/conciliar_abonos_fifo.py`
- Modify: `frontend/src/pages/portal/Portal.tsx:96,121`
- Modify: `docs/API_REFERENCE.md` (§ CRM / Clientes, Printer), `docs/FRONTEND_VIEWS.md` (tabla y sección de `/customers`), `docs/AUDITORIA-CRM-CREDITO-2026-10-28.md` (§3), `docs/superpowers/specs/2026-10-29-crm-cobranza-design.md` (estado)
- Test: `tests/test_conciliar_abonos_fifo.py` (nuevo), `frontend/src/pages/portal/__tests__/portalSaldo.test.ts` (nuevo)

**Interfaces:**
- Consumes: `deuda_cargada_por_documento`, `DocumentoAbierto`, `es_abono` (servicio).
- Produces: `scripts.conciliar_abonos_fifo.conciliar(db, *, org_id, antes: date, dry_run: bool) -> list[dict]` (`{customer_id, cliente, folio, saldo}` por ticket marcado).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_conciliar_abonos_fifo.py`:
```python
"""Abonos libres anteriores a la auditoría (sin enlace a ticket) dejaban los
tickets PENDING aunque el saldo estuviera en cero (spec 2026-10-29 §6.2)."""
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.conciliar_abonos_fifo import conciliar  # noqa: E402

from app.models.sales import DocumentStatus, SalesDocument  # noqa: E402
from app.modules.customers.models import Customer, CustomerLedgerEntry  # noqa: E402


def _doc(db, org, branch, user, cliente, monto, folio, cuando):
    d = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, customer_id=cliente.id,
                      folio=folio, series="A", subtotal=Decimal(monto), tax_amount=Decimal("0"),
                      total_amount=Decimal(monto), status=DocumentStatus.PENDING, doc_type="ORDER")
    d.created_at = cuando
    db.add(d); db.flush()
    a = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=d.id, organization_id=org.id,
                            amount=Decimal(monto), description=f"Venta a crédito #{folio}")
    a.created_at = cuando
    db.add(a); db.commit()
    return d


def _escenario(db, org, branch_a, cajero_a):
    c = Customer(name="Legada", organization_id=org.id, current_balance=Decimal("30"))
    db.add(c); db.commit()
    viejo = _doc(db, org, branch_a, cajero_a, c, "100", 7001, datetime(2026, 9, 1, tzinfo=timezone.utc))
    nuevo = _doc(db, org, branch_a, cajero_a, c, "50", 7002, datetime(2026, 9, 15, tzinfo=timezone.utc))
    suelto = CustomerLedgerEntry(customer_id=c.id, organization_id=org.id, amount=Decimal("-120"),
                                 description="PAGO RECIBIDO: Abono")
    suelto.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.add(suelto); db.commit()
    return c, viejo, nuevo


def test_dry_run_no_cambia_nada(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    acciones = conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=True)
    assert [a["folio"] for a in acciones] == ["A-7001"]
    db.expire_all()
    assert viejo.status == DocumentStatus.PENDING and nuevo.status == DocumentStatus.PENDING


def test_marca_pagado_lo_que_los_abonos_sueltos_cubren_y_no_toca_el_saldo(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    acciones = conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=False)
    assert [(a["folio"], float(a["saldo"])) for a in acciones] == [("A-7001", 100.0)]
    db.expire_all()
    assert viejo.status == DocumentStatus.PAID
    assert nuevo.status == DocumentStatus.PENDING, "los 20 que sobran no cubren el ticket de 50"
    assert Decimal(str(c.current_balance)) == Decimal("30")
    assert conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=False) == [], "idempotente"


def test_un_abono_posterior_a_la_auditoria_no_cuenta(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    assert conciliar(db, org_id=org.id, antes=date(2026, 9, 30), dry_run=True) == []
```

`frontend/src/pages/portal/__tests__/portalSaldo.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** El portal pintaba el saldo deudor en verde y el saldo a favor en rojo: al
 *  revés que el CRM (auditoría 2026-10-28 §3.7). */
const s = readFileSync(resolve(__dirname, '../Portal.tsx'), 'utf8')

describe('Portal: color del saldo', () => {
  it('deudor en rojo, a favor en verde, con tokens', () => {
    expect(s).not.toMatch(/current_balance < 0 \? 'text-red-400' : 'text-emerald-400'/)
    expect((s.match(/current_balance > 0 \? 'text-dax-danger' : 'text-dax-success'/g) ?? []).length).toBe(2)
  })
})
```

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conciliar_abonos_fifo.py; cd frontend && npx vitest run src/pages/portal/__tests__/portalSaldo.test.ts`
Expected: ambos FAIL.

- [ ] **Step 2: El script**

Crea `scripts/conciliar_abonos_fifo.py`:

```python
"""Concilia abonos viejos sin ticket (spec 2026-10-29 §6.2).

Antes de la auditoría 2026-10-28 un abono libre bajaba el saldo del cliente
pero no se ligaba a ningún ticket: esos tickets siguen PENDING aunque ya estén
pagados. Este script suma, por cliente, los abonos sueltos anteriores a
`--antes` y recorre sus tickets abiertos del más viejo al más nuevo marcando
PAID los que esa bolsa cubre por completo. No crea asientos ni toca
`current_balance` (el saldo ya es correcto); solo corrige el estado del ticket.

Uso (dentro del contenedor de producción, donde vive la base):
    python scripts/conciliar_abonos_fifo.py --org 17 --dry-run
    python scripts/conciliar_abonos_fifo.py --org 17
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def conciliar(db, *, org_id: int, antes: date, dry_run: bool) -> list[dict]:
    """Idempotente: la bolsa de abonos sueltos se consume recorriendo TODOS los
    tickets con cargo del cliente (PENDING y PAID) del más viejo al más nuevo;
    un ticket ya PAID solo gasta bolsa, uno PENDING cubierto se marca."""
    from app.models.sales import DocumentStatus, SalesDocument
    from app.modules.customers.models import Customer, CustomerLedgerEntry
    from app.modules.customers.services import DocumentoAbierto, deuda_cargada_por_documento, es_abono

    limite = datetime.combine(antes, datetime.min.time(), tzinfo=timezone.utc)

    def _utc(t):
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t

    acciones: list[dict] = []
    for c in db.query(Customer).filter(Customer.organization_id == org_id).order_by(Customer.id).all():
        sueltos = [
            a for a in db.query(CustomerLedgerEntry).filter(
                CustomerLedgerEntry.organization_id == org_id,
                CustomerLedgerEntry.customer_id == c.id,
                CustomerLedgerEntry.sales_document_id.is_(None),
            ).all()
            if es_abono(a) and a.created_at is not None and _utc(a.created_at) < limite
        ]
        bolsa = sum((-Decimal(str(a.amount)) for a in sueltos), Decimal("0"))
        if bolsa <= 0:
            continue
        docs = (
            db.query(SalesDocument)
            .filter(SalesDocument.organization_id == org_id, SalesDocument.customer_id == c.id,
                    SalesDocument.status.in_((DocumentStatus.PENDING, DocumentStatus.PAID)))
            .order_by(SalesDocument.created_at.asc(), SalesDocument.folio.asc())
            .all()
        )
        for d in docs:
            faltante = deuda_cargada_por_documento(db, org_id=org_id, documento=d, customer_id=c.id)
            if faltante <= 0:
                continue           # pagado al cobrar o ya cubierto por abonos ligados
            if bolsa < faltante:
                break
            bolsa -= faltante
            if d.status == DocumentStatus.PENDING:
                acciones.append({"customer_id": c.id, "cliente": c.name,
                                 "folio": DocumentoAbierto(documento=d, saldo=faltante).folio, "saldo": faltante})
                if not dry_run:
                    d.status = DocumentStatus.PAID
    if not dry_run:
        db.commit()
    return acciones


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--org", type=int, required=True, help="organization_id")
    p.add_argument("--antes", default="2026-10-28", help="solo abonos anteriores a esta fecha (ISO); default: día de la auditoría")
    p.add_argument("--dry-run", action="store_true", help="solo imprime lo que haría")
    args = p.parse_args()

    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        acciones = conciliar(db, org_id=args.org, antes=date.fromisoformat(args.antes), dry_run=args.dry_run)
    finally:
        db.close()
    modo = "HARÍA" if args.dry_run else "HECHO"
    for a in acciones:
        print(f"{modo}: cliente {a['customer_id']} ({a['cliente']}): ticket {a['folio']} por {a['saldo']} → PAID")
    print(f"{len(acciones)} ticket(s) {'por marcar' if args.dry_run else 'marcados'} PAID")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Portal**

En `frontend/src/pages/portal/Portal.tsx`, las dos expresiones `… current_balance < 0 ? 'text-red-400' : 'text-emerald-400'` (líneas 96 y 121) pasan a `… current_balance > 0 ? 'text-dax-danger' : 'text-dax-success'` (deudor en rojo, a favor en verde, como el CRM).

- [ ] **Step 4: Corre**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conciliar_abonos_fifo.py; cd frontend && npx tsc --noEmit && npx vitest run src/pages/portal`
Expected: PASS.

- [ ] **Step 5: Documentación**

- `docs/API_REFERENCE.md`, sección `## CRM / Clientes · /api/customers`: añade un párrafo "Cobranza (2026-10-31, spec `docs/superpowers/specs/2026-10-29-crm-cobranza-design.md`)": `GET /cobranza` (roles de oficina; parámetros y forma de la respuesta), `POST /{id}/pay` ahora responde `AbonoResponse` (campos) y rechaza efectivo sin sucursal con 422, `POST /api/printer/print-abono/{payment_id}` (recibo; quien cobró o rol de oficina). En la sección de reportes: la regla de venta incluye la fiada (`filtro_venta_reconocida`), `kpis.credit_sales/collections` del dashboard, `fiado/cobranza` en el Inicio, `por_cobrar`; en caja: `kpis.credit_sales/customer_payments` del corte y del resumen de sucursal, y que el abono libre ya entra al esperado.
- `docs/FRONTEND_VIEWS.md`: fila `| /customers/cobranza | crm/Cobranza | Admin, Dueño, Gerente | crm |` en la tabla, y una sección `### /customers/cobranza — Cuentas por cobrar 📱` con archivo, API y qué muestra; en la de `/customers` menciona `AbonoModal` compartido y el enlace. En la de `/pos`: botón Abonar en Cliente con recibo.
- `docs/AUDITORIA-CRM-CREDITO-2026-10-28.md` §3: a cada punto añádele `→ resuelto en el spec 2026-10-29 / plan 2026-10-31` (el 1 con la decisión: cuenta el día que sale la mercancía; el 5: 422; el 6: `scripts/conciliar_abonos_fifo.py`; el 7: hecho).
- `docs/superpowers/specs/2026-10-29-crm-cobranza-design.md`: en **Estado**, `implementado en la rama feat/crm-cobranza (plan docs/superpowers/plans/2026-10-31-crm-cobranza.md)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/conciliar_abonos_fifo.py tests/test_conciliar_abonos_fifo.py frontend/src/pages/portal/Portal.tsx frontend/src/pages/portal/__tests__/portalSaldo.test.ts docs/API_REFERENCE.md docs/FRONTEND_VIEWS.md docs/AUDITORIA-CRM-CREDITO-2026-10-28.md docs/superpowers/specs/2026-10-29-crm-cobranza-design.md
git commit -m "feat(crm): conciliación FIFO de abonos viejos, colores del portal y docs de cobranza"
```

---

## Cierre de la rama

Antes de la revisión final de toda la rama (y otra vez antes de fusionar):

```bash
python3 -m pytest -q --ignore=tests/test_cash_complete.py
cd frontend && npx tsc --noEmit && npx vitest run && npm run build && cd .. && python3 scripts/presupuesto_bundle.py
```

Esperado: pytest en verde salvo los 13 fallos conocidos de `tests/test_branch_dashboard.py` y `tests/test_cash_close_guided.py` (integraciones con `requests` contra un servidor vivo, ajenos a esta rama); vitest en verde salvo el flake de 5 s de `rutasPerezosas > MobileLayout`; presupuesto dentro de 452,500 B. La fusión a `main` y el push solo con permiso explícito del usuario (CLAUDE.md §2).
