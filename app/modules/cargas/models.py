"""Tablas de las cargas de mercancía.

Una carga es UN archivo subido, sus renglones leídos, las dudas que el
asistente le hace al usuario y la bitácora de cambios al plan. Nada de aquí
toca catálogo ni existencias: eso solo lo hace `aplicar_carga`.
Todas llevan `organization_id` para que cada consulta filtre por organización.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, Numeric,
    String, Text, UniqueConstraint,
)

from app.core.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDMixin

# Estados y clases como String + constantes (sin enums de Postgres).
ESTADOS_CARGA = ("leyendo", "plan", "aplicando", "aplicada", "error", "descartada")
PROPOSITOS = ("entrada", "migracion")
CLASES = ("EXISTE", "SUMA", "NUEVO", "YA_CARGADO", "IGNORADO")


class CargaMercancia(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "cargas_mercancia"
    __table_args__ = (
        UniqueConstraint("organization_id", "folio", name="uq_cargas_org_folio"),
    )

    folio = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    proposito = Column(String(16), nullable=False, default="entrada")
    estado = Column(String(16), nullable=False, default="leyendo")
    archivo_nombre = Column(String, nullable=True)
    archivo_sha256 = Column(String(64), nullable=True, index=True)
    archivo_tipo = Column(String(8), nullable=True)  # pdf | xlsx | csv
    sucursal_destino_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    monedas = Column(JSON, nullable=True)  # {"USD": 18.2, "CNY": null}
    totales = Column(JSON, nullable=True)
    # Mapa de columnas del Excel y estado de lectura entre la subida y las respuestas.
    lectura = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    aplicada_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    aplicada_at = Column(DateTime(timezone=True), nullable=True)
    tokens_entrada = Column(Integer, nullable=True)
    tokens_salida = Column(Integer, nullable=True)


class CargaArchivo(Base, UUIDMixin, AuditMixin, TenantMixin):
    """El original vive en la base: el repo es público y sobrevive a los redespliegues."""
    __tablename__ = "cargas_archivos"

    carga_id = Column(String(36), ForeignKey("cargas_mercancia.id"), nullable=False, index=True)
    contenido = Column(LargeBinary, nullable=False)


class CargaRenglon(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "cargas_renglones"
    # Dudas y operaciones nombran los renglones por `orden`.
    __table_args__ = (UniqueConstraint("carga_id", "orden", name="uq_cargas_renglones_carga_orden"),)

    carga_id = Column(String(36), ForeignKey("cargas_mercancia.id"), nullable=False, index=True)
    orden = Column(Integer, nullable=False, default=0)
    crudo = Column(JSON, nullable=True)
    normalizado = Column(JSON, nullable=True)
    clase = Column(String(16), nullable=True)
    grupo = Column(String, nullable=True)
    product_id = Column(String(36), nullable=True)
    variant_id = Column(String(36), nullable=True)
    sku = Column(String, nullable=True)
    cantidad = Column(Numeric(12, 3), nullable=False, default=0)
    precio = Column(Numeric(12, 2), nullable=True)
    costo = Column(Numeric(12, 2), nullable=True)
    resultado = Column(JSON, nullable=True)


class CargaDuda(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "cargas_dudas"
    __table_args__ = (UniqueConstraint("carga_id", "numero", name="uq_cargas_dudas_carga_numero"),)

    carga_id = Column(String(36), ForeignKey("cargas_mercancia.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)
    tipo = Column(String, nullable=False)
    texto = Column(Text, nullable=False)
    opciones = Column(JSON, nullable=True)  # [{"clave","etiqueta"}]
    recomendada = Column(String, nullable=True)
    renglones = Column(JSON, nullable=True)
    # Identidad estable "<tipo>|<objeto>" para reconocer la misma duda entre recálculos.
    clave = Column(String(200), nullable=True)
    contexto = Column(JSON, nullable=True)
    estado = Column(String(16), nullable=False, default="abierta")  # abierta | resuelta
    respuesta = Column(Text, nullable=True)
    resuelta_por = Column(Integer, ForeignKey("users.id"), nullable=True)


class CargaCambio(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "cargas_cambios"
    __table_args__ = (UniqueConstraint("carga_id", "secuencia", name="uq_cargas_cambios_carga_secuencia"),)

    carga_id = Column(String(36), ForeignKey("cargas_mercancia.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Orden de los cambios dentro de la carga (1, 2, 3…): solo se deshace el último.
    secuencia = Column(Integer, nullable=False, default=0)
    texto = Column(Text, nullable=True)
    operaciones = Column(JSON, nullable=True)
    antes = Column(JSON, nullable=True)
    despues = Column(JSON, nullable=True)
    deshecho = Column(Boolean, nullable=False, default=False)
