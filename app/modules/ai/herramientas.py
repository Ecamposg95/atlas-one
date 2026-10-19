"""Registro de herramientas del asistente y el despachador.

`ejecutar` nunca deja escapar un error de datos: lo devuelve al modelo como
`{"error": "..."}` para que se corrija o pregunte. Solo `proponer_cambio`
escribe, y solo una propuesta pendiente (herramientas_propuestas.py).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from .contexto import Contexto, ErrorHerramienta, Herramienta, texto_de_validacion
from .herramientas_catalogo import HERRAMIENTAS as _CATALOGO

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO}


def definiciones() -> list[dict]:
    return [h.definicion(nombre) for nombre, h in REGISTRO.items()]


def ejecutar(nombre: str, argumentos: Any, ctx: Contexto) -> dict:
    herramienta = REGISTRO.get(nombre)
    if herramienta is None:
        return {"error": f"Herramienta desconocida: {nombre}"}
    if not isinstance(argumentos, dict):
        return {"error": "Los argumentos deben ser un objeto JSON."}
    try:
        return herramienta.funcion(ctx, argumentos)
    except ErrorHerramienta as e:
        return {"error": str(e)}
    except HTTPException as e:
        return {"error": str(e.detail)}
    except ValidationError as e:
        return {"error": texto_de_validacion(e)}
    except (TypeError, ValueError) as e:
        logger.info("Herramienta %s con argumentos inválidos: %s", nombre, e)
        return {"error": f"Argumentos inválidos: {e}"}
