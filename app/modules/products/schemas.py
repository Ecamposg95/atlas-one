"""Atlas BOS modules/products/schemas — Pydantic schemas for product catalog.

DOMAIN: Catalogs / Products
STATUS: Stable

Phase 2 / S2: moved from app/schemas/products.py. The legacy path is now a
reverse-shim that re-exports from here.
"""
from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal

# --- Deptos / Categorías ---
class DepartmentRead(BaseModel):
    id: str # UUID
    name: str
    class Config:
        from_attributes = True

# --- Precios Escalonados ---
class ProductPriceBase(BaseModel):
    price_name: str
    min_quantity: Decimal
    unit_price: Decimal
    linked_package_id: Optional[str] = None

class ProductPriceCreate(ProductPriceBase):
    pass

class ProductPriceRead(ProductPriceBase):
    id: str # UUID
    class Config:
        from_attributes = True

# --- Unidades de Empaque ---
class PackagingUnitBase(BaseModel):
    name: Optional[str] = "Sin Nombre"
    barcode: Optional[str] = None
    units_per_package: Decimal
    package_price: Decimal
    weight: Optional[Decimal] = None
    dimensions: Optional[str] = None

class PackagingUnitCreate(PackagingUnitBase):
    temp_id: Optional[str] = None

class PackagingUnitRead(PackagingUnitBase):
    id: str # UUID
    class Config:
        from_attributes = True

# --- Variantes ---
class ProductVariantRead(BaseModel):
    id: str # UUID
    sku: str
    barcode: Optional[str] = None
    # Etiqueta y atributos (boutique). Antes no viajaban y el frontend no podia
    # distinguir dos variantes del mismo producto.
    variant_name: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    price: Decimal
    # Lo que el POS COBRA por esta variante en la sucursal objetivo: el
    # `price_override` del ProductBranchStatus si lo hay, y si no el precio
    # base. `price` se deja intacto porque es el que edita la ficha de
    # variantes. La llena `_compute_product_read`; no existe en el ORM.
    effective_price: Optional[Decimal] = None
    cost: Decimal
    has_iva: bool = False
    tax_rate: Decimal = 16.0
    # Existencia de ESTA variante en la sucursal objetivo. La llena
    # `_compute_product_read`; no existe en el ORM.
    stock_total: Decimal = Decimal(0)
    prices: List[ProductPriceRead] = [] # Incluimos la lista de precios
    packaging_units: List[PackagingUnitRead] = [] # Empaques específicos de esta variante
    class Config:
        from_attributes = True

class ProductVariantCreate(BaseModel):
    """Una variante de color/talla. `sku` vacio = generado desde el SKU base.
    `price`/`cost` vacios = heredan de la variante principal."""
    color: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    # Existencia inicial DE ESTA TALLA en la sucursal destino. Antes el alta
    # cargaba todo el stock inicial en la principal y M/G nacian en cero, asi
    # que la boutique tenia las diez prendas en la talla Ch.
    initial_stock: Decimal = Decimal(0)


class VariantBatchCreate(BaseModel):
    variants: List[ProductVariantCreate]
    # Sucursal donde aterriza `initial_stock`. Opcional: con una sola sucursal
    # habilitada se deduce sola; con varias hay que decirla (no se adivina).
    branch_id: Optional[int] = None


