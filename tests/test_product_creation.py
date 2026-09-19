"""
Tests: Product creation — RBAC, branch scoping, stock init, duplicates, multi-tenancy.

Covers the audit scope for CAJERO/GERENTE/ADMINISTRADOR creating products:
  - Branch auto-scoping for CAJERO/GERENTE
  - Role gating for VENDEDOR / users without branch_id
  - Duplicate SKU per-org vs across orgs
  - Cross-tenant branch injection
  - Initial stock semantics on multi-branch HQ creation
  - End-to-end visibility in POS search

Shared fixtures (org, branch_a, branch_b, hq_branch, cajero_a, gerente_a,
admin_user, auth_*, ...) come from tests/conftest.py.
"""
import pytest
from decimal import Decimal

from app.models.users import User, UserOrganization, Role, PlatformRole
from app.models.organization import Organization, Branch, BranchType
from app.models.products import ProductVariant, ProductBranchStatus
from app.models.inventory import StockOnHand, InventoryMovement, MovementType
from app.models.modules import Module, OrganizationModule
from app.core.security import get_password_hash, create_access_token


# ── Extra fixtures specific to creation tests ────────────────────────────────
@pytest.fixture()
def catalog_module_enabled(db, org):
    """Enable the `catalog` module for the test org so require_module passes."""
    mod = db.query(Module).filter(Module.key == "catalog").first()
    if not mod:
        mod = Module(key="catalog", name="Catalog")
        db.add(mod)
        db.flush()
    db.add(OrganizationModule(
        organization_id=org.id, module_key="catalog", is_enabled=True
    ))
    db.flush()


def _make_extra_user(db, org, username, role, branch=None):
    u = User(
        username=username, password_hash=get_password_hash("test1234"),
        role=role, branch_id=branch.id if branch else None,
        is_active=True, platform_role=PlatformRole.NONE,
    )
    db.add(u); db.flush()
    db.add(UserOrganization(
        user_id=u.id, organization_id=org.id,
        org_role="MEMBER", is_active=True,
    ))
    db.flush()
    return u


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


@pytest.fixture()
def admin_no_branch(db, org):
    return _make_extra_user(db, org, "admin_nobranch", Role.ADMINISTRADOR)


@pytest.fixture()
def auth_admin_nobranch(admin_no_branch):
    return _auth(admin_no_branch)


@pytest.fixture()
def vendedor(db, org):
    return _make_extra_user(db, org, "vendedor_test", Role.VENDEDOR)


@pytest.fixture()
def auth_vendedor(vendedor):
    return _auth(vendedor)


@pytest.fixture()
def cajero_no_branch(db, org):
    return _make_extra_user(db, org, "cajero_nobranch", Role.CAJERO)


@pytest.fixture()
def auth_cajero_no_branch(cajero_no_branch):
    return _auth(cajero_no_branch)


@pytest.fixture()
def department(db, org):
    """A catalog department in the test org (required for CAJERO/GERENTE creates)."""
    from app.models.products import Department
    d = Department(name="Abarrotes", organization_id=org.id)
    db.add(d); db.flush()
    return d


@pytest.fixture()
def brand(db, org):
    """A brand in the test org (required for CAJERO/GERENTE creates)."""
    from app.models.products import Brand
    b = Brand(name="Marca Test", organization_id=org.id)
    db.add(b); db.flush()
    return b


@pytest.fixture()
def other_org_branch(db):
    """A branch in a different organization — used to test cross-tenant rejection."""
    other = Organization(name="Other Org", status="ACTIVE")
    db.add(other); db.flush()
    b = Branch(
        name="Foreign Branch", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=other.id,
    )
    db.add(b); db.flush()
    return b


# ── Helpers ──────────────────────────────────────────────────────────────────
def _payload(sku="SKU-NEW", price=100, **extras):
    return {
        "name": f"Test {sku}",
        "sku": sku,
        "price": price,
        "cost": 50,
        **extras,
    }


def _with_org(auth_headers, org):
    return {**auth_headers, "X-Organization-ID": str(org.id)}


