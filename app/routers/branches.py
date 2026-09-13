# app/routers/branches.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
import shutil
import time
from app.core.database import get_db
from app.models.organization import Branch
from app.schemas.branches import BranchCreate, BranchRead, BranchUpdate
from app.core.security import get_current_user, require_admin_or_owner
from app.models.users import User, Role
from app.core.tenant_context import get_current_active_organization
from app.models.organization import BranchType
from app.models.products import ProductVariant, ProductBranchStatus
from app.models.inventory import StockOnHand

router = APIRouter()


@router.get("/", response_model=List[BranchRead])
def get_branches(
    db: Session = Depends(get_db), 
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    return db.query(Branch).filter(Branch.organization_id == org_id).all()


@router.post("/", response_model=BranchRead)
def create_branch(
    branch: BranchCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization)
):
    # Regla: Si es HQ, validar que no exista ya una para la organización
    # El índice único en DB lo previene, pero lo validamos aquí para error amigable
    if branch.branch_type == BranchType.HQ:
        existing_hq = db.query(Branch).filter(
            Branch.organization_id == org_id,
            Branch.branch_type == BranchType.HQ
        ).first()
        if existing_hq:
            raise HTTPException(status_code=400, detail="Esta organización ya tiene una oficina central (HQ).")
        
        # HQ por defecto no vende, salvo que el caller lo pida explícitamente:
        # un negocio de una sola sucursal (Ginebra, Imaltzin) tiene su matriz
        # como único punto de venta. Forzarlo a False dejaba el POS sin
        # catálogo (visto en producción el 2026-09-13).
        if "can_sell" not in branch.model_fields_set:
            branch.can_sell = False
        branch.is_headquarters = True # Keep in sync
    elif branch.branch_type in [BranchType.WAREHOUSE, BranchType.OFFICE]:
        branch.can_sell = False
        branch.is_headquarters = False
    else:
        branch.is_headquarters = False

    # Force org_id; strip inherit_catalog (not a DB column)
    branch_data = branch.dict(exclude_unset=True)
    inherit_catalog = branch_data.pop('inherit_catalog', False)
    branch_data['organization_id'] = org_id

    new_branch = Branch(**branch_data)
    db.add(new_branch)
    try:
        db.flush()  # get new_branch.id without committing

        if inherit_catalog:
            variants = db.query(ProductVariant).filter(
                ProductVariant.organization_id == org_id,
                ProductVariant.deleted_at == None
            ).all()
            if variants:
                # Si la sucursal no puede vender, los productos se crean deshabilitados
                pos_active = bool(new_branch.can_sell)

                stock_records = []
                status_records = []
                for v in variants:
                    stock_records.append(StockOnHand(
                        branch_id=new_branch.id,
                        variant_id=v.id,
                        organization_id=org_id,
                        qty_on_hand=0
                    ))
                    status_records.append(ProductBranchStatus(
                        branch_id=new_branch.id,
                        variant_id=v.id,
                        organization_id=org_id,
                        is_active_pos=pos_active,
                        is_active_hq=False,
                        is_visible=pos_active,
                    ))

                db.add_all(stock_records)
                db.add_all(status_records)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    db.refresh(new_branch)
    return new_branch


@router.get("/{branch_id}", response_model=BranchRead)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


