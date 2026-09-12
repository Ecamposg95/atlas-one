"""Prueba TDD para `folio_search` en `GET /api/sales/` (C-09, C-10).

Devoluciones necesitan encontrar un ticket por folio exacto: "A-540" debe
encontrar el mismo ticket que "A-0540". Antes de este cambio, el backend
ignoraba cualquier parámetro `search`/`folio_search` (422 o lista completa) y
`ReturnModal.tsx` raspaba las 20 ventas más recientes esperando que el folio
buscado estuviera ahí.
"""
from decimal import Decimal

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch, BranchType, Organization
from app.models.users import PlatformRole, Role, User, UserOrganization


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


def _with_org(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


def _preparar_pos(db, org, branch, user):
    """Habilita el módulo POS y abre una sesión de caja — mismo setup que
    tests/test_sales_idempotency.py, necesario para que create_sale acepte
    pagos en efectivo."""
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos").first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    if db.query(CashSession).filter(
        CashSession.user_id == user.id, CashSession.closed_at.is_(None)).first() is None:
        db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                            opening_balance=Decimal("0"), status="OPEN"))
    db.commit()


@pytest.fixture()
def seeded_sale(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Una venta pagada real. Devuelve (folio_str, headers_del_cajero_con_org)."""
    _preparar_pos(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    h = _with_org(auth_cajero_a, org)
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": "100.00"}],
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["folio"], h  # e.g. "A-1"


class TestFolioSearch:
    def test_encuentra_con_y_sin_ceros_a_la_izquierda(self, client, seeded_sale):
        folio, h = seeded_sale
        series, numero = folio.split("-")

        # Sin ceros y en minúsculas
        buscado = f"{series.lower()}-{int(numero)}"
        r = client.get("/api/sales/", params={"folio_search": buscado}, headers=h)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["series"] == series
        assert items[0]["folio"] == int(numero)
        sale_id = items[0]["id"]

        # Con ceros a la izquierda (como lo muestra saleLabel en el POS)
        con_ceros = f"{series}-{str(int(numero)).zfill(4)}"
        r2 = client.get("/api/sales/", params={"folio_search": con_ceros}, headers=h)
        assert [i["id"] for i in r2.json()["items"]] == [sale_id]

    def test_sin_digitos_no_regresa_toda_la_lista(self, client, seeded_sale):
        _, h = seeded_sale
        r = client.get("/api/sales/", params={"folio_search": "ABC"}, headers=h)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_no_cruza_organizaciones(self, client, db, seeded_sale):
        folio, _ = seeded_sale

        otra_org = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra_org); db.flush()
        otra_branch = Branch(
            name="Otra Sucursal", branch_type=BranchType.HQ,
            can_sell=False, is_active=True, is_headquarters=True,
            organization_id=otra_org.id,
        )
        db.add(otra_branch); db.flush()
        otro_admin = User(
            username="admin_otra_org", password_hash=get_password_hash("test1234"),
            role=Role.ADMINISTRADOR, branch_id=otra_branch.id, is_active=True,
            platform_role=PlatformRole.NONE,
        )
        db.add(otro_admin); db.flush()
        db.add(UserOrganization(user_id=otro_admin.id, organization_id=otra_org.id,
                                 org_role="MEMBER", is_active=True))
        db.commit()

        h = _with_org(_auth(otro_admin), otra_org)
        r = client.get("/api/sales/", params={"folio_search": folio}, headers=h)
        assert r.status_code == 200
        assert r.json()["items"] == []
