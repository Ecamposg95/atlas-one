"""Carga masiva de catalogo desde CSV para una organizacion y sucursal.

Crea, por cada fila: el departamento (categoria) si falta, el producto, su
variante con codigo y precios, el estado del producto en la sucursal y sus
existencias iniciales.

Idempotente por SKU dentro de la organizacion: volver a correrlo omite lo que
ya existe en vez de duplicarlo.

Columnas esperadas (las del formato que exporta el sistema):
    Nombre*, Categoria, Codigo, Descripcion, Costo unitario, Precio*,
    Mostrar en el catalogo, Controlar stock, Stock actual, Stock minimo

Columnas opcionales Color y Talla: filas con el mismo Nombre* (y categoria) y
distinta pareja color/talla se agrupan en un solo producto con N variantes;
la primera fila de cada grupo es la principal. Sin esas columnas, cada fila
sigue siendo un producto independiente, como siempre.

Uso:
    python scripts/import_products.py archivo.csv --org 15 --branch 17
    python scripts/import_products.py archivo.csv --org 15 --branch 17 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata)
from app.models.inventory import StockOnHand
from app.models.products import (
    Department,
    Product,
    ProductBranchStatus,
    ProductVariant,
)
from app.modules.products.variant_label import clean_attr, variant_label


def _norm(s: Optional[str]) -> str:
    """Normaliza una cabecera: sin acentos, sin asteriscos, en minusculas."""
    s = (s or "").strip().replace("*", "")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


CAMPOS = {
    "nombre": "nombre",
    "categoria": "categoria",
    "codigo": "codigo",
    "descripcion": "descripcion",
    "costo unitario": "costo",
    "precio": "precio",
    "mostrar en el catalogo": "visible",
    "controlar stock": "controla_stock",
    "stock actual": "stock",
    "stock minimo": "stock_min",
    "color": "color",
    "talla": "talla",
}


def _si(valor: Optional[str], por_omision: bool = True) -> bool:
    v = (valor or "").strip().upper()
    if not v:
        return por_omision
    return v in {"S", "SI", "SÍ", "Y", "YES", "TRUE", "1"}


def _num(valor: Optional[str], campo: str, fila: int) -> Optional[Decimal]:
    v = (valor or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(
            f"fila {fila}: {campo} invalido — {valor!r} no es un numero"
        ) from None


def _limpiar_attr(valor: Optional[str], maximo: int, nfila: int) -> Optional[str]:
    try:
        return clean_attr(valor, maximo)
    except ValueError as e:
        raise SystemExit(f"fila {nfila}: color/talla {e}")


def _sku_desde_nombre(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", unicodedata.normalize("NFKD", nombre).upper())
    return (base[:8] or "PROD")


def _leer(ruta: str):
    with open(ruta, newline="", encoding="utf-8-sig") as fh:
        lector = csv.DictReader(fh)
        for i, cruda in enumerate(lector, start=2):  # 1 es la cabecera
            yield i, {CAMPOS[_norm(k)]: v for k, v in cruda.items() if _norm(k) in CAMPOS}


def import_products(
    db,
    ruta_csv: str,
    org_id: int,
    branch_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Carga el catalogo. Devuelve un resumen con los conteos y las incidencias."""
    resumen: Dict[str, Any] = {
        "creados": 0,
        "omitidos": 0,
        "ignorados": 0,
        "codigos_generados": 0,
        "categorias_creadas": 0,
        "incidencias": [],
    }

    # SKUs ya usados por la organizacion, para no chocar con el indice unico.
    usados = {
        s for (s,) in db.query(ProductVariant.sku)
        .filter(ProductVariant.organization_id == org_id)
        .all()
        if s
    }
    departamentos: Dict[str, Department] = {}
    padres: Dict[tuple, Product] = {}
    # clave_padre -> {(color_lower, talla_lower): etiqueta con el casing original
    # de la primera fila que la trajo, para que la incidencia de duplicado
    # muestre esa etiqueta y no la de la fila repetida.
    parejas: Dict[tuple, Dict[tuple, str]] = {}

    def _departamento(nombre: str) -> Optional[Department]:
        clave = nombre.strip()
        if not clave:
            return None
        if clave in departamentos:
            return departamentos[clave]
        d = (
            db.query(Department)
            .filter(Department.organization_id == org_id, Department.name == clave)
            .first()
        )
        if d is None:
            d = Department(name=clave, organization_id=org_id)
            db.add(d)
            db.flush()
            resumen["categorias_creadas"] += 1
        departamentos[clave] = d
        return d

    for nfila, f in _leer(ruta_csv):
        nombre = (f.get("nombre") or "").strip()
        if not nombre:
            resumen["ignorados"] += 1
            continue

        precio = _num(f.get("precio"), "precio", nfila)
        costo = _num(f.get("costo"), "costo unitario", nfila)

        sku = (f.get("codigo") or "").strip()
        generado = False
        if not sku:
            sku = _sku_desde_nombre(nombre)
            generado = True
        if sku in usados:
            if not generado and sku == (f.get("codigo") or "").strip():
                # El codigo del archivo ya lo tiene otro producto de esta org.
                # Si el producto ya existe con ese SKU, se omite; si es un
                # codigo repetido dentro del propio archivo, se desambigua.
                existente = (
                    db.query(ProductVariant)
                    .filter(
                        ProductVariant.organization_id == org_id,
                        ProductVariant.sku == sku,
                    )
                    .join(Product, Product.id == ProductVariant.product_id)
                    .filter(Product.name == nombre)
                    .first()
                )
                if existente is not None:
                    resumen["omitidos"] += 1
                    continue
            base, n = sku, 2
            while f"{base}-{n}" in usados:
                n += 1
            sku = f"{base}-{n}"
            generado = True
        if generado:
            resumen["codigos_generados"] += 1
            resumen["incidencias"].append(
                f"fila {nfila}: '{nombre}' recibio el codigo generado {sku}"
            )
        usados.add(sku)

        dep = _departamento(f.get("categoria") or "")

        color = _limpiar_attr(f.get("color"), 60, nfila)
        talla = _limpiar_attr(f.get("talla"), 30, nfila)
        con_variante = bool(color or talla)
        clave_padre = (nombre.lower(), (dep.id if dep is not None else None))

        etiqueta = variant_label(color, talla)
        if con_variante and clave_padre in padres:
            producto = padres[clave_padre]
            pareja = ((color or "").lower(), (talla or "").lower())
            if pareja in parejas[clave_padre]:
                resumen["omitidos"] += 1
                resumen["incidencias"].append(
                    f"fila {nfila}: '{nombre}' ya tiene la variante {parejas[clave_padre][pareja]}; se omite"
                )
                continue
            parejas[clave_padre][pareja] = etiqueta
        else:
            producto = Product(
                name=nombre,
                description=(f.get("descripcion") or "").strip() or None,
                organization_id=org_id,
                department_id=dep.id if dep is not None else None,
                is_active=True,
                has_variants=con_variante,
            )
            db.add(producto)
            db.flush()
            resumen["creados"] += 1
            if con_variante:
                padres[clave_padre] = producto
                pareja = ((color or "").lower(), (talla or "").lower())
                parejas[clave_padre] = {pareja: etiqueta}

        variante = ProductVariant(
            product_id=producto.id,
            sku=sku,
            # Todas las rutas de creacion de la aplicacion asignan "Estándar"
            # cuando no hay color/talla; dejarlo en NULL tumbaba el cobro con
            # un 500 al armar la descripcion del renglon de venta.
            variant_name=etiqueta,
            color=color,
            size=talla,
            price=precio,
            cost=costo,
            organization_id=org_id,
        )
        db.add(variante)
        db.flush()
        if con_variante:
            resumen["variantes_creadas"] = resumen.get("variantes_creadas", 0) + 1

        stock_min = _num(f.get("stock_min"), "stock minimo", nfila)
        db.add(
            ProductBranchStatus(
                variant_id=variante.id,
                branch_id=branch_id,
                organization_id=org_id,
                is_active_pos=True,
                is_visible=_si(f.get("visible")),
                min_stock_alert=stock_min,
            )
        )

        controla = _si(f.get("controla_stock"))
        db.add(
            StockOnHand(
                variant_id=variante.id,
                branch_id=branch_id,
                organization_id=org_id,
                qty_on_hand=_num(f.get("stock"), "stock actual", nfila) or Decimal("0"),
                is_active=controla,
            )
        )

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return resumen


def main() -> None:
    p = argparse.ArgumentParser(description="Carga de catalogo desde CSV")
    p.add_argument("csv")
    p.add_argument("--org", type=int, required=True)
    p.add_argument("--branch", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r = import_products(db, args.csv, args.org, args.branch, dry_run=args.dry_run)
    finally:
        db.close()

    print("=" * 56)
    print("ENSAYO — nada se guardo" if args.dry_run else "CARGA APLICADA")
    print(f"  creados            {r['creados']}")
    if r.get("variantes_creadas"):
        print(f"  variantes creadas  {r['variantes_creadas']}")
    print(f"  omitidos (ya estan){r['omitidos']:>4}")
    print(f"  ignorados          {r['ignorados']}")
    print(f"  categorias creadas {r['categorias_creadas']}")
    print(f"  codigos generados  {r['codigos_generados']}")
    for inc in r["incidencias"]:
        print("   ·", inc)
    print("=" * 56)


if __name__ == "__main__":
    main()
