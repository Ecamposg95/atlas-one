"""``/api/products/{...}/branch-status`` family of endpoints — manage
ProductBranchStatus (commercial enablement) per variant/branch.

Endpoints (6):
    POST   /bulk-branch-status                    (bulk enable/disable)
    GET    /{product_id}/branch-status            (read all PBS for product)
    PUT    /branch-status/{status_id}             (update single PBS)
    POST   /branch-status/bulk-toggle             (bulk toggle is_active_pos)
    POST   /branch-status/clone                   (clone PBS branch -> branches)
    PATCH  /variants/{variant_id}/branch-status   (upsert PBS for variant)

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Product, ProductVariant, StockOnHand, User, ProductBranchStatus,
)
from app.core.security import get_current_user
from app.crud.products import (
    get_variant_if_visible,
    _is_admin,
    resolve_pbs_target_branch,
    update_branch_override,
    assert_variants_belong_to_org,
    assert_branches_belong_to_org,
    log_pbs_change,
)
from app.modules.products.schemas import (
    BranchStatusUpdate, PBSResponse,
    BulkToggleBranchStatusRequest, BranchStatusFlagsUpdate,
    PbsCloneRequest, PbsCloneResponse,
)

from ._shared import variante_principal

logger = logging.getLogger(__name__)

router = APIRouter()


class BulkEnableSchema(BaseModel):
    variant_ids: List[str]
    branch_ids: List[int]
    is_active: bool = True


@router.post("/bulk-branch-status")
def bulk_branch_status(
    payload: BulkEnableSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # Scope
):
    """
    Enable/Disable multiple products for multiple branches at once.
    Creates StockOnHand records if they don't exist.
    """
    if current_user.role not in ["ADMINISTRADOR", "GERENTE", "DUEÑO"]:
        raise HTTPException(status_code=403, detail="Restricted to Admin")

    # Tenancy guard: reject any variant_id or branch_id not owned by this org
    # before mutating anything.
    variant_ids = assert_variants_belong_to_org(db, payload.variant_ids, org_id)
    branch_ids = assert_branches_belong_to_org(db, payload.branch_ids, org_id)

    count = 0
    try:
        for bid in branch_ids:
            existing_stocks = db.query(StockOnHand).filter(
                StockOnHand.branch_id == bid,
                StockOnHand.organization_id == org_id,
                StockOnHand.variant_id.in_(variant_ids),
            ).all()

            existing_map = {s.variant_id: s for s in existing_stocks}

            for vid in variant_ids:
                if vid in existing_map:
                    existing_map[vid].is_active = payload.is_active
                else:
                    new_stock = StockOnHand(
                        branch_id=bid,
                        variant_id=vid,
                        qty_on_hand=0,
                        is_active=payload.is_active,
                        organization_id=org_id,
                    )
                    db.add(new_stock)
                count += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("BULK_BRANCH_STATUS_FAILED org_id=%s", org_id)
        raise HTTPException(status_code=500, detail="Error al actualizar el estado de los productos en la sucursal.")

    return {"message": "Bulk updated successfully", "updated_records": count}

# ===========================
# COMMERCIAL ENABLEMENT (ProductBranchStatus) ENDPOINTS
# ===========================

@router.get("/{product_id}/branch-status", response_model=List)
def get_product_branch_status(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Get commercial enablement status for a product across all branches.
    Returns ProductBranchStatus records with branch names.
    """
    from app.models.organization import Branch

    # Get main variant for this product
    product = db.query(Product).filter(
        Product.id == product_id,
        or_(Product.organization_id == org_id, Product.organization_id == None)
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # La principal es la primera VIVA: con `variants[0]` la matriz mostraba el
    # PBS de una talla retirada (o nada) en cuanto se retiraba la primera.
    principal = variante_principal(product)
    if principal is None:
        raise HTTPException(status_code=404, detail="Product not found")

    variant_id = principal.id

    # Get all branch statuses for this variant
    statuses = db.query(ProductBranchStatus, Branch).join(
        Branch, ProductBranchStatus.branch_id == Branch.id
    ).filter(
        ProductBranchStatus.variant_id == variant_id,
        ProductBranchStatus.organization_id == org_id
    ).all()

    result = []
    for status, branch in statuses:
        result.append({
            "id": status.id,
            "variant_id": status.variant_id,
            "branch_id": status.branch_id,
            "branch_name": branch.name,
            "is_active_pos": status.is_active_pos,
            "is_active_hq": status.is_active_hq,
            "is_visible": status.is_visible,
            "price_override": status.price_override
        })

    return result


@router.put("/branch-status/{status_id}")
def update_branch_status(
    status_id: str,
    update_data: BranchStatusFlagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Update commercial enablement flags for a specific variant-branch combination.
    Every applied field is written to the platform audit log.
    """
    if current_user.role not in ["ADMINISTRADOR", "GERENTE", "DUEÑO"]:
        raise HTTPException(status_code=403, detail="Restricted to Admin")

    pbs = db.query(ProductBranchStatus).filter(
        ProductBranchStatus.id == status_id,
        ProductBranchStatus.organization_id == org_id,
    ).first()

    if not pbs:
        raise HTTPException(status_code=404, detail="Branch status not found")

    data = update_data.model_dump(exclude_unset=True)
    before_snapshot = {}
    after_snapshot = {}
    for field in ("is_active_pos", "is_active_hq", "is_visible",
                  "price_override", "min_stock_alert", "max_stock_limit"):
        if field in data:
            old_val = getattr(pbs, field)
            new_val = data[field]
            if old_val == new_val:
                continue
            before_snapshot[field] = old_val
            after_snapshot[field] = new_val
            setattr(pbs, field, new_val)

    if before_snapshot:
        log_pbs_change(
            db,
            actor_user_id=current_user.id,
            action="PBS_UPDATE",
            pbs_id=pbs.id,
            variant_id=pbs.variant_id,
            branch_id=pbs.branch_id,
            before=before_snapshot,
            after=after_snapshot,
        )

    db.commit()
    return {"message": "Branch status updated", "id": status_id, "updated_fields": list(after_snapshot.keys())}

@router.post("/branch-status/bulk-toggle")
def bulk_toggle_branch_status(
    payload: BulkToggleBranchStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Bulk enable/disable products for POS across multiple branches.
    Creates ProductBranchStatus records if they don't exist.

    Tenancy: `variant_ids` and `branch_ids` are validated to belong to the
    active org BEFORE any mutation. PBS and StockOnHand queries also carry
    `organization_id == org_id` as defense-in-depth.
    """
    if current_user.role not in ["ADMINISTRADOR", "GERENTE", "DUEÑO"]:
        raise HTTPException(status_code=403, detail="Restricted to Admin")

    variant_ids = assert_variants_belong_to_org(db, payload.variant_ids, org_id)
    branch_ids = assert_branches_belong_to_org(db, payload.branch_ids, org_id)
    is_active_pos = payload.is_active_pos

    count = 0
    try:
        for bid in branch_ids:
            for vid in variant_ids:
                existing = db.query(ProductBranchStatus).filter(
                    ProductBranchStatus.variant_id == vid,
                    ProductBranchStatus.branch_id == bid,
                    ProductBranchStatus.organization_id == org_id,
                ).first()

                if existing:
                    old_val = existing.is_active_pos
                    existing.is_active_pos = is_active_pos
                    if payload.is_active_hq is not None:
                        existing.is_active_hq = payload.is_active_hq
                    if payload.is_visible is not None:
                        existing.is_visible = payload.is_visible
                    if old_val != is_active_pos:
                        log_pbs_change(
                            db,
                            actor_user_id=current_user.id,
                            action="PBS_BULK_TOGGLE",
                            pbs_id=existing.id,
                            variant_id=vid,
                            branch_id=bid,
                            before={"is_active_pos": old_val},
                            after={"is_active_pos": is_active_pos},
                        )
                else:
                    new_status = ProductBranchStatus(
                        variant_id=vid,
                        branch_id=bid,
                        is_active_pos=is_active_pos,
                        is_active_hq=payload.is_active_hq if payload.is_active_hq is not None else False,
                        is_visible=payload.is_visible if payload.is_visible is not None else is_active_pos,
                        organization_id=org_id,
                    )
                    db.add(new_status)
                    db.flush()  # need new_status.id for the audit row
                    log_pbs_change(
                        db,
                        actor_user_id=current_user.id,
                        action="PBS_BULK_CREATE",
                        pbs_id=new_status.id,
                        variant_id=vid,
                        branch_id=bid,
                        after={
                            "is_active_pos": is_active_pos,
                            "is_active_hq": new_status.is_active_hq,
                            "is_visible": new_status.is_visible,
                        },
                    )

                    existing_stock = db.query(StockOnHand).filter(
                        StockOnHand.variant_id == vid,
                        StockOnHand.branch_id == bid,
                        StockOnHand.organization_id == org_id,
                    ).first()

                    if not existing_stock:
                        new_stock = StockOnHand(
                            variant_id=vid,
                            branch_id=bid,
                            qty_on_hand=0,
                            is_active=is_active_pos,
                            organization_id=org_id,
                        )
                        db.add(new_stock)

                count += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("BULK_TOGGLE_BRANCH_STATUS_FAILED org_id=%s", org_id)
        raise HTTPException(status_code=500, detail="Error al actualizar el estado POS de los productos.")

    return {"message": "Bulk toggle complete", "updated_records": count}


# ---------------------------------------------------------------------------
# A3 — Clone PBS from one branch to one or more branches
# ---------------------------------------------------------------------------
_PBS_CLONEABLE_FIELDS = (
    "is_active_pos",
    "is_active_hq",
    "is_visible",
    "price_override",
    "min_stock_alert",
    "max_stock_limit",
)


@router.post("/branch-status/clone", response_model=PbsCloneResponse)
def clone_branch_status(
    payload: PbsCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Replica la configuración PBS de una sucursal origen a N sucursales destino.

    - Admin-only.
    - Sin `variant_ids`: clona todas las variantes que tengan PBS en
      `from_branch_id` (caso "abrir sucursal nueva desde una existente").
    - Con `variant_ids`: clona solo esas (validadas contra el tenant).
    - `overwrite=False` (default): si una sucursal destino ya tiene PBS
      para una variante, se deja intacto. `overwrite=True`: se pisa.
    - Emite `PBS_BULK_CREATE` / `PBS_BULK_TOGGLE` en el audit log por fila
      afectada.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Restringido a ADMIN / DUEÑO")

    # Validación tenancy
    from_branch = assert_branches_belong_to_org(db, [payload.from_branch_id], org_id)
    if not from_branch:
        raise HTTPException(status_code=422, detail="from_branch_id requerido")
    to_branch_ids = assert_branches_belong_to_org(db, payload.to_branch_ids, org_id)
    if not to_branch_ids:
        raise HTTPException(status_code=422, detail="to_branch_ids requerido (no vacío)")
    if payload.from_branch_id in to_branch_ids:
        raise HTTPException(status_code=422, detail="from_branch_id no puede estar en to_branch_ids")

    # Resolver variants fuente
    if payload.variant_ids:
        variant_ids = assert_variants_belong_to_org(db, payload.variant_ids, org_id)
        source_rows = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.organization_id == org_id,
            ProductBranchStatus.branch_id == payload.from_branch_id,
            ProductBranchStatus.variant_id.in_(variant_ids),
        ).all()
    else:
        source_rows = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.organization_id == org_id,
            ProductBranchStatus.branch_id == payload.from_branch_id,
        ).all()

    if not source_rows:
        raise HTTPException(
            status_code=404,
            detail="No hay PBS en la sucursal origen para las variantes indicadas",
        )

    created = 0
    updated = 0
    skipped = 0

    try:
        for src in source_rows:
            src_snapshot = {f: getattr(src, f) for f in _PBS_CLONEABLE_FIELDS}

            for target_bid in to_branch_ids:
                existing = db.query(ProductBranchStatus).filter(
                    ProductBranchStatus.organization_id == org_id,
                    ProductBranchStatus.variant_id == src.variant_id,
                    ProductBranchStatus.branch_id == target_bid,
                ).first()

                if existing is None:
                    new_pbs = ProductBranchStatus(
                        organization_id=org_id,
                        variant_id=src.variant_id,
                        branch_id=target_bid,
                        **src_snapshot,
                    )
                    db.add(new_pbs)
                    db.flush()
                    created += 1
                    log_pbs_change(
                        db,
                        actor_user_id=current_user.id,
                        action="PBS_BULK_CREATE",
                        pbs_id=new_pbs.id,
                        variant_id=src.variant_id,
                        branch_id=target_bid,
                        after=src_snapshot,
                        extra={"from_clone": payload.from_branch_id},
                    )
                    continue

                if not payload.overwrite:
                    skipped += 1
                    continue

                before = {f: getattr(existing, f) for f in _PBS_CLONEABLE_FIELDS}
                for f, v in src_snapshot.items():
                    setattr(existing, f, v)
                updated += 1
                log_pbs_change(
                    db,
                    actor_user_id=current_user.id,
                    action="PBS_BULK_TOGGLE",
                    pbs_id=existing.id,
                    variant_id=src.variant_id,
                    branch_id=target_bid,
                    before=before,
                    after=src_snapshot,
                    extra={"from_clone": payload.from_branch_id, "overwrite": True},
                )

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("PBS_CLONE_FAILED org_id=%s", org_id)
        raise HTTPException(status_code=500, detail="Error al clonar configuración de sucursal")

    return PbsCloneResponse(
        created=created,
        updated=updated,
        skipped=skipped,
        from_branch_id=payload.from_branch_id,
        to_branch_ids=to_branch_ids,
    )


# ---------------------------------------------------------------------------
# D0 — PATCH PBS per variant (CAJERO/GERENTE allowed for their own branch)
# ---------------------------------------------------------------------------
@router.patch("/variants/{variant_id}/branch-status", response_model=PBSResponse)
def patch_variant_branch_status(
    variant_id: str,
    body: BranchStatusUpdate,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    D0 — Upsert ProductBranchStatus for a variant/branch pair.

    Guards:
    - Variant must be visible to the caller (tenant + approval + branch
      when non-admin). Uses `get_variant_if_visible(..., require_pos_active=False)`
      so CAJERO/GERENTE can toggle their own PBS even if POS is currently
      disabled.
    - ADMIN/DUEÑO: must pass `?branch_id=N`. 400 if missing.
    - CAJERO/GERENTE/VENDEDOR/SOPORTE_OPERATIVO: forced to `user.branch_id`.
      403 if they pass a different branch_id.

    Body: only fields in `model_fields_set` are applied (partial update).

    Side-effects:
    - Emits one `PBS_UPDATE` `PlatformAuditLog` entry per changed field,
      with payload `{field, old, new, variant_id, branch_id}`.
    """
    variant = get_variant_if_visible(
        db, current_user, org_id,
        variant_id=variant_id,
        require_pos_active=False,
    )
    if variant is None:
        raise HTTPException(status_code=404, detail="Variante no encontrada")

    # Guard: branch resolution (raises 400/403 internally).
    target_branch_id = resolve_pbs_target_branch(current_user, branch_id)

    # Pre-fetch current PBS to capture old values for audit.
    existing = db.query(ProductBranchStatus).filter(
        ProductBranchStatus.variant_id == variant_id,
        ProductBranchStatus.branch_id == target_branch_id,
    ).first()

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422,
            detail="Debes enviar al menos un campo para actualizar."
        )

    # Capture old values (None for non-existent PBS = new row).
    old_values = {}
    for key in updates.keys():
        old_values[key] = getattr(existing, key, None) if existing else None

    try:
        pbs = update_branch_override(
            db, current_user, org_id,
            variant_id=variant_id,
            updates=updates,
            target_branch_id=target_branch_id,
        )

        # Audit log: one entry per changed field.
        import json as _json
        from app.models.platform import PlatformAuditLog
        for field, new_val in updates.items():
            old_val = old_values.get(field)
            if old_val == new_val:
                continue  # skip no-op writes
            db.add(PlatformAuditLog(
                actor_user_id=current_user.id,
                action="PBS_UPDATE",
                entity_type="ProductBranchStatus",
                entity_id=str(pbs.id),
                payload=_json.dumps({
                    "field": field,
                    "old": str(old_val) if old_val is not None else None,
                    "new": str(new_val) if new_val is not None else None,
                    "variant_id": variant_id,
                    "branch_id": target_branch_id,
                }),
            ))

        db.commit()
        db.refresh(pbs)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return pbs
