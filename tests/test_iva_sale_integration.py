"""El cobro (`app/routers/sales.py::create_sale`) desglosa el IVA con el
servicio unico, no con una formula propia.

Sustituye a las dos pruebas de IVA de Atlas-Rmazh que no son portables aqui
(`test_iva_sale_integration.py` pega por HTTP contra un servidor vivo y
`test_iva_sale_preview.py` prueba `/api/sales/preview`, endpoint que Atlas ONE
no tiene). Lo que si se puede verificar en proceso: que el documento guardado
cuadra subtotal + IVA == total en los dos modos de precio de la organizacion.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.products import Product, ProductBranchStatus, ProductVariant
from app.models.sales import SalesDocument


def _habilitar_pos(db, org):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta"))
        db.flush()
    ya = (
        db.query(OrganizationModule)
        .filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == "pos",
        )
        .first()
    )
    if ya is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    else:
        ya.is_enabled = True
    db.commit()


def _abrir_caja(db, org, branch, user):
    abierta = (
        db.query(CashSession)
        .filter(CashSession.user_id == user.id, CashSession.closed_at.is_(None))
        .first()
    )
    if abierta is None:
        db.add(CashSession(
            user_id=user.id, branch_id=branch.id, organization_id=org.id,
            opening_balance=Decimal("0"), status="OPEN",
        ))
        db.commit()


def _producto(db, org, branch, sku, precio, *, has_iva=True, tax_rate=Decimal("16")):
    _habilitar_pos(db, org)
    p = Product(name=f"Producto {sku}", organization_id=org.id, is_active=True)
    db.add(p); db.flush()
    v = ProductVariant(
        product_id=p.id, sku=sku, price=Decimal(str(precio)), cost=Decimal("10.00"),
        organization_id=org.id, variant_name="Estándar",
        has_iva=has_iva, tax_rate=tax_rate,
    )
    db.add(v); db.flush()
    db.add(ProductBranchStatus(
        variant_id=v.id, branch_id=branch.id, organization_id=org.id,
        is_active_pos=True, is_visible=True,
    ))
    db.add(StockOnHand(
        variant_id=v.id, branch_id=branch.id, organization_id=org.id,
        qty_on_hand=Decimal("100"), is_active=True,
    ))
    db.commit(); db.refresh(v)
    return v


def _vender(client, org, auth, sku, monto, *, requires_invoice=True):
    return client.post(
        "/api/sales/",
        json={
            "doc_type": "ORDER",
            "items": [{"sku": sku, "quantity": 1}],
            "payments": [{"method": "CASH", "amount": str(monto)}],
            "requires_invoice": requires_invoice,
        },
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


def _documento(db, org):
    return (
        db.query(SalesDocument)
        .filter(SalesDocument.organization_id == org.id)
        .order_by(SalesDocument.created_at.desc())
        .first()
    )


class TestIvaEnElCobro:
    def test_modo_neto_suma_el_iva_encima(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        """Modo por defecto de Atlas ONE: el precio del catalogo es neto."""
        _producto(db, org, branch_a, "IVA-NETO", "100.00")
        _abrir_caja(db, org, branch_a, cajero_a)
        resp = _vender(client, org, auth_cajero_a, "IVA-NETO", "116.00")
        assert resp.status_code in (200, 201), resp.text
        assert Decimal(str(resp.json()["total"])) == Decimal("116.00")

        doc = _documento(db, org)
        assert doc.subtotal == Decimal("100.00")
        assert doc.tax_amount == Decimal("16.00")
        assert doc.total_amount == Decimal("116.00")

    def test_modo_precio_con_iva_incluido_desglosa(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        """Con `organization.price_includes_tax`, el precio 116 NO se infla:
        se descompone en base 100 + IVA 16."""
        org.price_includes_tax = True
        db.commit()
        _producto(db, org, branch_a, "IVA-INCL", "116.00")
        _abrir_caja(db, org, branch_a, cajero_a)
        resp = _vender(client, org, auth_cajero_a, "IVA-INCL", "116.00")
        assert resp.status_code in (200, 201), resp.text
        assert Decimal(str(resp.json()["total"])) == Decimal("116.00")

        doc = _documento(db, org)
        assert doc.subtotal == Decimal("100.00")
        assert doc.tax_amount == Decimal("16.00")
        assert doc.total_amount == Decimal("116.00")

    def test_sin_factura_no_hay_desglose(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _producto(db, org, branch_a, "IVA-SF", "100.00")
        _abrir_caja(db, org, branch_a, cajero_a)
        resp = _vender(client, org, auth_cajero_a, "IVA-SF", "100.00", requires_invoice=False)
        assert resp.status_code in (200, 201), resp.text

        doc = _documento(db, org)
        assert doc.tax_amount == Decimal("0.00")
        assert doc.total_amount == Decimal("100.00")

    def test_producto_exento_no_causa_iva(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        """El catalogo manda: `has_iva=False` no se grava aunque haya factura.
        (Atlas ONE NO adopta la politica 'todo gravado' del POS de Rmazh.)"""
        _producto(db, org, branch_a, "IVA-EXENTO", "100.00", has_iva=False)
        _abrir_caja(db, org, branch_a, cajero_a)
        resp = _vender(client, org, auth_cajero_a, "IVA-EXENTO", "100.00")
        assert resp.status_code in (200, 201), resp.text

        doc = _documento(db, org)
        assert doc.tax_amount == Decimal("0.00")
        assert doc.total_amount == Decimal("100.00")
