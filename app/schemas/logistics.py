from typing import Optional, List, Any, Dict
from pydantic import BaseModel, field_validator
from datetime import datetime

# --- Container ---
class ContainerTypeBase(BaseModel):
    name: str
    inner_length: float
    inner_width: float
    inner_height: float
    max_weight_kg: float

class ContainerTypeCreate(ContainerTypeBase):
    pass

class ContainerTypeRead(ContainerTypeBase):
    id: int
    class Config:
        from_attributes = True

# --- Box ---
class BoxTypeBase(BaseModel):
    name: str
    outer_length: float
    outer_width: float
    outer_height: float
    weight_empty_kg: float

class BoxTypeCreate(BoxTypeBase):
    pass

class BoxTypeRead(BoxTypeBase):
    id: int
    class Config:
        from_attributes = True

# --- Packaging ---
class PackagingCreate(BaseModel):
    variant_id: str
    box_type_id: int
    units_per_box: int
    item_no: Optional[str] = None
    box_barcode: Optional[str] = None

class PackagingRead(PackagingCreate):
    id: int
    class Config:
        from_attributes = True

# --- Calculation ---
class LoadCalcRequest(BaseModel):
    container_type_id: int
    box_type_id: int
    weight_per_box_kg: Optional[float] = None

class LoadCalcResult(BaseModel):
    boxes_fit: int
    total_weight_kg: float
    utilization_pct: float
    orientation: str
    details: Dict[str, Any]
    saved_id: Optional[int] = None

# --- Shipments (Entradas) ---
class ShipmentItemCreate(BaseModel):
    box_type_id: Optional[int] = None
    variant_id: Optional[str] = None
    quantity_boxes: int = 1
    units_per_box: int = 1

# --- Products Minimal ---
class VariantSimpleRead(BaseModel):
    id: str
    sku: str
    barcode: Optional[str] = None
    
    class Config:
        from_attributes = True

class ShipmentItemRead(ShipmentItemCreate):
    id: int
    total_units: int
    # Optional nested details for UI
    variant: Optional[VariantSimpleRead] = None 
    box_type: Optional[BoxTypeRead] = None
    
    class Config:
        from_attributes = True

    @field_validator('variant', mode='before')
    @classmethod
    def parse_variant(cls, v):
        if not v:
            return None
        # Handle SQLAlchemy object manually to ensure serialization
        if hasattr(v, 'sku'):
            return {
                "id": str(v.id),
                "sku": v.sku, 
                "barcode": getattr(v, 'barcode', None)
            }
        return v

class ShipmentCreate(BaseModel):
    reference: Optional[str] = None
    notes: Optional[str] = None
    container_type_id: Optional[int] = None
    arrival_date: Optional[datetime] = None

class ShipmentRead(ShipmentCreate):
    id: int
    status: str
    created_at: datetime
    items: List[ShipmentItemRead] = []
    
    class Config:
        from_attributes = True

# --- Transfers ---
from app.models.logistics import TransferStatus, FulfillmentStatus
from decimal import Decimal

class TransferLineCreate(BaseModel):
    variant_id: str
    qty_requested: Decimal

class TransferOrderCreate(BaseModel):
    requesting_branch_id: int
    notes: Optional[str] = None
    lines: List[TransferLineCreate]

class TransferOrderRead(BaseModel):
    id: int
    requesting_branch_id: int
    status: TransferStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None  # el modelo solo lo llena en onupdate
    
    class Config:
        from_attributes = True

class FulfillmentLineCreate(BaseModel):
    transfer_line_id: int
    qty_fulfilled: Decimal

class TransferFulfillmentCreate(BaseModel):
    source_branch_id: int
    lines: List[FulfillmentLineCreate]

class TransferFulfillmentRead(BaseModel):
    id: int
    transfer_id: int
    source_branch_id: int
    status: FulfillmentStatus
    shipped_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
