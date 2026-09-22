"""Regresiones de la auditoría funcional del backend (2026-09-22) — ventas.

Cada prueba nace de un hallazgo CONFIRMADO con sonda sobre `main`:

* C-1 el descuento por línea (`item.discount`) evadía el guard de margen.
* C-2 una cantidad negativa inflaba el stock y daba totales negativos.
* C-3 el id de una venta PENDING ajena servía para "tomarla" desde otra sucursal.
* C-4 `DELETE /api/sales/{id}` cancelaba ventas de cualquier sucursal.
* A-2 `customer_id` de otra organización quedaba pegado al documento.
* M-6 `print-view` reventaba (500) en cualquier venta con partidas.
* B-1 `POST /sales/{id}/refund` declaraba `sale_id: int` (los ids son UUID).
"""
from decimal import Decimal

from app.models.inventory import StockOnHand
from app.models.organization import Organization
from app.models.sales import DocumentStatus, DocumentType, SalesDocument, SalesLineItem
from app.models.users import Role
from app.modules.customers.models import Customer
from conftest import _auth_header, _make_product, _make_user
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _h(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


# ---------------------------------------------------------------- C-1
def test_c1_cajero_no_puede_regalar_con_descuento_de_linea(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Descuento", "SKU-DESC", 1000, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-DESC", "variant_id": v.id, "quantity": 1, "discount": 100}],
        "payments": [],
    }, headers=_h(auth_cajero_a, org))

    assert r.status_code == 403, r.text
    assert "Descuento excede" in r.text
    assert db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).count() == 0


def test_c1_descuento_de_linea_hasta_50pct_sigue_pasando(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    """El tope es 50%: justo en el límite el cobro tiene que seguir saliendo."""
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Limite", "SKU-LIM", 100, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-LIM", "variant_id": v.id, "quantity": 1, "discount": 50}],
        "payments": [{"method": "CASH", "amount": "50.00"}],
    }, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 50.0


def test_c1_admin_sigue_autorizando_descuentos_grandes(
    client, db, org, branch_a, admin_user, auth_admin
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Admin", "SKU-ADM", 100, [(branch_a.id, True)])
    admin_user.branch_id = branch_a.id
    db.commit()
    _abrir_caja(db, org, branch_a, admin_user)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-ADM", "variant_id": v.id, "quantity": 1, "discount": 90}],
        "payments": [{"method": "CASH", "amount": "10.00"}],
    }, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 10.0


# ---------------------------------------------------------------- C-2
def test_c2_cantidad_negativa_se_rechaza_y_no_toca_el_stock(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Fraude", "SKU-FRAUDE", 100, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-FRAUDE", "variant_id": v.id, "quantity": -5}],
        "payments": [],
    }, headers=_h(auth_cajero_a, org))

    assert r.status_code == 422, r.text  # lo corta el schema (gt=0)
    db.expire_all()
    stock = db.query(StockOnHand).filter(
        StockOnHand.variant_id == v.id, StockOnHand.branch_id == branch_a.id
    ).one().qty_on_hand
    assert stock == Decimal("100")
    assert db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).count() == 0


