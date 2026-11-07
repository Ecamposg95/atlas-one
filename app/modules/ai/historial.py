"""Historial de una conversación: guardar mensajes en orden y armar lo que se
le manda al modelo (formato OpenAI `messages`)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import AiConversation, AiMessage

TOPE_HISTORIAL = 30


def guardar_mensaje(
    db: Session, conv: AiConversation, rol: str, contenido: Optional[str], *,
    tool_calls: Optional[list] = None, tool_call_id: Optional[str] = None,
    tokens_entrada: int = 0, tokens_salida: int = 0,
) -> AiMessage:
    """Agrega un mensaje al final de la conversación. Hace `flush`."""
    ultimo = db.query(func.max(AiMessage.orden)).filter(AiMessage.conversation_id == conv.id).scalar() or 0
    mensaje = AiMessage(
        organization_id=conv.organization_id,
        conversation_id=conv.id,
        orden=ultimo + 1,
        rol=rol,
        contenido=contenido,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
    )
    db.add(mensaje)
    db.flush()
    return mensaje


def mensajes_de(db: Session, conv: AiConversation) -> list[AiMessage]:
    return (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conv.id, AiMessage.organization_id == conv.organization_id)
        .order_by(AiMessage.orden)
        .all()
    )


def recortar_historial(mensajes: list[AiMessage], tope: int = TOPE_HISTORIAL) -> list[AiMessage]:
    """Los últimos `tope`, sin empezar en un `tool` huérfano (sin el
    `assistant` que lo pidió el proveedor rechaza la petición)."""
    recorte = list(mensajes[-tope:]) if tope > 0 else []
    while recorte and recorte[0].rol == "tool":
        recorte.pop(0)
    return recorte


def a_formato_llm(m: AiMessage) -> dict:
    if m.rol == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.contenido or ""}
    if m.rol == "assistant":
        salida = {"role": "assistant", "content": m.contenido or ""}
        if m.tool_calls:
            salida["tool_calls"] = m.tool_calls
        return salida
    if m.rol == "evento":
        return {"role": "user", "content": f"[Aviso del sistema] {m.contenido or ''}"}
    return {"role": "user", "content": m.contenido or ""}


def historial_para_llm(db: Session, conv: AiConversation, tope: int = TOPE_HISTORIAL) -> list[dict]:
    return [a_formato_llm(m) for m in recortar_historial(mensajes_de(db, conv), tope)]
