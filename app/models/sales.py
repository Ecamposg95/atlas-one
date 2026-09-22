"""
MOONSHOT_ENGINE: Transaction Engine (Data Layer)
DOMAIN: Sales / POS
"""
import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, Numeric, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.mixins import UUIDMixin, AuditMixin, TenantMixin

# --- Enums ---
class DocumentType(str, enum.Enum):
    QUOTE = "QUOTE"       # Cotización
    ORDER = "ORDER"       # Pedido
    INVOICE = "INVOICE"   # Ticket/Factura
    RETURN = "RETURN"     # Devolución

class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"       # Borrador (Creado en Móvil)
    PENDING = "PENDING"   # En Caja / Por cobrar
    PAID = "PAID"         # Pagado
    CANCELLED = "CANCELLED"
    REFUNDED_PARTIAL = "REFUNDED_PARTIAL"
    REFUNDED_TOTAL = "REFUNDED_TOTAL"

class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"

class CashSessionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

# --- Modelo 1: Encabezado de Venta ---
class SalesDocument(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "sales_documents"
    __table_args__ = {'extend_existing': True}

    doc_type = Column(Enum(DocumentType), default=DocumentType.INVOICE, index=True)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PAID, index=True)
    
    # Mantener Integer por ahora para evitar refactor masivo de User/Branch
    # TODO: Migrar a UUID en Fase 2
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False) # TODO: Migrate to UUID
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False) # TODO: Migrate to UUID
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # TODO: Migrate to UUID
    customer_name = Column(String(255), nullable=True) # Free-text name for ticket

    # Track 1 (POS bug-fix): vincula la venta a la sesión de caja OPEN del cajero
    # al momento de crearla. Permite que el corte agrupe por cash_session_id en
    # lugar de filtros temporales (problema con N PCs del mismo cajero).
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=True, index=True)

    series = Column(String, nullable=True)
    folio = Column(Integer, nullable=True)
    
    subtotal = Column(Numeric(10, 2), default=0.00)
    tax_amount = Column(Numeric(10, 2), default=0.00)
    total_amount = Column(Numeric(10, 2), default=0.00)

    # Vuelto entregado al cliente cuando paga con efectivo más de lo necesario.
    # Se calcula al crear la venta y se persiste para que el cuadre de turno NO
    # tenga que recomputarlo (evita inconsistencias si la lógica retrospectiva
    # cambia). NULL = venta legada anterior a la migración → recomputar.
    change_given = Column(Numeric(12, 2), nullable=True)

    # Equivalente en dolares (2026-09-17): tipo de cambio efectivo CONGELADO al
    # cobrar, para que el ticket y su reimpresion muestren siempre el mismo
    # numero aunque el FIX de mañana sea otro. NULL = venta anterior a la
    # funcion, o organizacion en modo 'off'. NO participa de ningun calculo de
    # cobro; es informativo (ver app/services/exchange_rate.py).
    usd_rate = Column(Numeric(10, 4), nullable=True)

    # Comision por pago con tarjeta (2026-09-17), CONGELADA al cobrar.
    # `total_amount` NO la incluye: es mercancia (+IVA +propina) y punto, para
    # que el reporte de ingresos y el histórico no se muevan. El total que el
    # cliente pago es `total_amount + card_surcharge_amount`.
    # `card_surcharge_pct` solo se guarda cuando la comision se aplico de
    # verdad; NULL = venta anterior a la funcion, organizacion sin comision, o
    # venta sin pago con tarjeta.
    # La regla de calculo vive en app/services/card_surcharge.py.
    card_surcharge_pct = Column(Numeric(5, 2), nullable=True)
    card_surcharge_amount = Column(Numeric(10, 2), default=0, server_default="0", nullable=False)

    requires_invoice = Column(Boolean, default=False)

    # Gastro — propina cobrada (se suma al total) y atribución al mesero de la
    # mesa para el reporte "ventas por mesero". server_user_id se copia del
    # DiningTable.server_user_id al cobrar; NULL para ventas de mostrador.
    tip_amount = Column(Numeric(10, 2), default=0)
    server_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Identificador que genera el POS por intento de cobro. Si el cajero
    # reintenta (cola offline / boton "Reintentar ahora") llega el MISMO
    # valor y el checkout devuelve la venta original en vez de duplicarla.
    client_uuid = Column(String(64), nullable=True, index=True)
    notes = Column(String, nullable=True)

    # Relaciones
    branch = relationship("Branch")
    seller = relationship("User", foreign_keys=[seller_id])
    customer = relationship("Customer")
    
    lines = relationship("SalesLineItem", back_populates="document", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="sales_document")
    returns = relationship("SaleReturn", back_populates="sale")

    @property
    def branch_name(self) -> str | None:
        return self.branch.name if self.branch else None

# --- Modelo 2: Detalle de Venta (Items) ---
class SalesLineItem(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "sales_lines"
    __table_args__ = {'extend_existing': True}

    document_id = Column(String(36), ForeignKey("sales_documents.id"), nullable=False)
    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=False) # Ahora es UUID
    
    description = Column(String) 
    quantity = Column(Float, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    discount_percent = Column(Numeric(5, 2), default=0.00, nullable=True)
    total_line = Column(Numeric(10, 2), nullable=False)

    document = relationship("SalesDocument", back_populates="lines")
    variant = relationship("ProductVariant")
    
    @property
    def sku(self):
        return self.variant.sku if self.variant else "UNKNOWN"

    @property
    def has_iva(self):
        return self.variant.has_iva if self.variant else False

    @property
    def tax_rate(self):
        return self.variant.tax_rate if self.variant else 16.0

# --- Modelo 3: Pagos ---
class Payment(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "payments"
    __table_args__ = {'extend_existing': True}

    # Puede pertenecer a una venta específica O ser un abono a cuenta global (sales_document_id=null)
    sales_document_id = Column(String(36), ForeignKey("sales_documents.id"), nullable=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # Integer por ahora
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Integer por ahora
    
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(Enum(PaymentMethod), default=PaymentMethod.CASH)
    reference = Column(String, nullable=True) # Referencia bancaria / Folio

    # Caja que RECIBIO este dinero. Antes el efectivo se atribuia por el
    # documento de venta, lo que mandaba el abono de un credito liquidado hoy
    # al corte del dia en que se abrio la venta. Nullable: los pagos
    # historicos y los de ventas sin caja se quedan sin atribucion explicita y
    # caen al respaldo por documento.
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=True, index=True)

    sales_document = relationship("SalesDocument", back_populates="payments")


# --- Modelo 4: Tickets pausados (Track 2 — POS bug-fix) ---
# Los pausados NO son ventas. Tabla aparte para que NO consuman folio,
# NO descuenten inventario y NO contaminen el historial de ventas.
# El usuario puede reanudar desde cualquier PC de su sucursal (hand-off).
class ParkedTicket(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "parked_tickets"
    __table_args__ = {'extend_existing': True}

    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # Snapshot completo del carrito + customer + descuentos. Se guarda
    # como JSONB para preservar la estructura sin obligar a un schema rígido
    # (el cart en frontend evoluciona; este es un buffer transitorio).
    cart_json = Column(JSONB, nullable=False)

    notes = Column(String, nullable=True)

    # parked_at viene de AuditMixin (created_at). expires_at se setea al
    # crear (default = +24h). Cleanup periódico opcional via cron/manual.
    expires_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch")
    user = relationship("User")
    customer = relationship("Customer")