class ProductVariantUpdate(BaseModel):
    color: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    unit: Optional[str] = "pza"
    image_url: Optional[str] = None

    sku: str
    barcode: Optional[str] = None

    # Color/talla de la VARIANTE PRINCIPAL (preset boutique). La matriz del
    # alta manda aqui su primera combinacion, asi que la principal ES esa
    # prenda y no una "Estándar" sin talla que nadie puede vender.
    # Ausentes (el resto de los tenants) -> variant_name = "Estándar".
    color: Optional[str] = None
    size: Optional[str] = None

    price: Decimal      # Precio base (se guarda en variant.price)
    cost: Decimal
    has_iva: bool = False
    tax_rate: Decimal = 16.0

    department_id: Optional[str] = None # UUID
    brand_id: Optional[str] = None # UUID

    initial_stock: Decimal = Decimal(0)
    branch_id: Optional[int] = None
    target_branch_ids: Optional[List[int]] = None # IDs de sucursales donde habilitar
    uses_inventory: bool = True

    # Lista de precios extra (Mayoreo, etc)
    prices: List[ProductPriceCreate] = []

    # Lista de empaques (Caja, etc)
    packaging_units: List[PackagingUnitCreate] = []

    # Extra Variants
    extra_variants: List[ProductVariantCreate] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    image_url: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    # Color/talla de la variante principal (mismo criterio que ProductCreate).
    color: Optional[str] = None
    size: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    has_iva: Optional[bool] = None
    tax_rate: Optional[Decimal] = None
    department_id: Optional[str] = None # UUID
    brand_id: Optional[str] = None # UUID
    uses_inventory: Optional[bool] = None
    is_active: Optional[bool] = None
    approval_status: Optional[str] = None

    # Para editar, reemplazamos la lista de precios completa
    prices: Optional[List[ProductPriceCreate]] = None

    # Reemplazamos la lista de empaques
    packaging_units: Optional[List[PackagingUnitCreate]] = None

    # Reemplazamos variantes extra (excepto la principal que se maneja con sku/price arriba)
    extra_variants: Optional[List[ProductVariantCreate]] = None

    # [NEW] Branch availability update (RBAC: only ADMIN can use this)
    target_branch_ids: Optional[List[int]] = None

class BatchActionRequest(BaseModel):
    action: str  # 'delete', 'activate', 'deactivate', 'approve'
    ids: List[str]

# --- Producto Lectura (Output) ---
class StockLevel(BaseModel):
    branch_id: int # Branch ID stays Integer for now
    branch_name: Optional[str] = None # NEW: For display
    qty_on_hand: Decimal
    is_active: bool = True
    is_active_pos: Optional[bool] = None  # ProductBranchStatus.is_active_pos (POS enablement)

class ProductRead(BaseModel):
    id: str # UUID
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool
    department: Optional[DepartmentRead] = None

    # En listados simples, devolvemos la variante principal aplanada
    variants: List[ProductVariantRead] = []
    # Que variante representan los campos aplanados (sku/price/stock_total).
    # En una busqueda por codigo es la que empato; si no, la primera.
    matched_variant_id: Optional[str] = None

    # Campos computados para facilitar el frontend
    sku: Optional[str] = ""
    barcode: Optional[str] = ""
    cost: Decimal = Decimal(0)
    price: Decimal = Decimal(0) # Main variant price
    has_iva: bool = False
    tax_rate: Decimal = 16.0

    stock_total: Decimal = Decimal(0) # Local branch stock (backward compat)
    global_stock: Decimal = Decimal(0) # NEW: Total across all branches
    prices: List[ProductPriceRead] = [] # Precios de la variante principal
    packaging_units: List[PackagingUnitRead] = [] # Empaques de la variante principal

    # Info de stock detallada (opcional)
    stock_levels: List[StockLevel] = []

    # Box / Packaging Highlights
    main_packaging_name: Optional[str] = None
    main_packaging_price: Optional[Decimal] = None
    main_packaging_units: Optional[Decimal] = None

    # Campos aplanados para el frontend POS (ATS-12)
    department_name: Optional[str] = None
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None

    # Workflow
    approval_status: Optional[str] = 'APPROVED'

    # Commercial Enablement (Module 2)
    branch_statuses: List['ProductBranchStatusRead'] = []

    class Config:
        from_attributes = True

# --- HABILITACIÓN COMERCIAL POR SUCURSAL ---
class ProductBranchStatusBase(BaseModel):
    variant_id: str
    branch_id: int
    is_active_pos: bool = True
    is_active_hq: bool = False
    is_visible: bool = True
    price_override: Optional[Decimal] = None
    min_stock_alert: Optional[Decimal] = None
    max_stock_limit: Optional[Decimal] = None

class ProductBranchStatusCreate(BaseModel):
    """Schema for creating branch status - variant_id will come from context"""
    branch_id: int
    is_active_pos: bool = True
    is_active_hq: bool = False
    is_visible: bool = True
    price_override: Optional[Decimal] = None

