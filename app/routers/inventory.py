# app/routers/inventory.py
"""
MOONSHOT_ENGINE: Inventory Engine
DOMAIN: Supply Chain / Logistics
STATUS: Core
"""
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import InventoryMovement, StockOnHand, MovementType, User, ProductVariant
from app.models.organization import Branch
from app.schemas.inventory import AdjustmentCreate, MovementRead, TransferCreate
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import get_variant_if_visible, _is_admin, _role_str

router = APIRouter()

def aplicar_ajuste(db: Session, *, org_id: int, branch_id: int, variant_id: str,
                   user_id: Optional[int], quantity: Decimal, reason: str,
                   notes: Optional[str] = None) -> InventoryMovement:
    """Entrada (+) o salida (−) manual con su renglón de kardex. Es la misma
    lógica de `POST /inventory/adjust`; la comparte el conteo físico
    (app/modules/conteos) para que sus ajustes se vean en el mismo kardex.
    400 si la salida dejaría la existencia negativa. Hace commit."""
    stock_record = db.query(StockOnHand).filter_by(
        branch_id=branch_id, variant_id=variant_id, organization_id=org_id,
    ).with_for_update().first()
    qty_before = stock_record.qty_on_hand if stock_record else Decimal("0")
    if quantity > 0:
        mov_type = MovementType.ADJUSTMENT_IN
    else:
        mov_type = MovementType.ADJUSTMENT_OUT
        if qty_before + quantity < 0:
            raise HTTPException(400, "Stock insuficiente para realizar este ajuste.")
    if not stock_record:
        stock_record = StockOnHand(branch_id=branch_id, variant_id=variant_id,
                                   qty_on_hand=0, organization_id=org_id)
        db.add(stock_record)
    stock_record.qty_on_hand += quantity
    movement = InventoryMovement(
        branch_id=branch_id, variant_id=variant_id, user_id=user_id,
        movement_type=mov_type, qty_change=quantity, qty_before=qty_before,
        qty_after=stock_record.qty_on_hand, reference=reason, notes=notes,
        organization_id=org_id,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


@router.post("/adjust", response_model=MovementRead)
def create_adjustment(
    adj: AdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Registra entradas (Compras) o salidas (Mermas) manuales.
    """
    # A2-10: Resolver variant con visibilidad tenant + (branch, si aplica).
    # require_pos_active=False → admite variantes inactivas siempre que el
    # tenant y la branch coincidan; evita IDOR cross-tenant.
    variant = get_variant_if_visible(
        db,
        current_user,
        org_id,
        variant_id=adj.variant_id,
        require_pos_active=False,
    )
    if not variant:
        raise HTTPException(404, "Producto no encontrado")

    # A2-10: Non-admins no pueden ajustar stock de otras sucursales —
    # se ignora `adj.branch_id` y se fuerza `user.branch_id`.
    if _is_admin(current_user):
        target_branch_id = adj.branch_id if adj.branch_id else current_user.branch_id
    else:
        if not current_user.branch_id:
            raise HTTPException(403, "Tu usuario no tiene sucursal asignada")
        target_branch_id = current_user.branch_id
    
    movement = aplicar_ajuste(
        db, org_id=org_id, branch_id=target_branch_id, variant_id=adj.variant_id,
        user_id=current_user.id, quantity=adj.quantity, reason=adj.reason, notes=adj.notes,
    )

    # Construir respuesta manual para incluir nombre usuario
    return MovementRead(
        id=movement.id,
        movement_type=movement.movement_type,
        qty_change=movement.qty_change,
        qty_after=movement.qty_after,
        reference=movement.reference,
        created_at=movement.created_at,
        user_name=current_user.username
    )

@router.post("/transfer")
def transfer_stock(
    transfer: TransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Transfiere stock de una sucursal a otra mediante una transacción segura.
    """
    if transfer.quantity <= 0:
        raise HTTPException(400, "La cantidad a transferir debe ser mayor a 0")

    if transfer.from_branch_id == transfer.to_branch_id:
        raise HTTPException(400, "Las sucursales de origen y destino no pueden ser la misma")

    # A2-11: Non-admins sólo pueden originar traspasos desde SU sucursal.
    if not _is_admin(current_user):
        if not current_user.branch_id:
            raise HTTPException(403, "Tu usuario no tiene sucursal asignada")
        if transfer.from_branch_id != current_user.branch_id:
            raise HTTPException(403, "No puedes originar traspasos desde otra sucursal")

    # A2-11: Source y destino deben pertenecer al mismo tenant.
    source_branch = db.query(Branch).filter(
        Branch.id == transfer.from_branch_id,
        Branch.organization_id == org_id,
    ).first()
    if not source_branch:
        raise HTTPException(404, "Sucursal origen no encontrada")
    dest_branch = db.query(Branch).filter(
        Branch.id == transfer.to_branch_id,
        Branch.organization_id == org_id,
    ).first()
    if not dest_branch:
        raise HTTPException(404, "Sucursal destino no encontrada")

    # A2-11: Variant tenant-scoped (no requiere PBS activo para el traspaso).
    variant = get_variant_if_visible(
        db,
        current_user,
        org_id,
        variant_id=transfer.variant_id,
        require_pos_active=False,
    )
    if not variant:
        raise HTTPException(404, "Producto no encontrado")

    # 2. Obtener Stock Origen
    stock_source = db.query(StockOnHand).filter_by(
        branch_id=transfer.from_branch_id,
        variant_id=transfer.variant_id,
        organization_id=org_id
    ).with_for_update().first() # Bloqueo para evitar race conditions

    if not stock_source or stock_source.qty_on_hand < transfer.quantity:
        raise HTTPException(400, "Stock insuficiente en la sucursal de origen")

    qty_source_before = stock_source.qty_on_hand

    # 3. Obtener/Crear Stock Destino
    stock_dest = db.query(StockOnHand).filter_by(
        branch_id=transfer.to_branch_id,
        variant_id=transfer.variant_id,
        organization_id=org_id
    ).with_for_update().first()

    if not stock_dest:
        stock_dest = StockOnHand(
            branch_id=transfer.to_branch_id,
            variant_id=transfer.variant_id,
            qty_on_hand=0,
            organization_id=org_id
        )
        db.add(stock_dest)

    qty_dest_before = stock_dest.qty_on_hand if stock_dest.id else 0

    # 4. Actualizar Cantidades
    stock_source.qty_on_hand -= transfer.quantity
    stock_dest.qty_on_hand += transfer.quantity

    # 5. Guardar Kardex (Deducción en Origen)
    mov_out = InventoryMovement(
        branch_id=transfer.from_branch_id,
        variant_id=transfer.variant_id,
        user_id=current_user.id,
        movement_type=MovementType.TRANSFER_OUT,
        qty_change=-transfer.quantity,
        qty_before=qty_source_before,
        qty_after=stock_source.qty_on_hand,
        reference=f"Traspaso a Suc. {transfer.to_branch_id} - {transfer.reason}",
        notes=transfer.notes,
        organization_id=org_id
    )
    db.add(mov_out)

    # 6. Guardar Kardex (Ingreso en Destino)
    mov_in = InventoryMovement(
        branch_id=transfer.to_branch_id,
        variant_id=transfer.variant_id,
        user_id=current_user.id,
        movement_type=MovementType.TRANSFER_IN,
        qty_change=transfer.quantity,
        qty_before=qty_dest_before,
        qty_after=stock_dest.qty_on_hand,
        reference=f"Traspaso desde Suc. {transfer.from_branch_id} - {transfer.reason}",
        notes=transfer.notes,
        organization_id=org_id
    )
    db.add(mov_in)

    db.commit()
    
    return {"message": "Transferencia completada con éxito"}

@router.get("/kardex/{variant_id}", response_model=List[MovementRead])
def get_kardex(
    variant_id: str,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Obtiene el historial de movimientos de un producto"""
    from sqlalchemy.orm import joinedload
    
    target_branch_id = current_user.branch_id
    # A2-12: `user.role` es Enum — comparar contra strings vía `_role_str`.
    # Only Admin/Manager can view other branches.
    if _role_str(current_user) in ("ADMINISTRADOR", "GERENTE", "DUEÑO") and branch_id:
        target_branch_id = branch_id

    movements = db.query(InventoryMovement).options(joinedload(InventoryMovement.user)).filter(
        InventoryMovement.variant_id == variant_id,
        InventoryMovement.branch_id == target_branch_id,
        InventoryMovement.organization_id == org_id
    ).order_by(InventoryMovement.created_at.desc()).limit(100).all()

    # Mapeo manual rápido para incluir user_name
    return [
        MovementRead(
            id=m.id,
            movement_type=m.movement_type,
            qty_change=m.qty_change,
            qty_after=m.qty_after,
            reference=m.reference,
            created_at=m.created_at,
            user_name=m.user.username if m.user else "Sistema"
        ) for m in movements
    ]