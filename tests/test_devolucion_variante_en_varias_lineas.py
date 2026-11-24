"""La misma variante en varias líneas de la venta.

`create_return` buscaba la línea de la variante con `.first()`: de una venta
con 2 + 3 piezas del mismo producto solo dejaba devolver 2 (la primera línea) y
prorrateaba el reembolso solo con el importe de esa línea. `approve_return`
comparaba lo devuelto contra cada línea por separado: devolver 1 de 1 + 1
marcaba la venta como devuelta por completo.

Lo vendido de una variante es la suma de sus líneas, menos lo ya devuelto.
"""
from decimal import Decimal

import pytest

from app.crud import returns as crud_returns
from app.models.sales import DocumentStatus, PaymentMethod, SalesDocument, SalesLineItem
from app.schemas.returns import SaleReturnCreate


def _venta(db, org, branch, user, variant, lineas):
    """`lineas`: lista de (cantidad, total cobrado de la línea)."""
    total = sum((t for _, t in lineas), Decimal("0"))
    s = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=7201, series="A", subtotal=total, tax_amount=Decimal("0"),
        total_amount=total, status=DocumentStatus.PAID, doc_type="INVOICE",
    )
    db.add(s); db.flush()
    for qty, total_linea in lineas:
        db.add(SalesLineItem(
            document_id=s.id, variant_id=variant.id, description="Producto",
            quantity=qty, unit_price=Decimal("50"), total_line=total_linea,
            organization_id=org.id,
        ))
    db.commit(); db.refresh(s)
    return s


def _solicitar(db, org, branch, user, sale, variant, qty):
    return crud_returns.create_return(
        db=db,
        return_in=SaleReturnCreate(
            sale_id=sale.id, reason="prueba", total_refunded=Decimal("0"),
            refund_method=PaymentMethod.CARD,
            items=[{"variant_id": variant.id, "quantity": qty, "refund_amount": Decimal("0")}],
        ),
        user_id=user.id, branch_id=branch.id, organization_id=org.id,
    )


def _aprobar(db, org, user, devolucion):
    return crud_returns.approve_return(
        db, devolucion.id, supervisor_id=user.id, organization_id=org.id)


@pytest.fixture()
def variante(products_setup):
    return products_setup["product_a"][1]


def test_se_puede_devolver_la_suma_de_las_lineas(db, org, branch_a, cajero_a, variante):
    # 2 piezas a precio lleno ($100) + 3 con descuento ($90): 5 piezas, $190.
    venta = _venta(db, org, branch_a, cajero_a, variante,
                   [(2, Decimal("100")), (3, Decimal("90"))])

    d = _solicitar(db, org, branch_a, cajero_a, venta, variante, 5)

    assert Decimal(str(d.total_refunded)) == Decimal("190.00"), (
        "devolver todas las piezas reembolsa lo cobrado por todas sus líneas"
    )
    _aprobar(db, org, cajero_a, d)
    db.refresh(venta)
    assert venta.status == DocumentStatus.REFUNDED_TOTAL
    assert Decimal(str(venta.total_amount)) == Decimal("0")


def test_no_se_puede_devolver_mas_que_la_suma(db, org, branch_a, cajero_a, variante):
    venta = _venta(db, org, branch_a, cajero_a, variante,
                   [(2, Decimal("100")), (3, Decimal("150"))])
    with pytest.raises(ValueError, match=r"excede lo disponible \(5"):
        _solicitar(db, org, branch_a, cajero_a, venta, variante, 6)


def test_lo_ya_devuelto_se_descuenta_del_total_de_la_variante(db, org, branch_a, cajero_a, variante):
    venta = _venta(db, org, branch_a, cajero_a, variante,
                   [(2, Decimal("100")), (3, Decimal("150"))])
    _aprobar(db, org, cajero_a, _solicitar(db, org, branch_a, cajero_a, venta, variante, 3))
    db.refresh(venta)
    assert venta.status == DocumentStatus.REFUNDED_PARTIAL

    with pytest.raises(ValueError, match=r"excede lo disponible \(2"):
        _solicitar(db, org, branch_a, cajero_a, venta, variante, 3)

    _aprobar(db, org, cajero_a, _solicitar(db, org, branch_a, cajero_a, venta, variante, 2))
    db.refresh(venta)
    assert venta.status == DocumentStatus.REFUNDED_TOTAL
    assert Decimal(str(venta.total_amount)) == Decimal("0")


def test_devolver_una_de_dos_lineas_iguales_es_parcial(db, org, branch_a, cajero_a, variante):
    venta = _venta(db, org, branch_a, cajero_a, variante,
                   [(1, Decimal("50")), (1, Decimal("50"))])

    _aprobar(db, org, cajero_a, _solicitar(db, org, branch_a, cajero_a, venta, variante, 1))

    db.refresh(venta)
    assert venta.status == DocumentStatus.REFUNDED_PARTIAL, (
        "queda una pieza sin devolver: la venta no está devuelta por completo"
    )
    assert Decimal(str(venta.total_amount)) == Decimal("50")
