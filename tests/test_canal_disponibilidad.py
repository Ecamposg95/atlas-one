"""Disponibilidad web materializada (canal «Tienda en línea», Tarea 5).

`channel_availability` guarda, por variante, si se puede vender en la tienda
web. La escribe un listener `before_flush` (sin tocar `create_sale`) solo
cuando el booleano cambia; `recalcular_disponibilidad` es la red de seguridad.
"""
import itertools
from decimal import Decimal

import pytest
from sqlalchemy import event, select, text

from conftest import TEST_ENGINE, _auth_header, _make_user
from app.core.security.channel_keys import MODULO_CANAL, canal_activo, invalidar_cache_canal
from app.models import Product, ProductVariant
from app.models.users import Role
from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.products import ProductBranchStatus
from app.modules.canal.models import ChannelAvailability
from app.services import canal_disponibilidad as cd

_n = itertools.count(1)


@pytest.fixture(autouse=True)
def _limpiar():
    invalidar_cache_canal()
    cd.registrar_listener()
    yield
    cd.registrar_listener()
    invalidar_cache_canal()


# ── Ayudantes ────────────────────────────────────────────────────────────────
def _modulo(db, org, key, config=None):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key))
        db.flush()
    om = db.query(OrganizationModule).filter_by(organization_id=org.id, module_key=key).first()
    if om is None:
        om = OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True)
        db.add(om)
    om.is_enabled = True
    if config is not None:
        om.config_json = config
    db.flush()
    if key == MODULO_CANAL:
        invalidar_cache_canal(org.id)
    return om


def _encender(db, org, sucursales_web=None):
    return _modulo(db, org, MODULO_CANAL, {"sucursales_web": sucursales_web})


def _producto(db, org, existencias):
    """Producto aprobado con una variante. `existencias`: {branch: qty}."""
    n = next(_n)
    p = Product(name=f"Bolsa {n}", organization_id=org.id, is_active=True,
                approval_status="APPROVED")
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=f"DSP-{n}", price=Decimal("100"),
                       cost=Decimal("50"), organization_id=org.id)
    db.add(v)
    db.flush()
    for branch, qty in existencias.items():
        db.add(ProductBranchStatus(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                                   is_active_pos=True, is_visible=True))
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(str(qty)), is_active=True))
    db.flush()
    return p, v


def _fila(db, org, v):
    """Lee la fila directo de la base (no del identity map)."""
    return db.execute(
        select(ChannelAvailability.available, ChannelAvailability.changed_at)
        .where(ChannelAvailability.organization_id == org.id,
               ChannelAvailability.variant_id == v.id)
    ).first()


def _filas(db, org):
    return db.execute(text(
        "SELECT COUNT(*) FROM channel_availability WHERE organization_id = :o"), {"o": org.id}
    ).scalar()


def _preparar_venta(db, org, branch, user):
    _modulo(db, org, "pos")
    if db.query(CashSession).filter_by(user_id=user.id, branch_id=branch.id).first() is None:
        db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                           opening_balance=Decimal("0"), status="OPEN"))
    db.commit()


def _post_venta(client, org, user, sku, qty=1):
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": sku, "quantity": qty}],
        "payments": [{"method": "CASH", "amount": str(100 * qty)}],
    }, headers={**_auth_header(user), "X-Organization-ID": str(org.id)})
    assert r.status_code in (200, 201), r.text
    return r


def _vender(client, db, org, branch, user, v, qty=1):
    _preparar_venta(db, org, branch, user)
    return _post_venta(client, org, user, v.sku, qty)


def _contar_venta(client, db, org, branch, user, v):
    """Statements que emite solo el POST de la venta (la preparación y la
    recarga de objetos expirados por el commit quedan fuera)."""
    _preparar_venta(db, org, branch, user)
    org_id, sku = org.id, v.sku
    _ = (user.id, user.username)
    contador = []

    def _contar(conn, cursor, statement, *a):
        contador.append(statement)

    event.listen(TEST_ENGINE, "before_cursor_execute", _contar)
    try:
        _post_venta(client, org, user, sku)
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", _contar)
    return contador


# ── Venta ────────────────────────────────────────────────────────────────────
def test_ultima_pieza_cambia_a_no_disponible(client, db, org, branch_a, cajero_a):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 1})
    # El listener ya la dio de alta al crear la existencia; recalcular no cambia nada.
    assert _fila(db, org, v).available is True
    assert cd.recalcular_disponibilidad(db, org.id) == 0

    _vender(client, db, org, branch_a, cajero_a, v)

    assert _fila(db, org, v).available is False