# ── RBAC & branch scoping ────────────────────────────────────────────────────
class TestProductCreationRBAC:
    def test_cajero_creates_for_own_branch(
        self, client, db, catalog_module_enabled, org, branch_a,
        cajero_a, auth_cajero_a, department, brand,
    ):
        """CAJERO → product auto-scoped, stock + kardex + PBS all on branch A."""
        r = client.post(
            "/api/products/",
            json=_payload(
                sku="C-1", initial_stock=10,
                department_id=department.id, brand_id=brand.id,
            ),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text

        variant = db.query(ProductVariant).filter(ProductVariant.sku == "C-1").first()
        assert variant is not None

        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == variant.id).all()
        assert len(soh) == 1
        assert soh[0].branch_id == branch_a.id
        assert soh[0].qty_on_hand == Decimal("10")

        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).all()
        assert len(pbs) == 1
        assert pbs[0].branch_id == branch_a.id
        assert pbs[0].is_active_pos is True

        mov = db.query(InventoryMovement).filter(
            InventoryMovement.variant_id == variant.id
        ).all()
        assert len(mov) == 1
        assert mov[0].qty_change == Decimal("10")
        assert mov[0].movement_type == MovementType.ADJUSTMENT_IN

    def test_cajero_cannot_target_other_branch(
        self, client, catalog_module_enabled, org, branch_b,
        cajero_a, auth_cajero_a, department, brand,
    ):
        """CAJERO branch=A sending target_branch_ids=[B] → 403."""
        r = client.post(
            "/api/products/",
            json=_payload(
                sku="C-2", target_branch_ids=[branch_b.id],
                department_id=department.id, brand_id=brand.id,
            ),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 403

    def test_cajero_without_branch_id_rejected(
        self, client, catalog_module_enabled, org,
        cajero_no_branch, auth_cajero_no_branch,
    ):
        """A CAJERO with no branch_id cannot create — would leak a global product."""
        r = client.post(
            "/api/products/", json=_payload(sku="C-3"),
            headers=_with_org(auth_cajero_no_branch, org),
        )
        assert r.status_code == 403

    def test_vendedor_cannot_create(
        self, client, catalog_module_enabled, org, vendedor, auth_vendedor,
    ):
        """VENDEDOR (mobile-only role) is blocked by the role gate."""
        r = client.post(
            "/api/products/", json=_payload(sku="V-1"),
            headers=_with_org(auth_vendedor, org),
        )
        assert r.status_code == 403


# ── Validation ───────────────────────────────────────────────────────────────
class TestProductCreationValidation:
    def test_cajero_crea_sin_marca_ni_departamento(
        self, client, catalog_module_enabled, org, cajero_a, auth_cajero_a,
    ):
        """Una tienda nueva no tiene marcas ni departamentos y el cajero no
        puede crearlos: exigirlos lo dejaba sin forma de registrar nada."""
        r = client.post(
            "/api/products/", json=_payload(sku="SM-1"),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text
        assert r.json()["brand_id"] is None

    def test_cajero_sin_costo_sigue_rechazado(
        self, client, catalog_module_enabled, org, cajero_a, auth_cajero_a,
    ):
        body = _payload(sku="SC-1"); body.pop("cost")
        r = client.post("/api/products/", json=body, headers=_with_org(auth_cajero_a, org))
        assert r.status_code == 422

    def test_zero_price_rejected(
        self, client, catalog_module_enabled, org, cajero_a, auth_cajero_a,
    ):
        r = client.post(
            "/api/products/", json=_payload(sku="P-1", price=0),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 422

    def test_duplicate_sku_within_org_rejected(
        self, client, catalog_module_enabled, org, cajero_a, auth_cajero_a,
        department, brand,
    ):
        r1 = client.post(
            "/api/products/",
            json=_payload(sku="DUP-1", department_id=department.id, brand_id=brand.id),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/api/products/",
            json=_payload(sku="DUP-1", department_id=department.id, brand_id=brand.id),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r2.status_code == 409

    def test_hq_multibranch_initial_stock_rejected(
        self, client, catalog_module_enabled, org, branch_a, branch_b,
        admin_no_branch, auth_admin_nobranch,
    ):
        """HQ admin cannot dump initial_stock across multiple branches in one call."""
        r = client.post(
            "/api/products/",
            json=_payload(
                sku="M-1",
                target_branch_ids=[branch_a.id, branch_b.id],
                initial_stock=5,
            ),
            headers=_with_org(auth_admin_nobranch, org),
        )
        assert r.status_code == 422

    def test_cross_tenant_branch_rejected(
        self, client, catalog_module_enabled, org,
        admin_no_branch, auth_admin_nobranch, other_org_branch,
    ):
        """target_branch_ids referencing another org's branch must be rejected."""
        r = client.post(
            "/api/products/",
            json=_payload(sku="X-1", target_branch_ids=[other_org_branch.id]),
            headers=_with_org(auth_admin_nobranch, org),
        )
        assert r.status_code == 422


# ── Catalog scope / Multi-tenancy ────────────────────────────────────────────
class TestProductCreationScope:
    def test_admin_creates_global_product(
        self, client, db, catalog_module_enabled, org,
        admin_no_branch, auth_admin_nobranch,
    ):
        """HQ admin without branch_id and without target_branch_ids → no PBS rows."""
        r = client.post(
            "/api/products/", json=_payload(sku="G-1"),
            headers=_with_org(auth_admin_nobranch, org),
        )
        assert r.status_code == 200, r.text
        variant = db.query(ProductVariant).filter(ProductVariant.sku == "G-1").first()
        assert variant is not None
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).all()
        assert len(pbs) == 0, "Global product should not create ProductBranchStatus rows"

    def test_product_visible_in_own_branch_pos_search(
        self, client, catalog_module_enabled, org,
        cajero_a, auth_cajero_a, department, brand,
    ):
        """End-to-end: CAJERO creates → POS search of same CAJERO finds it."""
        r = client.post(
            "/api/products/",
            json=_payload(sku="VIS-1", department_id=department.id, brand_id=brand.id),
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200
        search = client.get(
            "/api/products/pos/search?q=VIS",
            headers=_with_org(auth_cajero_a, org),
        )
        assert search.status_code == 200
        skus = [p.get("sku") for p in search.json()]
        assert "VIS-1" in skus
