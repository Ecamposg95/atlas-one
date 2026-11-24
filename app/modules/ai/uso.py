"""Cupo y consumo de IA.

**Cupo** (tokens de entrada + salida por día de negocio), de más específico a
más general:

1. `organization.ai_tokens_dia` — excepción de la organización (plataforma).
2. `AI_TOKENS_DIA_ORG` — si está puesta, tope global para todas (freno de mano).
3. El del plan: `app/services/plans.py::CUPO_IA_TOKENS_DIA` (hoy un valor
   provisional alto; la cifra final está por definir).

Además, opcional, un tope por persona: `AI_TOKENS_DIA_USUARIO` (sin la variable
no hay tope por usuario; el consumo por usuario se registra igual).

**Consumo**: `registrar_uso` deja una fila en `ai_llamadas` por llamada
(organización, usuario, rol, tarea, proveedor, modelo, tokens) y suma al
acumulado `ai_uso_diario` con un UPSERT atómico: dos peticiones simultáneas no
se pisan la cuenta. (Un `with_for_update` no serviría de prueba: en SQLite es
no-op; el UPSERT hace la suma dentro de la base en los dos motores.)

`verificar_cupo` es una comprobación previa: el costo de una llamada solo se
conoce al terminar, así que la que cruza el tope pasa y la siguiente ya no.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.fechas import hoy_negocio
from app.modules.ai.models import AiLlamada, AiUsoDiario
from app.modules.ai.proveedores import (
    MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, Proveedor, Respuesta, RespuestaJSON,
)
from app.services import plans


@dataclass
class Llamada:
    """Lo que consumió una llamada al modelo."""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    proveedor: str = ""
    modelo: str = ""


class Medidor:
    """Envuelve un `Proveedor` y anota en `llamadas` el consumo de cada respuesta.
    Sirve cuando una operación hace varias llamadas y registra al final."""

    def __init__(self, proveedor: Proveedor):
        self._proveedor = proveedor
        self.llamadas: list[Llamada] = []

    @property
    def nombre(self) -> str:
        return self._proveedor.nombre

    @property
    def modelo(self) -> str:
        return self._proveedor.modelo

    def _anotar(self, r: Any) -> Any:
        self.llamadas.append(Llamada(
            tokens_entrada=int(getattr(r, "tokens_entrada", 0) or 0),
            tokens_salida=int(getattr(r, "tokens_salida", 0) or 0),
            proveedor=getattr(r, "proveedor", "") or self.nombre,
            modelo=getattr(r, "modelo", "") or self.modelo,
        ))
        return r

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        return self._anotar(self._proveedor.conversar(
            mensajes=mensajes, herramientas=herramientas, max_tokens=max_tokens))

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        return self._anotar(self._proveedor.generar_json(
            sistema=sistema, contenido=contenido, esquema=esquema, max_tokens=max_tokens, latido=latido))


# ── cupo ─────────────────────────────────────────────────────────────────

def _entero_positivo(texto: Optional[str]) -> Optional[int]:
    try:
        valor = int((texto or "").strip())
    except ValueError:
        return None
    return valor if valor > 0 else None


def limite_tokens_dia(db: Session, org_id: int) -> int:
    """Cupo diario de la organización (ver el orden en la cabecera del módulo)."""
    from app.modules.tenants.models import Organization

    org = db.get(Organization, org_id)
    propio = getattr(org, "ai_tokens_dia", None) if org is not None else None
    if isinstance(propio, int) and propio > 0:
        return propio
    general = _entero_positivo(os.getenv("AI_TOKENS_DIA_ORG"))
    if general is not None:
        return general
    return plans.cupo_ia_tokens_dia(getattr(org, "plan", None))


def limite_tokens_dia_usuario() -> Optional[int]:
    """`AI_TOKENS_DIA_USUARIO`; None = sin tope por persona."""
    return _entero_positivo(os.getenv("AI_TOKENS_DIA_USUARIO"))


def tokens_de_hoy(db: Session, org_id: int) -> int:
    fila = db.query(AiUsoDiario.tokens_entrada, AiUsoDiario.tokens_salida).filter(
        AiUsoDiario.organization_id == org_id, AiUsoDiario.fecha == hoy_negocio(),
    ).first()
    return ((fila[0] or 0) + (fila[1] or 0)) if fila else 0


def tokens_de_hoy_usuario(db: Session, org_id: int, user_id: int) -> int:
    total = db.query(
        func.coalesce(func.sum(AiLlamada.tokens_entrada + AiLlamada.tokens_salida), 0)
    ).filter(
        AiLlamada.organization_id == org_id, AiLlamada.user_id == user_id,
        AiLlamada.fecha == hoy_negocio(),
    ).scalar()
    return int(total or 0)


def verificar_cupo(db: Session, org_id: int, user_id: Optional[int] = None) -> None:
    """429 si la organización (o la persona, si hay tope por usuario) ya gastó su día."""
    if tokens_de_hoy(db, org_id) >= limite_tokens_dia(db, org_id):
        raise HTTPException(
            status_code=429,
            detail="Se alcanzó el límite diario de uso de IA de tu organización. Intenta mañana.",
        )
    por_usuario = limite_tokens_dia_usuario()
    if user_id is not None and por_usuario is not None \
            and tokens_de_hoy_usuario(db, org_id, user_id) >= por_usuario:
        raise HTTPException(
            status_code=429,
            detail="Alcanzaste tu límite diario de uso de IA. Intenta mañana.",
        )


# ── registro ─────────────────────────────────────────────────────────────

def _texto_rol(rol: Any) -> Optional[str]:
    if rol is None:
        return None
    return str(getattr(rol, "value", rol))[:30]


def _sumar_al_dia(db: Session, org_id: int, fecha, entrada: int, salida: int, llamadas: int) -> None:
    """UPSERT atómico sobre (organization_id, fecha): la suma la hace la base."""
    tabla = AiUsoDiario.__table__
    dialecto = db.get_bind().dialect.name
    if dialecto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialecto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - motores que no usamos: candado de fila y suma
        fila = (db.query(AiUsoDiario)
                .filter(AiUsoDiario.organization_id == org_id, AiUsoDiario.fecha == fecha)
                .with_for_update().first())
        if fila is None:
            fila = AiUsoDiario(organization_id=org_id, fecha=fecha,
                               tokens_entrada=0, tokens_salida=0, llamadas=0)
            db.add(fila)
        fila.tokens_entrada = (fila.tokens_entrada or 0) + entrada
        fila.tokens_salida = (fila.tokens_salida or 0) + salida
        fila.llamadas = (fila.llamadas or 0) + llamadas
        db.flush()
        return
    stmt = insert(tabla).values(organization_id=org_id, fecha=fecha, tokens_entrada=entrada,
                                tokens_salida=salida, llamadas=llamadas)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tabla.c.organization_id, tabla.c.fecha],
        set_={
            "tokens_entrada": tabla.c.tokens_entrada + stmt.excluded.tokens_entrada,
            "tokens_salida": tabla.c.tokens_salida + stmt.excluded.tokens_salida,
            "llamadas": tabla.c.llamadas + stmt.excluded.llamadas,
        },
    )
    db.execute(stmt)
    # La fila cambió por SQL directo: lo que la sesión tenga cargado quedó viejo.
    for obj in list(db.identity_map.values()):
        if isinstance(obj, AiUsoDiario) and obj.organization_id == org_id and obj.fecha == fecha:
            db.expire(obj)


def registrar_llamadas(db: Session, org_id: int, llamadas: Iterable[Llamada], *,
                       user_id: Optional[int] = None, rol: Any = None,
                       tarea: Optional[str] = None) -> None:
    """Una fila en `ai_llamadas` por llamada y la suma al acumulado del día.
    Sin commit (lo hace la transacción que llama)."""
    llamadas = list(llamadas)
    if not llamadas:
        return
    fecha = hoy_negocio()
    rol_texto = _texto_rol(rol)
    for ll in llamadas:
        db.add(AiLlamada(
            organization_id=org_id, user_id=user_id, rol=rol_texto, tarea=tarea,
            proveedor=(ll.proveedor or None), modelo=(ll.modelo or None),
            tokens_entrada=int(ll.tokens_entrada or 0), tokens_salida=int(ll.tokens_salida or 0),
            fecha=fecha,
        ))
    db.flush()
    _sumar_al_dia(
        db, org_id, fecha,
        sum(int(ll.tokens_entrada or 0) for ll in llamadas),
        sum(int(ll.tokens_salida or 0) for ll in llamadas),
        len(llamadas),
    )


def registrar_uso(db: Session, org_id: int, tokens_entrada: int, tokens_salida: int, *,
                  user_id: Optional[int] = None, rol: Any = None, tarea: Optional[str] = None,
                  proveedor: str = "", modelo: str = "") -> None:
    """Registra UNA llamada. Sin commit (lo hace la transacción que llama)."""
    registrar_llamadas(
        db, org_id,
        [Llamada(tokens_entrada=int(tokens_entrada or 0), tokens_salida=int(tokens_salida or 0),
                 proveedor=proveedor, modelo=modelo)],
        user_id=user_id, rol=rol, tarea=tarea,
    )
