"""Atlas BOS modules/products/models — Product catalog ORM.

DOMAIN: Catalogs / Products
STATUS: Stable

Phase 2 / S2: moved from app/models/products.py. The legacy path is now a
reverse-shim that re-exports from here.

Owns: Department, Brand, UnitOfMeasure, Product, ProductVariant,
ProductPrice, PackagingUnit, ProductBranchStatus.
"""
from sqlalchemy import Column, String, Boolean, ForeignKey, Numeric, Integer, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.mixins import UUIDMixin, AuditMixin, TenantMixin

# --- DEPARTAMENTOS (Antes Categories) ---
class Department(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "departments"
    __table_args__ = {'extend_existing': True}

    name = Column(String, index=True)
    description = Column(String, nullable=True)

class Brand(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "brands"
    __table_args__ = {'extend_existing': True}

    name = Column(String, index=True)
    logo_url = Column(String, nullable=True)

class UnitOfMeasure(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "uom"
    __table_args__ = {'extend_existing': True}

    name = Column(String, index=True)
    code = Column(String, index=True)

# --- PRODUCTO PADRE ---
class Product(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "products"
    __table_args__ = {'extend_existing': True}

    name = Column(String, index=True)
    description = Column(String, nullable=True)
    unit = Column(String, default="pza") # Ej: pza, kg, lt
    image_url = Column(String, nullable=True) # URL de imagen del producto (Cloudinary, CDN, etc.)

    brand_id = Column(String(36), ForeignKey("brands.id"), nullable=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True) # Departamento

    has_variants = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True) # "Global" soft-delete or active flag

    # [NEW] Robust Workflow
    approval_status = Column(String, default='APPROVED') # PENDING, APPROVED, REJECTED
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relaciones
    department = relationship("Department") # Relación con el modelo Department
    brand = relationship("Brand")
    # Orden determinista: sin `order_by`, `variants[0]` cambiaba entre requests
    # en cuanto un producto tenia mas de una variante.
    variants = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan",
        order_by="[ProductVariant.created_at, ProductVariant.id]",
    )

# --- VARIANTES (SKU) ---
class ProductVariant(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "product_variants"
    # Composite unique index: SKU is unique per organization for non-deleted rows.
    # `postgresql_where` makes it a partial index in Postgres so soft-deleted
    # variants don't block re-use; SQLite (tests) ignores the clause and creates
    # a plain unique index — acceptable since tests don't exercise soft-delete.
    __table_args__ = (
        Index(
            "ux_variant_sku_per_org",
            "organization_id",
            "sku",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        {'extend_existing': True},
    )

    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)

    sku = Column(String, index=True)  # Removed unique=True
    barcode = Column(String, index=True, nullable=True)
    variant_name = Column(String) # Etiqueta derivada: "Estándar", "Rojo / M" (ver variant_label.py)
    # Atributos de boutique (preset ATLAS_POS_BOUTIQUE). Opcionales: el resto de
    # los giros sigue con una sola variante sin color ni talla.
    color = Column(String(60), nullable=True)
    size = Column(String(30), nullable=True)

    price = Column(Numeric(10, 2)) # Precio Base (Lista 1)
    cost = Column(Numeric(10, 2))  # Costo Base

    # [NEW] Tax Handling
    has_iva = Column(Boolean, default=False)
    tax_rate = Column(Numeric(5, 2), default=16.0) # Porcentaje ej: 16.0

    product = relationship("Product", back_populates="variants")
    prices = relationship("ProductPrice", back_populates="variant", cascade="all, delete-orphan")
    packaging_units = relationship("PackagingUnit", back_populates="variant", cascade="all, delete-orphan")

# --- PRECIOS ESCALONADOS (Basado en cantidad, sin empaque físico) ---
class ProductPrice(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "product_prices"
    __table_args__ = {'extend_existing': True}

    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=False)

    price_name = Column(String) # Ej: "Mayoreo", "Distribuidor"
    min_quantity = Column(Numeric(10, 2), default=1) # A partir de cuántas piezas
    unit_price = Column(Numeric(10, 2), nullable=False)

    linked_package_id = Column(String(36), ForeignKey("packaging_units.id"), nullable=True)

    variant = relationship("ProductVariant", back_populates="prices")
    linked_package = relationship("PackagingUnit")

# --- NUEVO: UNIDADES DE EMPAQUE (Jerarquía: Caja, Pack, etc) ---
class PackagingUnit(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "packaging_units"
    __table_args__ = {'extend_existing': True}

    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=False)

    name = Column(String) # Ej: "Caja", "Master", "Six-Pack"
    barcode = Column(String, index=True, nullable=True) # El "Item No" de la caja

    units_per_package = Column(Numeric(10, 2), default=1) # QTY (piezas en caja)
    package_price = Column(Numeric(10, 2), nullable=False) # Precio de la caja completa

    # Opcionales para trazabilidad/logística
    weight = Column(Numeric(10, 3), nullable=True)
    dimensions = Column(String, nullable=True) # Ej: "10x20x30"

    variant = relationship("ProductVariant", back_populates="packaging_units")

# --- HABILITACIÓN COMERCIAL POR SUCURSAL (Matriz Producto×Sucursal) ---
class ProductBranchStatus(Base, UUIDMixin, AuditMixin, TenantMixin):
    """
    Matriz de Habilitación Comercial: Define en qué sucursales se puede vender/cotizar cada producto.
    Separa la lógica de "disponibilidad comercial" del inventario físico.
    """
    __tablename__ = "product_branch_status"
    __table_args__ = (
        # Composite unique: Un producto-variante solo puede tener un registro por sucursal
        UniqueConstraint('variant_id', 'branch_id', name='uq_variant_branch_status'),
        {'extend_existing': True}
    )

    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)

    # Flags de Habilitación
    is_active_pos = Column(Boolean, default=True, server_default="true")  # Vendible en POS de esta sucursal
    is_active_hq = Column(Boolean, default=False, server_default="false")  # Disponible para cotizaciones/notas desde HQ para esta sucursal
    is_visible = Column(Boolean, default=True, server_default="true")     # Visible en catálogos/búsquedas

    # Opcionales: Políticas por Sucursal
    price_override = Column(Numeric(10, 2), nullable=True)  # Precio fijo para esta sucursal (anula precio base)
    min_stock_alert = Column(Numeric(10, 2), nullable=True) # Alerta de stock mínimo específica
    max_stock_limit = Column(Numeric(10, 2), nullable=True) # Límite de stock máximo

    # Relaciones
    variant = relationship("ProductVariant", backref="branch_statuses")
    # branch relationship will be added when Branch model is available
