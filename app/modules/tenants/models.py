"""Atlas BOS modules/tenants/models — Organizational / Tenancy.

MOONSHOT_ENGINE: Nucleus
DOMAIN: Organizational / Tenancy
STATUS: Stable

Phase 2 / S1 Phase B: this module owns the Organization, Branch, BranchType,
and IndustryType classes (the tenant root + its operational units). The
legacy `app/models/organization.py` is now a reverse-shim re-exporting
from here.
"""
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import TenantMixin


class BranchType(str, enum.Enum):
    HQ = "HQ"
    STORE = "STORE"
    WAREHOUSE = "WAREHOUSE"
    OFFICE = "OFFICE"


class IndustryType(str, enum.Enum):
    # Retail / Comercio
    ATLAS_POS = "ATLAS_POS"
    # Boutique de ropa/moda: ATLAS_POS + modulo `scanner` (camara para cajeros).
    ATLAS_POS_BOUTIQUE = "ATLAS_POS_BOUTIQUE"
    DISTRIBUTOR_POS = "DISTRIBUTOR_POS"
    RETAIL_CHAIN = "RETAIL_CHAIN"
    ECOMMERCE = "ECOMMERCE"
    WHOLESALE_B2B = "WHOLESALE_B2B"

    # Servicios
    SALON = "SALON"
    CLINIC = "CLINIC"
    DENTAL = "DENTAL"
    PROFESSIONAL_SERVICES = "PROFESSIONAL_SERVICES"

    # Hospitality
    RESTAURANT_QSR = "RESTAURANT_QSR"
    RESTAURANT_FULL = "RESTAURANT_FULL"
    CAFE_BAKERY = "CAFE_BAKERY"

    # Automotriz / Taller
    AUTO_REPAIR_SHOP = "AUTO_REPAIR_SHOP"
    FLEET_SERVICE = "FLEET_SERVICE"

    # Comercial / Ventas
    SALES_DISTRIBUTION = "SALES_DISTRIBUTION"
    B2B_ENTERPRISE = "B2B_ENTERPRISE"

    # Logística / Inventario
    WAREHOUSE_LOGISTICS = "WAREHOUSE_LOGISTICS"
    MANUFACTURING_LIGHT = "MANUFACTURING_LIGHT"

    # Genérico
    CUSTOM = "CUSTOM"

    # Atlas One commercial suite (2026-05-13)
    ATLAS_ONE_RETAIL = "ATLAS_ONE_RETAIL"
    ATLAS_ONE_BEAUTY = "ATLAS_ONE_BEAUTY"          # legacy — use BEAUTY_WELLNESS or BARBER
    ATLAS_ONE_GASTRO = "ATLAS_ONE_GASTRO"          # legacy — use RESTAURANT, CAFE, or BAR
    ATLAS_ONE_SERVICES = "ATLAS_ONE_SERVICES"
    ATLAS_ONE_ENTERPRISE = "ATLAS_ONE_ENTERPRISE"

    # Atlas One vertical-specific presets (2026-05-15 taxonomy v2)
    ATLAS_ONE_BARBER = "ATLAS_ONE_BARBER"
    ATLAS_ONE_BEAUTY_WELLNESS = "ATLAS_ONE_BEAUTY_WELLNESS"
    ATLAS_ONE_HEALTH = "ATLAS_ONE_HEALTH"
    ATLAS_ONE_RESTAURANT = "ATLAS_ONE_RESTAURANT"
    ATLAS_ONE_CAFE = "ATLAS_ONE_CAFE"
    ATLAS_ONE_BAR = "ATLAS_ONE_BAR"


class Branch(Base, TenantMixin):
    __tablename__ = "branches"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)

    # Datos base
    name = Column(String, index=True, nullable=False)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # Type & permissions
    branch_type = Column(Enum(BranchType), default=BranchType.STORE, nullable=False)
    can_sell = Column(Boolean, default=True)

    # Flags
    is_active = Column(Boolean, default=True)
    is_headquarters = Column(Boolean, default=False)  # legacy compat — prefer branch_type=HQ

    # Printer config (per branch)
    printer_name = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    ticket_header = Column(String, nullable=True)
    ticket_footer = Column(String, nullable=True)
    paper_width_mm = Column(Integer, nullable=True, default=80)
    open_drawer_on_print = Column(Boolean, default=True, nullable=False)

    # Cockpit / day-mode
    daily_sales_goal = Column(Numeric(12, 2), nullable=True)
    closing_time = Column(Time, nullable=True)

    # Geolocalización detallada
    address_line1 = Column(String, nullable=True)
    address_line2 = Column(String, nullable=True)
    neighborhood = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    country = Column(String, default="MX", nullable=True)

    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    maps_url = Column(String, nullable=True)
    place_id = Column(String, nullable=True)
    timezone = Column(String, nullable=True)

    # organization_id comes from TenantMixin

    users = relationship("User", back_populates="branch")

    outgoing_movements = relationship(
        "InventoryMovement",
        foreign_keys="InventoryMovement.from_branch_id",
        back_populates="from_branch",
    )
    incoming_movements = relationship(
        "InventoryMovement",
        foreign_keys="InventoryMovement.to_branch_id",
        back_populates="to_branch",
    )


