"""Piezas comunes de las herramientas del agente.

Regla de aislamiento: `org_id` y la sucursal salen SIEMPRE del contexto
autenticado, nunca de los argumentos del modelo. Un id ajeno a la organización
"no existe". Solo el perfil `direccion` (administrador, dueño) puede nombrar
una sucursal, y se valida contra la organización (`ambito_sucursal`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.organization import Branch
from app.models.users import User

from .matriz import DIRECCION, perfil_de
from .models import AiConversation

TOPE_FILAS_TABLA = 12


class ErrorHerramienta(Exception):
    """Mensaje para el MODELO: vuelve como `{"error": ...}`, no es un error HTTP."""


@dataclass
class Contexto:
    db: Session
    org_id: int
    user: User
    conversacion: Optional[AiConversation] = None
    # Tablas que las herramientas del turno dejaron para la pantalla (las arma
    # el servidor con el mismo resultado que vio el modelo, nunca el modelo).
    tablas: list = field(default_factory=list)

    @property
    def perfil(self) -> Optional[str]:
        """`caja`, `gerencia` o `direccion` (matriz.py); None = sin agente."""
        return perfil_de(self.user)


PARAMETRO_SUCURSAL = {
    "type": "integer",
    "description": "Id de una sucursal de la empresa. Sin él: toda la empresa.",
}


@dataclass(frozen=True)
class Herramienta:
    descripcion: str
    parametros: dict
    funcion: Callable[[Contexto, dict], dict]
    # True: administrador y dueño pueden nombrar una sucursal. El parámetro
    # `sucursal_id` solo existe en SU definición; a los demás ni se les ofrece
    # (y si lo mandan, `ambito_sucursal` lo rechaza).
    elige_sucursal: bool = False

    def definicion(self, nombre: str, perfil: Optional[str] = None) -> dict:
        parametros = self.parametros
        if self.elige_sucursal and perfil == DIRECCION:
            parametros = {**parametros, "properties": {
                **parametros.get("properties", {}), "sucursal_id": PARAMETRO_SUCURSAL,
            }}
        return {"type": "function", "function": {
            "name": nombre, "description": self.descripcion, "parameters": parametros,
        }}


def tabla(titulo: str, columnas: list[str], filas: list[list]) -> dict:
    """Tabla pequeña para la pantalla: como mucho `TOPE_FILAS_TABLA` filas."""
    return {
        "titulo": titulo, "columnas": columnas,
        "filas": filas[:TOPE_FILAS_TABLA], "mas": max(0, len(filas) - TOPE_FILAS_TABLA),
    }


def texto_de_validacion(e: ValidationError) -> str:
    partes = []
    for err in e.errors()[:8]:
        campo = ".".join(str(x) for x in err.get("loc", ())) or "datos"
        partes.append(f"{campo}: {err.get('msg')}")
    return "Datos inválidos: " + "; ".join(partes)


def ve_toda_la_org(user: User) -> bool:
    """Solo ADMINISTRADOR y DUEÑO (perfil `direccion`). GERENTE, CAJERO y
    VENDEDOR ven su sucursal (más estricto que `reports.HQ_ROLES`, que incluye
    a GERENTE)."""
    return perfil_de(user) == DIRECCION


def sucursal_propia(ctx: Contexto) -> int:
    """La sucursal de la sesión; error si el usuario no tiene una o si no es
    de la organización activa (usuario con membresía en dos empresas)."""
    propia = ctx.user.branch_id
    if propia is None or ctx.db.query(Branch.id).filter(
        Branch.id == propia, Branch.organization_id == ctx.org_id,
    ).first() is None:
        raise ErrorHerramienta("Tu usuario no tiene sucursal asignada; no puedo consultar existencias ni ventas.")
    return propia


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
    propia = sucursal_propia(ctx)
    if sucursal_id not in (None, "") and str(sucursal_id) != str(propia):
        raise ErrorHerramienta("Solo puedes consultar tu sucursal.")
    return propia
