"""
Regression tests for /admin/catalog hardening PRs (P1–P5, P7).

Covers:
  - DELETE /api/products/{id} — RBAC + PBS/Stock cascade       (PR #43)
  - POST /branch-status/bulk-toggle — cross-org tenancy guards  (PR #40)
  - PUT /branch-status/{id} — audit log on every mutation       (PR #44)
  - PUT /packaging/{id} — Pydantic numeric validation           (PR #40)
  - POST /products/ — explicit approval_status per role         (PR #42)

Uses fixtures from tests/conftest.py (org, branch_a, branch_b, hq_branch,
cajero_a, gerente_a, admin_user, products_setup, auth_*).
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.models.users import User, UserOrganization, Role, PlatformRole
from app.models.organization import Organization, Branch, BranchType
from app.models.products import (
    Product, ProductVariant, ProductBranchStatus, PackagingUnit,
)
from app.models.inventory import StockOnHand
from app.models.platform import PlatformAuditLog
from app.core.security import get_password_hash, create_access_token


# ── Extra fixtures ────────────────────────────────────────────────────────────

def _auth(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


def _with_org(auth_headers, org):
    return {**auth_headers, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def foreign_org_setup(db):
    """A second org with its own branch and variant — for cross-tenant tests."""
    other = Organization(name="Foreign Org", status="ACTIVE")
    db.add(other); db.flush()

    f_branch = Branch(
        name="Foreign Branch", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=other.id,
    )
    db.add(f_branch); db.flush()

    f_product = Product(name="Foreign Product", organization_id=other.id, is_active=True)
    db.add(f_product); db.flush()

    f_variant = ProductVariant(
        product_id=f_product.id, sku="FOREIGN-1",
        price=Decimal("99"), cost=Decimal("50"),
        organization_id=other.id,
    )
    db.add(f_variant); db.flush()

    return {"org": other, "branch": f_branch, "variant": f_variant}


# ── DELETE cascade & RBAC — PR #43 ────────────────────────────────────────────
class TestDeleteProductCascade:
    def test_cajero_can_soft_delete_product(
        self, client, db, products_setup, cajero_a, auth_cajero_a, org,
    ):
        """PR #43 removed the duplicate non-RBAC handler that let a CAJERO
        *physically* delete a product. Track 3 then made CAJERO an advanced
        catalog role: it may now *soft*-delete (archive) a product visible in
        its branch through the single RBAC + tenancy-guarded handler."""
        product, _ = products_setup["product_a"]
        r = client.delete(
            f"/api/products/{product.id}",
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        p = db.query(Product).filter(Product.id == product.id).first()
        assert p.is_active is False
        assert p.deleted_at is not None

    def test_admin_delete_cascades_to_pbs_and_stock(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        """DELETE as admin must soft-delete product + flip PBS flags + stock."""
        product, variant = products_setup["product_a"]

        r = client.delete(
            f"/api/products/{product.id}",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text

        db.expire_all()
        p = db.query(Product).filter(Product.id == product.id).first()
        assert p.is_active is False
        assert p.deleted_at is not None

        # PBS flipped on every row for the variant
        pbs_rows = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).all()
        assert len(pbs_rows) > 0
        for r_ in pbs_rows:
            assert r_.is_active_pos is False
            assert r_.is_active_hq is False
            assert r_.is_visible is False

        # StockOnHand flipped
        stock_rows = db.query(StockOnHand).filter(
            StockOnHand.variant_id == variant.id
        ).all()
        assert len(stock_rows) > 0
        for s in stock_rows:
            assert s.is_active is False


# ── Bulk-toggle cross-org rejection — PR #40 ──────────────────────────────────
class TestBulkToggleTenancy:
    def test_rejects_cross_org_variant(
        self, client, products_setup, foreign_org_setup,
        admin_user, auth_admin, org, branch_a,
    ):
        """variant_id from a different org → 403 before any mutation."""
        foreign_variant = foreign_org_setup["variant"]
        r = client.post(
            "/api/products/branch-status/bulk-toggle",
            json={
                "variant_ids": [foreign_variant.id],
                "branch_ids": [branch_a.id],
                "is_active_pos": True,
            },
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 403
        assert "fuera del tenant" in r.json().get("detail", "").lower()

    def test_rejects_cross_org_branch(
        self, client, products_setup, foreign_org_setup,
        admin_user, auth_admin, org,
    ):
        """branch_id from a different org → 403 before any mutation."""
        _, variant = products_setup["product_a"]
        foreign_branch = foreign_org_setup["branch"]
        r = client.post(
            "/api/products/branch-status/bulk-toggle",
            json={
                "variant_ids": [variant.id],
                "branch_ids": [foreign_branch.id],
                "is_active_pos": True,
            },
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 403

    def test_happy_path_updates_count(
        self, client, db, products_setup, admin_user, auth_admin,
        org, branch_a, branch_b,
    ):
        """Normal cross-branch toggle — count matches variants × branches."""
        _, var_a = products_setup["product_a"]
        _, var_b = products_setup["product_b"]
        r = client.post(
            "/api/products/branch-status/bulk-toggle",
            json={
                "variant_ids": [var_a.id, var_b.id],
                "branch_ids": [branch_a.id, branch_b.id],
                "is_active_pos": False,
            },
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text
        assert r.json()["updated_records"] == 4


# ── Packaging Pydantic validation — PR #40 ────────────────────────────────────
class TestPackagingValidation:
    def test_negative_price_rejected(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        _, variant = products_setup["product_a"]
        pkg = PackagingUnit(
            variant_id=variant.id, name="Caja", barcode=None,
            units_per_package=Decimal("10"), package_price=Decimal("90"),
            organization_id=org.id,
        )
        db.add(pkg); db.flush()

        r = client.put(
            f"/api/products/packaging/{pkg.id}",
            json={"package_price": -10},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 422

    def test_zero_units_per_package_rejected(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        _, variant = products_setup["product_a"]
        pkg = PackagingUnit(
            variant_id=variant.id, name="Caja", barcode=None,
            units_per_package=Decimal("10"), package_price=Decimal("90"),
            organization_id=org.id,
        )
        db.add(pkg); db.flush()

        r = client.put(
            f"/api/products/packaging/{pkg.id}",
            json={"units_per_package": 0},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 422


# ── PBS audit log — PR #44 ────────────────────────────────────────────────────
class TestPBSAudit:
    def test_put_branch_status_writes_audit_row(
        self, client, db, products_setup, admin_user, auth_admin,
        org, branch_a,
    ):
        _, variant = products_setup["product_a"]
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id,
            ProductBranchStatus.branch_id == branch_a.id,
        ).first()
        assert pbs is not None

        pre = db.query(PlatformAuditLog).count()
        r = client.put(
            f"/api/products/branch-status/{pbs.id}",
            json={"is_active_pos": False, "is_visible": False},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text

        post = db.query(PlatformAuditLog).count()
        assert post == pre + 1
        latest = db.query(PlatformAuditLog).order_by(
            PlatformAuditLog.id.desc()
        ).first()
        assert latest.action == "PBS_UPDATE"
        assert latest.entity_type == "ProductBranchStatus"
        assert str(variant.id) in latest.payload

    def test_put_branch_status_noop_skips_audit(
        self, client, db, products_setup, admin_user, auth_admin,
        org, branch_a,
    ):
        _, variant = products_setup["product_a"]
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id,
            ProductBranchStatus.branch_id == branch_a.id,
        ).first()
        pre = db.query(PlatformAuditLog).count()
        r = client.put(
            f"/api/products/branch-status/{pbs.id}",
            json={"is_active_pos": pbs.is_active_pos},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200
        post = db.query(PlatformAuditLog).count()
        assert post == pre, "No-op writes must not leave audit rows"


# ── Explicit approval_status — PR #42 ─────────────────────────────────────────
class TestApprovalStatusExplicit:
    def test_admin_create_is_approved(
        self, client, db, catalog_module_enabled,
        admin_user, auth_admin, org, branch_a,
    ):
        r = client.post(
            "/api/products/",
            json={
                "name": "Admin Product",
                "sku": "ADM-AP-1",
                "price": 100, "cost": 50,
                "target_branch_ids": [branch_a.id],
                "initial_stock": 0,
            },
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text
        prod = db.query(Product).filter(
            ProductVariant.sku == "ADM-AP-1",
        ).join(ProductVariant).first()
        assert prod is not None
        assert prod.approval_status == "APPROVED"
        assert prod.created_by_user_id == admin_user.id

    def test_cajero_create_is_approved(
        self, client, db, catalog_module_enabled,
        cajero_a, auth_cajero_a, org,
    ):
        # D4: a non-admin creator (CAJERO/GERENTE) must supply department_id
        # and brand_id, else the endpoint answers 422.
        from app.models.products import Department, Brand
        dept = Department(name="Abarrotes", organization_id=org.id)
        brand = Brand(name="Marca X", organization_id=org.id)
        db.add(dept); db.add(brand); db.flush()

        r = client.post(
            "/api/products/",
            json={
                "name": "Cajero Product",
                "sku": "CAJ-P-1",
                "price": 50, "cost": 20,
                "department_id": dept.id,
                "brand_id": brand.id,
                "initial_stock": 1,
            },
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text
        prod = db.query(Product).filter(
            ProductVariant.sku == "CAJ-P-1",
        ).join(ProductVariant).first()
        assert prod is not None
        # Track 3 / PR #42 revision: products are created APPROVED regardless of
        # role — CAJERO/GERENTE see their product live immediately; the approval
        # gate is intentionally out of scope (see create_product docstring).
        assert prod.approval_status == "APPROVED"
        assert prod.created_by_user_id == cajero_a.id