class Organization(Base):
    """Tenant root — fiscal identity, branding, ticket config."""
    __tablename__ = "organization"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)

    # Identidad
    name = Column(String, default="Mi Empresa")
    legal_name = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    tax_regime = Column(String, nullable=True)

    # Contacto
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)

    # Branding / tickets
    logo_url = Column(String, nullable=True)
    ticket_header = Column(String, nullable=True, default="ATLAS POS - Nota de Venta")
    ticket_footer = Column(String, nullable=True, default="Gracias por su compra!")
    printer_name = Column(String, nullable=True)

    # Secciones boutique del ticket (2026-09-19). Todas NULL por defecto: una
    # organizacion que no las capture imprime el ticket de siempre, byte por
    # byte (app/pos_printer.py::_build_boutique_footer).
    ticket_terms = Column(Text, nullable=True)
    # Enlace a la politica completa: el ticket lo imprime como QR nativo mas la
    # URL en texto, para no gastar papel copiando el reglamento entero.
    ticket_terms_url = Column(String, nullable=True)
    ticket_instagram = Column(String, nullable=True)
    ticket_facebook = Column(String, nullable=True)
    ticket_tiktok = Column(String, nullable=True)
    ticket_whatsapp = Column(String, nullable=True)
    # La linea del proveedor viene APAGADA: encenderla agrega dos lineas al
    # ticket de un negocio vivo, y eso lo decide su dueño desde Empresa.
    ticket_show_vendor = Column(Boolean, nullable=False, default=False, server_default="false")

    # Estilo del renglon de producto del ticket (2026-09-21):
    #   'compact'  -> una linea: cantidad + descripcion recortada + precios
    #                 (DEFAULT, y es lo que sigue viendo toda tienda viva)
    #   'detailed' -> tres lineas: marca / nombre completo envuelto / talla y
    #                 precios (app/pos_printer.py::_product_lines_detailed)
    ticket_line_style = Column(String(12), default="compact", server_default="compact", nullable=False)

    # Geolocalización
    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    maps_url = Column(String, nullable=True)
    timezone = Column(String, nullable=True, default="America/Mexico_City")

    # Fiscal — modo de precio. False (default): el precio del catálogo es neto y
    # el IVA se suma encima (comportamiento histórico de Atlas ONE). True: el
    # precio ya trae el IVA y se desglosa. Lo consume app/services/tax.py.
    price_includes_tax = Column(Boolean, default=False, server_default="false", nullable=False)

    # Equivalente en dolares (2026-09-17). `usd_rate_mode`:
    #   'off'    -> apagado: el POS y el ticket no muestran nada (DEFAULT, y es
    #               lo que queda para todas las organizaciones ya existentes)
    #   'auto'   -> FIX de Banxico del dia + `usd_rate_margin`
    #   'manual' -> `usd_rate_manual`, capturado por el administrador
    # VARCHAR con constantes en app/services/exchange_rate.py, NO enum de DB
    # (CLAUDE.md §5: un enum nuevo obliga a ALTER TYPE por cada modo).
    usd_rate_mode = Column(String(10), default="off", server_default="off", nullable=False)
    usd_rate_manual = Column(Numeric(10, 4), nullable=True)
    # Pesos que se suman al FIX en modo 'auto' (el spread de ventanilla del
    # negocio). Puede ser negativo.
    usd_rate_margin = Column(Numeric(10, 4), default=0, server_default="0", nullable=False)

    # Comision por pago con tarjeta (2026-09-17). Porcentaje que se suma a la
    # parte de la venta cobrada con TARJETA (solo `PaymentMethod.CARD`; en un
    # pago mixto, solo a esa parte). 0 = apagado, y es el DEFAULT para todas
    # las organizaciones ya existentes.
    #
    # NUMERIC(5,2) y no (6,3) a proposito: `app/pos_printer.py::_total_line` da
    # 20 columnas de etiqueta en papel de 58 mm y NO trunca, asi que un tercer
    # decimal desbordaria el renglon "COM. TARJETA 19.999%" del ticket.
    # La regla de calculo vive en app/services/card_surcharge.py.
    card_surcharge_pct = Column(Numeric(5, 2), default=0, server_default="0", nullable=False)

    # SaaS
    status = Column(String, default="ACTIVE", index=True)  # ACTIVE, SUSPENDED
    plan = Column(String, default="FREE")
    branding_config = Column(String, nullable=True)  # JSON storable

    # Modular suite
    industry_type = Column(Enum(IndustryType), nullable=True)
    slug = Column(String(64), nullable=True, unique=True)
    hq_branch_id = Column(
        Integer,
        ForeignKey("branches.id", use_alter=True, name="fk_organization_hq_branch"),
        nullable=True,
    )
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    users_association = relationship("UserOrganization", back_populates="organization")
    modules_association = relationship("OrganizationModule", back_populates="organization")
