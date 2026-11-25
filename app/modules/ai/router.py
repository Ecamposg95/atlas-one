"""Endpoints del agente (fase A1: consultas por rol). Prefijo `/api/ai`.

Todo pasa por `exigir_modulo_ai` (módulo `ai` encendido, sin pase libre de
administrador) y por `_persona_con_agente` (rol con fila en `matriz.py`;
superadministrador y soporte entran en A4). Una conversación es de UNA persona
en UNA organización: la de otro, o la de otra empresa, responde 404.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User

from . import historial
from .contexto import Contexto
from .gating import exigir_modulo_ai
from .matriz import es_de_plataforma, tiene_agente
from .models import AiConversation, AiMessage, AiPropuesta
from .motor import responder
from .schemas import (
    ConversacionCrear, ConversacionDetalle, ConversacionResumen, MensajeCrear, MensajeRead, RespuestaTurno,
)

router = APIRouter()

TOPE_CONVERSACIONES = 50


def _persona_con_agente(current_user: User = Depends(get_current_user)) -> User:
    if es_de_plataforma(current_user):
        raise HTTPException(
            status_code=403,
            detail="El agente para el equipo de plataforma todavía no está disponible.",
        )
    if not tiene_agente(current_user):
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso al agente.")
    return current_user


def _propia(db: Session, org_id: int, user: User, conversacion_id: str) -> AiConversation:
    conversacion = db.query(AiConversation).filter(
        AiConversation.id == conversacion_id,
        AiConversation.organization_id == org_id,
        AiConversation.user_id == user.id,
        AiConversation.deleted_at.is_(None),
    ).first()
    if conversacion is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return conversacion


def _visibles(db: Session, conversacion: AiConversation) -> List[AiMessage]:
    """Lo que la pantalla muestra: lo que escribió la persona y lo que contestó
    el agente. Los pasos intermedios (llamadas y resultados de herramientas) no."""
    return [
        m for m in historial.mensajes_de(db, conversacion)
        if m.rol in ("user", "assistant") and (m.contenido or "").strip()
    ]


@router.get("/health")
def health(current_user: User = Depends(get_current_user)):
    return {"module": "ai", "status": "beta", "ready": True}


@router.post("/conversaciones", response_model=ConversacionResumen, status_code=201)
def crear_conversacion(
    datos: ConversacionCrear,
    db: Session = Depends(get_db),
    org_id: int = Depends(exigir_modulo_ai),
    user: User = Depends(_persona_con_agente),
):
    conversacion = AiConversation(organization_id=org_id, user_id=user.id,
                                  titulo=(datos.titulo or "").strip() or None)
    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)
    return conversacion


@router.get("/conversaciones", response_model=List[ConversacionResumen])
def listar_conversaciones(
    db: Session = Depends(get_db),
    org_id: int = Depends(exigir_modulo_ai),
    user: User = Depends(_persona_con_agente),
):
    return (
        db.query(AiConversation)
        .filter(AiConversation.organization_id == org_id, AiConversation.user_id == user.id,
                AiConversation.deleted_at.is_(None))
        .order_by(AiConversation.updated_at.desc()).limit(TOPE_CONVERSACIONES).all()
    )


@router.get("/conversaciones/{conversacion_id}", response_model=ConversacionDetalle)
def leer_conversacion(
    conversacion_id: str,
    db: Session = Depends(get_db),
    org_id: int = Depends(exigir_modulo_ai),
    user: User = Depends(_persona_con_agente),
):
    conversacion = _propia(db, org_id, user, conversacion_id)
    return ConversacionDetalle(
        id=conversacion.id, titulo=conversacion.titulo,
        created_at=conversacion.created_at, updated_at=conversacion.updated_at,
        mensajes=[MensajeRead.model_validate(m) for m in _visibles(db, conversacion)],
    )


@router.post("/conversaciones/{conversacion_id}/mensajes", response_model=RespuestaTurno)
def enviar_mensaje(
    conversacion_id: str,
    datos: MensajeCrear,
    db: Session = Depends(get_db),
    org_id: int = Depends(exigir_modulo_ai),
    user: User = Depends(_persona_con_agente),
):
    """Un turno: 429 si se acabó el cupo del día, 503 si no hay llave del
    proveedor o el proveedor falló."""
    conversacion = _propia(db, org_id, user, conversacion_id)
    texto = datos.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Escribe tu pregunta.")
    turno = responder(db, Contexto(db=db, org_id=org_id, user=user, conversacion=conversacion),
                      conversacion, texto)
    db.commit()
    db.refresh(turno.mensaje)
    return RespuestaTurno(mensaje=MensajeRead.model_validate(turno.mensaje))


@router.delete("/conversaciones/{conversacion_id}", status_code=204)
def borrar_conversacion(
    conversacion_id: str,
    db: Session = Depends(get_db),
    org_id: int = Depends(exigir_modulo_ai),
    user: User = Depends(_persona_con_agente),
):
    conversacion = _propia(db, org_id, user, conversacion_id)
    db.query(AiPropuesta).filter(AiPropuesta.conversation_id == conversacion.id).delete(synchronize_session=False)
    db.query(AiMessage).filter(AiMessage.conversation_id == conversacion.id).delete(synchronize_session=False)
    db.delete(conversacion)
    db.commit()
    return Response(status_code=204)
