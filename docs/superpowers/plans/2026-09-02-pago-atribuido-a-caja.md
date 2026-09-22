# Atribuir el efectivo a la caja donde se recibió — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el efectivo de un pago cuente en el corte de la caja que lo recibió, no en el de la caja donde nació la venta.

**Architecture:** Hoy el efectivo se atribuye por el **documento** (`SalesDocument.cash_session_id`). Se agrega `Payment.cash_session_id` y la lectura pasa a preferirlo, cayendo al filtro por documento cuando es nulo. Eso conserva vivo el camino heredado y hace que la migración no sea un salto al vacío.

**Tech Stack:** FastAPI · SQLAlchemy · pytest · PostgreSQL 18 · React 18 + vitest

**Spec:** `docs/audits/2026-09-01-cuadratura-corte-caja.md` — hallazgo H-2 ("los abonos de clientes en efectivo se acreditan a la sesión equivocada") y H-3 ("completar una venta PENDING en un turno posterior manda el efectivo al turno anterior"), más el hallazgo 4.1 de la revisión final de la rama anterior.

## Global Constraints

- **La fórmula del esperado no cambia de forma.** Sigue siendo
  `apertura + efectivo_neto + entradas − salidas − reembolsos`. Lo que cambia es
  **de dónde sale `efectivo_neto`**, no la aritmética.
- **Retrocompatible por diseño.** Un `Payment` con `cash_session_id` nulo debe
  seguir contando exactamente como hoy, vía el filtro por documento. Ninguna
  tarea puede romper eso.
- Base **MULTICLIENTE** (organizaciones 14 Novedades Kaory y 15 Novedades
  Ginebra). Toda consulta nueva filtra por `organization_id`.
- Producción viva en dos entornos. Suite completa verde antes de cada commit:
  hoy **348 pruebas backend, 2 saltadas, 3 xfailed** y **13 de frontend**.
- Rama: `feat/pago-atribuido-a-caja`.
- **No tocar** las guardas ya instaladas y revisadas: `_validar_salida`,
  `_lock_cash_session_query`, la ventana de caja limpia, `SALES_WITHOUT_SESSION`,
  ni el criterio de "cobrar en efectivo exige caja abierta".
- **Los 5 pagos huérfanos de producción se quedan en nulo.** El respaldo por
  documento los trata igual que hoy; inventarles una caja sería peor.

## Estado de partida en producción

| | |
|---|---|
| Pagos totales | 12,635 |
| Con venta que tiene caja | 12,630 → se rellenan |
| Con venta sin caja | 5 → quedan en nulo |
| Consumidores de `session_sales_filter` | 9, incluido `branch_dashboard.py` con su **propia copia** de la lógica |

---

### Task 1: La columna y su relleno

**Files:**
- Modify: `app/models/sales.py` (clase `Payment`)
- Create: `scripts/migrate_add_payment_cash_session.py`
- Test: `tests/test_payment_cash_session_column.py` (crear)

**Interfaces:**
- Produces: `Payment.cash_session_id` (FK a `cash_sessions.id`, nullable, indexado), poblada hacia atrás desde `SalesDocument.cash_session_id`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""La columna que atribuye un pago a la caja que lo recibio.

Hasta ahora el efectivo se atribuia por el DOCUMENTO de venta. Eso hace que
liquidar una venta a credito en otro turno mueva el efectivo de ayer al corte
de hoy, y que un abono de cliente cuente en la caja de la venta original en vez
de la que recibio el dinero.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument


def test_el_pago_puede_apuntar_a_una_sesion(db, org, branch_a, cajero_a):
    sesion = CashSession(user_id=cajero_a.id, branch_id=branch_a.id,
                         organization_id=org.id, opening_balance=Decimal("0"), status="OPEN")
    db.add(sesion); db.commit(); db.refresh(sesion)

    venta = SalesDocument(
        organization_id=org.id, branch_id=branch_a.id, seller_id=cajero_a.id,
        folio=1, series="A", subtotal=Decimal("50"), tax_amount=Decimal("0"),
        total_amount=Decimal("50"), status=DocumentStatus.PAID, doc_type="ORDER",
    )
    db.add(venta); db.flush()
    pago = Payment(sales_document_id=venta.id, amount=Decimal("50"),
                   method=PaymentMethod.CASH, organization_id=org.id,
                   cash_session_id=sesion.id)
    db.add(pago); db.commit(); db.refresh(pago)

    assert pago.cash_session_id == sesion.id


