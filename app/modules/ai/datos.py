"""Datos como datos: el texto del catálogo nunca le da órdenes al modelo.

Nombres de producto, marcas, departamentos, sucursales y notas los escribe la
gente de la tienda (o llegan de un archivo importado). Entran al modelo por dos
puertas, el prompt y los resultados de herramientas, y en las dos van:

1. **saneados** con `dato()`: sin saltos de línea ni caracteres de control,
   recortados, y sin `<` / `>` (así ningún nombre puede cerrar la valla ni
   abrir otra);
2. **delimitados** con `envolver()`: dentro de `<datos_tienda>…</datos_tienda>`.

La regla fija 1 de `prompts/base.md` le dice al modelo qué significa la valla.
Esto reduce el riesgo; el candado de verdad es que las herramientas ya vienen
filtradas por rol y sucursal: aunque el modelo obedeciera a un nombre de
producto, no tiene con qué sacar lo que el rol no ve.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

ETIQUETA = "datos_tienda"
ABRE = f"<{ETIQUETA}>"
CIERRA = f"</{ETIQUETA}>"
TOPE_DATO = 160

_CONTROL = re.compile(r"[\x00-\x1f\x7f  ]+")
_ESPACIOS = re.compile(r"\s{2,}")


def dato(valor: Any, tope: int = TOPE_DATO) -> Optional[str]:
    """Texto de catálogo listo para viajar al modelo; None se queda None."""
    if valor is None:
        return None
    texto = _CONTROL.sub(" ", str(valor))
    texto = texto.replace("<", "‹").replace(">", "›").replace("`", "'")
    texto = _ESPACIOS.sub(" ", texto).strip()
    if len(texto) > tope:
        texto = texto[: tope - 1].rstrip() + "…"
    return texto


def envolver(resultado: Any) -> str:
    """Resultado de una herramienta como lo recibe el modelo: JSON dentro de la valla.

    Las cadenas ya pasaron por `dato()` en cada herramienta; aquí se vuelve a
    quitar `<` y `>` de todo el JSON por si alguna se escapó (defensa doble: la
    etiqueta de cierre aparece una sola vez, al final)."""
    cuerpo = json.dumps(resultado, ensure_ascii=False, default=str)
    cuerpo = cuerpo.replace("<", "‹").replace(">", "›")
    return f"{ABRE}\n{cuerpo}\n{CIERRA}"


def envolver_texto(texto: str) -> str:
    """Bloque de texto (listas del prompt) dentro de la valla."""
    return f"{ABRE}\n{texto.replace('<', '‹').replace('>', '›')}\n{CIERRA}"
