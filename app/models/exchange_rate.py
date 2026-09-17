"""Tipo de cambio diario (FIX de Banxico, serie SF43718).

Tabla GLOBAL a proposito: el FIX es un dato publico, uno por dia, compartido
por todos los inquilinos — NO lleva `organization_id` ni `TenantMixin`, igual
que `modules`. La politica por organizacion (modo, margen, tipo manual) vive en
columnas de `organization`; aqui solo esta el numero publicado.

La llena `app/core/exchange_rate_job.py` (job diario) y el endpoint de refresco
manual. La lee `app/services/exchange_rate.py::ultimo_fix`.
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        # Una fila por moneda y dia. El job es idempotente y puede correr N
        # veces (N replicas del backend, refresco manual del dueño); esta
        # restriccion es la red que lo garantiza en la base.
        UniqueConstraint("currency", "rate_date", name="uq_exchange_rate_day"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(String(3), nullable=False, default="USD", index=True)
    # Dia AL QUE CORRESPONDE el tipo segun Banxico, no el dia en que se bajo:
    # en fin de semana y feriados el dato mas reciente es el del ultimo habil.
    rate_date = Column(Date, nullable=False, index=True)
    rate = Column(Numeric(10, 4), nullable=False)  # pesos por unidad de `currency`
    source = Column(String(16), nullable=False, default="banxico")  # banxico | manual
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