def test_la_columna_admite_nulo(db, org, branch_a, cajero_a):
    """Los pagos historicos y los de ventas sin caja quedan en nulo a proposito."""
    venta = SalesDocument(
        organization_id=org.id, branch_id=branch_a.id, seller_id=cajero_a.id,
        folio=2, series="A", subtotal=Decimal("10"), tax_amount=Decimal("0"),
        total_amount=Decimal("10"), status=DocumentStatus.PAID, doc_type="ORDER",
    )
    db.add(venta); db.flush()
    pago = Payment(sales_document_id=venta.id, amount=Decimal("10"),
                   method=PaymentMethod.CASH, organization_id=org.id)
    db.add(pago); db.commit(); db.refresh(pago)

    assert pago.cash_session_id is None
```

- [ ] **Step 2: Correrla y confirmar que falla**

```bash
python3 -m pytest tests/test_payment_cash_session_column.py -v
```

Esperado: FALLA con `TypeError: 'cash_session_id' is an invalid keyword argument for Payment`.

- [ ] **Step 3: Agregar la columna**

En `app/models/sales.py`, dentro de `Payment`:

```python
    # Caja que RECIBIO este dinero. Antes el efectivo se atribuia por el
    # documento de venta, lo que mandaba el abono de un credito liquidado hoy
    # al corte del dia en que se abrio la venta. Nullable: los pagos
    # historicos y los de ventas sin caja se quedan sin atribucion explicita y
    # caen al respaldo por documento.
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=True, index=True)
```

- [ ] **Step 4: Escribir la migración con relleno**

Crear `scripts/migrate_add_payment_cash_session.py`, siguiendo el patrón de
`scripts/migrate_add_cash_movement_author.py` que ya existe en el repositorio
(condiciona el `ALTER` por dialecto, envuelve la llave foránea en
`EXCEPTION WHEN duplicate_object`, y usa `CREATE INDEX IF NOT EXISTS`).

El relleno, después de crear la columna:

```sql
UPDATE payments p
SET cash_session_id = s.cash_session_id
FROM sales_documents s
WHERE s.id = p.sales_document_id
  AND s.cash_session_id IS NOT NULL
  AND p.cash_session_id IS NULL
```

Es correcto históricamente: hasta este cambio, el pago se creaba en la misma
transacción que la venta, así que la caja del documento **era** la caja que
recibió el dinero. El script debe imprimir cuántas filas rellenó y cuántas
quedaron en nulo.

- [ ] **Step 5: Correr las pruebas y la migración contra la base de pruebas**

```bash
python3 -m pytest tests/test_payment_cash_session_column.py -v
python3 -m pytest -q -p no:warnings
```

Esperado: las 2 nuevas en PASS y la suite completa verde.

- [ ] **Step 6: Commit**

```bash
git add app/models/sales.py scripts/migrate_add_payment_cash_session.py tests/test_payment_cash_session_column.py
git commit -m "feat(caja): columna cash_session_id en payments, con relleno historico"
```

---

### Task 2: La lectura prefiere la caja del pago

**Files:**
- Modify: `app/services/cash_reconciliation.py` (`compute_expected_cash`, ~línea 224, y `_compute_change_given`)
- Test: `tests/test_cash_atribucion_por_pago.py` (crear)

**Interfaces:**
- Consumes: `Payment.cash_session_id` de la Task 1.
- Produces: `compute_expected_cash` suma un pago cuando su `cash_session_id` es el de la sesión, **o** cuando es nulo y el documento cae en `session_sales_filter`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""El efectivo cuenta en la caja que lo recibio, no en la de la venta."""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument
from app.services.cash_reconciliation import compute_expected_cash


def _sesion(db, org, branch, user, fondo="0"):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal(fondo), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _venta(db, org, branch, user, folio, total, sesion_doc=None):
    v = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=DocumentStatus.PAID, doc_type="ORDER",
        cash_session_id=sesion_doc.id if sesion_doc else None,
    )
    db.add(v); db.flush()
    return v


class TestAtribucionPorPago:
    def test_el_pago_cuenta_en_su_propia_caja(self, db, org, branch_a, cajero_a):
        """La venta nacio en la sesion 1; el dinero entro en la sesion 2."""
        s1 = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 1, "100", sesion_doc=s1)
        s1.status = "CLOSED"; db.commit()
        s2 = _sesion(db, org, branch_a, cajero_a)

        db.add(Payment(sales_document_id=venta.id, amount=Decimal("100"),
                       method=PaymentMethod.CASH, organization_id=org.id,
                       cash_session_id=s2.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s2).expected)) == Decimal("100.00"), (
            "el dinero entro en la sesion 2 y ahi debe contar"
        )
        assert Decimal(str(compute_expected_cash(db, s1).expected)) == Decimal("0.00"), (
            "la sesion 1 no recibio ese dinero y no debe verse alterada"
        )

    def test_un_pago_sin_atribucion_sigue_contando_como_antes(self, db, org, branch_a, cajero_a):
        """Retrocompatibilidad: el respaldo por documento no se rompe."""
        s = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 2, "40", sesion_doc=s)
        db.add(Payment(sales_document_id=venta.id, amount=Decimal("40"),
                       method=PaymentMethod.CASH, organization_id=org.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s).expected)) == Decimal("40.00")

    def test_no_se_cuenta_dos_veces(self, db, org, branch_a, cajero_a):
        """Un pago atribuido a la MISMA sesion del documento cuenta una sola vez."""
        s = _sesion(db, org, branch_a, cajero_a)
        venta = _venta(db, org, branch_a, cajero_a, 3, "60", sesion_doc=s)
        db.add(Payment(sales_document_id=venta.id, amount=Decimal("60"),
                       method=PaymentMethod.CASH, organization_id=org.id,
                       cash_session_id=s.id))
        db.commit()

        assert Decimal(str(compute_expected_cash(db, s).expected)) == Decimal("60.00")
```

