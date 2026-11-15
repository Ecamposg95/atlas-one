"""Uso diario de tokens de IA por organización (día de negocio)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.fechas import hoy_negocio
from app.modules.ai.cliente_llm import limite_tokens_dia
from app.modules.ai.models import AiUsoDiario


def _fila_de_hoy(db: Session, org_id: int):
    return db.query(AiUsoDiario).filter(
        AiUsoDiario.organization_id == org_id,
        AiUsoDiario.fecha == hoy_negocio(),
    ).first()


def verificar_cupo(db: Session, org_id: int) -> None:
    fila = _fila_de_hoy(db, org_id)
    usados = ((fila.tokens_entrada or 0) + (fila.tokens_salida or 0)) if fila else 0
    if usados >= limite_tokens_dia():
        raise HTTPException(
            status_code=429,
            detail="Se alcanzó el límite diario de uso de IA de tu organización. Intenta mañana.",
        )


def registrar_uso(db: Session, org_id: int, tokens_entrada: int, tokens_salida: int) -> None:
    """Suma al día de negocio; sin commit (lo hace la transacción que llama)."""
    fila = _fila_de_hoy(db, org_id)
    if fila is None:
        fila = AiUsoDiario(organization_id=org_id, fecha=hoy_negocio(),
                           tokens_entrada=0, tokens_salida=0, llamadas=0)
        db.add(fila)
    fila.tokens_entrada = (fila.tokens_entrada or 0) + int(tokens_entrada)
    fila.tokens_salida = (fila.tokens_salida or 0) + int(tokens_salida)
    fila.llamadas = (fila.llamadas or 0) + 1
    db.flush()
