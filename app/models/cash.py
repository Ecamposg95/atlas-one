# app/models/cash.py
import enum
from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Enum, Index, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.mixins import TenantMixin

class CashSessionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class CashSession(Base, TenantMixin):
    __tablename__ = "cash_sessions"

    # Una sola sesion ABIERTA por (usuario, sucursal). Guarda dura contra la
    # carrera al abrir caja (auditoria Rmazh §5): el chequeo previo del
    # endpoint es check-then-insert y dos peticiones concurrentes lo pasan las
    # dos. El indice es PARCIAL para no estorbar al historial de cortes
    # cerrados, que acumula muchas filas del mismo par.
    #
    # `create_all` solo lo crea en bases nuevas (pruebas, dev); la base de
    # produccion ya existe, asi que alli lo crea scripts/railway_init.py.
    __table_args__ = (
        Index(
            "uq_cash_sessions_open_user_branch",
            "user_id", "branch_id",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    
    # Tiempos de operación
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Montos (Sincronizados con schemas/cash.py)
    opening_balance = Column(Numeric(10, 2), default=0.00)  # Saldo inicial / Fondo
    closing_balance = Column(Numeric(10, 2), default=0.00) # Contado por el cajero
    
    total_cash_sales = Column(Numeric(10, 2), default=0.00)
    total_change_given = Column(Numeric(10, 2), default=0.00)  # Cambio entregado en efectivo
    difference = Column(Numeric(10, 2), default=0.00)      # Faltante o sobrante
    
    status = Column(Enum(CashSessionStatus), default=CashSessionStatus.OPEN)
    notes = Column(String, nullable=True)

    # Relaciones
    user = relationship("User")
    branch = relationship("Branch")
    movements = relationship("CashMovement", back_populates="session")

class CashMovement(Base):
    __tablename__ = "cash_movements"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("cash_sessions.id"))
    
    type = Column(String) # 'IN', 'OUT'
    amount = Column(Numeric(10, 2))
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Autoria del hecho, no del log: un movimiento sin autor no es auditable.
    # Nullable porque las filas creadas antes de esta columna no lo tienen.
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    session = relationship("CashSession", back_populates="movements")