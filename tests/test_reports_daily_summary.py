"""`/api/reports/daily-summary` -- el resumen del dia que ve el duenio en el movil.

Dos defectos preexistentes, ambos en produccion desde el 8 de mayo de 2026:

1. La utilidad bruta filtraba por `DocumentStatus.COMPLETED`, un miembro que
   nunca existio en el enum (`DRAFT`, `PENDING`, `PAID`, `CANCELLED`,
   `REFUNDED_PARTIAL`, `REFUNDED_TOTAL`). El endpoint entero reventaba con
   `AttributeError` -> HTTP 500, de modo que `MobileDashboard.tsx` no cargaba.

2. Las otras tres consultas (total vendido, desglose de pagos y productos mas
   vendidos) no filtraban por estatus, asi que sumaban ventas canceladas y
   borradores como si fueran ingreso del dia. Ademas productos y utilidad no
   filtraban por sucursal, mezclando sucursales en una organizacion multi-sucursal.

El criterio de "esta venta ya es ingreso reconocido" tiene una sola fuente:
`SALES_REPORT_STATUSES` en `app/services/cash_reconciliation.py`.
"""
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models.sales import (
    DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem,
)


def _v(products_setup):
    """Variante cualquiera: la linea exige `variant_id`, pero estas pruebas
    agrupan por `description`, que se fija por venta."""
    return products_setup["product_a"][1]


_MX = ZoneInfo("America/Mexico_City")


def _hoy_mx_a_las(hora):
    """Instante UTC que corresponde a `hora` de hoy en hora de Mexico.

    `sales-by-hour` solo arma franjas de 8 a 21 (app/routers/reports.py), asi
    que una venta creada con la hora real del reloj deja la prueba en verde
    falso si la suite corre de madrugada.
    """
    hoy_mx = datetime.now(_MX).date()
    return datetime.combine(hoy_mx, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variant, folio, total, status, costo_unitario="40",
           entregado=None, hora_mx=None):
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        folio=folio, series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=status, doc_type="ORDER",
        change_given=Decimal(entregado) - Decimal(total) if entregado else None,
    )
    if hora_mx is not None:
        doc.created_at = _hoy_mx_a_las(hora_mx)
    db.add(doc); db.commit(); db.refresh(doc)
    db.add(SalesLineItem(
        organization_id=org.id, document_id=doc.id, variant_id=variant.id,
        description=f"Producto {folio}", quantity=1,
        unit_price=Decimal(total), total_line=Decimal(total),
        unit_cost=Decimal(costo_unitario),
    ))
    db.add(Payment(
        organization_id=org.id, sales_document_id=doc.id,
        method=PaymentMethod.CASH, amount=Decimal(entregado or total),
    ))
    db.commit()
    return doc