- [ ] **Step 2: Correrla y confirmar que falla**

```bash
python3 -m pytest tests/test_cash_atribucion_por_pago.py -v
```

Esperado: FALLA `test_el_pago_cuenta_en_su_propia_caja` — hoy el dinero se
atribuye al documento, así que la sesión 2 daría 0 y la 1 daría 100.

- [ ] **Step 3: Cambiar la consulta de efectivo**

En `compute_expected_cash`, sustituir el filtro de la suma de pagos por uno que
prefiera la atribución del pago:

```python
    # Un pago cuenta en esta sesion si (a) esta atribuido explicitamente a ella,
    # o (b) no tiene atribucion y su documento cae en el filtro heredado. La
    # rama (b) mantiene vivo el camino de los pagos anteriores a esta columna.
    pago_de_esta_sesion = or_(
        Payment.cash_session_id == session.id,
        and_(Payment.cash_session_id.is_(None), session_sales_filter(session)),
    )
    cash_payments = (
        db.query(func.sum(Payment.amount))
        .join(SalesDocument)
        .filter(
            Payment.method == PaymentMethod.CASH,
            pago_de_esta_sesion,
            SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
        )
        .scalar()
        or Decimal(0)
    )
```

Aplicar el **mismo criterio** en `_compute_change_given`: el cambio entregado
pertenece a la caja que entregó los billetes, no a la del documento. Lee esa
función completa antes de tocarla — itera ventas y lee `change_given`.

- [ ] **Step 4: Correr las pruebas**

```bash
python3 -m pytest tests/test_cash_atribucion_por_pago.py tests/test_cash_math.py tests/test_cash_credito_y_abonos.py -v
```

Esperado: las 3 nuevas en PASS y las de caja existentes sin romperse. **Si alguna
de `test_cash_math.py` falla, no bajes su exigencia**: significa que el criterio
nuevo cambió un caso que esa prueba fija, y hay que entender cuál antes de tocar
nada.

- [ ] **Step 5: Commit**

```bash
git add app/services/cash_reconciliation.py tests/test_cash_atribucion_por_pago.py
git commit -m "feat(caja): el esperado prefiere la caja del pago sobre la del documento"
```

---

### Task 3: Escribir la atribución en el checkout

**Files:**
- Modify: `app/routers/sales.py` (creación de `Payment`, ~línea 839; y la rama `existing_sale`)
- Test: `tests/test_checkout_atribuye_caja.py` (crear)

