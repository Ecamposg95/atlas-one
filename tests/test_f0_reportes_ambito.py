"""F0 seguridad: arqueos y centro de mando respetan el ámbito por rol.

Dueño y administrador ven la organización; gerente y caja, solo su sucursal.
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.models.cash import CashSession, CashSessionStatus
from tests.test_reports_dashboard import _v, _venta


def _corte(db, branch, user):
    s = CashSession(user_id=user.id, branch_id=branch.id, status=CashSessionStatus.CLOSED,
                    opening_balance=Decimal("100"), closing_balance=Decimal("100"),
                    closed_at=datetime.now(timezone.utc))
    db.add(s)
    db.flush()
    return s


def test_arqueos_cajero_y_gerente_solo_su_sucursal(client, db, branch_a, branch_b, cajero_a, admin_user,
                                                    auth_cajero_a, auth_gerente_a, auth_admin):
    propio = _corte(db, branch_a, cajero_a)
    ajeno = _corte(db, branch_b, admin_user)
    for h in (auth_cajero_a, auth_gerente_a):
        r = client.get("/api/reports/audit/discrepancies", headers=h)
        assert r.status_code == 200
        assert [x["session_id"] for x in r.json()] == [propio.id]
    todos = client.get("/api/reports/audit/discrepancies", headers=auth_admin).json()
    assert {x["session_id"] for x in todos} == {propio.id, ajeno.id}


def test_arqueos_sin_sucursal_asignada_no_ve_nada(client, db, branch_a, cajero_a, auth_vendedor_sin_sucursal):
    _corte(db, branch_a, cajero_a)
    r = client.get("/api/reports/audit/discrepancies", headers=auth_vendedor_sin_sucursal)
    assert r.status_code == 200 and r.json() == []


def test_centro_de_mando_gerente_solo_su_sucursal(client, db, org, branch_a, branch_b, cajero_a,
                                                  auth_gerente_a, auth_admin, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")

    g = client.get("/api/reports/command-center/stats", headers=auth_gerente_a).json()
    assert g["global"]["total_sales"] == 100.0 and g["global"]["total_tickets"] == 1
    assert [b["id"] for b in g["branches"]] == [branch_a.id]
    assert g["branches_included"] == [branch_a.id]
    assert sum(g["payment_methods"].values()) == 100.0
    assert all(a["source"] == branch_a.name for a in g["alerts"])

    a = client.get("/api/reports/command-center/stats", headers=auth_admin).json()
    assert a["global"]["total_sales"] == 300.0
    assert {branch_a.id, branch_b.id} <= {b["id"] for b in a["branches"]}


def test_centro_de_mando_cajero_sigue_en_403(client, auth_cajero_a):
    assert client.get("/api/reports/command-center/stats", headers=auth_cajero_a).status_code == 403
