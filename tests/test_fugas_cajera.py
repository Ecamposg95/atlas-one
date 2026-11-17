"""Fugas de backend de la cajera (2026-11-17): las pantallas ya ocultan los
importes por el conteo ciego y la regla de "solo hoy", pero el servidor los
seguía mandando. Con el turno abierto, nada que permita despejar el efectivo
esperado; de caja, solo sus propios turnos de hoy; el último ticket, solo de
hoy. El centro de mando: oficina ve la org, el gerente su sucursal, el resto 403."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.cash import CashSession
from app.models.users import Role
from tests.cobranza_helpers import _abrir_caja, _escenario, _habilitar
from tests.conftest import _auth_header, _make_user
from tests.test_cajero_ventas_del_dia import _ayer, _v, _venta


def _vender(client, h, sku, pagos):
    r = client.post("/api/sales/", json={"items": [{"sku": sku, "quantity": 1}], "payments": pagos}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _cerrar(db, sesion, cuando=None, diferencia="0"):
    sesion.status = "CLOSED"
    sesion.closed_at = cuando or datetime.now(timezone.utc)
    sesion.closing_balance = Decimal("0")
    sesion.difference = Decimal(diferencia)
    db.commit()


def _sesion_vieja(db, org, branch, user, dias=1, diferencia="-50"):
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="CLOSED")
    s.opened_at = datetime.now(timezone.utc) - timedelta(days=dias, hours=2)
    s.closed_at = datetime.now(timezone.utc) - timedelta(days=dias)
    s.difference = Decimal(diferencia)
    s.closing_balance = Decimal("0")
    db.add(s); db.commit(); db.refresh(s)
    return s


def _otra_cajera(db, org, branch):
    u = _make_user(db, org, branch, "cajero_a2", Role.CAJERO)
    db.commit()
    return u


# --- 1. /api/branch/dashboard ----------------------------------------------

def test_dashboard_cajera_turno_abierto_sin_importes(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variante, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    branch_a.daily_sales_goal = Decimal("1000"); db.commit()
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 100}])
    _vender(client, h, variante.sku, [{"method": "CARD", "amount": 100}])

    hoy = client.get("/api/branch/dashboard", headers=h).json()["today"]
    assert hoy["sales_total"] is None
    assert hoy["avg_ticket"] is None
    assert hoy["goal_progress_pct"] is None
    assert hoy["payment_methods"] is None
    assert hoy["sales_count"] == 2           # el número de tickets se queda


def test_dashboard_cajera_sin_alerta_de_diferencia(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, _, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    otra = _otra_cajera(db, org, branch_a)
    _sesion_vieja(db, org, branch_a, otra, diferencia="-50")
    alertas = client.get("/api/branch/dashboard", headers=h).json()["alerts"]
    assert all(a["kind"] != "cash_variance" for a in alertas)


def test_dashboard_gerente_conserva_alerta_de_diferencia(client, db, org, branch_a, cajero_a, gerente_a, auth_gerente_a, products_setup):
    _habilitar(db, org, "pos")
    _sesion_vieja(db, org, branch_a, cajero_a, diferencia="-50")
    alertas = client.get("/api/branch/dashboard", headers=auth_gerente_a).json()["alerts"]
    assert any(a["kind"] == "cash_variance" for a in alertas)


def test_dashboard_cajera_no_ve_turno_cerrado_de_otra(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Sin turno propio, el respaldo "cerrado hoy" no puede ser el de otra cajera."""
    _habilitar(db, org, "pos", "crm")
    otra = _otra_cajera(db, org, branch_a)
    sesion = _abrir_caja(db, org, branch_a, otra)
    h2 = {**_auth_header(otra), "X-Organization-ID": str(org.id)}
    _vender(client, h2, _v(products_setup).sku, [{"method": "CASH", "amount": 100}])
    _cerrar(db, sesion)
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    hoy = client.get("/api/branch/dashboard", headers=h).json()["today"]
    assert hoy["sales_count"] == 0
    assert Decimal(str(hoy["sales_total"] or 0)) == 0


