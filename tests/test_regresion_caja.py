"""Regresiones de la auditoría funcional del backend (2026-09-22) — caja.

* A-3 `close-guided` no comparaba la sucursal: un GERENTE de A cerraba la caja
  de un cajero de B.
* M-3 `close-guided` solo aceptaba GERENTE: la dueña (ADMINISTRADOR) recibía
  403 al cerrar el turno de su cajera.
* A-4 `GET /cash/branch-summary?branch_id=` solo filtraba por organización: un
  GERENTE de A veía el corte consolidado de B.
* M-4 `PATCH /cash/sessions/{id}/opening-balance` tenía la misma fuga que A-3:
  un GERENTE de A reescribía el fondo inicial de una sesión de B.
"""
from decimal import Decimal

from app.models.cash import CashSession, CashSessionStatus
from app.models.users import Role
from conftest import _make_user


def _h(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


def _abrir(db, org, branch, user, opening=Decimal("100")):
    s = CashSession(
        user_id=user.id, branch_id=branch.id, organization_id=org.id,
        opening_balance=opening, status=CashSessionStatus.OPEN,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------- M-3
def test_m3_administrador_puede_cerrar_el_turno_de_su_cajera(
    client, db, org, branch_a, cajero_a, admin_user, auth_admin
):
    session = _abrir(db, org, branch_a, cajero_a)

    r = client.post(
        f"/api/cash/sessions/{session.id}/close-guided",
        json={"counted_cash": "100.00", "notes": "cierre remoto por la dueña"},
        headers=_h(auth_admin, org),
    )
    assert r.status_code == 200, r.text
    db.refresh(session)
    assert session.status == CashSessionStatus.CLOSED


# ---------------------------------------------------------------- A-3
def test_a3_gerente_no_cierra_la_caja_de_otra_sucursal(
    client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a
):
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_a3", Role.CAJERO)
    session_b = _abrir(db, org, branch_b, cajero_b, Decimal("50"))
    assert gerente_a.branch_id == branch_a.id

    r = client.post(
        f"/api/cash/sessions/{session_b.id}/close-guided",
        json={"counted_cash": "50.00", "notes": "cierre desde otra sucursal"},
        headers=_h(auth_gerente_a, org),
    )
    assert r.status_code == 403, r.text
    db.refresh(session_b)
    assert session_b.status == CashSessionStatus.OPEN


def test_a3_gerente_si_cierra_la_caja_de_su_propia_sucursal(
    client, db, org, branch_a, cajero_a, gerente_a, auth_gerente_a
):
    session_a = _abrir(db, org, branch_a, cajero_a, Decimal("50"))
    r = client.post(
        f"/api/cash/sessions/{session_a.id}/close-guided",
        json={"counted_cash": "50.00", "notes": "cierre del gerente de la sucursal"},
        headers=_h(auth_gerente_a, org),
    )
    assert r.status_code == 200, r.text
    db.refresh(session_a)
    assert session_a.status == CashSessionStatus.CLOSED


def test_a3_el_cajero_sigue_cerrando_su_propio_turno(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    session = _abrir(db, org, branch_a, cajero_a, Decimal("50"))
    r = client.post(
        f"/api/cash/sessions/{session.id}/close-guided",
        json={"counted_cash": "50.00", "notes": "cierre propio"},
        headers=_h(auth_cajero_a, org),
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- A-4
def test_a4_gerente_no_ve_el_corte_de_otra_sucursal(
    client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a
):
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_a4", Role.CAJERO)
    _abrir(db, org, branch_b, cajero_b, Decimal("200"))

    r = client.get("/api/cash/branch-summary", params={"branch_id": branch_b.id},
                   headers=_h(auth_gerente_a, org))
    assert r.status_code == 403, r.text


def test_a4_gerente_si_ve_el_corte_de_la_suya(
    client, db, org, branch_a, cajero_a, gerente_a, auth_gerente_a
):
    _abrir(db, org, branch_a, cajero_a, Decimal("200"))
    r = client.get("/api/cash/branch-summary", params={"branch_id": branch_a.id},
                   headers=_h(auth_gerente_a, org))
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == branch_a.id


def test_a4_admin_sigue_consolidando_cualquier_sucursal(
    client, db, org, branch_b, admin_user, auth_admin
):
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_a4b", Role.CAJERO)
    _abrir(db, org, branch_b, cajero_b, Decimal("200"))
    r = client.get("/api/cash/branch-summary", params={"branch_id": branch_b.id},
                   headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == branch_b.id


# ---------------------------------------------------------------- M-4
_CORRECCION = {"opening_balance": "777.00", "reason": "Fondo capturado mal al abrir"}


def test_m4_gerente_no_corrige_el_fondo_de_otra_sucursal(
    client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a
):
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_m4", Role.CAJERO)
    session_b = _abrir(db, org, branch_b, cajero_b, Decimal("100"))
    assert gerente_a.branch_id == branch_a.id

    r = client.patch(f"/api/cash/sessions/{session_b.id}/opening-balance",
                     json=_CORRECCION, headers=_h(auth_gerente_a, org))
    assert r.status_code == 403, r.text
    db.refresh(session_b)
    assert session_b.opening_balance == Decimal("100")


def test_m4_gerente_si_corrige_el_fondo_de_su_sucursal(
    client, db, org, branch_a, cajero_a, gerente_a, auth_gerente_a
):
    session_a = _abrir(db, org, branch_a, cajero_a, Decimal("100"))
    r = client.patch(f"/api/cash/sessions/{session_a.id}/opening-balance",
                     json=_CORRECCION, headers=_h(auth_gerente_a, org))
    assert r.status_code == 200, r.text
    db.refresh(session_a)
    assert session_a.opening_balance == Decimal("777.00")


def test_m4_admin_corrige_cualquier_sucursal(
    client, db, org, branch_b, admin_user, auth_admin
):
    cajero_b = _make_user(db, org, branch_b, "cajero_b_reg_m4b", Role.CAJERO)
    session_b = _abrir(db, org, branch_b, cajero_b, Decimal("100"))
    r = client.patch(f"/api/cash/sessions/{session_b.id}/opening-balance",
                     json=_CORRECCION, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.refresh(session_b)
    assert session_b.opening_balance == Decimal("777.00")


def test_m4_el_cajero_sigue_corrigiendo_su_propio_fondo(
    client, db, org, branch_a, cajero_a, auth_cajero_a
):
    session = _abrir(db, org, branch_a, cajero_a, Decimal("100"))
    r = client.patch(f"/api/cash/sessions/{session.id}/opening-balance",
                     json=_CORRECCION, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.refresh(session)
    assert session.opening_balance == Decimal("777.00")
