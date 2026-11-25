"""Suscripción de la organización, sus cargos por periodo y sus pagos.

Lo que Atlas le cobra a cada tienda. Primera versión: registro manual desde
plataforma; nada de aquí bloquea accesos (megaplan 2026-11-24 §7).

PKs enteras porque la organización lo es. Dinero en Numeric, nunca float.
Estados y métodos como String + constantes (CLAUDE.md §5: sin enums de
Postgres). Las tres tablas las crea `create_all`.
"""
from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# --- Estado de la suscripción ---
AL_CORRIENTE = "al_corriente"
POR_VENCER = "por_vencer"
VENCIDA = "vencida"
SUSPENDIDA = "suspendida"
CORTESIA = "cortesia"
ESTADOS = (AL_CORRIENTE, POR_VENCER, VENCIDA, SUSPENDIDA, CORTESIA)
# Solo se ponen a mano y ganan sobre el cálculo por fechas.
ESTADOS_MANUALES = (SUSPENDIDA, CORTESIA)

# --- Periodicidad ---
MENSUAL = "mensual"
ANUAL = "anual"
PERIODICIDADES = (MENSUAL, ANUAL)

# --- Estado del cargo ---
PENDIENTE = "pendiente"
PAGADO = "pagado"
CANCELADO = "cancelado"

# --- Método de pago ---
METODOS = ("transferencia", "deposito", "efectivo", "tarjeta", "otro")

# --- Origen del pago: hoy solo manual; la pasarela pondrá el suyo ---
ORIGEN_MANUAL = "manual"


class Suscripcion(Base):
    __tablename__ = "suscripciones"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_suscripcion_org"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    # Espejo de organization.plan; los mueve juntos services.guardar_suscripcion.
    plan = Column(String(20), nullable=False)
    # Precio pactado por periodo (mes o año, según periodicidad). Puede diferir del de lista.
    precio_mxn = Column(Numeric(12, 2), nullable=False, default=0)
    periodicidad = Column(String(10), nullable=False, default=MENSUAL)
    dia_corte = Column(Integer, nullable=False, default=1)  # 1..28
    fecha_inicio = Column(Date, nullable=False)
    proxima_renovacion = Column(Date, nullable=False)
    # Foto del último cálculo; la verdad es services.calcular_estado. Solo
    # manda lo guardado cuando es manual (suspendida, cortesia).
    estado = Column(String(15), nullable=False, default=AL_CORRIENTE)
    notas = Column(Text, nullable=True)  # internas de plataforma; la tienda no las ve
    # Datos fiscales para un CFDI futuro.
    rfc = Column(String(13), nullable=True)
    razon_social = Column(String(255), nullable=True)
    correo_facturacion = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cargos = relationship(
        "CargoSuscripcion", back_populates="suscripcion",
        order_by="CargoSuscripcion.periodo_desde.desc()",
    )


class CargoSuscripcion(Base):
    __tablename__ = "suscripcion_cargos"
    __table_args__ = (
        # Un cargo por organización y periodo: la idempotencia de generar_cargo.
        UniqueConstraint("organization_id", "periodo_desde", name="uq_suscripcion_cargo_periodo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    suscripcion_id = Column(Integer, ForeignKey("suscripciones.id"), nullable=False, index=True)
    periodo_desde = Column(Date, nullable=False)
    periodo_hasta = Column(Date, nullable=False)  # inclusive
    importe = Column(Numeric(12, 2), nullable=False)
    vence_el = Column(Date, nullable=False)
    estado = Column(String(10), nullable=False, default=PENDIENTE)
    pagado_at = Column(DateTime(timezone=True), nullable=True)
    cancelado_at = Column(DateTime(timezone=True), nullable=True)
    motivo_cancelacion = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    suscripcion = relationship("Suscripcion", back_populates="cargos")
    pagos = relationship(
        "PagoSuscripcion", back_populates="cargo", order_by="PagoSuscripcion.id",
    )


class PagoSuscripcion(Base):
    __tablename__ = "suscripcion_pagos"
    __table_args__ = (
        # Para la pasarela: el mismo evento externo no entra dos veces. En el
        # registro manual id_externo es NULL y la restricción no aplica.
        UniqueConstraint("origen", "id_externo", name="uq_suscripcion_pago_externo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    cargo_id = Column(Integer, ForeignKey("suscripcion_cargos.id"), nullable=False, index=True)
    importe = Column(Numeric(12, 2), nullable=False)
    fecha_pago = Column(Date, nullable=False)
    metodo = Column(String(20), nullable=False)
    referencia = Column(String(120), nullable=True)
    notas = Column(Text, nullable=True)
    registrado_por_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    origen = Column(String(20), nullable=False, default=ORIGEN_MANUAL)
    id_externo = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cargo = relationship("CargoSuscripcion", back_populates="pagos")
    registrado_por = relationship("User", foreign_keys=[registrado_por_user_id])
