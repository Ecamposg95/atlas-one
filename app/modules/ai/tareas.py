"""Qué modelo atiende cada tipo de tarea de IA.

Tres tareas: `consulta` (precio, existencia: rápida y barata), `captura`
(altas, documentos) y `analisis` (reportes). Cada una tiene una lista ordenada
de (proveedor, modelo): se usa el primero y, si falla por red, 5xx o cuota, el
siguiente (`ProveedorConRespaldo`).

De dónde sale la lista, en orden de prioridad:

1. Excepción por organización: `organization.ai_modelos`, un JSON
   `{"consulta": ["anthropic:claude-haiku-5-5", "compatible:gemini-3.8-flash"]}`.
2. Variable global `AI_MODELOS_CONSULTA` / `_CAPTURA` / `_ANALISIS`, con el
   mismo formato separado por comas.
3. Valor por omisión (`POR_OMISION`): Claude en las tres.

Proveedores (cómo se arma cada uno y qué llave necesita):

- `anthropic` → `ANTHROPIC_API_KEY`.
- `compatible` → API compatible con OpenAI: `LLM_BASE_URL` (por omisión la capa
  compatible de Gemini), `LLM_API_KEY`; sin modelo en la entrada usa `LLM_MODEL`.
- cualquier otro nombre `x` → también compatible con OpenAI, con
  `AI_PROVEEDOR_X_BASE_URL` y `AI_PROVEEDOR_X_API_KEY` (para tener varios a la vez).

Una entrada cuyo proveedor no tiene llave se salta. Si ninguna queda: 503.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.ai.proveedores import (
    Proveedor, ProveedorAnthropic, ProveedorConRespaldo, ProveedorOpenAI,
)
from app.modules.ai.proveedores.anthropic_nativo import timeout_configurado

logger = logging.getLogger(__name__)

CONSULTA, CAPTURA, ANALISIS = "consulta", "captura", "analisis"
TAREAS = (CONSULTA, CAPTURA, ANALISIS)

BASE_URL_COMPATIBLE = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELO_COMPATIBLE = "gemini-3.8-flash"

_NOMBRE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


@dataclass(frozen=True)
class Opcion:
    proveedor: str
    modelo: str  # "" = el modelo por omisión del proveedor

    def __str__(self) -> str:
        return f"{self.proveedor}:{self.modelo}" if self.modelo else self.proveedor


POR_OMISION: dict[str, tuple[Opcion, ...]] = {
    CONSULTA: (Opcion("anthropic", "claude-haiku-5-5"),),
    CAPTURA: (Opcion("anthropic", "claude-opus-5-5"),),
    ANALISIS: (Opcion("anthropic", "claude-opus-5-5"),),
}


def _exigir_tarea(tarea: str) -> None:
    if tarea not in TAREAS:
        raise ValueError(f"Tarea de IA desconocida: {tarea!r} (válidas: {', '.join(TAREAS)})")


def interpretar_opcion(texto: Any) -> Optional[Opcion]:
    """`"proveedor:modelo"` o `"proveedor"` → Opcion; None si no se entiende."""
    if not isinstance(texto, str):
        return None
    proveedor, _, modelo = texto.strip().partition(":")
    proveedor, modelo = proveedor.strip().lower(), modelo.strip()
    if not _NOMBRE.match(proveedor):
        return None
    if proveedor == "anthropic" and not modelo:
        return None  # Anthropic no tiene modelo implícito: hay que nombrarlo
    return Opcion(proveedor, modelo)


def _interpretar_lista(valores: Any, origen: str) -> list[Opcion]:
    if isinstance(valores, str):
        valores = [v for v in valores.split(",") if v.strip()]
    if not isinstance(valores, (list, tuple)):
        return []
    opciones: list[Opcion] = []
    for v in valores:
        opcion = interpretar_opcion(v)
        if opcion is None:
            logger.warning("IA: entrada de modelo inválida en %s: %r (se ignora)", origen, v)
        elif opcion not in opciones:
            opciones.append(opcion)
    return opciones


def validar_ai_modelos(valor: Any) -> Optional[dict[str, list[str]]]:
    """Normaliza lo que se guarda en `organization.ai_modelos`; ValueError si no sirve.
    `None` o `{}` = sin excepción (la organización usa la lista global)."""
    if valor in (None, {}):
        return None
    if not isinstance(valor, dict):
        raise ValueError("ai_modelos debe ser un objeto {tarea: [\"proveedor:modelo\", …]}.")
    limpio: dict[str, list[str]] = {}
    for tarea, lista in valor.items():
        if tarea not in TAREAS:
            raise ValueError(f"Tarea de IA desconocida: {tarea!r} (válidas: {', '.join(TAREAS)}).")
        if not isinstance(lista, list) or not lista:
            raise ValueError(f"La lista de modelos de {tarea!r} debe traer al menos una entrada.")
        opciones = []
        for entrada in lista:
            opcion = interpretar_opcion(entrada)
            if opcion is None:
                raise ValueError(f"Entrada de modelo inválida en {tarea!r}: {entrada!r} "
                                 "(formato: \"proveedor:modelo\").")
            opciones.append(str(opcion))
        limpio[tarea] = opciones
    return limpio


def cadena_global(tarea: str) -> list[Opcion]:
    """La lista de la tarea sin mirar la organización (variable de entorno u omisión)."""
    _exigir_tarea(tarea)
    variable = f"AI_MODELOS_{tarea.upper()}"
    opciones = _interpretar_lista(os.getenv(variable) or "", variable)
    if opciones:
        return opciones
    if tarea == CAPTURA:
        # `AI_MODELO` es la variable con la que nació Cargar mercancía: sigue valiendo.
        heredado = (os.getenv("AI_MODELO") or "").strip()
        if heredado:
            return [Opcion("anthropic", heredado)]
    return list(POR_OMISION[tarea])


def cadena_de(db: Optional[Session], org_id: Optional[int], tarea: str) -> list[Opcion]:
    """La lista efectiva: la excepción de la organización si la tiene, si no la global."""
    _exigir_tarea(tarea)
    if db is not None and org_id is not None:
        from app.modules.tenants.models import Organization

        org = db.get(Organization, org_id)
        propio = getattr(org, "ai_modelos", None) if org is not None else None
        if isinstance(propio, dict) and propio.get(tarea):
            opciones = _interpretar_lista(propio[tarea], f"organization.ai_modelos[{tarea}] de la org {org_id}")
            if opciones:
                return opciones
    return cadena_global(tarea)


# ── construcción de proveedores ──────────────────────────────────────────

# Los clientes httpx se reutilizan por (url, llave, modelo): evita abrir un pool
# de conexiones por petición. FastAPI corre los handlers síncronos en hilos:
# todo acceso a la caché va bajo `_CANDADO`.
_COMPATIBLES: dict[tuple, ProveedorOpenAI] = {}
_CANDADO = threading.Lock()


def reiniciar_proveedores() -> None:
    """Cierra y olvida los clientes en caché (para pruebas)."""
    with _CANDADO:
        for c in list(_COMPATIBLES.values()):
            c.cerrar()
        _COMPATIBLES.clear()


def _variables(proveedor: str) -> tuple[str, str]:
    """(variable de la URL base, variable de la llave) de un proveedor compatible."""
    if proveedor == "compatible":
        return "LLM_BASE_URL", "LLM_API_KEY"
    prefijo = f"AI_PROVEEDOR_{proveedor.upper()}"
    return f"{prefijo}_BASE_URL", f"{prefijo}_API_KEY"


def variable_de_llave(proveedor: str) -> str:
    return "ANTHROPIC_API_KEY" if proveedor == "anthropic" else _variables(proveedor)[1]


def construir(opcion: Opcion) -> Optional[Proveedor]:
    """El proveedor listo para usarse, o None si falta su llave (o su URL)."""
    if opcion.proveedor == "anthropic":
        llave = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not llave:
            return None
        return ProveedorAnthropic(api_key=llave, modelo=opcion.modelo, timeout=timeout_configurado())
    var_url, var_llave = _variables(opcion.proveedor)
    llave = (os.getenv(var_llave) or "").strip()
    base = (os.getenv(var_url) or "").strip()
    modelo = opcion.modelo
    if opcion.proveedor == "compatible":
        base = base or BASE_URL_COMPATIBLE
        modelo = modelo or (os.getenv("LLM_MODEL") or "").strip() or MODELO_COMPATIBLE
    if not llave or not base or not modelo:
        return None
    clave = (opcion.proveedor, base, llave, modelo)
    with _CANDADO:
        cliente = _COMPATIBLES.get(clave)
        if cliente is None:
            cliente = _COMPATIBLES[clave] = ProveedorOpenAI(base, llave, modelo, nombre=opcion.proveedor)
        return cliente


def proveedor_para(db: Optional[Session], org_id: Optional[int], tarea: str) -> Proveedor:
    """El proveedor (con respaldo) que atiende `tarea` para la organización.
    503 con el nombre de la variable que falta si ninguna entrada tiene llave."""
    cadena = cadena_de(db, org_id, tarea)
    listos = [p for p in (construir(o) for o in cadena) if p is not None]
    if not listos:
        faltan = sorted({variable_de_llave(o.proveedor) for o in cadena})
        raise HTTPException(
            status_code=503,
            detail=f"IA no configurada: falta {' o '.join(faltan)} en el servidor.",
        )
    return ProveedorConRespaldo(listos)