**Interfaces:**
- Consumes: la columna de la Task 1 y la lectura de la Task 2.
- Produces: todo `Payment` creado en el checkout lleva la sesión abierta del cobrador.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""El pago nace atribuido a la caja de quien cobra."""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import Payment


def _preparar(db, org, branch, user):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos").first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_el_pago_del_checkout_lleva_la_caja(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    sesion = _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]

    resp = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert resp.status_code in (200, 201), resp.text

    pago = db.query(Payment).filter(Payment.organization_id == org.id).one()
    assert pago.cash_session_id == sesion.id, (
        "el pago debe quedar atribuido a la caja abierta del cajero que cobro"
    )
```

- [ ] **Step 2: Correrla y confirmar que falla**

```bash
python3 -m pytest tests/test_checkout_atribuye_caja.py -v
```

Esperado: FALLA con `assert None == <id>`.

- [ ] **Step 3: Poblar la columna al crear el pago**

En `app/routers/sales.py`, en el `Payment(...)` del checkout (~línea 839), agregar
`cash_session_id=cash_session_id_value`. Esa variable ya existe en la función y
es la que se asigna al documento; **léela antes de usarla** para confirmar que
sostiene la sesión abierta del cobrador y no otra cosa.

En la rama `existing_sale`, los pagos se borran y se recrean: los nuevos deben
llevar la **sesión de hoy**, que es la que ya se resuelve ahí para reasignar el
documento.

- [ ] **Step 4: Correr las pruebas**

```bash
python3 -m pytest tests/test_checkout_atribuye_caja.py tests/test_cash_math.py tests/test_sales_idempotency.py -v
```

Esperado: todo en PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/sales.py tests/test_checkout_atribuye_caja.py
git commit -m "feat(caja): el checkout atribuye cada pago a la caja de quien cobra"
```

---

### Task 4: El abono de cliente cuenta donde se recibe

**Files:**
- Modify: `app/modules/customers/router.py` (~línea 474, creación de `SalesPayment`)
- Test: `tests/test_abono_cliente_atribuye_caja.py` (crear)

**Interfaces:**
- Produces: un abono en efectivo queda atribuido a la sesión abierta de quien lo cobra, no a la de la venta original.

- [ ] **Step 1: Escribir la prueba que falla**

```python
"""Un abono cobrado hoy pertenece al corte de hoy.

El endpoint colgaba el pago del documento original, asi que el esperado lo
acreditaba a la sesion de la VENTA — posiblemente cerrada hace semanas — y el
corte del dia que recibio el dinero no lo veia.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.sales import DocumentStatus, Payment, SalesDocument
from app.services.cash_reconciliation import compute_expected_cash


def test_el_abono_cuenta_en_la_caja_de_hoy(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    # Venta a credito de un turno anterior, ya cerrado.
    s_vieja = CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                          opening_balance=Decimal("0"), status="CLOSED")
    db.add(s_vieja); db.flush()
    venta = SalesDocument(
        organization_id=org.id, branch_id=branch_a.id, seller_id=cajero_a.id,
        folio=1, series="A", subtotal=Decimal("500"), tax_amount=Decimal("0"),
        total_amount=Decimal("500"), status=DocumentStatus.PENDING, doc_type="ORDER",
        cash_session_id=s_vieja.id,
    )
    db.add(venta); db.commit(); db.refresh(venta)

    # Turno de hoy, abierto.
    s_hoy = CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                        opening_balance=Decimal("0"), status="OPEN")
    db.add(s_hoy); db.commit(); db.refresh(s_hoy)

    # El cliente abona 200 en efectivo, hoy.
    from app.models.sales import PaymentMethod
    db.add(Payment(sales_document_id=venta.id, amount=Decimal("200"),
                   method=PaymentMethod.CASH, organization_id=org.id,
                   cash_session_id=s_hoy.id))
    db.commit()

    assert Decimal(str(compute_expected_cash(db, s_hoy).expected)) == Decimal("200.00"), (
        "los 200 pesos estan en el cajon de hoy"
    )
