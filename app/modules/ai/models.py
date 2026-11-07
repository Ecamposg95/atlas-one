"""Tablas del asistente IA (SP4, 2026-10).

Conversación → mensajes (el historial que se le manda al modelo, en `orden`) y
propuestas (lo único que el asistente puede "escribir": una ficha pendiente
que la persona confirma en pantalla). `ai_uso_diario` mide tokens por
organización y día para el tope `AI_TOKENS_DIA_ORG`.

Regla de oro #4: toda FK a una tabla con PK UUID es String(36).
Estados y roles son cadenas con constantes de Python, no enums de Postgres
(CLAUDE.md §5: un valor nuevo no debe costar un ALTER TYPE).
"""
from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.core.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDMixin

# `evento` = aviso del sistema dentro de la conversación ("Propuesta aplicada…").
# Al modelo se le manda como mensaje de usuario: un `tool` sin el `assistant`
# que lo pidió hace que el proveedor rechace la petición.
ROLES_MENSAJE = ("user", "assistant", "tool", "evento")
TIPOS_PROPUESTA = ("crear_producto", "agregar_variantes", "ajustar_existencias")
ESTADOS_PROPUESTA = ("pendiente", "confirmada", "descartada", "aplicada_manual", "error")


class AiConversation(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_conversations"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    titulo = Column(String(120), nullable=True)


class AiMessage(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_messages"

    conversation_id = Column(String(36), ForeignKey("ai_conversations.id"), nullable=False, index=True)
    # Orden dentro de la conversación: varias filas del mismo turno pueden
    # compartir `created_at`.
    orden = Column(Integer, nullable=False)
    rol = Column(String(12), nullable=False)
    contenido = Column(Text, nullable=True)
    # Formato OpenAI: [{"id", "type": "function", "function": {"name", "arguments"}}]
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(80), nullable=True)
    tokens_entrada = Column(Integer, nullable=False, default=0)
    tokens_salida = Column(Integer, nullable=False, default=0)


class AiPropuesta(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_propuestas"

    conversation_id = Column(String(36), ForeignKey("ai_conversations.id"), nullable=False, index=True)
    tipo = Column(String(30), nullable=False)
    # Datos ya normalizados por el schema del tipo (crear_producto = ProductCreate de SP1).
    datos = Column(JSON, nullable=False)
    avisos = Column(JSON, nullable=True)
    estado = Column(String(20), nullable=False, default="pendiente", index=True)
    resultado = Column(JSON, nullable=True)
    # Resumen humano: lo arma el servidor, nunca el modelo.
    resumen = Column(String(300), nullable=False)
    confirmada_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmada_at = Column(DateTime(timezone=True), nullable=True)


class AiUsoDiario(Base):
    __tablename__ = "ai_uso_diario"
    __table_args__ = (UniqueConstraint("organization_id", "fecha", name="uq_ai_uso_org_fecha"),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    fecha = Column(Date, nullable=False)  # día del negocio (app/core/fechas.py)
    tokens_entrada = Column(Integer, nullable=False, default=0)
    tokens_salida = Column(Integer, nullable=False, default=0)
    llamadas = Column(Integer, nullable=False, default=0)
