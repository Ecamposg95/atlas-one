"""Catálogo de capacidades: qué funciones se pueden apagar y de qué módulo dependen.

Es una LISTA BLANCA a propósito. Solo se puede apagar lo que está declarado aquí;
todo lo demás está siempre encendido. La alternativa —ponerle candado a todo y ver
qué se rompe— dejaría sin dar de alta cajeras a las cuatro tiendas reales, que
tienen el módulo `users` apagado.

El archivo JSON es la única fuente de verdad: lo lee este módulo para resolver y
lo lee una prueba de vitest para comprobar que la pantalla no invente claves.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

_ARCHIVO = Path(__file__).with_name("catalogo.json")

CATALOGO: list[dict] = json.loads(_ARCHIVO.read_text(encoding="utf-8"))
CLAVES: set[str] = {f["clave"] for f in CATALOGO}
_POR_CLAVE: dict[str, str] = {f["clave"]: f["modulo"] for f in CATALOGO}


def modulo_de(clave: str) -> Optional[str]:
    """Módulo que exige esa función, o None si la función no está en el catálogo."""
    return _POR_CLAVE.get(clave)


def resolver(modulos: Iterable[str]) -> list[str]:
    """Funciones que una organización con esos módulos puede usar, ordenadas."""
    prendidos = set(modulos)
    return sorted(f["clave"] for f in CATALOGO if f["modulo"] in prendidos)
