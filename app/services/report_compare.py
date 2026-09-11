"""Comparación de periodos para los reportes de plataforma (spec §5.1).

Puro: no toca la BD. El router corre la misma consulta agregada para la
ventana previa y usa `decorate_with_previous` para pegar las dos listas por
la llave del pivote.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, Literal, Optional

CompareMode = Literal["none", "prev", "yoy"]
COMPARE_MODES = ("none", "prev", "yoy")

# Las ventanas son cerradas por los dos extremos (`>= s` y `<= e`), así que la
# previa termina un tic ANTES de que empiece la actual. Sin este tic, el
# instante `start` caería en las dos y el periodo previo mediría un
# microsegundo de más.
_RESOLUTION = timedelta(microseconds=1)


def compare_window(start: datetime, end: datetime, mode: str) -> Optional[tuple[datetime, datetime]]:
    """Ventana de comparación para [start, end].

    - `none`: sin comparación.
    - `prev`: la ventana inmediatamente anterior de la misma duración; termina
      un microsegundo antes de que empiece la actual (ni se solapan ni dejan
      hueco).
    - `yoy`: las mismas fechas un año atrás. El 29 de febrero de un bisiesto
      cae en el 28 del año anterior (no existe el 29).
    """
    if mode == "none":
        return None
    if mode == "prev":
        span = end - start
        prev_end = start - _RESOLUTION
        prev_start = prev_end - span
        return prev_start, prev_end
    if mode == "yoy":
        return _shift_year(start, -1), _shift_year(end, -1)
    raise ValueError(f"compare inválido: {mode!r}")


def _shift_year(dt: datetime, delta: int) -> datetime:
    try:
        return dt.replace(year=dt.year + delta)
    except ValueError:
        # 29 de febrero en un año no bisiesto.
        return dt.replace(year=dt.year + delta, day=28)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def pct_delta(current, previous) -> Optional[float]:
    """`(actual − previo) / previo × 100`, redondeado a un decimal.

    `None` cuando no hay con qué comparar (previo 0, ausente o ilegible):
    la UI pinta un guion en vez de un porcentaje inventado.
    """
    cur = _to_decimal(current)
    prev = _to_decimal(previous)
    if cur is None or prev is None or prev == 0:
        return None
    return round(float((cur - prev) / prev * 100), 1)


def decorate_with_previous(
    items: list[dict],
    prev_items: Iterable[dict],
    *,
    key: str,
    fields: tuple[str, ...],
) -> list[dict]:
    """Copia `items` agregando `prev_<campo>` y `delta_<campo>_pct` por cada campo.

    Empareja por `key`. Una fila sin par previo lleva un `prev_*` en cero y
    `delta_* = None` (entidad nueva en el periodo: no creció, apareció).
    No muta la entrada.
    """
    prev_by_key = {row[key]: row for row in prev_items if key in row}
    out: list[dict] = []
    for row in items:
        new_row = dict(row)
        prev_row = prev_by_key.get(row.get(key))
        for field in fields:
            prev_value = prev_row.get(field) if prev_row else None
            prev_dec = _to_decimal(prev_value) or Decimal("0")
            new_row[f"prev_{field}"] = _like(row.get(field), prev_dec)
            new_row[f"delta_{field}_pct"] = pct_delta(row.get(field), prev_value)
        out.append(new_row)
    return out


def _like(current, prev: Decimal):
    """Da al `prev_*` la misma forma que el campo del periodo actual.

    Un conteo previo de 8 tickets es `8`, no `"8.00"`: cuantizar a centavos
    todo por igual convertía los conteos en cifras con decimales inventados.
    El dinero (que llega como cadena ya formateada) conserva sus dos decimales.
    """
    if isinstance(current, bool):
        return prev
    if isinstance(current, int):
        return int(prev)
    if isinstance(current, float):
        return float(prev)
    return str(prev.quantize(Decimal("1.00")))
