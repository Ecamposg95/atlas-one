"""``/api/products/barcodes/*`` y ``/api/products/export/labels.csv``.

Tres endpoints alrededor del código de barras por talla:
  * cuántas variantes visibles siguen sin código,
  * generárselos al catálogo que ya existe (admin/dueño),
  * exportar el CSV que come la etiquetadora (ZebraDesigner y compañía).

La generación vive en `app/services/barcodes.py`; aquí solo está el contrato
HTTP, el alcance por usuario y el formato del archivo.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security.guards import require_admin_or_owner
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin, query_visible_products
from app.models import Product, ProductVariant, StockOnHand, User
from app.modules.products.sale_name import variant_sale_name
from app.services.barcodes import asignar_codigos_faltantes, contar_codigos_faltantes

router = APIRouter()

# Las cuatro columnas de la ficha boutique van AL FINAL: los diseños de
# etiqueta que ya existen mapean por posicion, y meterlas en medio les correria
# el precio y la existencia de lugar.
ENCABEZADOS_ETIQUETAS = [
    "SKU", "Codigo de barras", "Producto", "Marca", "Talla", "Color",
    "Precio", "Existencia", "Genero", "Modelo", "Material", "Nombre de venta",
]


class AsignarCodigosRequest(BaseModel):
    product_id: Optional[str] = None


def _ids_visibles(db: Session, current_user: User, org_id: int):
    """`SELECT` de los productos que este usuario puede ver.

    Se devuelve la subconsulta y no la lista de ids: materializarla convierte
    el filtro en un `IN (…)` con el catálogo entero (miles de UUID viajando en
    la sentencia) cuando el usuario es admin y ve todo.
    """
    q = query_visible_products(db, current_user, org_id, include_inactive=True)
    return q.with_entities(Product.id).scalar_subquery()


def _fmt_cantidad(qty) -> str:
    """Existencia legible en la etiqueta: sin decimales si es entera."""
    d = Decimal(str(qty or 0))
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


@router.get("/barcodes/missing-count")
def contar_faltantes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Cuántas variantes vivas y visibles para el usuario no tienen código."""
    return {"missing": contar_codigos_faltantes(db, org_id, _ids_visibles(db, current_user, org_id))}


@router.post("/barcodes/assign-missing")
def asignar_faltantes(
    body: Optional[AsignarCodigosRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization),
):
    """Genera el código interno de las variantes que no tienen.

    Toca todo el catálogo de la organización (o un solo producto), así que es
    ADMINISTRADOR/DUEÑO. Nunca sobrescribe un código existente.
    """
    product_id = body.product_id if body else None
    if product_id:
        existe = (
            db.query(Product.id)
            .filter(Product.id == product_id, Product.organization_id == org_id)
            .first()
        )
        if not existe:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

    asignadas = asignar_codigos_faltantes(db, org_id, product_id)
    db.commit()
    return {"assigned": asignadas}


@router.get("/export/labels.csv")
def exportar_etiquetas_csv(
    product_id: Optional[str] = None,
    only_with_stock: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """CSV de etiquetas: una fila por variante viva.

    Mismo alcance que el export de Excel (`query_visible_products`): un
    CAJERO/GERENTE solo baja lo de su sucursal. UTF-8 con BOM y separador
    coma — es lo que abren Excel y los diseñadores de etiquetas sin pelear
    con el encoding.
    """
    q = (
        query_visible_products(db, current_user, org_id)
        .options(joinedload(Product.variants), joinedload(Product.brand))
        .filter(Product.deleted_at == None)  # noqa: E711
    )
    if product_id:
        q = q.filter(Product.id == product_id)
    productos = q.order_by(Product.name).all()

    variantes = [
        (p, v) for p in productos for v in p.variants if v.deleted_at is None
    ]

    # Existencia: la de SU sucursal para los usuarios de tienda. Un admin no
    # tiene tienda propia (su branch_id es el HQ, que nunca guarda mercancía),
    # así que para él se suma la organización entera — si no, todas las
    # etiquetas saldrían con existencia 0.
    stock: dict[str, Decimal] = {}
    ids = [v.id for _, v in variantes]
    if ids:
        sq = (
            db.query(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand))
            .filter(
                StockOnHand.variant_id.in_(ids),
                StockOnHand.organization_id == org_id,
            )
        )
        if not _is_admin(current_user) and current_user.branch_id:
            sq = sq.filter(StockOnHand.branch_id == current_user.branch_id)
        for vid, total in sq.group_by(StockOnHand.variant_id).all():
            stock[vid] = Decimal(str(total or 0))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ENCABEZADOS_ETIQUETAS)
    for p, v in variantes:
        existencia = stock.get(v.id, Decimal(0))
        if only_with_stock and existencia <= 0:
            continue
        writer.writerow([
            v.sku or "",
            v.barcode or "",
            p.name or "",
            p.brand.name if p.brand else "",
            v.size or "",
            v.color or "",
            f"{Decimal(str(v.price or 0)):.2f}",
            _fmt_cantidad(existencia),
            p.gender or "",
            p.model or "",
            p.material or "",
            variant_sale_name(
                p.brand.name if p.brand else None, p.name or "", p.model, v.color, v.size
            ),
        ])

    # BOM: sin él Excel abre "Camisón" como "CamisÃ³n" y la etiqueta sale mal.
    contenido = ("﻿" + buffer.getvalue()).encode("utf-8")
    nombre = f"etiquetas_{date.today().isoformat()}.csv"
    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