@router.put("/{branch_id}", response_model=BranchRead)
def update_branch(
    branch_id: int,
    branch: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # [PERMISSION CHECK]
    # If not Admin/Owner, verify they are only updating printer config
    # and that they belong to this branch.
    is_admin = current_user.role in [Role.ADMINISTRADOR, Role.DUEÑO]
    can_update_printer = current_user.role in [Role.CAJERO, Role.GERENTE]

    db_branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not db_branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    if not is_admin:
        # Non-admins can only update their own branch (or verify access??)
        # Assuming if they are authenticated and active, and target their own branch context...
        if current_user.branch_id != branch_id:
             raise HTTPException(status_code=403, detail="No tienes permiso para modificar esta sucursal.")

        # Filter ALLOWED fields based on role
        if can_update_printer:
            allowed_fields = {"printer_name", "ticket_header", "ticket_footer", "paper_width_mm", "open_drawer_on_print"}
        else:
            allowed_fields = set()

        incoming_data = branch.dict(exclude_unset=True)

        for field in incoming_data:
            if field not in allowed_fields:
                raise HTTPException(status_code=403, detail=f"No tienes permiso para modificar el campo: {field}")


    # Validar HQ única si se está cambiando el tipo a HQ
    if branch.branch_type == BranchType.HQ:
        existing_hq = db.query(Branch).filter(
            Branch.organization_id == org_id,
            Branch.branch_type == BranchType.HQ,
            Branch.id != branch_id
        ).first()
        if existing_hq:
            raise HTTPException(status_code=400, detail="Esta organización ya tiene una oficina central (HQ).")
        
        # HQ => can_sell = False solo si el caller no manda can_sell explícito
        # (ver create_branch: la matriz de un negocio de una sucursal vende).
        if "can_sell" not in branch.model_fields_set:
            db_branch.can_sell = False
        db_branch.is_headquarters = True
    elif branch.branch_type is not None:
        db_branch.is_headquarters = False

    for key, value in branch.dict(exclude_unset=True).items():
        setattr(db_branch, key, value)

    # Re-enforce HQ rules after update: is_headquarters sigue al tipo. can_sell
    # NO se toca aquí: el default False para la matriz se aplica solo cuando
    # el tipo cambia a HQ en esta misma petición (bloque de arriba). Antes se
    # forzaba siempre, así que editar cualquier campo de la matriz desde el
    # panel apagaba la venta de la única sucursal.
    if db_branch.branch_type == BranchType.HQ:
        db_branch.is_headquarters = True

    db.commit()
    db.refresh(db_branch)
    return db_branch


def _can_manage_branch_logo(user: User, branch_id: int) -> bool:
    """HQ admins manage any branch in their org; GERENTE/CAJERO manage only their own."""
    if user.platform_role and str(user.platform_role).endswith("SUPERADMIN"):
        return True
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_str in ("ADMINISTRADOR", "DUEÑO"):
        return True
    if role_str in ("GERENTE", "CAJERO") and user.branch_id == branch_id:
        return True
    return False


@router.post("/{branch_id}/logo")
async def upload_branch_logo(
    branch_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Upload logo for a branch. Saves to app/static/branch_logos/ and updates Branch.logo_url."""
    if not _can_manage_branch_logo(current_user, branch_id):
        raise HTTPException(status_code=403, detail="No autorizado para gestionar el logo de esta sucursal")
    db_branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not db_branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if not file.content_type or file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Formato no permitido (PNG/JPEG/WEBP)")

    content = await file.read()
    if len(content) > 1 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="La imagen no debe superar 1 MB")

    from app.utils import image_storage
    db_branch.logo_url = image_storage.upload_image(
        content,
        public_id=f"branch_{branch_id}",
        folder=image_storage.BRANCH_LOGOS_FOLDER,
        content_type=file.content_type,
    )
    db.commit()
    db.refresh(db_branch)
    return {"status": "success", "logo_url": db_branch.logo_url}


@router.delete("/{branch_id}/logo")
def delete_branch_logo(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if not _can_manage_branch_logo(current_user, branch_id):
        raise HTTPException(status_code=403, detail="No autorizado para gestionar el logo de esta sucursal")
    db_branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not db_branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    from app.utils import image_storage
    image_storage.delete_image(f"branch_{branch_id}", folder=image_storage.BRANCH_LOGOS_FOLDER)
    db_branch.logo_url = None
    db.commit()
    return {"status": "success", "logo_url": None}


@router.delete("/{branch_id}")
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization)
):
    from app.models.users import User
    from app.models.sales import SalesDocument
    from app.models.cash import CashSession
    from app.models.organization import Organization

    db_branch = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if not db_branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    # Prevent deleting HQ branch
    if db_branch.branch_type == BranchType.HQ:
        raise HTTPException(status_code=400, detail="No se puede eliminar la oficina central (HQ). Cambia el tipo primero.")

    # Prevent deleting if org.hq_branch_id points here
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and org.hq_branch_id == branch_id:
        raise HTTPException(status_code=400, detail="Esta sucursal está configurada como HQ de la organización.")

    # Check for blocking references
    has_users = db.query(User).filter(User.branch_id == branch_id).first()
    if has_users:
        raise HTTPException(status_code=400, detail="No se puede eliminar: hay usuarios asignados a esta sucursal. Reasígnalos primero.")

    has_sales = db.query(SalesDocument).filter(SalesDocument.branch_id == branch_id).first()
    if has_sales:
        raise HTTPException(status_code=400, detail="No se puede eliminar: esta sucursal tiene ventas registradas. Desactívala en su lugar.")

    has_sessions = db.query(CashSession).filter(CashSession.branch_id == branch_id).first()
    if has_sessions:
        raise HTTPException(status_code=400, detail="No se puede eliminar: esta sucursal tiene sesiones de caja. Desactívala en su lugar.")

    # Clean up non-blocking references (stock, branch status, inventory movements)
    db.query(StockOnHand).filter(StockOnHand.branch_id == branch_id).delete()
    db.query(ProductBranchStatus).filter(ProductBranchStatus.branch_id == branch_id).delete()

    try:
        db.delete(db_branch)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar la sucursal: {str(e)}")

    return {"ok": True}
