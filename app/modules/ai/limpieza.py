"""Borrado de los datos del asistente de una organización.

Lo llama la cascada manual de `DELETE /api/platform/organizations/{id}?force=true`
(app/routers/platform/organizations.py): las cuatro tablas tienen FK a
`organization` o `users` y sin esto el borrado forzado truena.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AiConversation, AiMessage, AiPropuesta, AiUsoDiario


def borrar_datos_ai_de_org(db: Session, org_id: int) -> dict[str, int]:
    conversaciones = select(AiConversation.id).where(AiConversation.organization_id == org_id)
    borrados = {
        "ai_propuestas": db.query(AiPropuesta).filter(
            AiPropuesta.conversation_id.in_(conversaciones)
        ).delete(synchronize_session=False),
        "ai_messages": db.query(AiMessage).filter(
            AiMessage.conversation_id.in_(conversaciones)
        ).delete(synchronize_session=False),
    }
    borrados["ai_conversations"] = db.query(AiConversation).filter(
        AiConversation.organization_id == org_id
    ).delete(synchronize_session=False)
    borrados["ai_uso_diario"] = db.query(AiUsoDiario).filter(
        AiUsoDiario.organization_id == org_id
    ).delete(synchronize_session=False)
    db.flush()
    return borrados
