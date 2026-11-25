"""Revisión fiscal del catálogo: productos sin tasa de IVA del SAT o con una
tasa que contradice sus banderas de cobro (`has_iva`/`tax_rate`), por
sucursal, para que cada tienda los corrija.

Solo lectura. La regla de qué es "sin clasificar" y qué es "discrepancia" vive
en `app/services/desglose_fiscal.py` (`iva_efectivo`, `discrepancia_iva`); aquí
solo se recorre el catálogo y se agrupa por sucursal.

Un producto aparece una vez por cada sucursal donde se vende (estado por
sucursal con `is_active_pos`); el que no se vende en ninguna sale en "Sin
sucursal". Los archivados no salen: no se venden.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models import Product, ProductBranchStatus, ProductVariant
from app.models.organization import Branch
from app.services.desglose_fiscal import (
    IVA_8,
    discrepancia_de_producto,
    iva_efectivo_de_variante,
)

from .comun import variantes_vivas

SIN_CLASIFICACION = "SIN_CLASIFICACION"
DISCREPANCIA = "DISCREPANCIA"
PROBLEMAS = (SIN_CLASIFICACION, DISCREPANCIA)


@dataclass(frozen=True)
class Hallazgo:
    branch_id: Optional[int]
    branch_name: str
    product_id: str
    producto: str
    sku: str
    problema: str
    detalle: str
    iva_tratamiento: Optional[str]
    sat_objeto_imp: Optional[str]
    has_iva: bool
    tax_rate: Optional[str]


def _detalle_sin_clasificar(variante) -> str:
    supuesta = "8" if iva_efectivo_de_variante(variante).tratamiento.clave == IVA_8 else "16"
    return (
        f"Sin tasa de IVA en los datos fiscales: el IVA de sus ventas se calcula suponiendo {supuesta} % "
        "incluido en el precio. Captura la tasa en «Datos fiscales (SAT)»."
    )


def revisar_catalogo(db: Session, org_id: int, branch_ids: Optional[set[int]] = None) -> list[Hallazgo]:
    """Hallazgos de la organización, discrepancias primero, luego por
    sucursal y nombre. `branch_ids` acota a esas sucursales (None = todas, y
    entonces también sale el grupo "Sin sucursal")."""
    sucursales = {
        b.id: b.name
        for b in db.query(Branch.id, Branch.name).filter(Branch.organization_id == org_id).all()
    }
    pbs = (
        db.query(ProductBranchStatus.variant_id, ProductBranchStatus.branch_id)
        .join(ProductVariant, ProductVariant.id == ProductBranchStatus.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.organization_id == org_id, ProductBranchStatus.is_active_pos.is_(True))
        .all()
    )
    sucursales_de_variante: dict[str, set[int]] = {}
    for variant_id, branch_id in pbs:
        if branch_id in sucursales:
            sucursales_de_variante.setdefault(variant_id, set()).add(branch_id)

    productos = (
        db.query(Product)
        .options(selectinload(Product.variants))
        .filter(Product.organization_id == org_id, Product.is_active.is_(True))
        .all()
    )
    hallazgos: list[Hallazgo] = []
    for producto in productos:
        vivas = variantes_vivas(producto)
        if not vivas:
            continue
        principal = vivas[0]
        discrepancia = discrepancia_de_producto(producto, vivas)
        if discrepancia:
            problema, detalle = DISCREPANCIA, discrepancia
        elif not iva_efectivo_de_variante(principal).clasificado:
            problema, detalle = SIN_CLASIFICACION, _detalle_sin_clasificar(principal)
        else:
            continue
        donde: set[Optional[int]] = set()
        for v in vivas:
            donde |= sucursales_de_variante.get(v.id, set())
        if not donde:
            donde = {None}
        for branch_id in donde:
            if branch_ids is not None and branch_id not in branch_ids:
                continue
            hallazgos.append(Hallazgo(
                branch_id=branch_id,
                branch_name=sucursales.get(branch_id, "Sin sucursal"),
                product_id=producto.id,
                producto=producto.name or principal.sku,
                sku=principal.sku,
                problema=problema,
                detalle=detalle,
                iva_tratamiento=producto.iva_tratamiento,
                sat_objeto_imp=producto.sat_objeto_imp,
                has_iva=bool(principal.has_iva),
                tax_rate=str(principal.tax_rate) if principal.tax_rate is not None else None,
            ))
    hallazgos.sort(key=lambda h: (
        h.problema != DISCREPANCIA, h.branch_id is None, h.branch_name.lower(), h.producto.lower(), h.sku,
    ))
    return hallazgos


def resumen_por_sucursal(hallazgos: list[Hallazgo]) -> list[dict]:
    """Conteo por sucursal, en el mismo orden en que salen las sucursales."""
    conteo: dict[Optional[int], dict] = {}
    for h in sorted(hallazgos, key=lambda h: (h.branch_id is None, h.branch_name.lower())):
        fila = conteo.setdefault(h.branch_id, {
            "branch_id": h.branch_id, "branch_name": h.branch_name,
            "sin_clasificacion": 0, "con_discrepancia": 0,
        })
        fila["con_discrepancia" if h.problema == DISCREPANCIA else "sin_clasificacion"] += 1
    return list(conteo.values())
