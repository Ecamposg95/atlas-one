"""Piezas comunes de las herramientas del asistente.

Regla de aislamiento: `org_id` sale SIEMPRE del contexto autenticado, nunca de
los argumentos del modelo. Un id ajeno a la organización "no existe".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models.organization import Branch
from app.models.users import User

from .models import AiConversation


class ErrorHerramienta(Exception):
    """Mensaje para el MODELO: vuelve como `{"error": ...}`, no es un error HTTP."""


@dataclass
class Contexto:
    db: Session
    org_id: int
    user: User
    conversacion: AiConversation


@dataclass(frozen=True)
class Herramienta:
    descripcion: str
    parametros: dict
    funcion: Callable[[Contexto, dict], dict]

    def definicion(self, nombre: str) -> dict:
        return {"type": "function", "function": {
            "name": nombre, "description": self.descripcion, "parameters": self.parametros,
        }}


def texto_de_validacion(e: ValidationError) -> str:
    partes = []
    for err in e.errors()[:8]:
        campo = ".".join(str(x) for x in err.get("loc", ())) or "datos"
        partes.append(f"{campo}: {err.get('msg')}")
    return "Datos inválidos: " + "; ".join(partes)


def ve_toda_la_org(user: User) -> bool:
    """Solo ADMINISTRADOR y DUEÑO. GERENTE y CAJERO ven su sucursal (spec SP4
    §1, más estricto que `reports.HQ_ROLES`, que incluye a GERENTE)."""
    return _is_admin(user)


def sucursal_de_la_org(ctx: Contexto, sucursal_id: Any) -> Branch:
    try:
        sid = int(sucursal_id)
    except (TypeError, ValueError):
        raise ErrorHerramienta(f"La sucursal {sucursal_id} no existe.")
    sucursal = ctx.db.query(Branch).filter(Branch.id == sid, Branch.organization_id == ctx.org_id).first()
    if sucursal is None:
        raise ErrorHerramienta(f"La sucursal {sucursal_id} no existe.")
    return sucursal


def ambito_sucursal(ctx: Contexto, sucursal_id: Any) -> Optional[int]:
    """Sucursal de una consulta: None = toda la organización (solo admin/dueño)."""
    if ve_toda_la_org(ctx.user):
        if sucursal_id in (None, "", 0):
            return None
        return sucursal_de_la_org(ctx, sucursal_id).id
    propia = ctx.user.branch_id
    if propia is None:
        raise ErrorHerramienta("Tu usuario no tiene sucursal asignada; no puedo consultar existencias ni ventas.")
    if sucursal_id not in (None, "") and str(sucursal_id) != str(propia):
        raise ErrorHerramienta("Solo puedes consultar tu sucursal.")
    return propia