def test_venta_parcial_no_escribe(client, db, org, branch_a, cajero_a):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 5})
    cd.recalcular_disponibilidad(db, org.id)
    antes = _fila(db, org, v)
    total = _filas(db, org)

    _vender(client, db, org, branch_a, cajero_a, v)

    assert db.query(StockOnHand.qty_on_hand).filter_by(variant_id=v.id).scalar() == 4
    assert _filas(db, org) == total
    despues = _fila(db, org, v)
    assert despues.available is True
    assert despues.changed_at == antes.changed_at


def test_sucursal_no_web_no_cuenta(client, db, org, branch_a, branch_b):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 0, branch_b: 3})
    cd.recalcular_disponibilidad(db, org.id)
    assert _fila(db, org, v) is None  # sin fila = no disponible
    assert cd.variante_disponible(db, org.id, v.id) is False

    cajero_b = _make_user(db, org, branch_b, "cajero_b_dsp", Role.CAJERO)
    _vender(client, db, org, branch_b, cajero_b, v)
    assert _filas(db, org) == 0


def test_entrada_vuelve_disponible(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 1})
    cd.recalcular_disponibilidad(db, org.id)
    stock = db.query(StockOnHand).filter_by(variant_id=v.id).one()
    stock.qty_on_hand = Decimal("0")
    db.flush()
    assert _fila(db, org, v).available is False

    stock.qty_on_hand += Decimal("1")
    db.flush()
    assert _fila(db, org, v).available is True


def test_existencia_nueva_en_sucursal_web(db, org, branch_a):
    """Fila de existencias nueva (compra/traspaso a una sucursal sin registro)."""
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {})
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, qty_on_hand=Decimal("2")))
    db.flush()  # sin organization_id: se deduce de la sucursal
    assert _fila(db, org, v).available is True


def test_rollback_no_deja_fila(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 0})
    cd.recalcular_disponibilidad(db, org.id)
    assert _fila(db, org, v) is None

    sp = db.begin_nested()
    stock = db.query(StockOnHand).filter_by(variant_id=v.id).one()
    stock.qty_on_hand = Decimal("3")
    db.flush()
    assert _fila(db, org, v).available is True
    sp.rollback()

    assert _fila(db, org, v) is None


def test_org_sin_modulo_sin_consultas_extra(client, db, org, branch_a, cajero_a):
    _, v = _producto(db, org, {branch_a: 50})
    _vender(client, db, org, branch_a, cajero_a, v)  # calentamiento (folios, caches)
    assert canal_activo(db, org.id) is False  # cache caliente

    cd.quitar_listener()
    sin = _contar_venta(client, db, org, branch_a, cajero_a, v)
    cd.registrar_listener()
    con = _contar_venta(client, db, org, branch_a, cajero_a, v)
    assert len(con) == len(sin), [x[:80] for x in con if x not in sin]
    assert _filas(db, org) == 0


def test_org_con_modulo_consultas_acotadas(client, db, org, branch_a, cajero_a):
    """Con el módulo, una venta cuesta un puñado fijo de consultas extra."""
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 50})
    _vender(client, db, org, branch_a, cajero_a, v)
    assert canal_activo(db, org.id) is True

    cd.quitar_listener()
    sin = _contar_venta(client, db, org, branch_a, cajero_a, v)
    cd.registrar_listener()
    con = _contar_venta(client, db, org, branch_a, cajero_a, v)
    extra = len(con) - len(sin)
    assert 0 < extra <= 8, (extra, [x[:80] for x in con])
    assert not any(x.lstrip().upper().startswith("INSERT INTO CHANNEL") for x in con)


