"""La venta congela el tipo de cambio efectivo, y jamas se cae por eso.

`create_sale` es el motor ATS-critico: el equivalente en dolares es
informativo y no puede impedir un cobro ni mover un centavo del total."""
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.models.exchange_rate import ExchangeRate
from app.models.inventory import StockOnHand
from app.models.products import ProductVariant
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


def test_si_la_tabla_esta_caida_la_venta_se_cobra_igual(
    client, db, org, branch_a, cajero_a, auth_cajero_a, monkeypatch
):
    """La caida de la Task 1 anterior era un `raise` de Python puro: nunca
    tocaba SQL, asi que nunca dejaba a la sesion en un estado abortado.

    Aqui la consulta que revienta es SQL real EN LA MISMA SESION que
    `create_sale` esta usando para la venta: `tipo_vigente_o_error` (a
    diferencia de `snapshot_usd_rate`) NO se traga el error, asi que sube
    hasta el `with db.begin_nested():` del router, que hace ROLLBACK TO
    SAVEPOINT (SQLite lo soporta igual que Postgres) y deja la sesion sana
    para el resto del cobro — el `db.flush()` de la venta (linea siguiente)
    y todo lo de despues corren en una transaccion limpia. Si el try/except
    estuviera DENTRO del `with` (como con `snapshot_usd_rate`), esta misma
    prueba fallaria: el `with` no veria ninguna excepcion y, en Postgres,
    emitiria RELEASE SAVEPOINT sobre una conexion ya abortada."""
    _preparar(db, org, branch_a, cajero_a)
    org.usd_rate_mode = "manual"
    org.usd_rate_manual = Decimal("19.5000")
    db.commit()

    from app.services import exchange_rate as servicio

    def _tabla_caida(db_, currency="USD"):
        db_.execute(text("SELECT * FROM tabla_que_no_existe"))

    monkeypatch.setattr(servicio, "ultimo_fix", _tabla_caida)

    variante = db.query(ProductVariant).filter(ProductVariant.sku == "USD-01").one()
    stock_antes = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variante.id, StockOnHand.branch_id == branch_a.id,
    ).one().qty_on_hand

    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert r.json()["usd_rate"] is None
    assert r.json()["total"] == 185.0

    db.expire_all()
    stock_despues = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variante.id, StockOnHand.branch_id == branch_a.id,
    ).one().qty_on_hand
    assert stock_despues == stock_antes - 1

    # La sesion sigue sana: ni PendingRollbackError ni InFailedSqlTransaction.
    # Se prueba con la MISMA sesion que uso `create_sale` (el fixture `client`
    # sobrescribe `get_db` para devolver este `db`, ver tests/conftest.py),
    # tanto para una lectura nueva como para poder seguir escribiendo.
    venta = db.query(SalesDocument).filter(SalesDocument.id == r.json()["sale_id"]).one()
    assert venta.total_amount == Decimal("185.00")
    db.execute(text("SELECT 1"))
    db.commit()
