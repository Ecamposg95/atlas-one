from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
import math
from datetime import datetime
from decimal import Decimal

from app.core.database import get_db
from app.models import (
    ContainerType, BoxType, ContainerLoadCalc, 
    InboundShipment, ShipmentItem, 
    ProductVariant, InventoryMovement, StockOnHand, MovementType
)
from app.schemas.logistics import (
    ContainerTypeCreate, ContainerTypeRead,
    BoxTypeCreate, BoxTypeRead,
    LoadCalcRequest, LoadCalcResult,
    ShipmentCreate, ShipmentRead, ShipmentItemCreate
)
from app.core.security import get_current_user
from app.models import User
from app.core.tenant_context import get_current_active_organization
from app.core.permissions import require_module

router = APIRouter(dependencies=[Depends(require_module("warehouse"))])

# --- CRUD Container ---
# Catálogo por organización (regla de oro 5): antes era global y sin usuario, y
# el GET sembraba filas sin organization_id la primera vez. Ya no se siembra nada.
@router.post("/containers", response_model=ContainerTypeRead)
def create_container(
    c: ContainerTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    new_c = ContainerType(**c.dict(), organization_id=org_id)
    db.add(new_c)
    db.commit()
    db.refresh(new_c)
    return new_c

@router.get("/containers", response_model=List[ContainerTypeRead])
def list_containers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return db.query(ContainerType).filter(ContainerType.organization_id == org_id).order_by(ContainerType.id).all()

# --- CRUD Boxes ---
@router.post("/boxes", response_model=BoxTypeRead)
def create_box(
    b: BoxTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    new_b = BoxType(**b.dict(), organization_id=org_id)
    db.add(new_b)
    db.commit()
    db.refresh(new_b)
    return new_b

@router.get("/boxes", response_model=List[BoxTypeRead])
def list_boxes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return db.query(BoxType).filter(BoxType.organization_id == org_id).order_by(BoxType.id).all()

# --- Calculation Logic ---

def calculate_fit_simple(cont_l, cont_w, cont_h, box_l, box_w, box_h):
    """
    Returns (total_boxes, boxes_per_layer, layers)
    Strategy: Simple stacking without rotation (all boxes same orientation).
    """
    if box_l > cont_l or box_w > cont_w or box_h > cont_h:
        return 0, 0, 0
    
    along_l = math.floor(cont_l / box_l)
    along_w = math.floor(cont_w / box_w)
    along_h = math.floor(cont_h / box_h)
    
    boxes_per_layer = along_l * along_w
    total = boxes_per_layer * along_h
    return total, boxes_per_layer, along_h

@router.post("/calculate", response_model=LoadCalcResult)
def calculate_load(
    req: LoadCalcRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    # Solo contenedores y cajas de la organización activa (regla de oro 5).
    container = db.query(ContainerType).filter(ContainerType.id == req.container_type_id, ContainerType.organization_id == org_id).first()
    box = db.query(BoxType).filter(BoxType.id == req.box_type_id, BoxType.organization_id == org_id).first()
    
    if not container or not box:
        raise HTTPException(404, "Contenedor o Caja no encontrados")
    
    # Dimensions (Internal vs External)
    CL, CW, CH = float(container.inner_length), float(container.inner_width), float(container.inner_height)
    BL, BW, BH = float(box.outer_length), float(box.outer_width), float(box.outer_height)
    
    BoxWeight = req.weight_per_box_kg or float(box.weight_empty_kg or 0)
    
    # Try Orientation 1: Align Box L with Container L
    fit1, bpl1, layers1 = calculate_fit_simple(CL, CW, CH, BL, BW, BH)
    
    # Try Orientation 2: Align Box W with Container L (Rotate 90 deg on floor)
    fit2, bpl2, layers2 = calculate_fit_simple(CL, CW, CH, BW, BL, BH)
    
    # Select Best Fit by Quantity
    best_fit = 0
    orientation = "LxW"
    details = {}
    
    if fit1 >= fit2:
        best_fit = fit1
        orientation = "Normal (LxL)"
        details = {"boxes_per_layer": bpl1, "layers": layers1, "variant": "Length along Container Length"}
    else:
        best_fit = fit2
        orientation = "Rotated (WxL)"
        details = {"boxes_per_layer": bpl2, "layers": layers2, "variant": "Width along Container Length"}
        
    # Weight Constraint
    total_weight = best_fit * BoxWeight
    
    msg = "OK"
    if container.max_weight_kg > 0 and total_weight > float(container.max_weight_kg):
        # Exceeds limit. Cap it.
        max_boxes_by_weight = math.floor(float(container.max_weight_kg) / BoxWeight) if BoxWeight > 0 else best_fit
        if max_boxes_by_weight < best_fit:
            best_fit = max_boxes_by_weight
            total_weight = best_fit * BoxWeight
            msg = "Limited by Max Weight"
            
    details["status"] = msg
    
    # Calculate Utilization % (Volume)
    cont_vol = CL * CW * CH
    box_vol = BL * BW * BH
    used_vol = best_fit * box_vol
    
    pct = 0
    if cont_vol > 0:
        pct = round((used_vol / cont_vol) * 100, 2)
        
    # Save History
    calc_record = ContainerLoadCalc(
        organization_id=org_id,
        container_type_id=container.id,
        box_type_id=box.id,
        total_boxes_fit=best_fit,
        total_weight_kg=total_weight,
        volume_utilization_pct=pct,
        orientation_used=orientation,
        result_json=details,
        created_by_user_id=current_user.id
    )
    db.add(calc_record)
    db.commit()
    db.refresh(calc_record)
    
    return LoadCalcResult(
        boxes_fit=best_fit,
        total_weight_kg=total_weight,
        utilization_pct=pct,
        orientation=orientation,
        details=details,
        saved_id=calc_record.id
    )

# --------------------------------------------------------------------------
# SHIPMENTS CURD (Entradas de Mercancía)
# --------------------------------------------------------------------------

def _validar_contenedor(db: Session, container_type_id: Optional[int], org_id: int) -> None:
    """El contenedor de una entrada debe ser de la organización activa."""
    if container_type_id is None:
        return
    ok = db.query(ContainerType.id).filter(ContainerType.id == container_type_id, ContainerType.organization_id == org_id).first()
    if not ok:
        raise HTTPException(404, "Contenedor no encontrado")


def _get_shipment_or_404(db: Session, shipment_id: int, org_id: int) -> InboundShipment:
    s = db.query(InboundShipment).filter(
        InboundShipment.id == shipment_id,
        InboundShipment.organization_id == org_id,
    ).first()
    if not s:
        raise HTTPException(404, "Entrada no encontrada")
    return s

@router.post("/shipments", response_model=ShipmentRead)
def create_shipment(
    s: ShipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _validar_contenedor(db, s.container_type_id, org_id)
    data = s.dict()
    data["organization_id"] = org_id
    new_s = InboundShipment(**data)
    db.add(new_s)
    db.commit()
    db.refresh(new_s)
    return new_s

@router.get("/shipments", response_model=List[ShipmentRead])
def list_shipments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return db.query(InboundShipment).filter(
        InboundShipment.organization_id == org_id
    ).order_by(InboundShipment.created_at.desc()).all()

@router.get("/shipments/{id}", response_model=ShipmentRead)
def get_shipment(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    s = db.query(InboundShipment).options(
        joinedload(InboundShipment.items).joinedload(ShipmentItem.variant)
    ).filter(InboundShipment.id == id, InboundShipment.organization_id == org_id).first()
    if not s:
        raise HTTPException(404, "Entrada no encontrada")
    return s

@router.put("/shipments/{id}", response_model=ShipmentRead)
def update_shipment(
    id: int,
    up: ShipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    s = _get_shipment_or_404(db, id, org_id)
    if s.status == "RECEIVED":
        raise HTTPException(400, "No se puede editar una entrada ya recibida")
    _validar_contenedor(db, up.container_type_id, org_id)
    s.reference = up.reference
    s.notes = up.notes
    s.container_type_id = up.container_type_id
    s.arrival_date = up.arrival_date
    db.commit()
    db.refresh(s)
    return s

@router.delete("/shipments/{id}")
def delete_shipment(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    s = _get_shipment_or_404(db, id, org_id)
    if s.status == "RECEIVED":
        raise HTTPException(400, "No se puede eliminar una entrada ya procesada")
    db.delete(s)
    db.commit()
    return {"message": "Entrada eliminada"}

@router.post("/shipments/{id}/items", response_model=ShipmentRead)
def add_shipment_item(
    id: int,
    item: ShipmentItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    s = _get_shipment_or_404(db, id, org_id)
    if s.status == "RECEIVED":
        raise HTTPException(400, "No se puede modificar una entrada ya recibida")
    new_item = ShipmentItem(
        shipment_id=id,
        **item.dict(),
        total_units=item.quantity_boxes * item.units_per_box
    )
    db.add(new_item)
    db.commit()
    db.refresh(s)
    return s

@router.delete("/shipments/{id}/items/{item_id}", response_model=ShipmentRead)
def remove_shipment_item(
    id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    s = _get_shipment_or_404(db, id, org_id)
    if s.status == "RECEIVED":
        raise HTTPException(400, "No se puede modificar una entrada ya recibida")
    item = db.query(ShipmentItem).filter(
        ShipmentItem.id == item_id,
        ShipmentItem.shipment_id == id
    ).first()
    if item:
        db.delete(item)
        db.commit()
    db.refresh(s)
    return s

@router.post("/shipments/{id}/receive")
def receive_shipment(
    id: int,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Finalize shipment: Update Stock"""
    s = db.query(InboundShipment).options(joinedload(InboundShipment.items)).filter(
        InboundShipment.id == id,
        InboundShipment.organization_id == org_id,
    ).first()
    if not s:
        raise HTTPException(404, "Entrada no encontrada")
    if s.status == "RECEIVED":
        raise HTTPException(400, "Esta entrada ya fue procesada")

    target_branch_id = branch_id if branch_id else current_user.branch_id

    # Update Inventory
    for item in s.items:
        if not item.variant_id:
            continue
            
        qty_to_add = Decimal(item.total_units)
        
        # 1. Update StockOnHand — A2-20 propagate organization_id on read+create.
        stock = db.query(StockOnHand).filter(
            StockOnHand.variant_id == item.variant_id,
            StockOnHand.branch_id == target_branch_id,
            StockOnHand.organization_id == org_id,
        ).first()

        qty_before = Decimal(0)
        if stock:
            qty_before = stock.qty_on_hand
            stock.qty_on_hand += qty_to_add
        else:
            # Create stock record if not exists
            stock = StockOnHand(
                organization_id=org_id,
                branch_id=target_branch_id,
                variant_id=item.variant_id,
                qty_on_hand=qty_to_add
            )
            db.add(stock)

        # 2. Record Movement — A2-20 propagate organization_id.
        mv = InventoryMovement(
            organization_id=org_id,
            branch_id=target_branch_id,
            variant_id=item.variant_id,
            user_id=current_user.id,
            movement_type=MovementType.PURCHASE_IN, # Or ADJUSTMENT_IN
            qty_change=qty_to_add,
            qty_before=qty_before,
            qty_after=qty_before + qty_to_add,
            reference=f"Entrada #{s.id} Ref: {s.reference or ''}",
            notes=f"Recepción de Cajas: {item.quantity_boxes} x {item.units_per_box}"
        )
        db.add(mv)

    s.status = "RECEIVED"
    db.commit()
    
    return {"message": "Entrada procesada y stock actualizado", "shipment_id": s.id}
