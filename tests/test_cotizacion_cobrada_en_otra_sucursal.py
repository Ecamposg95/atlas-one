"""Cotiza la sucursal A, cobra la sucursal B.

`convert-to-sale` descuenta existencias, abre el pago y toma folio en la
sucursal de quien COBRA, pero el documento conservaba la sucursal de quien
cotizó. Los subscribers de `SalesDocumentCreated` (insumos de receta,
app/subscribers/recipes.py) y `cancel_sale` leen la sucursal del DOCUMENTO: los
insumos se descontaban —y una cancelación reponía existencias— en A, aunque el
producto había salido de B.

La venta queda en la sucursal que la cobra; al cambiar de sucursal toma folio
de la nueva (el índice único es por sucursal, serie y folio).
"""
from decimal import Decimal

from app.core.security import create_access_token
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.sales import SalesDocument
from app.models.users import Role
from tests.conftest import _make_user
from tests.test_quote_convert_cash_session import (
    _abrir_caja, _crear_cotizacion, _habilitar_modulo,
)


def _cajero_b(db, org, branch_b):
    u = _make_user(db, org, branch_b, "cajero_b_conv", Role.CAJERO)
    db.commit()
    token = create_access_token(data={"sub": u.username, "role": u.role.value})
    return u, {"Authorization": f"Bearer {token}", "X-Organization-ID": str(org.id)}


def _existencias(db, variant, branch):
    return Decimal(str(db.query(StockOnHand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch.id,
    ).one().qty_on_hand))


def test_la_venta_queda_en_la_sucursal_que_descuenta_existencias(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup
):
    _habilitar_modulo(db, org, "quotes")
    _, variant = products_setup["product_both"]
    h_a = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    qid = _crear_cotizacion(client, h_a, variant.sku)
    cajero_b, h_b = _cajero_b(db, org, branch_b)
    sesion_b = _abrir_caja(db, org, branch_b, cajero_b)

    resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h_b)
    assert resp.status_code in (200, 201), resp.text

    db.expire_all()
    venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
    salida = db.query(InventoryMovement).filter(
        InventoryMovement.variant_id == variant.id,
        InventoryMovement.movement_type == MovementType.SALE_OUT,
    ).one()
    assert salida.branch_id == branch_b.id
    assert _existencias(db, variant, branch_b) == Decimal("99")
    assert _existencias(db, variant, branch_a) == Decimal("100")
    # El subscriber de recetas consume en `sale.branch_id` (lee el documento
    # del evento): debe ser la misma sucursal que descontó el producto.
    assert venta.branch_id == salida.branch_id, (
        "el documento (y con él los insumos de receta) debe quedar en la "
        "sucursal que descontó las existencias"
    )
    assert venta.cash_session_id == sesion_b.id


def test_un_pedido_cobrado_en_otra_sucursal_toma_folio_de_esa_sucursal(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup
):
    """P-1 de A no puede aterrizar sobre el P-1 que B ya emitió."""
    _habilitar_modulo(db, org, "quotes")
    _, variant = products_setup["product_both"]
    h_a = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    cajero_b, h_b = _cajero_b(db, org, branch_b)
    _abrir_caja(db, org, branch_b, cajero_b)

    def _pedido(h):
        r = client.post("/api/quotes/", json={
            "doc_type": "ORDER", "items": [{"sku": variant.sku, "quantity": 1}],
            "payments": []}, headers=h)
        assert r.status_code in (200, 201), r.text
        return r.json()["quote_id"]

    pedido_b = _pedido(h_b)      # P-1 de la sucursal B
    pedido_a = _pedido(h_a)      # P-1 de la sucursal A

    resp = client.post(f"/api/quotes/{pedido_a}/convert-to-sale?payment_method=CASH", headers=h_b)
    assert resp.status_code in (200, 201), resp.text

    db.expire_all()
    de_b = db.query(SalesDocument).filter(SalesDocument.id == pedido_b).one()
    cobrado = db.query(SalesDocument).filter(SalesDocument.id == pedido_a).one()
    assert cobrado.branch_id == branch_b.id
    assert cobrado.series == de_b.series == "P"
    assert cobrado.folio == de_b.folio + 1


def test_cobrar_en_la_misma_sucursal_no_cambia_el_folio_del_pedido(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _habilitar_modulo(db, org, "quotes")
    _, variant = products_setup["product_a"]
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/quotes/", json={
        "doc_type": "ORDER", "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": []}, headers=h)
    qid = r.json()["quote_id"]
    folio = db.query(SalesDocument).filter(SalesDocument.id == qid).one().folio

    resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
    assert resp.status_code in (200, 201), resp.text

    db.expire_all()
    venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
    assert (venta.branch_id, venta.series, venta.folio) == (branch_a.id, "P", folio)