def test_daily_summary_responde_200(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Regresion del AttributeError: el endpoint debe responder, no reventar."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)

    resp = client.get("/api/reports/daily-summary", headers=auth_cajero_a)

    assert resp.status_code == 200, resp.text
    assert resp.json()["transactions_count"] == 1


def test_daily_summary_excluye_ventas_canceladas(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """Una venta cancelada no es ingreso: no cuenta en total, pagos, top ni utilidad."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-2", "500", DocumentStatus.CANCELLED)

    data = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()

    assert data["transactions_count"] == 1
    assert data["total_revenue"] == 100.0
    assert data["payments"].get("CASH") == 100.0
    assert [p["name"] for p in data["top_selling_items"]] == ["Producto R-1"]
    assert data["gross_profit"] == 60.0  # 100 de venta - 40 de costo


def test_daily_summary_no_mezcla_sucursales(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup
):
    """Productos y utilidad se limitan a la sucursal del usuario, como el total."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()

    assert data["total_revenue"] == 100.0
    assert [p["name"] for p in data["top_selling_items"]] == ["Producto R-1"]
    assert data["gross_profit"] == 60.0


def test_daily_summary_descuenta_el_vuelto_del_efectivo(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    """El vuelto no es ingreso.

    `Payment.amount` guarda lo que el cliente ENTREGO, no lo que se quedo en el
    cajon. Sin descontar el vuelto, el desglose de pagos reportaba mas efectivo
    que la venta del dia -- en produccion, $1,264.00 de CASH contra $992.78
    vendidos, exactamente los $271.22 de vuelto entregado. El corte de caja ya
    aplica este criterio (`net_cash = gross_cash - change_given`).
    """
    # Venta de $100 pagada con un billete de $150: el cajon se queda con $100.
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100",
           DocumentStatus.PAID, entregado="150")

    data = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()

    assert data["total_revenue"] == 100.0
    assert data["payments"]["CASH"] == 100.0


def test_rol_de_oficina_ve_toda_la_organizacion_con_branch_cero(
    client, db, org, branch_a, branch_b, admin_user, auth_admin, products_setup
):
    """`branch_id=0` es la convención que ya usa sales-by-hour: toda la org."""
    _venta(db, org, branch_a, admin_user, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, admin_user, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get("/api/reports/daily-summary?branch_id=0", headers=auth_admin).json()

    assert data["total_revenue"] == 800.0
    assert data["transactions_count"] == 2


def test_rol_de_oficina_puede_pedir_otra_sucursal(
    client, db, org, branch_a, branch_b, admin_user, auth_admin, products_setup
):
    _venta(db, org, branch_a, admin_user, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, admin_user, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get(
        f"/api/reports/daily-summary?branch_id={branch_b.id}", headers=auth_admin
    ).json()

    assert data["total_revenue"] == 700.0


def test_un_cajero_no_puede_mirar_otra_sucursal(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup
):
    """Aunque mande el branch_id de otra sucursal, sigue viendo la suya."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get(
        f"/api/reports/daily-summary?branch_id={branch_b.id}", headers=auth_cajero_a
    ).json()

    assert data["total_revenue"] == 100.0


def test_sin_parametro_el_comportamiento_no_cambia(
    client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup
):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()

    assert data["total_revenue"] == 100.0


def test_un_rol_sin_sucursal_no_ve_la_organizacion_entera(
    client, db, org, branch_a, branch_b, cajero_a,
    vendedor_sin_sucursal, auth_vendedor_sin_sucursal, products_setup
):
    """`branch_id` nulo es "este usuario no tiene sucursal", no "toda la org".

    Aislamiento: un VENDEDOR sin sucursal asignada no es un rol de oficina
    central. El guard `if target_branch_id` trataba `None` igual que el `0` de
    "toda la organizacion", asi que este usuario pasaba de no ver nada a ver la
    venta, la utilidad y el desglose de pagos del negocio completo.
    """
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get(
        "/api/reports/daily-summary", headers=auth_vendedor_sin_sucursal
    ).json()

    assert data["total_revenue"] == 0.0
    assert data["transactions_count"] == 0
    assert data["gross_profit"] == 0.0
    assert data["payments"] == {}
    assert data["top_selling_items"] == []


def test_un_rol_sin_sucursal_tampoco_ve_el_ritmo_de_la_organizacion(
    client, db, org, branch_a, branch_b, cajero_a,
    vendedor_sin_sucursal, auth_vendedor_sin_sucursal, products_setup
):
    """Mismo criterio en `sales-by-hour`: dos endpoints, una sola regla."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100",
           DocumentStatus.PAID, hora_mx=15)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700",
           DocumentStatus.PAID, hora_mx=15)

    data = client.get(
        "/api/reports/sales-by-hour", headers=auth_vendedor_sin_sucursal
    ).json()

    assert sum(h["amount"] for h in data["hourly"]) == 0.0
    assert sum(h["tickets"] for h in data["hourly"]) == 0


def test_un_rol_sin_sucursal_no_puede_pedir_toda_la_organizacion(
    client, db, org, branch_a, branch_b, cajero_a,
    vendedor_sin_sucursal, auth_vendedor_sin_sucursal, products_setup
):
    """Ni mandando `branch_id=0` a mano: esa convencion es solo de oficina central."""
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-1", "100", DocumentStatus.PAID)
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-9", "700", DocumentStatus.PAID)

    data = client.get(
        "/api/reports/daily-summary?branch_id=0", headers=auth_vendedor_sin_sucursal
    ).json()

    assert data["total_revenue"] == 0.0


from app.models.returns import SaleReturn  # noqa: E402


def test_daily_summary_resta_devoluciones_aprobadas(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-10", "100", DocumentStatus.PAID)
    db.add(SaleReturn(organization_id=org.id, sale_id=v.id, user_id=cajero_a.id, branch_id=branch_a.id,
                      total_refunded=Decimal("30"), refund_method=PaymentMethod.CASH, reason="Prueba",
                      status="APPROVED"))
    db.commit()
    d = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()
    assert d["gross_revenue"] == 100.0
    assert d["returns_total"] == 30.0 and d["returns_count"] == 1
    assert d["total_revenue"] == 70.0
    assert d["payments"]["CASH"] == 70.0


def test_daily_summary_admin_sin_parametro_ve_toda_la_org(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-11", "100", DocumentStatus.PAID)
    doc_b = _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-12", "200", DocumentStatus.PAID)
    assert doc_b.branch_id == branch_b.id
    d = client.get("/api/reports/daily-summary", headers=auth_admin_a).json()
    assert d["total_revenue"] == 300.0
    solo_a = client.get(f"/api/reports/daily-summary?branch_id={branch_a.id}", headers=auth_admin_a).json()
    assert solo_a["total_revenue"] == 100.0
