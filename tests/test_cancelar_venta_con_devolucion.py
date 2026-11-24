"""Cancelar una venta que ya tiene una devolución aprobada duplicaba existencias.

`approve_return` reingresa las piezas devueltas, saca el dinero y netea
`total_amount`. `cancel_sale` no miraba nada de eso: reponía TODAS las líneas
de la venta otra vez. Vender 2, devolver 1 y cancelar dejaba 101 piezas donde
había 100; además la venta salía de la venta bruta (CANCELLED) mientras su
devolución seguía restando, y la salida de efectivo quedaba sin cobro.

Regla: cancelación y devolución son vías excluyentes (espejo del R-0 de
`approve_return`). Con devolución aprobada, la cancelación responde 409 con un
`detail` que manda a Devoluciones, y no toca existencias, saldo ni estado.
"""
from decimal import Decimal

from app.crud import returns as crud_returns
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.returns import SaleReturn
from app.models.sales import (
    DocumentStatus, DocumentType, PaymentMethod, SalesDocument, SalesLineItem,
)
from app.schemas.returns import SaleReturnCreate


def _habilitar_pos(db, org):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta"))
        db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos",
    ).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.commit()


def _existencias(db, variant, branch):
    db.expire_all()
    return Decimal(str(db.query(StockOnHand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch.id,
    ).one().qty_on_hand))


def _venta_de_dos(db, org, branch, user, variant):
    """Venta ya cobrada de 2 piezas a $50; las existencias quedan en 98."""
    v = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=7101, series="A", subtotal=Decimal("100"), tax_amount=Decimal("0"),
        total_amount=Decimal("100"), status=DocumentStatus.PAID,
        doc_type=DocumentType.INVOICE,
    )
    db.add(v); db.flush()
    db.add(SalesLineItem(
        document_id=v.id, variant_id=variant.id, description="Producto",
        quantity=2, unit_price=Decimal("50"), total_line=Decimal("100"),
        organization_id=org.id,
    ))
    stock = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch.id).one()
    stock.qty_on_hand = Decimal("98")
    db.commit(); db.refresh(v)
    return v


def _solicitar(db, org, branch, user, venta, variant, qty):
    return crud_returns.create_return(
        db=db,
        return_in=SaleReturnCreate(
            sale_id=venta.id, reason="prueba", total_refunded=Decimal("50") * qty,
            refund_method=PaymentMethod.CARD,
            items=[{"variant_id": variant.id, "quantity": qty,
                    "refund_amount": Decimal("50") * qty}],
        ),
        user_id=user.id, branch_id=branch.id, organization_id=org.id,
    )


def _devolver(db, org, branch, user, venta, variant, qty):
    d = _solicitar(db, org, branch, user, venta, variant, qty)
    return crud_returns.approve_return(db, d.id, supervisor_id=user.id, organization_id=org.id)


def test_cancelar_tras_devolucion_parcial_no_repone_dos_veces(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup,
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    venta = _venta_de_dos(db, org, branch_a, cajero_a, variant)
    _devolver(db, org, branch_a, cajero_a, venta, variant, 1)
    assert _existencias(db, variant, branch_a) == Decimal("99")

    r = client.delete(f"/api/sales/{venta.id}", headers=auth_cajero_a)

    assert r.status_code == 409, r.text
    assert "Devoluciones" in r.json()["detail"]
    assert _existencias(db, variant, branch_a) == Decimal("99"), (
        "la cancelación no debe volver a reponer la pieza que ya reingresó la devolución"
    )
    venta = db.query(SalesDocument).filter(SalesDocument.id == venta.id).one()
    assert venta.status == DocumentStatus.REFUNDED_PARTIAL
    assert Decimal(str(venta.total_amount)) == Decimal("50")


def test_cancelar_tras_devolucion_total_no_repone_dos_veces(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup,
):
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    venta = _venta_de_dos(db, org, branch_a, cajero_a, variant)
    _devolver(db, org, branch_a, cajero_a, venta, variant, 2)
    assert _existencias(db, variant, branch_a) == Decimal("100")

    r = client.delete(f"/api/sales/{venta.id}", headers=auth_cajero_a)

    assert r.status_code == 409, r.text
    assert _existencias(db, variant, branch_a) == Decimal("100")
    venta = db.query(SalesDocument).filter(SalesDocument.id == venta.id).one()
    assert venta.status == DocumentStatus.REFUNDED_TOTAL


def test_una_devolucion_solo_pendiente_no_impide_cancelar(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup,
):
    """Una devolución sin aprobar no movió nada: la venta se cancela como
    siempre (y el R-0 de `approve_return` impide aprobarla después)."""
    _habilitar_pos(db, org)
    _, variant = products_setup["product_a"]
    venta = _venta_de_dos(db, org, branch_a, cajero_a, variant)
    _solicitar(db, org, branch_a, cajero_a, venta, variant, 1)

    r = client.delete(f"/api/sales/{venta.id}", headers=auth_cajero_a)

    assert r.status_code == 200, r.text
    assert _existencias(db, variant, branch_a) == Decimal("100")
    assert db.query(SaleReturn).filter(SaleReturn.sale_id == venta.id).one().status == "PENDING"
