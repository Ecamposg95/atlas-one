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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.inventory import StockOnHand
from app.routers.inventory import aplicar_ajuste   # mismo kardex que /inventory/adjust
from app.modules.conteos.models import ABIERTO, CERRADO, InventoryCount, InventoryCountLine
from app.modules.conteos.schemas import (
    AjusteAplicado, AjusteLineaResult, Avance, ConteoDetalle, ConteoRead, FilaDesconocido, FilaLista, FilaReporte, LineaRead,
    Lista, ProductoResumen, Reporte, ScanResult,
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
        variant_id=v.id, product_id=p.id,
        nombre=variant_sale_name(marca, p.name, p.model, v.color, v.size, v.variant_name),
        marca=marca, marca_id=p.brand_id, modelo=p.model, descripcion=p.description,
        precio=v.price, talla=v.size, color=v.color, sku=v.sku, barcode=v.barcode,
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


def _sumar_linea(db: Session, conteo: InventoryCount, qty: Decimal, user_id: Optional[int],
                 variant_id: Optional[str] = None, codigo: Optional[str] = None) -> InventoryCountLine:
    """Suma `qty` a la línea de la variante (o del código desconocido), creándola si
    no existe. Sin leer-sumar-escribir en Python: la línea existente se incrementa
    con un UPDATE atómico, y si dos primeros escaneos chocan contra el índice único
    el perdedor reintenta contra la línea que ganó, sin perder la pieza."""
    def buscar() -> Optional[InventoryCountLine]:
        q = db.query(InventoryCountLine).filter(
            InventoryCountLine.organization_id == conteo.organization_id,
            InventoryCountLine.count_id == conteo.id)
        if variant_id is not None:
            q = q.filter(InventoryCountLine.variant_id == variant_id)
        else:
            q = q.filter(InventoryCountLine.variant_id.is_(None),
                         InventoryCountLine.codigo == codigo)
        return q.first()

    linea = buscar()
    if linea is None:
        nueva = InventoryCountLine(organization_id=conteo.organization_id, count_id=conteo.id,
                                   variant_id=variant_id, codigo=codigo, qty_contada=qty,
                                   created_by_user_id=user_id)
        db.add(nueva)
        try:
            db.commit()
            db.expire(conteo, ["lineas"])
            db.refresh(nueva)
            return nueva
        except IntegrityError:
            db.rollback()
            linea = buscar()
            if linea is None:
                raise
    db.query(InventoryCountLine).filter(InventoryCountLine.id == linea.id).update(
        {InventoryCountLine.qty_contada: InventoryCountLine.qty_contada + qty},
        synchronize_session=False)
    db.commit()
    db.expire(conteo, ["lineas"])
    db.refresh(linea)
    return linea


def _sumar(db: Session, conteo: InventoryCount, v: ProductVariant, qty: Decimal,
           user_id: Optional[int]) -> InventoryCountLine:
    return _sumar_linea(db, conteo, qty, user_id, variant_id=v.id)


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
    linea = _sumar_linea(db, conteo, Decimal("1"), user_id, codigo=code)
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
    if linea.count_id != conteo.id or linea.organization_id != conteo.organization_id:
        raise HTTPException(404, "Línea no encontrada")
    if Decimal(qty) <= 0:
        conteo.lineas.remove(linea)
        db.delete(linea)
        db.commit()
        return None
    linea.qty_contada = Decimal(qty)
    db.commit()
    db.refresh(linea)
    return linea


def marcar_corregida(db: Session, conteo: InventoryCount, linea: InventoryCountLine,
                     valor: bool) -> InventoryCountLine:
    _exigir_abierto(conteo)
    if linea.count_id != conteo.id or linea.organization_id != conteo.organization_id:
        raise HTTPException(404, "Línea no encontrada")
    linea.corregida = bool(valor)
    db.commit()
    db.refresh(linea)
    return linea


def lista(db: Session, conteo: InventoryCount) -> Lista:
    """Todo el catálogo del departamento (también existencia 0) con su estado:
    pendiente (nada contado), revisado (contado == sistema), diferencia."""
    stock = existencias(db, conteo)
    lineas = {l.variant_id: l for l in conteo.lineas if l.variant_id}
    filas: List[FilaLista] = []
    orden = lambda x: ((x.product.name or "").lower(), x.size or "", x.color or "")  # noqa: E731
    for v in sorted(_alcance(db, conteo), key=orden):
        sistema = stock.get(v.id, CERO)
        l = lineas.get(v.id)
        contado = Decimal(l.qty_contada or 0) if l else CERO
        if l is None:
            estado = "pendiente"
        elif contado == sistema:
            estado = "revisado"
        else:
            estado = "diferencia"
        filas.append(FilaLista(producto=resumen_producto(v), sistema=sistema, contado=contado,
                               estado=estado, corregida=bool(l.corregida) if l else False,
                               ajustada=bool(l.ajustada_at) if l else False,
                               line_id=l.id if l else None))
    return Lista(filas=filas, totales={
        "total": len(filas),
        "revisados": sum(1 for f in filas if f.estado == "revisado"),
        "pendientes": sum(1 for f in filas if f.estado == "pendiente"),
        "con_diferencia": sum(1 for f in filas if f.estado == "diferencia"),
        "corregidas": sum(1 for f in filas if f.corregida),
    })


# ── Ajustes al kardex ────────────────────────────────────────────────────────
def _nota(conteo: InventoryCount) -> str:
    depto = conteo.department.name if conteo.department else "toda la tienda"
    return f"Conteo #{conteo.id} · {depto}"


def ajustar_linea(db: Session, conteo: InventoryCount, linea: InventoryCountLine,
                  user_id: Optional[int]) -> AjusteLineaResult:
    """Ajuste en piso: deja la existencia igual a lo contado en esta línea."""
    _exigir_abierto(conteo)
    if linea.count_id != conteo.id or linea.organization_id != conteo.organization_id or not linea.variant_id:
        raise HTTPException(404, "Línea no encontrada")
    actual = existencias(db, conteo).get(linea.variant_id, CERO)
    delta = Decimal(linea.qty_contada or 0) - actual
    if delta == 0:
        raise HTTPException(409, "La existencia ya cuadra con lo contado.")
    mov = aplicar_ajuste(db, org_id=conteo.organization_id, branch_id=conteo.branch_id,
                         variant_id=linea.variant_id, user_id=user_id, quantity=delta,
                         reason="Conteo", notes=_nota(conteo) + " · ajuste en piso")
    linea.ajustada_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(linea)
    return AjusteLineaResult(linea=a_linea_read(linea), qty_sistema=Decimal(mov.qty_after),
                             movimiento_id=mov.id)


def aplicar(db: Session, conteo: InventoryCount, variant_ids: List[str],
            user_id: Optional[int]) -> Reporte:
    """Aplica al kardex la DIFERENCIA congelada de las filas elegidas del reporte
    cerrado. Una venta posterior al cierre no se descuenta dos veces porque se
    aplica el delta, no el valor contado. Si la salida dejaría negativo, se
    recorta a 0 y se anota. Filas ya aplicadas se omiten (idempotente)."""
    if conteo.status != CERRADO or not conteo.resumen:
        raise HTTPException(409, "Primero cierra el conteo.")
    if not variant_ids:
        raise HTTPException(422, "Elige al menos una talla.")
    rep = Reporte.model_validate(json.loads(conteo.resumen))
    ya = {a.variant_id for a in rep.ajustes}
    filas = {f.variant_id: f for f in rep.faltantes + rep.sobrantes + rep.fuera_de_alcance}
    stock = existencias(db, conteo)
    ahora = datetime.now(timezone.utc)
    for vid in variant_ids:
        f = filas.get(vid)
        if f is None or vid in ya:
            continue
        delta = Decimal(f.diferencia)
        actual = stock.get(vid, CERO)
        recortado = False
        if actual + delta < 0:
            delta, recortado = -actual, True
        mov_id = None
        if delta != 0:
            mov = aplicar_ajuste(db, org_id=conteo.organization_id, branch_id=conteo.branch_id,
                                 variant_id=vid, user_id=user_id, quantity=delta, reason="Conteo",
                                 notes=_nota(conteo) + (" · recortado a 0" if recortado else ""))
            mov_id = mov.id
        rep.ajustes.append(AjusteAplicado(variant_id=vid, delta=delta, qty_before=actual,
                                          qty_after=actual + delta, movimiento_id=mov_id,
                                          recortado=recortado, en=ahora))
        ya.add(vid)
        linea = next((l for l in conteo.lineas if l.variant_id == vid), None)
        if linea is not None:
            linea.ajustada_at = ahora
    rep = _marcar_ajustadas(rep)
    rep.aplicado_en = rep.aplicado_en or ahora
    if conteo.aplicado_at is None:
        conteo.aplicado_at = ahora
        conteo.aplicado_por_user_id = user_id
    conteo.resumen = json.dumps(rep.model_dump(mode="json"))
    db.commit()
    return rep


def _marcar_ajustadas(rep: Reporte) -> Reporte:
    ya = {a.variant_id for a in rep.ajustes}
    for seccion in (rep.faltantes, rep.sobrantes, rep.fuera_de_alcance):
        for f in seccion:
            f.ajustada = f.variant_id in ya
    rep.totales["ajustadas"] = len(rep.ajustes)
    rep.totales["piezas_ajustadas"] = sum((abs(Decimal(a.delta)) for a in rep.ajustes), CERO)
    return rep


# ── Reporte ──────────────────────────────────────────────────────────────────
def _fila(v: ProductVariant, sistema: Decimal, contado: Decimal, corregida: bool = False,
          ajustada: bool = False) -> FilaReporte:
    r = resumen_producto(v)
    return FilaReporte(variant_id=v.id, sku=v.sku, nombre=r.nombre, marca=r.marca, talla=r.talla,
                       color=r.color, departamento=r.departamento, sistema=sistema,
                       contado=contado, diferencia=contado - sistema, corregida=corregida,
                       ajustada=ajustada)


def _calcular(db: Session, conteo: InventoryCount) -> Reporte:
    stock = existencias(db, conteo)
    alcance = _alcance(db, conteo)
    ids_alcance = {v.id for v in alcance}
    contadas = {l.variant_id: Decimal(l.qty_contada or 0) for l in conteo.lineas if l.variant_id}

    corregidas = {l.variant_id: bool(l.corregida) for l in conteo.lineas if l.variant_id}
    ajustadas = {l.variant_id: bool(l.ajustada_at) for l in conteo.lineas if l.variant_id}
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
            faltantes.append(_fila(v, sistema, contado, corregidas.get(v.id, False), ajustadas.get(v.id, False)))
        elif contado > sistema:
            sobrantes.append(_fila(v, sistema, contado, corregidas.get(v.id, False), ajustadas.get(v.id, False)))
        elif sistema > 0 and contado == sistema:
            cuadradas += 1

    fuera: List[FilaReporte] = []
    for l in conteo.lineas:
        if l.variant_id and l.variant_id not in ids_alcance and l.variant is not None:
            fuera.append(_fila(l.variant, stock.get(l.variant_id, CERO), Decimal(l.qty_contada or 0),
                              bool(l.corregida), bool(l.ajustada_at)))
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
            "corregidas": sum(1 for l in conteo.lineas if l.corregida),
            "ajustadas": sum(1 for l in conteo.lineas if l.ajustada_at),
            "piezas_ajustadas": CERO,
        },
        faltantes=faltantes, sobrantes=sobrantes, fuera_de_alcance=fuera, desconocidos=desconocidos,
    )


def reporte(db: Session, conteo: InventoryCount) -> Reporte:
    """Abierto: se calcula en vivo. Cerrado: el JSON congelado, tal cual."""
    if conteo.status == CERRADO and conteo.resumen:
        # Los congelados antes de la fase 2 no traen `ajustes`: lista vacía.
        return _marcar_ajustadas(Reporte.model_validate(json.loads(conteo.resumen)))
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
        corregida=bool(linea.corregida), ajustada=bool(linea.ajustada_at),
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
        created_at=conteo.created_at, closed_at=conteo.closed_at, aplicado_at=conteo.aplicado_at,
        aplicado_por=conteo.aplicado_por.username if conteo.aplicado_por else None,
        avance=avance(db, conteo),
    )
    if con_lineas:
        return ConteoDetalle(**datos, lineas=[a_linea_read(l) for l in conteo.lineas])
    return ConteoRead(**datos)