def test_c2_cantidad_cero_tambien_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Cero", "SKU-CERO", 100, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-CERO", "variant_id": v.id, "quantity": 0}],
        "payments": [],
    }, headers=_h(auth_cajero_a, org))
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- C-3
def test_c3_no_se_puede_tomar_una_venta_pending_de_otra_sucursal(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_c3", Role.CAJERO)
    auth_cajero_b = _auth_header(cajero_b)

    _, v_b = _make_product(db, org, "Producto B", "SKU-B-C3", 200, [(branch_b.id, True)])
    _, v_a = _make_product(db, org, "Producto A", "SKU-A-C3", 100, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_b, cajero_b)
    _abrir_caja(db, org, branch_a, cajero_a)

    r1 = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-B-C3", "variant_id": v_b.id, "quantity": 1}],
        "payments": [],
    }, headers=_h(auth_cajero_b, org))
    assert r1.status_code == 200, r1.text
    sale_id = r1.json()["sale_id"]

    r2 = client.post("/api/sales/", json={
        "id": sale_id,
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-A-C3", "variant_id": v_a.id, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=_h(auth_cajero_a, org))

    assert r2.status_code == 404, r2.text
    db.expire_all()
    doc = db.query(SalesDocument).filter(SalesDocument.id == sale_id).one()
    assert doc.status == DocumentStatus.PENDING
    assert doc.branch_id == branch_b.id
    # El stock de A no se movió y el de B sigue descontado por su propia venta.
    assert db.query(StockOnHand).filter(
        StockOnHand.variant_id == v_a.id, StockOnHand.branch_id == branch_a.id
    ).one().qty_on_hand == Decimal("100")
    assert db.query(StockOnHand).filter(
        StockOnHand.variant_id == v_b.id, StockOnHand.branch_id == branch_b.id
    ).one().qty_on_hand == Decimal("99")


def test_c3_el_dueno_del_turno_si_puede_actualizar_su_pending(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Propio", "SKU-PROP", 100, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r1 = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-PROP", "variant_id": v.id, "quantity": 1}],
        "payments": [],
    }, headers=_h(auth_cajero_a, org))
    assert r1.status_code == 200, r1.text
    sale_id = r1.json()["sale_id"]

    r2 = client.post("/api/sales/", json={
        "id": sale_id,
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-PROP", "variant_id": v.id, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=_h(auth_cajero_a, org))
    assert r2.status_code == 200, r2.text


# ---------------------------------------------------------------- C-4
def test_c4_cajero_no_cancela_ventas_de_otra_sucursal(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, admin_user, products_setup
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_b"]
    stock_b = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch_b.id
    ).one()
    qty_antes = stock_b.qty_on_hand

    venta = SalesDocument(
        seller_id=admin_user.id, branch_id=branch_b.id, organization_id=org.id,
        total_amount=Decimal("100"), subtotal=Decimal("100"), tax_amount=Decimal("0"),
        status=DocumentStatus.PAID, doc_type=DocumentType.INVOICE, series="A", folio=99001,
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)
    db.add(SalesLineItem(
        document_id=venta.id, variant_id=variant.id, quantity=2,
        unit_price=Decimal("50"), total_line=Decimal("100"), organization_id=org.id,
    ))
    db.commit()

    r = client.delete(f"/api/sales/{venta.id}", headers=_h(auth_cajero_a, org))
    assert r.status_code == 404, r.text

    db.refresh(venta)
    db.refresh(stock_b)
    assert venta.status == DocumentStatus.PAID
    assert stock_b.qty_on_hand == qty_antes


def test_c4_admin_sigue_pudiendo_cancelar_cualquier_sucursal(
    client, db, org, branch_b, admin_user, auth_admin, products_setup
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_b"]
    venta = SalesDocument(
        seller_id=admin_user.id, branch_id=branch_b.id, organization_id=org.id,
        total_amount=Decimal("100"), subtotal=Decimal("100"), tax_amount=Decimal("0"),
        status=DocumentStatus.PAID, doc_type=DocumentType.INVOICE, series="A", folio=99002,
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    r = client.delete(f"/api/sales/{venta.id}", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.refresh(venta)
    assert venta.status == DocumentStatus.CANCELLED


# ---------------------------------------------------------------- A-2
def test_a2_customer_de_otra_organizacion_se_rechaza(
    client, db, org, branch_a, admin_user, auth_admin, products_setup
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    admin_user.branch_id = branch_a.id
    db.commit()

    otra_org = Organization(name="Otra Org A2", status="ACTIVE")
    db.add(otra_org)
    db.flush()
    cliente_ajeno = Customer(name="Cliente De Otra Empresa", organization_id=otra_org.id)
    db.add(cliente_ajeno)
    db.commit()
    db.refresh(cliente_ajeno)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "customer_id": cliente_ajeno.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CARD", "amount": "100.00"}],
    }, headers=_h(auth_admin, org))

    assert r.status_code == 404, r.text
    assert db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).count() == 0


def test_a2_customer_propio_sigue_funcionando(
    client, db, org, branch_a, admin_user, auth_admin, products_setup
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    admin_user.branch_id = branch_a.id
    cliente = Customer(name="Cliente Propio", organization_id=org.id)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CARD", "amount": "100.00"}],
    }, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    venta = db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).one()
    assert venta.customer_id == cliente.id
    assert venta.customer_name == "Cliente Propio"


# ---------------------------------------------------------------- M-6
def test_m6_print_view_responde_200_en_venta_con_partidas(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Print", "SKU-PRINT", 50, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-PRINT", "variant_id": v.id, "quantity": 2}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    sale_id = r.json()["sale_id"]

    rv = client.get(f"/api/sales/{sale_id}/print-view", headers=_h(auth_cajero_a, org))
    assert rv.status_code == 200, rv.text[:500]
    assert "Producto Print" in rv.text


# ---------------------------------------------------------------- B-1
def test_b1_refund_acepta_el_uuid_de_la_venta(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    _habilitar_pos(db, org)
    _, v = _make_product(db, org, "Producto Refund", "SKU-REFUND", 50, [(branch_a.id, True)])
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "SKU-REFUND", "variant_id": v.id, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "50.00"}],
    }, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    sale_id = r.json()["sale_id"]

    r2 = client.post(f"/api/sales/{sale_id}/refund", headers=_h(auth_cajero_a, org))
    assert r2.status_code == 200, r2.text