```

- [ ] **Step 2: Correrla**

```bash
python3 -m pytest tests/test_abono_cliente_atribuye_caja.py -v
```

Esta prueba **puede pasar ya** con las tareas 1 y 2 hechas, porque construye el
pago a mano. Si pasa, **no la borres**: fija el comportamiento esperado. Lo que
falta es que el ENDPOINT lo haga solo, y eso es el paso 3.

- [ ] **Step 3: Poblar la sesión en el endpoint de abonos**

En `app/modules/customers/router.py`, antes de crear el `SalesPayment`, resolver
la sesión abierta del cobrador con el mismo criterio que usa el checkout
(`user_id` + `branch_id` + `status == OPEN`) y asignarla. Si no hay sesión
abierta y el método es efectivo, **el pago sigue registrándose** — este endpoint
no está en el alcance del guard de "efectivo exige caja"; lo que no puede es
acreditarse a una caja ajena.

Agregar una segunda prueba que ejercite el endpoint real y verifique la
atribución. Lee su contrato en el propio archivo antes de escribirla.

- [ ] **Step 4: Correr las pruebas**

```bash
python3 -m pytest tests/test_abono_cliente_atribuye_caja.py tests/test_customers_statement_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/customers/router.py tests/test_abono_cliente_atribuye_caja.py
git commit -m "feat(caja): el abono de cliente cuenta en la caja que lo recibe"
```

---

### Task 5: Reactivar el crédito

Con la atribución en su lugar, `PENDING` puede volver a contar como efectivo sin
corromper cortes cerrados. Esta tarea deshace la reversión que se hizo por
seguridad y reactiva las pruebas que quedaron marcadas.

**Files:**
- Modify: `app/services/cash_reconciliation.py` (`CASH_INCLUDED_STATUSES`)
- Modify: `tests/test_cash_credito_y_abonos.py` (quitar los 3 `xfail`)

**Interfaces:**
- Consumes: las tareas 1 a 4 completas.

- [ ] **Step 1: Quitar los `xfail` y confirmar que las pruebas fallan o pasan**

En `tests/test_cash_credito_y_abonos.py` hay 3 pruebas marcadas
`@pytest.mark.xfail(strict=True)` con motivo escrito. Quítales la marca y
córrelas:

```bash
python3 -m pytest tests/test_cash_credito_y_abonos.py -v
```

Anota cuáles pasan ya y cuáles no. **No cambies sus aserciones.**

- [ ] **Step 2: Devolver `PENDING` a la tupla**

```python
CASH_INCLUDED_STATUSES = (
    DocumentStatus.PAID,
    DocumentStatus.REFUNDED_PARTIAL,
    DocumentStatus.REFUNDED_TOTAL,
    # Reactivado: con `Payment.cash_session_id`, el abono de una venta a credito
    # cuenta en la caja que lo recibio, asi que liquidar en otro turno ya no
    # mueve el efectivo de ayer ni reescribe un corte cerrado.
    DocumentStatus.PENDING,
)
```

`SALES_REPORT_STATUSES` **no cambia**: una venta a crédito sigue sin ser ingreso
reconocido, y sacarla de los reportes de venta fue una corrección aparte que
sigue vigente.

- [ ] **Step 3: Correr todo**

```bash
python3 -m pytest tests/test_cash_credito_y_abonos.py tests/test_cash_math.py tests/test_cash_atribucion_por_pago.py -v
python3 -m pytest -q -p no:warnings
```

Esperado: las 3 pruebas antes marcadas ahora pasan de verdad, y la suite completa
verde **sin ningún `xfail`**.

- [ ] **Step 4: Verificar a mano el escenario que motivó todo esto**

Escribe una prueba que reproduzca el caso completo: venta a crédito con abono en
el turno 1, turno 1 cerrado, liquidación en el turno 2. Debe verificar que el
esperado del turno 1 **no cambia** después de la liquidación, y que el turno 2
solo recibe el dinero que entró en él.

- [ ] **Step 5: Commit**

```bash
git add app/services/cash_reconciliation.py tests/test_cash_credito_y_abonos.py
git commit -m "feat(caja): reactivar credito a clientes sobre la atribucion por pago"
```

---

## Orden y despliegue

Las tareas van en orden: 1 → 2 → 3 → 4 → 5. La 5 **no puede** ir antes que la 4.

**La migración corre antes que el código**, en los dos entornos, igual que la
anterior:

```bash
ssh ionos 'docker exec -e PYTHONPATH=/app atlas-one-prod python /tmp/migrate_add_payment_cash_session.py'
ssh ionos 'docker exec -e PYTHONPATH=/app -e DATABASE_URL="$(cat /root/.railway_url)" atlas-one-prod python /tmp/migrate_add_payment_cash_session.py'
```

## Qué NO hace este plan

- **No toca `branch_dashboard.py`**, que tiene su propia copia de la lógica de
  atribución. Es deuda conocida y merece su propia tarea: unificarlo con
  `session_sales_filter` es un trabajo de refactor, no de este cambio.
- **No rellena los 5 pagos huérfanos de producción.** Quedan en nulo y el
  respaldo por documento los trata igual que hoy.
- **No cambia la fórmula del esperado**, solo de dónde sale el efectivo neto.
