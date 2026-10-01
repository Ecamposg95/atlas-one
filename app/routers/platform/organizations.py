"""Organizations CRUD + admin assign + lifecycle (archive/suspend/etc)
+ industry/preset toggling + per-org module flags."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json as _json

from app.core.database import get_db
from app.models.organization import Organization
from app.models.users import User, UserOrganization, Role as AppRole
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.core.security import get_password_hash
from app.services import plans
from app.modules.platform.dependencies import require_platform_admin, require_superadmin

from ._shared import (
    AdminAssign,
    _ORG_UPDATE_FIELDS,
    _audit,
    _existing_tables,
)

router = APIRouter()


# --- Organizations CRUD ---

@router.post("/organizations", response_model=OrganizationRead)
def create_organization(org: OrganizationCreate, db: Session = Depends(get_db)):
    import logging
    log = logging.getLogger(__name__)
    payload = org.model_dump()
    db_org = Organization(**payload)
    db.add(db_org)
    db.commit()
    db.refresh(db_org)

    # Auto-apply el preset por industria para que la org nazca lista para operar.
    # Tolerante a errores: si Module rows no están seedeadas en este env, log y sigue.
    if db_org.industry_type:
        try:
            from app.services.capabilities_service import apply_industry_preset
            apply_industry_preset(db, db_org.id, db_org.industry_type)
        except Exception:
            # rollback de la sub-transacción del preset para dejar la session limpia
            # antes de serializar la respuesta.
            try:
                db.rollback()
            except Exception:
                pass
            try:
                db.refresh(db_org)
            except Exception:
                pass
            log.warning(
                "apply_industry_preset failed for org %s (%s) — la org se creó, "
                "el SUPERADMIN puede aplicar el preset manualmente más tarde.",
                db_org.id, db_org.industry_type, exc_info=True,
            )

    try:
        return OrganizationRead.model_validate(db_org)
    except Exception:
        log.exception("OrganizationRead serialization failed for org %s", db_org.id)
        raise

@router.get("/organizations", response_model=List[OrganizationRead])
def list_organizations(
    skip: int = 0,
    limit: int = 100,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(Organization)
    if not include_archived:
        q = q.filter(Organization.is_active.is_(True))
    return q.order_by(Organization.id.desc()).offset(skip).limit(limit).all()

@router.get("/organizations/{org_id}", response_model=OrganizationRead)
def read_organization(org_id: int, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@router.put("/organizations/{org_id}", response_model=OrganizationRead)
def update_organization(org_id: int, org_in: OrganizationUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    import logging
    log = logging.getLogger(__name__)
    db_org = db.query(Organization).filter(Organization.id == org_id).first()
    if not db_org:
        raise HTTPException(status_code=404, detail="Organization not found")

    update_data = org_in.model_dump(exclude_unset=True)
    applied = {k: v for k, v in update_data.items() if k in _ORG_UPDATE_FIELDS}
    if "plan" in applied and not plans.es_plan_valido(applied["plan"]):
        raise HTTPException(
            status_code=400,
            detail=f"Plan desconocido {applied['plan']!r}. Válidos: {', '.join(plans.claves_validas())}",
        )
    for field, value in applied.items():
        setattr(db_org, field, value)

    _audit(db, current_user.id, "UPDATE_ORGANIZATION", "ORGANIZATION", org_id,
           _json.dumps({k: str(v) for k, v in applied.items()}))
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    try:
        return OrganizationRead.model_validate(db_org)
    except Exception:
        log.exception("OrganizationRead serialization failed for org %s", db_org.id)
        raise

@router.delete("/organizations/{org_id}")
def delete_organization(
    org_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    from app.models.organization import Branch
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if not force:
        branch_count = db.query(Branch).filter(Branch.organization_id == org_id).count()
        if branch_count > 0:
            raise HTTPException(status_code=400, detail=f"No se puede eliminar: la organización tiene {branch_count} sucursal(es). Elimínelas primero.")
        user_count = db.query(UserOrganization).filter(UserOrganization.organization_id == org_id).count()
        if user_count > 0:
            raise HTTPException(status_code=400, detail=f"No se puede eliminar: la organización tiene {user_count} usuario(s) asociado(s). Desasócielos primero.")

        _audit(db, current_user.id, "DELETE_ORGANIZATION", "ORGANIZATION", org_id,
               _json.dumps({"name": org.name}))
        db.delete(org)
        db.commit()
        return {"message": "Organization deleted"}

    from app.models.sales import SalesDocument, SalesLineItem, Payment
    from app.models.cash import CashSession, CashMovement
    from app.models.returns import SaleReturn, SaleReturnItem
    from app.models.products import (
        Product, ProductVariant, Brand, Department, UnitOfMeasure,
        ProductPrice, PackagingUnit, ProductBranchStatus,
    )
    from app.models.inventory import InventoryMovement, StockOnHand
    from app.models.crm import Customer, CustomerLedgerEntry
    from app.models.finance import AccountTransaction, Expense, PurchaseOrder, PurchaseOrderLine
    from app.models.logistics import (
        ContainerType, BoxType, ProductPackaging, ContainerLoadCalc,
        InboundShipment, ShipmentItem,
        TransferOrder, TransferOrderLine, TransferFulfillment, TransferFulfillmentLine,
    )
    from app.models.abasto import PurchaseRecommendation
    from app.models.hr import Employee, BranchAssignment, Attendance
    from app.models.modules import OrganizationModule
    from app.models.print_job import PrintJob

    deleted = {}

    try:
        existing_tables = _existing_tables(db)
        branch_ids = [b.id for b in db.query(Branch.id).filter(Branch.organization_id == org_id).all()]

        user_ids_in_org = [r[0] for r in db.query(UserOrganization.user_id).filter(
            UserOrganization.organization_id == org_id
        ).all()]

        deleted["user_organizations"] = db.query(UserOrganization).filter(
            UserOrganization.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        orphan_user_ids = []
        for uid in user_ids_in_org:
            still_has = db.query(UserOrganization).filter(UserOrganization.user_id == uid).count()
            if still_has == 0:
                orphan_user_ids.append(uid)

        employee_ids = []
        if branch_ids:
            employee_ids = [r[0] for r in db.query(Employee.id).filter(
                Employee.base_branch_id.in_(branch_ids)
            ).all()]

        if orphan_user_ids:
            extra_emp_ids = [r[0] for r in db.query(Employee.id).filter(
                Employee.user_id.in_(orphan_user_ids)
            ).all()]
            for eid in extra_emp_ids:
                if eid not in employee_ids:
                    employee_ids.append(eid)

        if employee_ids:
            deleted["attendances"] = db.query(Attendance).filter(
                Attendance.employee_id.in_(employee_ids)
            ).delete(synchronize_session=False)
            deleted["branch_assignments"] = db.query(BranchAssignment).filter(
                BranchAssignment.employee_id.in_(employee_ids)
            ).delete(synchronize_session=False)
            db.flush()
            deleted["employees"] = db.query(Employee).filter(
                Employee.id.in_(employee_ids)
            ).delete(synchronize_session=False)
            db.flush()

        sale_ids = [r[0] for r in db.query(SalesDocument.id).filter(
            SalesDocument.organization_id == org_id
        ).all()]

        if sale_ids:
            return_ids = [r[0] for r in db.query(SaleReturn.id).filter(
                SaleReturn.sale_id.in_(sale_ids)
            ).all()]
            if return_ids:
                deleted["sale_return_items"] = db.query(SaleReturnItem).filter(
                    SaleReturnItem.return_id.in_(return_ids)
                ).delete(synchronize_session=False)
                db.flush()
            deleted["sale_returns"] = db.query(SaleReturn).filter(
                SaleReturn.organization_id == org_id
            ).delete(synchronize_session=False)
            db.flush()

            deleted["payments"] = db.query(Payment).filter(
                Payment.organization_id == org_id
            ).delete(synchronize_session=False)
            deleted["sales_lines"] = db.query(SalesLineItem).filter(
                SalesLineItem.organization_id == org_id
            ).delete(synchronize_session=False)
            db.flush()
            deleted["sales"] = db.query(SalesDocument).filter(
                SalesDocument.organization_id == org_id
            ).delete(synchronize_session=False)
            db.flush()
        else:
            deleted["sale_returns"] = db.query(SaleReturn).filter(
                SaleReturn.organization_id == org_id
            ).delete(synchronize_session=False)
            deleted["payments"] = db.query(Payment).filter(
                Payment.organization_id == org_id
            ).delete(synchronize_session=False)
            deleted["sales_lines"] = db.query(SalesLineItem).filter(
                SalesLineItem.organization_id == org_id
            ).delete(synchronize_session=False)
            deleted["sales"] = 0
            db.flush()

        if branch_ids:
            session_ids = [r[0] for r in db.query(CashSession.id).filter(
                CashSession.branch_id.in_(branch_ids)
            ).all()]
            if session_ids:
                deleted["cash_movements"] = db.query(CashMovement).filter(
                    CashMovement.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.flush()
                deleted["cash_sessions"] = db.query(CashSession).filter(
                    CashSession.id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.flush()

        deleted["account_transactions"] = db.query(AccountTransaction).filter(
            AccountTransaction.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["customer_ledger_entries"] = db.query(CustomerLedgerEntry).filter(
            CustomerLedgerEntry.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()
        deleted["customers"] = db.query(Customer).filter(
            Customer.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        po_ids = [r[0] for r in db.query(PurchaseOrder.id).filter(
            PurchaseOrder.organization_id == org_id
        ).all()]
        if po_ids:
            deleted["purchase_order_lines"] = db.query(PurchaseOrderLine).filter(
                PurchaseOrderLine.purchase_order_id.in_(po_ids)
            ).delete(synchronize_session=False)
            db.flush()
        deleted["purchase_orders"] = db.query(PurchaseOrder).filter(
            PurchaseOrder.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["expenses"] = db.query(Expense).filter(
            Expense.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        deleted["purchase_recommendations"] = db.query(PurchaseRecommendation).filter(
            PurchaseRecommendation.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        deleted["inventory_movements"] = db.query(InventoryMovement).filter(
            InventoryMovement.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["stock_on_hand"] = db.query(StockOnHand).filter(
            StockOnHand.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        deleted["product_branch_status"] = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["product_prices"] = db.query(ProductPrice).filter(
            ProductPrice.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["packaging_units"] = db.query(PackagingUnit).filter(
            PackagingUnit.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()
        deleted["product_variants"] = db.query(ProductVariant).filter(
            ProductVariant.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()
        deleted["products"] = db.query(Product).filter(
            Product.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["brands"] = db.query(Brand).filter(
            Brand.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["departments"] = db.query(Department).filter(
            Department.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["uom"] = db.query(UnitOfMeasure).filter(
            UnitOfMeasure.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        ct_ids = [r[0] for r in db.query(ContainerType.id).filter(
            ContainerType.organization_id == org_id
        ).all()]
        if ct_ids:
            deleted["container_load_calcs"] = db.query(ContainerLoadCalc).filter(
                ContainerLoadCalc.container_type_id.in_(ct_ids)
            ).delete(synchronize_session=False)
            db.flush()
        deleted["product_packagings"] = db.query(ProductPackaging).filter(
            ProductPackaging.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()
        ship_ids = [r[0] for r in db.query(InboundShipment.id).filter(
            InboundShipment.organization_id == org_id
        ).all()]
        if ship_ids:
            deleted["shipment_items"] = db.query(ShipmentItem).filter(
                ShipmentItem.shipment_id.in_(ship_ids)
            ).delete(synchronize_session=False)
            db.flush()
        deleted["inbound_shipments"] = db.query(InboundShipment).filter(
            InboundShipment.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        transfer_ids = [r[0] for r in db.query(TransferOrder.id).filter(
            TransferOrder.organization_id == org_id
        ).all()]
        if transfer_ids:
            ful_ids = [r[0] for r in db.query(TransferFulfillment.id).filter(
                TransferFulfillment.transfer_id.in_(transfer_ids)
            ).all()]
            if ful_ids:
                deleted["transfer_fulfillment_lines"] = db.query(TransferFulfillmentLine).filter(
                    TransferFulfillmentLine.fulfillment_id.in_(ful_ids)
                ).delete(synchronize_session=False)
                db.flush()
                deleted["transfer_fulfillments"] = db.query(TransferFulfillment).filter(
                    TransferFulfillment.id.in_(ful_ids)
                ).delete(synchronize_session=False)
                db.flush()
            deleted["transfer_order_lines"] = db.query(TransferOrderLine).filter(
                TransferOrderLine.transfer_id.in_(transfer_ids)
            ).delete(synchronize_session=False)
            db.flush()
            deleted["transfer_orders"] = db.query(TransferOrder).filter(
                TransferOrder.id.in_(transfer_ids)
            ).delete(synchronize_session=False)
            db.flush()

        deleted["box_types"] = db.query(BoxType).filter(
            BoxType.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["container_types"] = db.query(ContainerType).filter(
            ContainerType.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        deleted["print_jobs"] = db.query(PrintJob).filter(
            PrintJob.organization_id == org_id
        ).delete(synchronize_session=False)
        deleted["organization_modules"] = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        if branch_ids:
            db.query(User).filter(User.branch_id.in_(branch_ids)).update(
                {"branch_id": None}, synchronize_session=False
            )
            db.flush()
        deleted["branches"] = db.query(Branch).filter(
            Branch.organization_id == org_id
        ).delete(synchronize_session=False)
        db.flush()

        deleted_users = 0
        if orphan_user_ids:
            deleted_users = db.query(User).filter(
                User.id.in_(orphan_user_ids)
            ).delete(synchronize_session=False)
            db.flush()
        deleted["users"] = deleted_users

        db.delete(org)
        db.flush()

        _audit(db, current_user.id, "HARD_DELETE_ORGANIZATION", "ORGANIZATION", org_id,
               _json.dumps({"name": org.name, "deleted": deleted}, default=str))
        db.commit()
        return {"message": f"Organization {org.name} hard-deleted with cascade", "deleted": deleted}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Hard delete failed: {str(e)}")

@router.post("/organizations/{org_id}/admins")
def assign_org_admin(org_id: int, user_data: AdminAssign, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user = db.query(User).filter(User.username == user_data.username).first()
    if not user:
        if not user_data.password:
            raise HTTPException(status_code=400, detail="Password required for new user")

        user = User(
            username=user_data.username,
            full_name=user_data.full_name,
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            role=AppRole.DUEÑO,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    assoc = db.query(UserOrganization).filter(
        UserOrganization.user_id == user.id,
        UserOrganization.organization_id == org.id
    ).first()

    if assoc:
        assoc.org_role = "OWNER"
        assoc.is_active = True
    else:
        assoc = UserOrganization(
            user_id=user.id,
            organization_id=org.id,
            org_role="OWNER",
            is_active=True
        )
        db.add(assoc)

    # [HARDENING] Assign a default branch context
    from app.models.organization import Branch, BranchType
    hq = db.query(Branch).filter(Branch.organization_id == org.id, Branch.branch_type == BranchType.HQ).first()
    if hq and not user.branch_id:
        user.branch_id = hq.id
        db.add(user)

    _audit(db, current_user.id, "ASSIGN_ORG_ADMIN", "ORGANIZATION", org_id,
           _json.dumps({"username": user.username}))
    db.commit()
    return {"message": f"User {user.username} assigned as OWNER to {org.name}"}

@router.get("/organizations/{org_id}/dependencies")
def org_dependencies(org_id: int, db: Session = Depends(get_db)):
    """Report counts of records that block a hard delete of this org."""
    from app.models.organization import Branch
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "branches": db.query(Branch).filter(Branch.organization_id == org_id).count(),
        "users": db.query(UserOrganization).filter(UserOrganization.organization_id == org_id).count(),
    }

@router.post("/organizations/{org_id}/archive")
def archive_organization(org_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.is_active = False
    org.status = "ARCHIVED"
    _audit(db, current_user.id, "ARCHIVE_ORGANIZATION", "ORGANIZATION", org_id,
           _json.dumps({"name": org.name}))
    db.commit()
    return {"message": "Organization archived", "is_active": False, "status": "ARCHIVED"}

@router.post("/organizations/{org_id}/unarchive")
def unarchive_organization(org_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.is_active = True
    org.status = "ACTIVE"
    _audit(db, current_user.id, "UNARCHIVE_ORGANIZATION", "ORGANIZATION", org_id,
           _json.dumps({"name": org.name}))
    db.commit()
    return {"message": "Organization restored", "is_active": True, "status": "ACTIVE"}

@router.post("/organizations/{org_id}/suspend")
def suspend_organization(org_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.status = "SUSPENDED"
    _audit(db, current_user.id, "SUSPEND_ORGANIZATION", "ORGANIZATION", org_id,
           _json.dumps({"name": org.name}))
    db.commit()
    return {"message": "Organization suspended", "status": org.status}

@router.post("/organizations/{org_id}/activate")
def activate_organization(org_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.status = "ACTIVE"
    _audit(db, current_user.id, "ACTIVATE_ORGANIZATION", "ORGANIZATION", org_id,
           _json.dumps({"name": org.name}))
    db.commit()
    return {"message": "Organization activated", "status": org.status}

@router.post("/organizations/{org_id}/bootstrap")
def bootstrap_organization(org_id: int, db: Session = Depends(get_db)):
    from app.models.organization import Branch, BranchType
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    created = []
    # 1. HQ
    hq = db.query(Branch).filter(Branch.organization_id == org_id, Branch.branch_type == BranchType.HQ).first()
    if not hq:
        hq = Branch(
            name=f"HQ - {org.name}",
            branch_type=BranchType.HQ,
            can_sell=False,
            is_active=True,
            is_headquarters=True,
            organization_id=org_id
        )
        db.add(hq)
        created.append("HQ")

    # 2. STORE
    store = db.query(Branch).filter(Branch.organization_id == org_id, Branch.branch_type == BranchType.STORE).first()
    if not store:
        store = Branch(
            name=f"Sucursal Principal - {org.name}",
            branch_type=BranchType.STORE,
            can_sell=True,
            is_active=True,
            is_headquarters=False,
            organization_id=org_id
        )
        db.add(store)
        created.append("STORE")

    db.commit()
    return {
        "message": f"Bootstrap completed for {org.name}",
        "created_branches": created
    }

@router.get("/organizations/{org_id}/export")
def export_organization_data(org_id: int, db: Session = Depends(get_db)):
    """
    Generates a JSON dump of the organization's critical data.
    Focuses on Customers (Clients) as requested for backup.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Fetch Customers
    from app.models.crm import Customer
    customers = db.query(Customer).filter(Customer.organization_id == org_id).all()

    customers_data = []
    for c in customers:
        customers_data.append({
            "id": c.id,
            "name": c.name,
            "tax_id": c.tax_id,
            "email": c.email,
            "phone": c.phone,
            "address": c.address,
            "has_credit": c.has_credit,
            "current_balance": float(c.current_balance or 0),
            "notes": c.notes,
            "is_active": c.is_active
        })

    export_payload = {
        "metadata": {
            "organization_id": org.id,
            "organization_name": org.name,
            "export_date": "NOW", # Frontend can handle specific formatting or use server time
            "version": "1.0"
        },
        "customers": customers_data,
        "customer_count": len(customers_data)
    }

    return export_payload


