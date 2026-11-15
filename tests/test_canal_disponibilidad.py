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


# ── Acciones en bloque (UPDATE que el listener no ve) ────────────────────────
def _lote(client, org, auth, accion, ids):
    r = client.post("/api/products/batch-action", json={"action": accion, "ids": ids},
                    headers={**auth, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("accion", ["deactivate", "delete"])
def test_lote_desactivar_y_reactivar(client, db, org, branch_a, auth_admin, accion):
    _encender(db, org, [branch_a.id])
    p, v = _producto(db, org, {branch_a: 3})
    otro_p, otro_v = _producto(db, org, {branch_a: 3})
    assert _fila(db, org, v).available is True

    assert _lote(client, org, auth_admin, accion, [p.id])["processed"] == 1
    assert _fila(db, org, v).available is False
    assert _fila(db, org, otro_v).available is True

    assert _lote(client, org, auth_admin, "activate", [p.id])["processed"] == 1
    assert _fila(db, org, v).available is True


def test_lote_aprobar_pendiente_con_existencias(client, db, org, branch_a, auth_admin):
    _encender(db, org, [branch_a.id])
    p, v = _producto(db, org, {})
    p.approval_status = "PENDING"
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("2")))
    db.flush()
    assert _fila(db, org, v) is None  # pendiente: no se publica

    assert _lote(client, org, auth_admin, "approve", [p.id])["processed"] == 1
    assert _fila(db, org, v).available is True


def test_lote_org_sin_modulo_no_escribe(client, db, org, branch_a, auth_admin):
    p, v = _producto(db, org, {branch_a: 3})
    _lote(client, org, auth_admin, "deactivate", [p.id])
    _lote(client, org, auth_admin, "activate", [p.id])
    assert _filas(db, org) == 0


# ── Nunca tumba el cobro ─────────────────────────────────────────────────────
def test_fallo_del_listener_no_tumba_la_venta(client, db, org, branch_a, cajero_a, monkeypatch):
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 1})
    assert _fila(db, org, v).available is True

    def _revienta(*a, **k):
        raise RuntimeError("falla simulada del canal")

    monkeypatch.setattr(cd, "_procesar_org", _revienta)
    r = _vender(client, db, org, branch_a, cajero_a, v)
    assert r.status_code in (200, 201)
    assert db.query(StockOnHand.qty_on_hand).filter_by(variant_id=v.id).scalar() == 0
    assert _fila(db, org, v).available is True  # se perdió solo el recálculo


def test_fallo_sql_dentro_del_savepoint_no_tumba_la_venta(client, db, org, branch_a, cajero_a, monkeypatch):
    """Un error de base dentro del listener se deshace en su SAVEPOINT."""
    _encender(db, org, [branch_a.id])
    _, v = _producto(db, org, {branch_a: 2})

    def _sql_roto(session, *a, **k):
        session.execute(text("SELECT * FROM tabla_que_no_existe"))

    monkeypatch.setattr(cd, "_procesar_org", _sql_roto)
    _vender(client, db, org, branch_a, cajero_a, v)
    assert db.query(StockOnHand.qty_on_hand).filter_by(variant_id=v.id).scalar() == 1


def test_stock_sin_org_en_org_sin_modulo_sin_escrituras(db, org, branch_a):
    """La sucursal se resuelve dentro del SAVEPOINT y, sin módulo, no escribe."""
    cd._org_por_sucursal.pop(branch_a.id, None)
    _, v = _producto(db, org, {})
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, qty_on_hand=Decimal("2")))
    db.flush()
    assert cd._org_por_sucursal.get(branch_a.id) == org.id
    assert _filas(db, org) == 0


_SCRIPT_SIN_APP = r'''
import sys
from decimal import Decimal
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
compiles(JSONB, "sqlite")(lambda *a, **k: "JSON")  # igual que conftest
from app.core.database import Base, SessionLocal, engine
import app.models  # noqa: F401  (lo único que importa un script de mantenimiento)
from app.models import Product, ProductVariant
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch, BranchType, Organization
from app.modules.canal.models import ChannelAvailability

assert "app.main" not in sys.modules
Base.metadata.create_all(bind=engine)
db = SessionLocal()
org = Organization(name="Script", status="ACTIVE"); db.add(org); db.flush()
b = Branch(name="S", branch_type=BranchType.STORE, can_sell=True, is_active=True,
           organization_id=org.id); db.add(b); db.flush()
db.add(Module(key="tienda_en_linea", name="tienda_en_linea")); db.flush()
db.add(OrganizationModule(organization_id=org.id, module_key="tienda_en_linea",
                          is_enabled=True, config_json={"sucursales_web": [b.id]}))
p = Product(name="Bolsa", organization_id=org.id, is_active=True, approval_status="APPROVED")
db.add(p); db.flush()
v = ProductVariant(product_id=p.id, sku="SCR-1", price=Decimal("1"), cost=Decimal("1"),
                   organization_id=org.id)
db.add(v); db.flush()
db.add(StockOnHand(variant_id=v.id, branch_id=b.id, organization_id=org.id,
                   qty_on_hand=Decimal("3"), is_active=True))
db.commit()
fila = db.query(ChannelAvailability).filter_by(organization_id=org.id, variant_id=v.id).first()
print("DISPONIBLE", fila is not None and fila.available)
'''


def test_listener_activo_en_scripts_sin_la_app(tmp_path):
    """Un script que solo importa los modelos y abre SessionLocal() (sin pasar
    por el startup de FastAPI) también mantiene channel_availability."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'script.db'}",
           "PYTHONPATH": str(raiz)}
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", _SCRIPT_SIN_APP],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "DISPONIBLE True" in r.stdout, r.stdout + r.stderr[-2000:]