def test_dashboard_cajera_turno_cerrado_propio_ve_su_desglose(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Tras cerrar (el conteo ya se hizo) la cajera ve su propio turno, con el cambio restado."""
    h, variante, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 150}])
    _cerrar(db, sesion)
    hoy = client.get("/api/branch/dashboard", headers=h).json()["today"]
    assert Decimal(str(hoy["sales_total"])) == Decimal("100")
    assert Decimal(str(hoy["payment_methods"]["CASH"])) == Decimal("100")


# --- 2. /api/cash/summary ---------------------------------------------------

def test_summary_cajera_turno_abierto_sin_esperado(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variante, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 100}])
    r = client.get("/api/cash/summary", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["expected"]["cash_physical"] is None
    assert d["expected"]["total_system"] is None
    assert d["kpis"]["total_sales"] is None
    assert d["payments"]["cash"]["total"] is None
    assert d["reconciliation"]["difference"] is None
    assert d["returns"]["cash_refunds"] is None


def test_summary_cajera_otra_sesion_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _habilitar(db, org, "pos")
    otra = _otra_cajera(db, org, branch_a)
    ajena = _abrir_caja(db, org, branch_a, otra)
    _cerrar(db, ajena)
    vieja = _sesion_vieja(db, org, branch_a, cajero_a)
    assert client.get(f"/api/cash/summary?session_id={ajena.id}", headers=auth_cajero_a).status_code == 404
    assert client.get(f"/api/cash/summary?session_id={vieja.id}", headers=auth_cajero_a).status_code == 404


def test_summary_cajera_su_turno_cerrado_de_hoy_completo(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variante, sesion = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 100}])
    _cerrar(db, sesion)
    r = client.get(f"/api/cash/summary?session_id={sesion.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["expected"]["cash_physical"] == 100.0


def test_summary_gerente_ve_esperado_y_otras_sesiones(client, db, org, branch_a, cajero_a, auth_gerente_a, products_setup):
    _habilitar(db, org, "pos")
    vieja = _sesion_vieja(db, org, branch_a, cajero_a)
    r = client.get(f"/api/cash/summary?session_id={vieja.id}", headers=auth_gerente_a)
    assert r.status_code == 200
    assert r.json()["expected"]["cash_physical"] is not None


# --- 3. /api/cash/history ---------------------------------------------------

def test_history_cajera_solo_sus_turnos_de_hoy(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _habilitar(db, org, "pos")
    otra = _otra_cajera(db, org, branch_a)
    _sesion_vieja(db, org, branch_a, cajero_a)                 # suya, de ayer
    ajena = _abrir_caja(db, org, branch_a, otra); _cerrar(db, ajena)
    propia = _abrir_caja(db, org, branch_a, cajero_a)
    ids = {s["id"] for s in client.get("/api/cash/history?limit=100", headers=auth_cajero_a).json()}
    assert ids == {propia.id}


def test_history_gerente_ve_toda_la_sucursal(client, db, org, branch_a, cajero_a, auth_gerente_a, products_setup):
    _habilitar(db, org, "pos")
    otra = _otra_cajera(db, org, branch_a)
    vieja = _sesion_vieja(db, org, branch_a, cajero_a)
    ajena = _abrir_caja(db, org, branch_a, otra)
    ids = {s["id"] for s in client.get("/api/cash/history", headers=auth_gerente_a).json()}
    assert {vieja.id, ajena.id} <= ids


# --- 4. /api/sales/my-last --------------------------------------------------

def test_my_last_cajera_venta_de_ayer_404(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    _habilitar(db, org, "pos")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), dia=_ayer())
    assert client.get("/api/sales/my-last", headers=auth_cajero_a).status_code == 404
    hoy = _venta(db, org, branch_a, cajero_a, _v(products_setup))
    r = client.get("/api/sales/my-last", headers=auth_cajero_a)
    assert r.status_code == 200 and r.json()["id"] == hoy.id


def test_my_last_gerente_sigue_viendo_ayer(client, db, org, branch_a, gerente_a, auth_gerente_a, products_setup):
    _habilitar(db, org, "pos")
    ayer = _venta(db, org, branch_a, gerente_a, _v(products_setup), dia=_ayer())
    r = client.get("/api/sales/my-last", headers=auth_gerente_a)
    assert r.status_code == 200 and r.json()["id"] == ayer.id


# --- 5. /reports/command-center/stats --------------------------------------

def _cc(client, h):
    return client.get("/api/reports/command-center/stats", headers=h)


def test_command_center_gerente_solo_su_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_gerente_a, products_setup):
    _habilitar(db, org, "pos")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    r = _cc(client, auth_gerente_a)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["global"]["total_sales"] == 100.0
    assert d["branches_included"] == [branch_a.id]


def test_command_center_admin_toda_la_org(client, db, org, branch_a, branch_b, cajero_a, auth_admin, products_setup):
    _habilitar(db, org, "pos")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    d = _cc(client, auth_admin).json()
    assert d["global"]["total_sales"] == 300.0
    assert {branch_a.id, branch_b.id} <= set(d["branches_included"])


def test_command_center_vendedor_403(client, db, org, branch_a, products_setup):
    _habilitar(db, org, "pos")
    vendedor = _make_user(db, org, branch_a, "vendedor_a", Role.VENDEDOR); db.commit()
    assert _cc(client, _auth_header(vendedor)).status_code == 403
