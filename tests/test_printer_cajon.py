"""Cajón de dinero (2026-11-06): el corte lo abre solo al cerrar turno y si la
sucursal lo tiene encendido; la apertura manual queda en la auditoría de caja."""
import base64

from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.pos_printer import PosPrinter
from tests.cobranza_helpers import _abrir_caja



def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _corte(client, h, sesion, **extra):
    r = client.post("/api/printer/print-cash-cut", json={"session_id": sesion.id, **extra}, headers=h)
    assert r.status_code == 200, r.text
    return base64.b64decode(r.json()["content_base64"])


def _kick():
    return PosPrinter("x").CMD["DRAWER"]


def test_el_corte_no_abre_el_cajon_por_omision(client, db, org, branch_a, cajero_a, auth_cajero_a):
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    assert _kick() not in _corte(client, _h(auth_cajero_a, org), sesion)


def test_el_corte_abre_el_cajon_si_se_pide(client, db, org, branch_a, cajero_a, auth_cajero_a):
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    assert _kick() in _corte(client, _h(auth_cajero_a, org), sesion, open_drawer=True)


def test_la_sucursal_con_el_cajon_apagado_manda_sobre_el_pedido(client, db, org, branch_a, cajero_a, auth_cajero_a):
    branch_a.open_drawer_on_print = False
    db.commit()
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    assert _kick() not in _corte(client, _h(auth_cajero_a, org), sesion, open_drawer=True)


def test_la_apertura_manual_queda_con_su_caja(client, db, org, branch_a, cajero_a, auth_cajero_a):
    sesion = _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/printer/drawer-opened", json={"printer_name": "POS-80"}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 204, r.text
    fila = db.query(CashAuditLog).filter(CashAuditLog.event_type == CashAuditEvent.DRAWER_OPENED_MANUAL).one()
    assert fila.session_id == sesion.id
    assert fila.organization_id == org.id
    assert fila.branch_id == branch_a.id
    assert fila.user_id == cajero_a.id
    assert fila.payload_json["printer_name"] == "POS-80"


def test_la_apertura_manual_sin_caja_abierta_tambien_queda(client, db, org, branch_a, cajero_a, auth_cajero_a):
    r = client.post("/api/printer/drawer-opened", json={}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 204, r.text
    fila = db.query(CashAuditLog).filter(CashAuditLog.event_type == CashAuditEvent.DRAWER_OPENED_MANUAL).one()
    assert fila.session_id is None
    assert fila.branch_id == branch_a.id


def test_la_apertura_manual_exige_sesion(client):
    assert client.post("/api/printer/drawer-opened", json={}).status_code == 401
