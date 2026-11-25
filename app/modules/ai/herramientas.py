"""Registro de herramientas del agente y el despachador.

Qué herramientas tiene cada rol lo dice `matriz.py`. Aquí:

- `definiciones(ctx)`: lo que se le entrega al modelo, solo las del rol.
- `ejecutar(nombre, argumentos, ctx)`: rechaza la herramienta que no es del
  rol aunque el modelo la nombre (o la recuerde de otra conversación) y nunca
  deja escapar un error de datos: lo devuelve como `{"error": "..."}` para que
  el modelo se corrija o pregunte.

Fase A1: todas leen. Ninguna escribe.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from .contexto import Contexto, ErrorHerramienta, Herramienta, texto_de_validacion
from .herramientas_catalogo import HERRAMIENTAS as _CATALOGO
from .herramientas_operacion import HERRAMIENTAS as _OPERACION
from .matriz import HERRAMIENTAS_POR_ROL, herramientas_de

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO, **_OPERACION}

_SIN_REGISTRO = {n for nombres in HERRAMIENTAS_POR_ROL.values() for n in nombres} - set(REGISTRO)
if _SIN_REGISTRO:  # pragma: no cover - error de programación, se ve al importar
    raise RuntimeError(f"matriz.py nombra herramientas que no existen: {sorted(_SIN_REGISTRO)}")


def definiciones(ctx: Contexto) -> list[dict]:
    """Las herramientas del rol de `ctx.user`, en el orden de la matriz."""
    perfil = ctx.perfil
    return [REGISTRO[nombre].definicion(nombre, perfil) for nombre in herramientas_de(ctx.user)]


def ejecutar(nombre: str, argumentos: Any, ctx: Contexto) -> dict:
    if nombre not in herramientas_de(ctx.user):
        # Mismo texto exista o no: el modelo no averigua qué hay para otros roles.
        logger.info("IA: herramienta fuera de rol o desconocida: %s", nombre)
        return {"error": f"Herramienta no disponible: {nombre}"}
    if not isinstance(argumentos, dict):
        return {"error": "Los argumentos deben ser un objeto JSON."}
    try:
        resultado = REGISTRO[nombre].funcion(ctx, argumentos)
    except ErrorHerramienta as e:
        return {"error": str(e)}
    except HTTPException as e:
        return {"error": str(e.detail)}
    except ValidationError as e:
        return {"error": texto_de_validacion(e)}
    except (TypeError, ValueError) as e:
        logger.info("Herramienta %s con argumentos inválidos: %s", nombre, e)
        return {"error": f"Argumentos inválidos: {e}"}
    # La tabla es para la pantalla, no para el modelo.
    tabla = resultado.pop("_tabla", None) if isinstance(resultado, dict) else None
    if tabla and tabla.get("filas"):
        ctx.tablas.append(tabla)
    return resultado