class ProductBranchStatusUpdate(BaseModel):
    """Schema for updating branch status flags"""
    is_active_pos: Optional[bool] = None
    is_active_hq: Optional[bool] = None
    is_visible: Optional[bool] = None
    price_override: Optional[Decimal] = None
    min_stock_alert: Optional[Decimal] = None
    max_stock_limit: Optional[Decimal] = None

class ProductBranchStatusRead(ProductBranchStatusBase):
    id: str
    branch_name: Optional[str] = None  # For display purposes
    class Config:
        from_attributes = True


class BranchStatusUpdate(BaseModel):
    """
    D0 — PATCH PBS body. Only fields explicitly set are applied (see
    `model_fields_set` / `model_dump(exclude_unset=True)`).

    Used by `PATCH /api/products/variants/{variant_id}/branch-status` to let
    CAJERO/GERENTE edit PBS for their own branch; ADMIN/DUEÑO must pass
    `?branch_id=N` as query param.
    """
    price_override: Optional[Decimal] = None
    min_stock_alert: Optional[Decimal] = None
    max_stock_limit: Optional[Decimal] = None
    is_active_pos: Optional[bool] = None
    is_active_hq: Optional[bool] = None
    is_visible: Optional[bool] = None


class BulkToggleBranchStatusRequest(BaseModel):
    """
    Body para `POST /api/products/branch-status/bulk-toggle`.

    Habilita/deshabilita múltiples variantes en múltiples sucursales en una
    sola llamada. Todas las variantes y sucursales deben pertenecer a la
    organización del token (validado server-side).
    """
    variant_ids: List[str]
    branch_ids: List[int]
    is_active_pos: bool = True
    is_active_hq: Optional[bool] = None
    is_visible: Optional[bool] = None


class BranchStatusFlagsUpdate(BaseModel):
    """
    Body para `PUT /api/products/branch-status/{status_id}`.

    Solo los campos explícitamente enviados se aplican (exclude_unset).
    Sustituye el payload `dict` crudo que se usaba antes.
    """
    is_active_pos: Optional[bool] = None
    is_active_hq: Optional[bool] = None
    is_visible: Optional[bool] = None
    price_override: Optional[Decimal] = None
    min_stock_alert: Optional[Decimal] = None
    max_stock_limit: Optional[Decimal] = None


class PackagingUpdate(BaseModel):
    """Body para `PUT /api/products/packaging/{packaging_id}`."""
    box_name: Optional[str] = None
    units_per_package: Optional[Decimal] = None
    package_price: Optional[Decimal] = None
    box_barcode: Optional[str] = None


class PbsCloneRequest(BaseModel):
    """
    Body para `POST /api/products/branch-status/clone`.

    Clona configuración PBS (is_active_pos, is_active_hq, is_visible,
    price_override, min_stock_alert, max_stock_limit) desde `from_branch_id`
    hacia cada una de las `to_branch_ids`.

    Si `variant_ids` queda vacío, se clonan TODAS las variantes que tienen
    PBS en la sucursal origen — útil para replicar una sucursal nueva a
    partir de otra existente.

    `overwrite=False` (default) deja intactos los PBS que ya existan en las
    sucursales destino; `overwrite=True` pisa sus valores con los del origen.
    """
    from_branch_id: int
    to_branch_ids: List[int]
    variant_ids: Optional[List[str]] = None
    overwrite: bool = False


class PbsCloneResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    from_branch_id: int
    to_branch_ids: List[int]


class PBSResponse(BaseModel):
    """D0 — Full PBS serialization returned by PATCH/GET branch-status."""
    id: str
    variant_id: str
    branch_id: int
    is_active_pos: bool
    is_active_hq: bool
    is_visible: bool
    price_override: Optional[Decimal] = None
    min_stock_alert: Optional[Decimal] = None
    max_stock_limit: Optional[Decimal] = None

    class Config:
        from_attributes = True

# --- HQ Inventory Paginated Response ---
class ProductListResponse(BaseModel):
    items: List[ProductRead]
    total: int

class HQInventoryKPIs(BaseModel):
    total_skus: int
    low_stock_count: int
    zero_stock_count: int
    inventory_value: float

class HQInventoryPage(BaseModel):
    items: List[ProductRead]
    total: int
    skip: int
    limit: int
    kpis: HQInventoryKPIs