def test_muchas_filas_en_un_flush_son_consultas_constantes(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    variantes = [_producto(db, org, {branch_a: 1})[1] for _ in range(30)]
    cd.recalcular_disponibilidad(db, org.id)
    stocks = db.query(StockOnHand).filter(
        StockOnHand.variant_id.in_([v.id for v in variantes])).all()

    contador = []

    def _contar(conn, cursor, statement, *a):
        contador.append(statement)

    for s in stocks:
        s.qty_on_hand = Decimal("0")
    event.listen(TEST_ENGINE, "before_cursor_execute", _contar)
    try:
        db.flush()
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", _contar)
    ajenas = [s for s in contador if "stock_on_hand" not in s.lower() or not s.lower().startswith("update")]
    assert len(ajenas) <= 10, ajenas
    assert all(_fila(db, org, v).available is False for v in variantes)


# ── Estado del producto ──────────────────────────────────────────────────────
@pytest.mark.parametrize("cambio", ["variante_borrada", "producto_inactivo", "pendiente", "producto_borrado"])
def test_variante_borrada_o_producto_inactivo(db, org, branch_a, cambio):
    from datetime import datetime, timezone
    _encender(db, org, [branch_a.id])
    p, v = _producto(db, org, {branch_a: 4})
    cd.recalcular_disponibilidad(db, org.id)
    assert _fila(db, org, v).available is True

    if cambio == "variante_borrada":
        v.deleted_at = datetime.now(timezone.utc)
    elif cambio == "producto_inactivo":
        p.is_active = False
    elif cambio == "pendiente":
        p.approval_status = "PENDING"
    else:
        p.deleted_at = datetime.now(timezone.utc)
    db.flush()

    assert _fila(db, org, v).available is False
    assert cd.variante_disponible(db, org.id, v.id) is False


def test_variante_eliminada_de_verdad(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    p, v = _producto(db, org, {branch_a: 4})
    p2, v2 = _producto(db, org, {branch_a: 4})
    cd.recalcular_disponibilidad(db, org.id)
    db.query(ProductBranchStatus).filter_by(variant_id=v.id).delete()
    db.query(StockOnHand).filter_by(variant_id=v.id).delete()
    db.delete(v)
    db.flush()
    assert _fila(db, org, v).available is False
    assert _fila(db, org, v2).available is True


# ── Red de seguridad ─────────────────────────────────────────────────────────
def test_recalcular_corrige_update_crudo(db, org, branch_a):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 2})
    cd.recalcular_disponibilidad(db, org.id)
    assert _fila(db, org, v).available is True

    db.execute(text("UPDATE stock_on_hand SET qty_on_hand = 0 WHERE variant_id = :v"), {"v": v.id})
    assert _fila(db, org, v).available is True  # el listener no ve SQL crudo

    assert cd.recalcular_disponibilidad(db, org.id) == 1
    assert _fila(db, org, v).available is False
    assert cd.recalcular_disponibilidad(db, org.id) == 0


def test_sucursales_web_por_omision_son_las_que_venden(db, org, branch_a, branch_b, hq_branch):
    _encender(db, org, None)
    assert sorted(cd.sucursales_web(db, org.id)) == sorted([branch_a.id, branch_b.id])
    _encender(db, org, [branch_b.id])
    assert cd.sucursales_web(db, org.id) == [branch_b.id]


def test_cambiar_sucursales_recalcula(client, db, org, branch_a, branch_b, auth_admin):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 0, branch_b: 3})
    cd.recalcular_disponibilidad(db, org.id)
    assert _fila(db, org, v) is None

    r = client.put("/api/canal/config", json={"sucursales_web": [branch_b.id]},
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert _fila(db, org, v).available is True

    r = client.put("/api/canal/config", json={"sucursales_web": [branch_a.id]},
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert _fila(db, org, v).available is False


def test_activar_modulo_desde_plataforma_recalcula(client, db, org, branch_a, auth_superadmin):
    org.plan = "ULTRA_PLUS"
    _, v = _producto(db, org, {branch_a: 3})
    if db.query(Module).filter(Module.key == MODULO_CANAL).first() is None:
        db.add(Module(key=MODULO_CANAL, name="Tienda en línea"))
    db.commit()
    assert canal_activo(db, org.id) is False  # cache caliente en "apagado"

    r = client.patch(f"/api/platform/organizations/{org.id}/modules/{MODULO_CANAL}?enable=true",
                     headers=auth_superadmin)
    assert r.status_code == 200, r.text
    assert canal_activo(db, org.id) is True
    assert _fila(db, org, v).available is True

    r = client.patch(f"/api/platform/organizations/{org.id}/modules/{MODULO_CANAL}?enable=false",
                     headers=auth_superadmin)
    assert r.status_code == 200, r.text
    assert canal_activo(db, org.id) is False


def test_registrar_listener_es_idempotente():
    from sqlalchemy.orm import Session
    cd.registrar_listener()
    cd.registrar_listener()
    assert event.contains(Session, "before_flush", cd._antes_del_flush)
    cd.quitar_listener()
    assert not event.contains(Session, "before_flush", cd._antes_del_flush)
    cd.registrar_listener()
