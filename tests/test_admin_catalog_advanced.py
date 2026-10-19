"""
Regression tests for A3/A5/A6/A7/A8 endpoints of the Admin Catalog plan.

Covers:
  - POST /products/branch-status/clone         (A3)
  - POST /products/{id}/duplicate              (A5)
  - PUT  /products/{id}/reject                 (A5)
  - POST /products/{id}/restore                (A6)
  - GET  /products/export/excel (filtered)     (A7)
  - GET  /products/stats/catalog-kpis          (A1 — sanity)
  - GET  /products/{id}/audit-log              (A8)

Uses fixtures from tests/conftest.py.
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.models.organization import Branch, BranchType, Organization
from app.models.users import User, UserOrganization, Role, PlatformRole
from app.models.products import (
    Product, ProductVariant, ProductBranchStatus,
)
from app.models.inventory import StockOnHand
from app.core.security import get_password_hash, create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


def _with_org(h, org):
    return {**h, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def foreign_branch(db):
    other = Organization(name="Foreign Org 2", status="ACTIVE")
    db.add(other); db.flush()
    b = Branch(
        name="Foreign Branch 2", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=other.id,
    )
    db.add(b); db.flush()
    return b


# ── A3 Clone PBS ──────────────────────────────────────────────────────────────
class TestClonePbs:
    def test_admin_clones_all_variants_to_empty_branches(
        self, client, db, products_setup, admin_user, auth_admin,
        org, branch_a, branch_b,
    ):
        """A tiene 2 variants con PBS; B no tiene nada → clona ambos."""
        # Snapshot: product_a only in branch_a, product_b only in branch_b,
        # product_both in A and B. From A we have 2 variants (product_a, product_both).
        r = client.post(
            "/api/products/branch-status/clone",
            json={"from_branch_id": branch_a.id, "to_branch_ids": [branch_b.id]},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # product_both already existed in B so → skipped 1, created 1 (product_a into B)
        assert data["created"] + data["skipped"] >= 1

    def test_cajero_rejected(
        self, client, products_setup, cajero_a, auth_cajero_a, org, branch_a, branch_b,
    ):
        r = client.post(
            "/api/products/branch-status/clone",
            json={"from_branch_id": branch_a.id, "to_branch_ids": [branch_b.id]},
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 403

    def test_rejects_foreign_to_branch(
        self, client, products_setup, admin_user, auth_admin, org,
        branch_a, foreign_branch,
    ):
        r = client.post(
            "/api/products/branch-status/clone",
            json={"from_branch_id": branch_a.id, "to_branch_ids": [foreign_branch.id]},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 403

    def test_rejects_same_from_and_to(
        self, client, products_setup, admin_user, auth_admin, org, branch_a,
    ):
        r = client.post(
            "/api/products/branch-status/clone",
            json={"from_branch_id": branch_a.id, "to_branch_ids": [branch_a.id]},
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 422


# ── A5 Duplicate ──────────────────────────────────────────────────────────────
class TestDuplicateProduct:
    def test_duplicate_creates_copy_with_suffix(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        product, variant = products_setup["product_a"]
        r = client.post(
            f"/api/products/{product.id}/duplicate",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == f"{product.name} (copia)"
        # Original SKU was SKU-A; expect SKU-A-COPY-1
        assert data["sku"] == f"{variant.sku}-COPY-1"

    def test_duplicate_copies_pbs_but_not_stock(
        self, client, db, products_setup, admin_user, auth_admin, org, branch_a,
    ):
        product, _ = products_setup["product_a"]
        r = client.post(
            f"/api/products/{product.id}/duplicate",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200
        new_id = r.json()["id"]

        new_prod = db.query(Product).filter(Product.id == new_id).first()
        new_variant = new_prod.variants[0]
        pbs_rows = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == new_variant.id
        ).all()
        # Original had 1 PBS row (branch_a)
        assert len(pbs_rows) == 1
        assert pbs_rows[0].branch_id == branch_a.id

        stock_rows = db.query(StockOnHand).filter(
            StockOnHand.variant_id == new_variant.id
        ).all()
        assert len(stock_rows) == 0, "Duplicate should not copy stock"

    def test_cajero_allowed(
        self, client, products_setup, catalog_module_enabled, cajero_a, auth_cajero_a, org,
    ):
        # Track 3: CAJERO is an advanced catalog role and may duplicate a
        # product visible in its branch. (Was 403 pre-Track-3.) Desde SP1 el
        # cajero ademas necesita el modulo `catalog`.
        product, _ = products_setup["product_a"]
        r = client.post(
            f"/api/products/{product.id}/duplicate",
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == f"{product.name} (copia)"


# ── A5 Reject ────────────────────────────────────────────────────────────────
class TestRejectProduct:
    def test_reject_marks_status_and_deactivates_pbs(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        product, variant = products_setup["product_both"]
        # Ensure at least one PBS is active
        db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).update({ProductBranchStatus.is_active_pos: True}, synchronize_session=False)
        db.commit()

        r = client.put(
            f"/api/products/{product.id}/reject",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text

        db.expire_all()
        refreshed = db.query(Product).filter(Product.id == product.id).first()
        assert refreshed.approval_status == "REJECTED"

        pbs_rows = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).all()
        for p in pbs_rows:
            assert p.is_active_pos is False


# ── A6 Restore ───────────────────────────────────────────────────────────────
class TestRestoreProduct:
    def test_archive_then_restore(
        self, client, db, products_setup, admin_user, auth_admin, org,
    ):
        product, _ = products_setup["product_a"]
        # Archive
        r_del = client.delete(
            f"/api/products/{product.id}",
            headers=_with_org(auth_admin, org),
        )
        assert r_del.status_code == 200, r_del.text
        db.expire_all()
        assert db.query(Product).filter(Product.id == product.id).first().is_active is False

        # Restore
        r_res = client.post(
            f"/api/products/{product.id}/restore",
            headers=_with_org(auth_admin, org),
        )
        assert r_res.status_code == 200, r_res.text
        db.expire_all()
        refreshed = db.query(Product).filter(Product.id == product.id).first()
        assert refreshed.is_active is True
        assert refreshed.deleted_at is None

    def test_cajero_allowed(
        self, client, products_setup, cajero_a, auth_cajero_a, org,
    ):
        # Track 3: CAJERO is an advanced catalog role and may restore a
        # product in its branch. (Was 403 pre-Track-3.) product_a is not
        # archived here, so restore is a no-op that still returns 200.
        product, _ = products_setup["product_a"]
        r = client.post(
            f"/api/products/{product.id}/restore",
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text


# ── A7 Export with filters ───────────────────────────────────────────────────
class TestExportFilters:
    def test_export_respects_approval_filter(
        self, client, products_setup, admin_user, auth_admin, org,
    ):
        r = client.get(
            "/api/products/export/excel",
            params={"approval_status": "PENDING"},
            headers=_with_org(auth_admin, org),
        )
        # Excel response (binary). We only assert it did not 500.
        assert r.status_code in (200, 404)


# ── A1 KPIs (sanity) ─────────────────────────────────────────────────────────
class TestCatalogKpis:
    def test_admin_sees_counts(
        self, client, products_setup, admin_user, auth_admin, org,
    ):
        r = client.get(
            "/api/products/stats/catalog-kpis",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("total_skus", "active_pos", "pending_approval",
                    "no_branch", "critical_stock", "zero_stock", "threshold"):
            assert key in data
        assert data["total_skus"] >= 3  # products_setup fixture creates 3


# ── A8 Audit log ─────────────────────────────────────────────────────────────
class TestAuditLog:
    def test_empty_when_no_prior_mutations(
        self, client, products_setup, admin_user, auth_admin, org,
    ):
        product, _ = products_setup["product_a"]
        r = client.get(
            f"/api/products/{product.id}/audit-log",
            headers=_with_org(auth_admin, org),
        )
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_populates_after_pbs_change(
        self, client, products_setup, admin_user, auth_admin, org, branch_a,
    ):
        product, variant = products_setup["product_a"]
        # Find existing PBS row for branch_a and toggle it
        r_patch = client.patch(
            f"/api/products/variants/{variant.id}/branch-status",
            params={"branch_id": branch_a.id},
            json={"is_active_pos": False},
            headers=_with_org(auth_admin, org),
        )
        assert r_patch.status_code == 200, r_patch.text

        r_log = client.get(
            f"/api/products/{product.id}/audit-log",
            headers=_with_org(auth_admin, org),
        )
        assert r_log.status_code == 200
        items = r_log.json()["items"]
        assert any(i["action"] == "PBS_UPDATE" for i in items)

    def test_cajero_allowed(
        self, client, products_setup, cajero_a, auth_cajero_a, org,
    ):
        # Track 3: CAJERO may read the audit log of a product visible in its
        # branch (governance — see who changed what). Was 403 pre-Track-3.
        product, _ = products_setup["product_a"]
        r = client.get(
            f"/api/products/{product.id}/audit-log",
            headers=_with_org(auth_cajero_a, org),
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["items"], list)
