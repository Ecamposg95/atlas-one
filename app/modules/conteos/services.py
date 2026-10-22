# app/modules/conteos/services.py
"""Reglas del conteo físico. El router solo valida permisos y delega aquí.

Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §4-§5.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.inventory import StockOnHand
from app.modules.conteos.models import ABIERTO, CERRADO, InventoryCount, InventoryCountLine
from app.modules.conteos.schemas import (
    Avance, ConteoDetalle, ConteoRead, FilaDesconocido, FilaReporte, LineaRead,
    ProductoResumen, Reporte, ScanResult,
)
from app.modules.products.models import PackagingUnit, Product, ProductVariant
from app.modules.products.sale_name import variant_sale_name

CERO = Decimal("0")


# ── Resolución del código ────────────────────────────────────────────────────
def resolver_codigo(db: Session, org_id: int, code: str) -> List[ProductVariant]:
    """Misma regla exacta que `pos/search?exact=true`: SKU sin importar
    mayúsculas, código de barras o código de empaque, dentro de la org, con
    producto activo y variante sin baja. Devuelve TODAS las que empatan: con
    más de una, el pasillo pregunta en vez de adivinar."""
    code = (code or "").strip()
    if not code:
        return []
    filas = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(PackagingUnit, PackagingUnit.variant_id == ProductVariant.id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(
            Product.organization_id == org_id,
            Product.is_active.is_(True),
            ProductVariant.deleted_at.is_(None),
            or_(
                func.lower(ProductVariant.sku) == code.lower(),
                ProductVariant.barcode == code,
                PackagingUnit.barcode == code,
            ),
        )
        .all()
    )
    # El outerjoin a empaques puede repetir la variante: una por id.
    unicas: Dict[str, ProductVariant] = {}
    for v in filas:
        unicas.setdefault(v.id, v)
    return list(unicas.values())


def resumen_producto(v: ProductVariant) -> ProductoResumen:
    p = v.product
    marca = p.brand.name if getattr(p, "brand", None) else None
    return ProductoResumen(
        variant_id=v.id,
        nombre=variant_sale_name(marca, p.name, p.model, v.color, v.size, v.variant_name),
        marca=marca, talla=v.size, color=v.color, sku=v.sku, barcode=v.barcode,
        foto=p.image_url,
        departamento=p.department.name if getattr(p, "department", None) else None,
    )


def _variante_de_la_org(db: Session, org_id: int, variant_id: str) -> Optional[ProductVariant]:
    return (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(Product.organization_id == org_id, ProductVariant.id == variant_id,
                ProductVariant.deleted_at.is_(None))
        .first()
    )


# ── Existencias y alcance ────────────────────────────────────────────────────
def existencias(db: Session, conteo: InventoryCount) -> Dict[str, Decimal]:
    filas = (
        db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand)
        .filter(StockOnHand.organization_id == conteo.organization_id,
                StockOnHand.branch_id == conteo.branch_id)
        .all()
    )
    return {vid: Decimal(q or 0) for vid, q in filas}


def _alcance(db: Session, conteo: InventoryCount) -> List[ProductVariant]:
    q = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(Product.organization_id == conteo.organization_id,
                Product.is_active.is_(True), ProductVariant.deleted_at.is_(None))
    )
    if conteo.department_id:
        q = q.filter(Product.department_id == conteo.department_id)
    return q.all()


def _fuera_de_alcance(conteo: InventoryCount, v: ProductVariant) -> bool:
    return bool(conteo.department_id) and v.product.department_id != conteo.department_id


# ── Líneas ───────────────────────────────────────────────────────────────────
def _exigir_abierto(conteo: InventoryCount) -> None:
    if conteo.status != ABIERTO:
        raise HTTPException(409, "Este conteo ya está cerrado.")


def _sumar(db: Session, conteo: InventoryCount, v: ProductVariant, qty: Decimal,
           user_id: Optional[int]) -> InventoryCountLine:
    linea = next((l for l in conteo.lineas if l.variant_id == v.id), None)
    if linea is None:
        linea = InventoryCountLine(organization_id=conteo.organization_id, count_id=conteo.id,
                                   variant_id=v.id, qty_contada=CERO,
                                   created_by_user_id=user_id)
        conteo.lineas.append(linea)
    linea.qty_contada = Decimal(linea.qty_contada or 0) + qty
    db.commit()
    db.refresh(linea)
    return linea


def escanear(db: Session, conteo: InventoryCount, code: str, user_id: Optional[int]) -> ScanResult:
    _exigir_abierto(conteo)
    code = (code or "").strip()
    if not code:
        raise HTTPException(422, "Código vacío.")
    hits = resolver_codigo(db, conteo.organization_id, code)
    if len(hits) == 1:
        v = hits[0]
        linea = _sumar(db, conteo, v, Decimal("1"), user_id)
        return ScanResult(
            resultado="contado", linea=a_linea_read(linea), producto=resumen_producto(v),
            qty_sistema=existencias(db, conteo).get(v.id, CERO),
            fuera_de_alcance=_fuera_de_alcance(conteo, v),
        )
    if len(hits) > 1:
        return ScanResult(resultado="ambiguo", candidatos=[resumen_producto(v) for v in hits])
    linea = next((l for l in conteo.lineas if l.variant_id is None and l.codigo == code), None)
    if linea is None:
        linea = InventoryCountLine(organization_id=conteo.organization_id, count_id=conteo.id,
                                   codigo=code, qty_contada=CERO, created_by_user_id=user_id)
        conteo.lineas.append(linea)
    linea.qty_contada = Decimal(linea.qty_contada or 0) + 1
    db.commit()
    db.refresh(linea)
    return ScanResult(resultado="desconocido", linea=a_linea_read(linea))


def agregar_linea(db: Session, conteo: InventoryCount, variant_id: str, qty: Decimal,
                  user_id: Optional[int]) -> InventoryCountLine:
    _exigir_abierto(conteo)
    v = _variante_de_la_org(db, conteo.organization_id, variant_id)
    if v is None:
        raise HTTPException(404, "Producto no encontrado")
    return _sumar(db, conteo, v, Decimal(qty), user_id)


def fijar_linea(db: Session, conteo: InventoryCount, linea: InventoryCountLine,
                qty: Decimal) -> Optional[InventoryCountLine]:
    _exigir_abierto(conteo)
    if Decimal(qty) <= 0:
        conteo.lineas.remove(linea)
        db.delete(linea)
        db.commit()
        return None
    linea.qty_contada = Decimal(qty)
    db.commit()
    db.refresh(linea)
    return linea


# ── Reporte ──────────────────────────────────────────────────────────────────
def _fila(v: ProductVariant, sistema: Decimal, contado: Decimal) -> FilaReporte:
    r = resumen_producto(v)
    return FilaReporte(variant_id=v.id, sku=v.sku, nombre=r.nombre, marca=r.marca, talla=r.talla,
                       color=r.color, departamento=r.departamento, sistema=sistema,
                       contado=contado, diferencia=contado - sistema)


def _calcular(db: Session, conteo: InventoryCount) -> Reporte:
    stock = existencias(db, conteo)
    alcance = _alcance(db, conteo)
    ids_alcance = {v.id for v in alcance}
    contadas = {l.variant_id: Decimal(l.qty_contada or 0) for l in conteo.lineas if l.variant_id}

    faltantes: List[FilaReporte] = []
    sobrantes: List[FilaReporte] = []
    cuadradas = 0
    esperadas_variantes = 0
    esperadas_piezas = CERO
    for v in alcance:
        sistema = stock.get(v.id, CERO)
        contado = contadas.get(v.id, CERO)
        if sistema > 0:
            esperadas_variantes += 1
            esperadas_piezas += sistema
        if sistema > 0 and contado < sistema:
            faltantes.append(_fila(v, sistema, contado))
        elif contado > sistema:
            sobrantes.append(_fila(v, sistema, contado))
        elif sistema > 0 and contado == sistema:
            cuadradas += 1

    fuera: List[FilaReporte] = []
    for l in conteo.lineas:
        if l.variant_id and l.variant_id not in ids_alcance and l.variant is not None:
            fuera.append(_fila(l.variant, stock.get(l.variant_id, CERO), Decimal(l.qty_contada or 0)))
    desconocidos = [FilaDesconocido(codigo=l.codigo or "", contado=Decimal(l.qty_contada or 0))
                    for l in conteo.lineas if l.variant_id is None]

    por_diferencia = lambda f: -abs(f.diferencia)  # noqa: E731
    faltantes.sort(key=por_diferencia)
    sobrantes.sort(key=por_diferencia)
    fuera.sort(key=por_diferencia)

    contadas_en_alcance = [l for l in conteo.lineas if l.variant_id in ids_alcance]
    return Reporte(
        estado=conteo.status,
        generado_en=datetime.now(timezone.utc),
        alcance={
            "sucursal": conteo.branch.name if conteo.branch else None,
            "departamento": conteo.department.name if conteo.department else None,
        },
        totales={
            "esperadas_variantes": esperadas_variantes,
            "esperadas_piezas": esperadas_piezas,
            "contadas_variantes": len(contadas_en_alcance),
            "contadas_piezas": sum((Decimal(l.qty_contada or 0) for l in contadas_en_alcance), CERO),
            "cuadradas_variantes": cuadradas,
            "faltantes_piezas": sum((-f.diferencia for f in faltantes), CERO),
            "sobrantes_piezas": sum((s.diferencia for s in sobrantes), CERO),
            "fuera_de_alcance_piezas": sum((f.contado for f in fuera), CERO),
            "desconocidos": len(desconocidos),
        },
        faltantes=faltantes, sobrantes=sobrantes, fuera_de_alcance=fuera, desconocidos=desconocidos,
    )


def reporte(db: Session, conteo: InventoryCount) -> Reporte:
    """Abierto: se calcula en vivo. Cerrado: el JSON congelado, tal cual."""
    if conteo.status == CERRADO and conteo.resumen:
        return Reporte.model_validate(json.loads(conteo.resumen))
    return _calcular(db, conteo)


def cerrar(db: Session, conteo: InventoryCount, user_id: Optional[int]) -> Reporte:
    _exigir_abierto(conteo)
    rep = _calcular(db, conteo)
    stock = existencias(db, conteo)
    for l in conteo.lineas:
        l.qty_sistema = stock.get(l.variant_id, CERO) if l.variant_id else None
    conteo.status = CERRADO
    conteo.closed_at = datetime.now(timezone.utc)
    rep.estado = CERRADO
    conteo.resumen = json.dumps(rep.model_dump(mode="json"))
    db.commit()
    db.refresh(conteo)
    return rep


# ── Lecturas ─────────────────────────────────────────────────────────────────
def avance(db: Session, conteo: InventoryCount) -> Avance:
    stock = existencias(db, conteo)
    ids_alcance = {v.id for v in _alcance(db, conteo)}
    esperadas = [vid for vid in ids_alcance if stock.get(vid, CERO) > 0]
    contadas = [l for l in conteo.lineas if l.variant_id in ids_alcance]
    return Avance(
        esperadas_variantes=len(esperadas),
        esperadas_piezas=sum((stock[vid] for vid in esperadas), CERO),
        contadas_variantes=len(contadas),
        contadas_piezas=sum((Decimal(l.qty_contada or 0) for l in contadas), CERO),
        desconocidos=sum(1 for l in conteo.lineas if l.variant_id is None),
    )


def a_linea_read(linea: InventoryCountLine) -> LineaRead:
    return LineaRead(
        id=linea.id, variant_id=linea.variant_id, codigo=linea.codigo,
        qty_contada=Decimal(linea.qty_contada or 0), qty_sistema=linea.qty_sistema,
        producto=resumen_producto(linea.variant) if linea.variant is not None else None,
        updated_at=linea.updated_at,
    )


def a_conteo_read(db: Session, conteo: InventoryCount, con_lineas: bool = False):
    datos = dict(
        id=conteo.id, branch_id=conteo.branch_id,
        branch_name=conteo.branch.name if conteo.branch else None,
        department_id=conteo.department_id,
        department_name=conteo.department.name if conteo.department else None,
        status=conteo.status, notes=conteo.notes,
        created_by=conteo.created_by.username if conteo.created_by else None,
        created_at=conteo.created_at, closed_at=conteo.closed_at,
        avance=avance(db, conteo),
    )
    if con_lineas:
        return ConteoDetalle(**datos, lineas=[a_linea_read(l) for l in conteo.lineas])
    return ConteoRead(**datos)
