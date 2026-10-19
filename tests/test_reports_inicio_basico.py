# tests/test_reports_inicio_basico.py
"""`GET /api/reports/inicio-basico` — el "¿cómo voy?" de la dueña en modo básico.

Una sola llamada (una PC vieja de tienda no debe hacer cinco): vendido hoy,
ayer y en 7 días, cobros de hoy por método, lo más vendido, lo que se está
acabando y el estado de la caja. Aislado por organización y por sucursal con
las mismas reglas que el valor de la tienda.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Product, ProductVariant
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem

_MX = ZoneInfo("America/Mexico_City")
URL = "/api/reports/inicio-basico"
_folios = count(1)


def _instante(dias_atras: int, hora: int = 12) -> datetime:
    """Mediodía (hora de México) de hace `dias_atras` días, en UTC."""
    dia = datetime.now(_MX).date() - timedelta(days=dias_atras)
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _variante(db, org, branch, nombre, sku, existencia):
    p = Product(name=nombre, organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, price=Decimal("100"), cost=Decimal("40"),
                       organization_id=org.id)
    db.add(v)
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal(str(existencia)), is_active=True))
    db.flush()
    return v


def _venta(db, org, branch, user, variante, total, *, metodo=PaymentMethod.CASH, dias_atras=0,
           descripcion="Producto", cantidad=1, status=DocumentStatus.PAID):
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=status, doc_type="ORDER",
    )
    doc.created_at = _instante(dias_atras)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(
        organization_id=org.id, document_id=doc.id, variant_id=variante.id,
        description=descripcion, quantity=cantidad,
        unit_price=Decimal(total) / cantidad, total_line=Decimal(total), unit_cost=Decimal("10"),
    ))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo, amount=Decimal(total))
    pago.created_at = _instante(dias_atras)
    db.add(pago)
    db.commit()
    return doc


def test_hoy_ayer_y_semana(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "500", status=DocumentStatus.CANCELLED)
    _venta(db, org, branch_a, admin_user, v, "70", dias_atras=1)
    _venta(db, org, branch_a, admin_user, v, "30", dias_atras=6)
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=7)

    r = client.get(URL, headers=auth_admin)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["branch_id"] is None
    assert (d["hoy"]["total"], d["hoy"]["tickets"]) == (150.0, 2)
    assert (d["ayer"]["total"], d["ayer"]["tickets"]) == (70.0, 1)
    assert (d["semana"]["total"], d["semana"]["tickets"]) == (250.0, 4)
    assert d["hoy"]["desde"] == d["hoy"]["hasta"] == d["semana"]["hasta"]


def test_cobros_de_hoy_por_metodo(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "80", dias_atras=1)

    d = client.get(URL, headers=auth_admin).json()

    assert d["por_metodo_hoy"] == {"CASH": 100.0, "CARD": 50.0}


def test_lo_mas_vendido_de_la_semana_por_piezas_y_maximo_cinco(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "40", descripcion="Blusa", cantidad=2)
    _venta(db, org, branch_a, admin_user, v, "20", descripcion="Blusa", cantidad=1, dias_atras=3)
    for nombre in ("Falda", "Short", "Gorra", "Bolsa", "Cinto"):
        _venta(db, org, branch_a, admin_user, v, "10", descripcion=nombre)
    _venta(db, org, branch_a, admin_user, v, "999", descripcion="Vieja", cantidad=50, dias_atras=8)

    top = client.get(URL, headers=auth_admin).json()["top_semana"]

    assert len(top) == 5
    assert top[0] == {"nombre": "Blusa", "cantidad": 3.0, "total": 60.0}
    assert "Vieja" not in [t["nombre"] for t in top]


def test_poca_existencia_con_el_tope_de_la_empresa(client, db, org, branch_a, admin_user, auth_admin):
    for n in range(12):
        _variante(db, org, branch_a, f"Prod {n:02d}", f"SKU-{n:02d}", n)
    db.commit()

    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 3
    assert [p["existencia"] for p in d["productos"]] == [0.0, 1.0, 2.0, 3.0]
    assert d["productos"][0]["nombre"] == "Prod 00"

    org.umbral_poca_existencia = 20
    db.commit()
    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 20
    assert len(d["productos"]) == 10


def test_poca_existencia_sin_inactivos_borrados_ni_bodegas(client, db, org, branch_a, hq_branch, admin_user, auth_admin):
    _variante(db, org, branch_a, "Activo", "A-1", 1)
    inactivo = _variante(db, org, branch_a, "Inactivo", "I-1", 0)
    db.get(Product, inactivo.product_id).is_active = False
    borrada = _variante(db, org, branch_a, "Borrada", "B-1", 0)
    borrada.deleted_at = datetime.now(timezone.utc)
    _variante(db, org, hq_branch, "Bodega", "H-1", 0)  # HQ de conftest: can_sell=False
    db.commit()

    productos = client.get(URL, headers=auth_admin).json()["poca_existencia"]["productos"]

    assert [p["nombre"] for p in productos] == ["Activo"]


def test_otra_organizacion_no_se_mezcla(client, db, org, branch_a, admin_user, auth_admin):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True,
                   organization_id=otra.id)
    db.add(ajena)
    db.flush()
    v = _variante(db, otra, ajena, "Ajeno", "AJ-1", 0)
    _venta(db, otra, ajena, admin_user, v, "777")

    d = client.get(URL, headers=auth_admin).json()

    assert d["hoy"]["tickets"] == 0
    assert d["por_metodo_hoy"] == {}
    assert d["top_semana"] == []
    assert d["poca_existencia"]["productos"] == []
    assert client.get(f"{URL}?branch_id={ajena.id}", headers=auth_admin).status_code == 404


def test_la_duena_puede_mirar_una_sucursal(client, db, org, branch_a, branch_b, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_admin).json()

    assert d["branch_id"] == branch_b.id
    assert d["hoy"]["total"] == 700.0
    assert client.get(URL, headers=auth_admin).json()["hoy"]["total"] == 800.0


def test_el_gerente_solo_ve_su_sucursal(client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, gerente_a, v, "100")
    _venta(db, org, branch_b, gerente_a, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_gerente_a).json()

    assert d["branch_id"] == branch_a.id
    assert d["hoy"]["total"] == 100.0
    assert d["por_metodo_hoy"] == {"CASH": 100.0}


def test_la_cajera_no_ve_el_inicio(client, cajero_a, auth_cajero_a):
    assert client.get(URL, headers=auth_cajero_a).status_code == 403


def test_corte_abierto_con_efectivo_esperado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), status="OPEN"))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "abierto"
    assert c["cajera"] == "cajero_a"
    assert c["efectivo_esperado"] == 500.0
    assert c["abierto_en"] is not None
    assert c["efectivo_contado"] is None


def test_corte_sin_turno_y_cerrado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    assert client.get(URL, headers=auth_admin).json()["corte"] == {
        "estado": "sin_turno", "cajera": None, "abierto_en": None, "cerrado_en": None,
        "efectivo_esperado": None, "efectivo_contado": None,
    }
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("850"),
                       status="CLOSED", closed_at=datetime.now(timezone.utc)))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "cerrado"
    assert c["efectivo_contado"] == 850.0
    assert c["efectivo_esperado"] is None
    assert c["cerrado_en"] is not None