# --- 4. INDUSTRY & PRESETS (MdM) ---

@router.patch("/organizations/{org_id}/industry")
def update_org_industry(org_id: int, industry_type: str, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    from app.models.organization import IndustryType
    from app.models.platform import PlatformAuditLog
    import json

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        enum_val = IndustryType(industry_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid industry type")

    old_val = org.industry_type.value if org.industry_type else None
    org.industry_type = enum_val

    # Audit
    db.add(PlatformAuditLog(
        actor_user_id=current_user.id,
        action="UPDATE_ORG_INDUSTRY",
        entity_type="ORGANIZATION",
        entity_id=str(org_id),
        payload=json.dumps({"old": old_val, "new": industry_type})
    ))

    db.commit()
    return {"message": "Industry updated", "industry_type": org.industry_type}

@router.post("/organizations/{org_id}/apply-preset")
def apply_org_preset(org_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_platform_admin)):
    """
    Applies the module preset corresponding to the organization's industry type.
    """
    from app.services.capabilities_service import apply_industry_preset
    from app.models.platform import PlatformAuditLog

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if not org.industry_type:
        raise HTTPException(status_code=400, detail="Organization has no industry type set")

    apply_industry_preset(db, org.id, org.industry_type)

    # Audit
    db.add(PlatformAuditLog(
        actor_user_id=current_user.id,
        action="APPLY_PRESET",
        entity_type="ORGANIZATION",
        entity_id=str(org_id),
        payload=f"Applied preset for {org.industry_type.value}"
    ))
    db.commit()

    return {"message": f"Preset applied for {org.industry_type.value}"}

# --- 5. MODULE MANGEMENT (Feature Flags) ---

@router.get("/organizations/{org_id}/modules")
def get_org_module_status(org_id: int, db: Session = Depends(get_db)):
    """Returning Matrix of All vs Enabled"""
    from app.models.modules import Module, OrganizationModule

    all_modules = db.query(Module).all()
    # Marcas de plan: se calculan una vez por organizacion.
    org = db.query(Organization).filter(Organization.id == org_id).first()
    permitidos = plans.modulos_permitidos(db, org) if org is not None else set()
    enabled_map = {
        m.module_key: m
        for m in db.query(OrganizationModule).filter(OrganizationModule.organization_id == org_id).all()
    }

    result = []
    for mod in all_modules:
        is_enabled = False
        if mod.key in enabled_map and enabled_map[mod.key].is_enabled:
            is_enabled = True

        minimo = plans.plan_minimo_para(mod.key)
        result.append({
            "key": mod.key,
            "name": mod.name,
            "scope": mod.scope,
            "status": mod.status,
            "is_enabled": is_enabled,
            "plan_minimo": minimo.clave if minimo else None,
            "permitido_por_plan": mod.key in permitidos,
        })
    return result

@router.patch("/organizations/{org_id}/modules/{module_key}")
def toggle_org_module(
    org_id: int,
    module_key: str,
    enable: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    from app.models.modules import OrganizationModule
    from app.models.platform import PlatformAuditLog
    import json

    # Check org exists
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Org not found")

    if module_key == "core" and not enable:
         raise HTTPException(400, "Cannot disable CORE module")

    # Gating por plan: solo al encender; apagar siempre se permite.
    if enable:
        from app.models.modules import Module
        mod = db.query(Module).filter(Module.key == module_key).first()
        # Una clave que no esta en el catalogo no se puede encender: sin esto
        # quedaria un OrganizationModule huerfano que ningun gate reconoce.
        if mod is None:
            raise HTTPException(status_code=404, detail="Módulo desconocido")
        try:
            plans.verificar_activar_modulo(db, org, module_key, mod.name)
        except plans.ModuloFueraDePlan as e:
            raise HTTPException(status_code=403, detail=str(e))

    org_mod = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.module_key == module_key
    ).first()

    if org_mod:
        org_mod.is_enabled = enable
    else:
        if enable:
            db.add(OrganizationModule(organization_id=org_id, module_key=module_key, is_enabled=True))

    # Audit
    db.add(PlatformAuditLog(
        actor_user_id=current_user.id,
        action="TOGGLE_MODULE",
        entity_type="ORGANIZATION",
        entity_id=str(org_id),
        payload=json.dumps({"module": module_key, "enabled": enable})
    ))
    db.commit()
    return {"message": f"Module {module_key} set to {enable}"}


@router.get("/organizations/{org_id}/upsell-recommendations")
def get_upsell_recommendations(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Return modules NOT enabled for this org, with upsell metadata, grouped by recommended preset."""
    from app.models.modules import Module, OrganizationModule
    from app.schemas.modules import UpsellRecommendation, UpsellResponse

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_modules = [
        om.module_key
        for om in db.query(OrganizationModule)
        .filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.is_enabled == True,  # noqa: E712
        )
        .all()
    ]
    active_preset = org.industry_type.value if org.industry_type else None

    # Modules with metadata, not yet enabled
    candidates = (
        db.query(Module)
        .filter(Module.upsell_metadata.isnot(None))
        .all()
    )

    recommendations = []
    grouped: dict[str, list[str]] = {}

    for mod in candidates:
        if mod.key in active_modules:
            continue
        meta = mod.upsell_metadata or {}
        recommended = meta.get("recommended_presets", []) or []

        rec = UpsellRecommendation(
            module_key=mod.key,
            module_name=mod.name,
            description=mod.description,
            category=meta.get("category"),
            status=mod.status.value if mod.status else "STABLE",
            in_recommended_preset=bool(active_preset and active_preset in recommended),
            recommended_presets=recommended,
            value_props=meta.get("value_props", []) or [],
            upgrade_prompt=meta.get("upgrade_prompt"),
            icon=meta.get("icon"),
            sort_hint=meta.get("sort_hint", 100),
            plan_minimo=(minimo.clave if (minimo := plans.plan_minimo_para(mod.key)) else None),
        )
        recommendations.append(rec)

        for preset_key in recommended:
            grouped.setdefault(preset_key, []).append(mod.key)

    recommendations.sort(key=lambda r: (r.sort_hint, r.module_key))

    return UpsellResponse(
        org_id=org_id,
        active_preset=active_preset,
        active_modules=active_modules,
        recommendations=recommendations,
        grouped_by_preset=grouped,
    )


@router.post("/organizations/{org_id}/reset-preset")
def reset_organization_preset(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Resets an organization's preset configuration.
    Sets industry_type to None and clears all organization modules.
    This will trigger the welcome journey (/startup) for users.
    """
    from app.models.modules import OrganizationModule
    from app.models.platform import PlatformAuditLog
    import json

    # Check org exists
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Store old values for audit
    old_industry = org.industry_type.value if org.industry_type else None

    # Reset industry type
    org.industry_type = None

    # Clear all organization modules
    deleted_count = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org_id
    ).delete()

    # Audit log
    db.add(PlatformAuditLog(
        actor_user_id=current_user.id,
        action="RESET_PRESET",
        entity_type="ORGANIZATION",
        entity_id=str(org_id),
        payload=json.dumps({
            "old_industry": old_industry,
            "modules_cleared": deleted_count
        })
    ))

    db.commit()

    return {
        "status": "success",
        "message": f"Preset reset for {org.name}. Welcome journey will be triggered on next login.",
        "modules_cleared": deleted_count
    }
