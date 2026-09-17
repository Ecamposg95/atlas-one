"""La venta congela el tipo de cambio efectivo, y jamas se cae por eso.

`create_sale` es el motor ATS-critico: el equivalente en dolares es
informativo y no puede impedir un cobro ni mover un centavo del total."""
from datetime import date
from decimal import Decimal

from app.models.exchange_rate import ExchangeRate
from app.models.sales import SalesDocument
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _preparar(db, org, branch, cajero, precio="185.00"):
    _habilitar_pos(db, org)
    _make_product(db, org, "Playera USD", "USD-01", Decimal(precio), [(branch.id, True)])
    _abrir_caja(db, org, branch, cajero)
    db.commit()


def _vender(client, org, auth, monto="185.00"):
    return client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "USD-01", "quantity": 1}],
        "payments": [{"method": "CASH", "amount": monto}],
    }, headers={**auth, "X-Organization-ID": str(org.id)})


def test_organizacion_sin_tipo_de_cambio_deja_null(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert r.json()["usd_rate"] is None
    venta = db.query(SalesDocument).filter(SalesDocument.id == r.json()["sale_id"]).one()
    assert venta.usd_rate is None


def test_modo_auto_congela_fix_mas_margen(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.2000")))
    org.usd_rate_mode = "auto"
    org.usd_rate_margin = Decimal("0.30")
    db.commit()

    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert Decimal(str(r.json()["usd_rate"])) == Decimal("18.5000")
    venta = db.query(SalesDocument).filter(SalesDocument.id == r.json()["sale_id"]).one()
    assert venta.usd_rate == Decimal("18.5000")


def test_el_snapshot_no_mueve_el_total_cobrado(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    org.usd_rate_mode = "manual"
    org.usd_rate_manual = Decimal("19.5000")
    db.commit()

    cuerpo = _vender(client, org, auth_cajero_a).json()
    assert cuerpo["total"] == 185.0
    assert cuerpo["paid"] == 185.0
    assert cuerpo["change"] == 0.0
    assert Decimal(str(cuerpo["usd_rate"])) == Decimal("19.5000")


def test_si_el_servicio_revienta_la_venta_se_cobra_igual(
    client, db, org, branch_a, cajero_a, auth_cajero_a, monkeypatch
):
    """Banxico caido, tabla ausente o bug del servicio: se cobra igual y el
    equivalente queda en NULL. Es la unica forma aceptable de tocar create_sale."""
    _preparar(db, org, branch_a, cajero_a)
    org.usd_rate_mode = "manual"
    org.usd_rate_manual = Decimal("19.5000")
    db.commit()

    from app.services import exchange_rate as servicio

    def _revienta(db_, org_):
        raise RuntimeError("tabla exchange_rates caída")

    monkeypatch.setattr(servicio, "tipo_vigente", _revienta)

    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert r.json()["usd_rate"] is None
    assert r.json()["total"] == 185.0
