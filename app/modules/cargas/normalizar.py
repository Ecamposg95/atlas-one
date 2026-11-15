"""Normalizar, agrupar y armar SKU. Funciones puras: sin base ni red."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.modules.cargas.reglas import ReglasCarga
from app.modules.cargas.tipos import Grupo, RenglonCrudo, RenglonNormalizado
from app.modules.products.sale_name import sku_sugerido

_CENTAVOS = Decimal("0.01")
_NO_SKU = re.compile(r"[^A-Z0-9]")


def _llave(texto: Optional[str]) -> str:
    """Comparable: sin acentos, minúsculas y sin espacios de los lados."""
    if not texto:
        return ""
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(plano.split()).casefold()


def _dinero(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _buscar(mapa: dict, clave: Optional[str]):
    objetivo = _llave(clave)
    if not objetivo:
        return None
    for k, v in mapa.items():
        if _llave(k) == objetivo:
            return v
    return None


def _material_efectivo(material: Optional[str], reglas: ReglasCarga) -> Optional[str]:
    """Solo cuenta el material que está en `materiales_aparte`."""
    m = _llave(material)
    if not m or m == _llave(reglas.material_normal):
        return None
    return m if any(_llave(a) == m for a in reglas.materiales_aparte) else None


def _talla_normalizada(talla: Optional[str], reglas: ReglasCarga) -> Optional[str]:
    if talla is None or not talla.strip():
        return None
    mapeada = _buscar(reglas.mapa_tallas, talla)
    return mapeada if mapeada is not None else talla.strip()


def _costo(r: RenglonCrudo, reglas: ReglasCarga, monedas: dict[str, Optional[Decimal]]) -> Optional[Decimal]:
    if r.costo_unitario is not None:
        moneda = (r.moneda or "MXN").strip().upper()
        cambio = next((v for k, v in monedas.items() if k.strip().upper() == moneda), None)
        if cambio is None and moneda == "MXN":
            cambio = Decimal(1)
        return None if cambio is None else _dinero(r.costo_unitario * cambio)
    if reglas.costo_si_falta == "fraccion_precio" and r.precio is not None:
        return _dinero(r.precio * reglas.fraccion)
    return None


def _precio_llave(precio: Optional[Decimal]) -> str:
    return "sin-precio" if precio is None else str(_dinero(precio))


def normalizar_renglon(
    r: RenglonCrudo, reglas: ReglasCarga, monedas: dict[str, Optional[Decimal]]
) -> RenglonNormalizado:
    tipo = _buscar(reglas.tipos, r.tipo)
    genero = _buscar(reglas.genero_por_marca, r.marca) or reglas.genero_por_omision
    datos = r.model_dump()
    datos["talla"] = _talla_normalizada(r.talla, reglas)
    llave = "|".join(
        [
            _llave(r.marca),
            _llave(r.tipo),
            _material_efectivo(r.material, reglas) or "",
            _precio_llave(r.precio),
        ]
    )
    return RenglonNormalizado(
        **datos,
        genero=genero,
        departamento=tipo.departamento if tipo else None,
        costo_mxn=_costo(r, reglas, monedas),
        llave_grupo=llave,
    )


def _base(llave: str) -> str:
    return llave.rsplit("|", 1)[0]


def agrupar(renglones: list[RenglonNormalizado]) -> list[Grupo]:
    """Un grupo por producto. Mismo tipo con precios distintos en la MISMA talla
    se parte en grupos con sufijo "", "-2", "-3"; en tallas distintas es un
    solo grupo con precio por talla."""
    por_base: dict[str, list[int]] = {}
    for i, r in enumerate(renglones):
        por_base.setdefault(_base(r.llave_grupo), []).append(i)

    grupos: list[Grupo] = []
    for base, idxs in por_base.items():
        precios_por_talla: dict[str, set] = {}
        for i in idxs:
            r = renglones[i]
            precios_por_talla.setdefault(r.talla or "", set()).add(_precio_llave(r.precio))
        hay_choque = any(len(p) > 1 for p in precios_por_talla.values())

        if not hay_choque:
            subgrupos = [(base, idxs, "")]
        else:
            por_precio: dict[str, list[int]] = {}
            for i in idxs:
                por_precio.setdefault(_precio_llave(renglones[i].precio), []).append(i)
            subgrupos = [
                (renglones[ids[0]].llave_grupo, ids, "" if n == 0 else f"-{n + 1}")
                for n, ids in enumerate(por_precio.values())
            ]

        for llave, ids, sufijo in subgrupos:
            primero = renglones[ids[0]]
            colores = {_llave(renglones[i].color) for i in ids}
            grupos.append(
                Grupo(
                    llave=llave,
                    renglones=ids,
                    tallas={
                        renglones[i].talla or "": (
                            None if renglones[i].precio is None else _dinero(renglones[i].precio)
                        )
                        for i in ids
                    },
                    sufijo=sufijo,
                    marca=primero.marca,
                    tipo=primero.tipo,
                    material=primero.material,
                    color=primero.color if len(colores) == 1 else None,
                    genero=primero.genero,
                )
            )
    return grupos



def prefijo_de_marca(skus_existentes_de_la_marca: list[str]) -> Optional[str]:
    """Prefijo más común antes del primer "-" (los SKU sin "-" no cuentan)."""
    cuenta = Counter(s.split("-", 1)[0].strip() for s in skus_existentes_de_la_marca if "-" in s)
    cuenta.pop("", None)
    return cuenta.most_common(1)[0][0] if cuenta else None


def _limpia_sku(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return _NO_SKU.sub("", plano.upper())


def _talla_principal(grupo: Grupo, reglas: ReglasCarga) -> Optional[str]:
    tallas = [t for t in grupo.tallas if t]
    if not tallas:
        return None
    for t in reglas.escala_ropa:
        for propia in tallas:
            if _llave(propia) == _llave(t):
                return propia
    return tallas[0]


def sku_para(grupo: Grupo, talla: Optional[str], reglas: ReglasCarga, prefijo: Optional[str]) -> str:
    """`PREFIJO-CODIGO[-MAT][sufijo]`; la talla principal sin sufijo y las demás
    con `-<talla>`. Tipo desconocido: cae en `sku_sugerido`."""
    tipo = _buscar(reglas.tipos, grupo.tipo)
    es_principal = not talla or talla == _talla_principal(grupo, reglas)
    sufijo_talla = "" if es_principal else _limpia_sku(talla)
    if tipo is None:
        base = sku_sugerido(grupo.marca, grupo.tipo or "", None, grupo.color, None, grupo.genero)
    else:
        partes = [p for p in (prefijo, tipo.codigo_sku) if p]
        material = _material_efectivo(grupo.material, reglas)
        if material:
            partes.append(_limpia_sku(material)[:3])
        base = "-".join(partes)
    base += grupo.sufijo
    return f"{base}-{sufijo_talla}" if sufijo_talla else base
