"""Nombre de venta y SKU sugerido de una prenda.

Sin base de datos ni FastAPI a proposito: es la unica fuente del texto que el
POS pinta en la tarjeta, la ficha muestra de titulo, la etiqueta CSV exporta y
el ticket congela en `sales_lines.description`
(`app/routers/sales.py::_line_description`).

La marca va PRIMERO porque asi se pide la prenda en el mostrador:
"Louis Vuitton · Chamarra mezclilla · Talla M".

REGLA DE COMPATIBILIDAD (no negociable): un producto SIN marca y SIN modelo se
sigue llamando exactamente como hoy. Con talla, el renglon del ticket de hoy
dice "Playera (M)" -- `variant_sale_name` conserva ESE formato y solo usa el
de " · " cuando hay marca o modelo. Asi ninguna tienda que no capture los
campos nuevos ve cambiar su ticket ni su pantalla. La misma regla cubre el
catalogo VIEJO, cuyas variantes traen una etiqueta escrita a mano
(`variant_name` = "600ml") con color y talla vacios: pasa `variant_name` y
sale "Refresco (600ml)", que es como se ha llamado siempre.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Genero de la prenda. Cadenas, no enum de DB (CLAUDE.md §5): agregar un valor
# no puede costar un ALTER TYPE. "NINO" sin eñe para que el valor viaje igual
# por URL, CSV y ticket latin-1.
GENDERS = ("HOMBRE", "MUJER", "UNISEX", "NINO")

_ESPACIOS = re.compile(r"\s+")
_NO_SKU = re.compile(r"[^A-Z0-9]")

SEPARADOR = " · "

# Etiquetas que NO distinguen nada: una variante con esto en `variant_name` es
# la unica del producto y se llama como el producto. "Default" lo dejaron
# importaciones viejas; "Estándar" es el que pone `variant_label`.
ETIQUETAS_NEUTRAS = frozenset({"estandar", "default"})


def _limpio(valor: Optional[str]) -> str:
    """Texto sin espacios de sobra; "" para None y para lo que quede vacio."""
    return _ESPACIOS.sub(" ", valor).strip() if isinstance(valor, str) else ""


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def normalizar_genero(valor: Optional[str]) -> Optional[str]:
    """"niño" -> "NINO", " mujer " -> "MUJER", "" -> None.

    Lanza ValueError con los valores validos si no es ninguno: el caller lo
    convierte en 422 con el campo señalado.
    """
    texto = _sin_acentos(_limpio(valor)).upper()
    if not texto:
        return None
    if texto not in GENDERS:
        raise ValueError(f"debe ser uno de: {', '.join(GENDERS)}")
    return texto


def sale_name(brand: Optional[str], name: str, model: Optional[str]) -> str:
    """"Louis Vuitton · Chamarra mezclilla".

    La marca va primero y separada; el modelo se pega al nombre con un espacio
    (es parte de como se llama la prenda, no un atributo aparte). Sin marca:
    "Chamarra mezclilla". Sin marca ni modelo: el `name` tal cual.
    """
    prenda = " ".join(p for p in (_limpio(name), _limpio(model)) if p)
    marca = _limpio(brand)
    return f"{marca}{SEPARADOR}{prenda}" if marca and prenda else (prenda or marca)


def atributos_venta(color: Optional[str], size: Optional[str]) -> str:
    """"Beige, Talla M", "Talla M", "Beige" o "" cuando no hay atributos.

    La talla se nombra ("Talla M") porque sola es una letra suelta que no se
    entiende en un ticket; el color se lee solo.
    """
    partes = []
    limpio_color = _limpio(color)
    limpio_talla = _limpio(size)
    if limpio_color:
        partes.append(limpio_color)
    if limpio_talla:
        partes.append(f"Talla {limpio_talla}")
    return ", ".join(partes)


def _etiqueta_heredada(variant_name: Optional[str]) -> str:
    """La etiqueta escrita a mano del catalogo viejo, o "" si no distingue nada."""
    etiqueta = _limpio(variant_name)
    if not etiqueta:
        return ""
    plano = _sin_acentos(etiqueta).casefold()
    return "" if plano in ETIQUETAS_NEUTRAS else etiqueta


def variant_sale_name(
    brand: Optional[str],
    name: str,
    model: Optional[str],
    color: Optional[str],
    size: Optional[str],
    variant_name: Optional[str] = None,
) -> str:
    """Nombre de venta de UNA talla/color concreta.

    Con marca o modelo: "Louis Vuitton · Chamarra mezclilla · Beige, Talla M".

    Sin marca NI modelo conserva el formato historico del ticket:
    "Playera (Rojo / M)" / "Playera (M)" / "Playera".

    `variant_name` es la etiqueta GUARDADA de la variante y es la unica fuente
    del caso viejo: sin marca, sin modelo y sin color/talla, una variante con
    etiqueta propia ("600ml") se sigue llamando "Refresco (600ml)". Sin ese
    dato dos variantes viejas del mismo producto quedan con el mismo nombre en
    pantalla mientras el ticket sigue imprimiendo la etiqueta.
    """
    base = sale_name(brand, name, model)
    atributos = atributos_venta(color, size)
    if _limpio(brand) or _limpio(model):
        return f"{base}{SEPARADOR}{atributos}" if atributos else base
    # Sin marca ni modelo: el formato de siempre. Color/talla mandan; si no
    # hay, la etiqueta heredada; si tampoco, el nombre a secas.
    # Misma etiqueta que `variant_label` (sin su guarda de longitud: aqui solo
    # se formatea, nunca se valida a media impresion).
    etiqueta = " / ".join(p for p in (_limpio(color), _limpio(size)) if p) \
        or _etiqueta_heredada(variant_name)
    return f"{_limpio(name)} ({etiqueta})" if etiqueta else base


# ─── SKU sugerido ────────────────────────────────────────────────────────────
#
# Convencion acordada con la boutique (2026-09-21):
#     MARCA-PRENDA-MODELO-COLOR-TALLA
# Es una SUGERENCIA: el alta acepta cualquier SKU unico por organizacion, y
# nada la aplica sola.

def _palabras(valor: Optional[str]) -> list[str]:
    """Palabras en mayusculas, sin acentos y sin signos ("Tiffany & Co." ->
    ["TIFFANY", "CO"])."""
    crudo = _sin_acentos(_limpio(valor)).upper()
    return [p for p in (_NO_SKU.sub("", w) for w in crudo.split()) if p]


def _marca_corta(brand: Optional[str]) -> str:
    """Iniciales si la marca tiene 2+ palabras, si no las 3 primeras letras.

    "Louis Vuitton" -> LV, "Dolce & Gabbana" -> DG (el "&" no es palabra),
    "Gucci" -> GUC.
    """
    palabras = _palabras(brand)
    if len(palabras) >= 2:
        return "".join(p[0] for p in palabras)
    return palabras[0][:3] if palabras else ""


def _primeras(valor: Optional[str], n: int) -> str:
    """Las `n` primeras letras de la PRIMERA palabra ("Pantalón formal" ->
    PANT con n=4)."""
    palabras = _palabras(valor)
    return palabras[0][:n] if palabras else ""


def sku_sugerido(
    brand: Optional[str],
    name: str,
    model: Optional[str],
    color: Optional[str],
    size: Optional[str],
) -> str:
    """"LV-CHAM-MEZ-BEI-M". Solo [A-Z0-9-]; las partes vacias se omiten.

    Marca: iniciales (2+ palabras) o 3 letras. Prenda: 4 letras. Modelo y
    color: 3 letras. Talla tal cual, sin signos ("26.5" -> "265").
    """
    partes = [
        _marca_corta(brand),
        _primeras(name, 4),
        _primeras(model, 3),
        _primeras(color, 3),
        _NO_SKU.sub("", _sin_acentos(_limpio(size)).upper()),
    ]
    return "-".join(p for p in partes if p)
