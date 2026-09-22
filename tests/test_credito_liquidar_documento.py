"""Liquidar un documento no puede regalarle saldo a favor al cliente.

Ronda de correcciones 2 (MAYOR): el ajuste de credito de `create_sale` movia
el saldo por `remaining_debt - deuda_previa`, y `deuda_previa` se derivaba de
`total_amount - pagos_previos` asumiendo que TODO documento PENDING ya le
habia cargado esa deuda al cliente. Es falso: `app/routers/quotes.py` crea
pedidos PENDING con `customer_id` sin tocar `current_balance` ni el ledger.
Cobrar uno de esos pedidos calculaba `ajuste = 0 - deuda_previa` y le dejaba
al cliente un saldo a favor por el importe completo del pedido, mas un asiento
"Liquidacion de venta a credito" por una deuda que nunca existio.

La deuda que un documento le cargo al cliente solo la sabe el ledger, asi que
ahi se lee (y por eso el asiento de una venta nueva ya nace con
`sales_document_id`). Estas pruebas cubren los dos lados: el pedido que nunca
cargo nada no puede abonar nada, y la venta a credito que si cargo tiene que
seguir liberando el saldo al liquidarse.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, SalesDocument
from app.modules.customers.models import Customer, CustomerLedgerEntry


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(
                organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _abrir_caja(db, org, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _cliente_a_credito(db, org):
    c = Customer(name="Cliente a credito", organization_id=org.id,
                 has_credit=True, credit_limit=Decimal("5000"),
                 current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _asientos(db, cliente):
    return db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == cliente.id).all()


def test_liquidar_un_pedido_de_cotizaciones_no_le_regala_saldo_al_cliente(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """El pedido nace PENDING sin cargar nada al saldo: cobrarlo completo deja
    la cuenta del cliente donde estaba, no en menos cien."""
    _habilitar(db, org, "pos", "quotes")
    _, variant = products_setup["product_a"]
    cliente = _cliente_a_credito(db, org)
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

    pedido = client.post("/api/quotes/", json={
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [],
    }, headers=h)
    assert pedido.status_code == 200, pedido.text
    pedido_id = pedido.json()["quote_id"]

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    assert _asientos(db, cliente) == [], (
        "el pedido no toca el saldo: si algun dia lo hiciera, esta prueba deja "
        "de medir lo que cree medir"
    )

    _abrir_caja(db, org, branch_a, cajero_a)
    cobro = client.post("/api/sales/", json={
        "id": pedido_id,
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=h)
    assert cobro.status_code in (200, 201), cobro.text

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00"), (
        "el cliente pago en efectivo un pedido que nunca le cargo deuda: la "
        "tienda no puede quedar debiendole el importe del pedido"
    )
    assert _asientos(db, cliente) == [], (
        "no hay deuda que liquidar, asi que no puede haber asiento de "
        "liquidacion en el estado de cuenta"
    )
    assert db.query(SalesDocument).filter(
        SalesDocument.id == pedido_id).one().status == DocumentStatus.PAID


def test_liquidar_una_venta_a_credito_si_libera_el_saldo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """La contraparte (no reabrir MAYOR-1): la venta que SI cargo deuda tiene
    que abonarla al liquidarse. Como el cargo lo hace el checkout, la unica
    forma de saber cuanto cargo ESE documento es que su asiento lo diga."""
    _habilitar(db, org, "pos")
    _, variant = products_setup["product_a"]
    cliente = _cliente_a_credito(db, org)
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

    _abrir_caja(db, org, branch_a, cajero_a)
    # Venta a credito: se lleva la mercancia sin pagar nada (PENDING por 100).
    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [],
    }, headers=h)
    assert venta.status_code in (200, 201), venta.text
    venta_id = venta.json()["sale_id"]

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("100.00")

    # Liquidacion sobre el mismo documento, en efectivo.
    liquidacion = client.post("/api/sales/", json={
        "id": venta_id,
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=h)
    assert liquidacion.status_code in (200, 201), liquidacion.text

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00"), (
        "el cliente pago la venta de 100 que tenia cargada: la deuda que ese "
        "documento le cargo tiene que quedar liquidada"
    )
    assert db.query(SalesDocument).filter(
        SalesDocument.id == venta_id).one().status == DocumentStatus.PAID


def test_pedido_pasado_a_credito_por_caja_carga_y_luego_libera_su_deuda(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """El pedido que se factura a credito por caja: ese cobro (sin pago) es el
    que le carga la deuda al cliente, y la liquidacion posterior la libera.
    Ni mas ni menos que lo que ese documento cargo."""
    _habilitar(db, org, "pos", "quotes")
    _, variant = products_setup["product_a"]
    cliente = _cliente_a_credito(db, org)
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

    pedido_id = client.post("/api/quotes/", json={
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [],
    }, headers=h).json()["quote_id"]

    _abrir_caja(db, org, branch_a, cajero_a)
    a_credito = client.post("/api/sales/", json={
        "id": pedido_id,
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [],
    }, headers=h)
    assert a_credito.status_code in (200, 201), a_credito.text

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("100.00"), (
        "el pedido facturado a credito por caja si carga la deuda"
    )

    resto = client.post("/api/sales/", json={
        "id": pedido_id,
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=h)
    assert resto.status_code in (200, 201), resto.text

    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
