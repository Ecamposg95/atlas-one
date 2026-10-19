"""Atlas BOS routers/reports_valuacion — valor de la tienda (valuacion de inventario).

`GET /api/reports/valor-inventario` responde "¿cuanto vale mi existencia hoy?"
con dos cifras que SIEMPRE van juntas:

* `valor_venta` = Σ existencia × precio. Completa: toda variante tiene precio.
* `valor_costo` = Σ existencia × costo, solo de las variantes con costo > 0.
  Los catalogos importados (rmazh deja `cost` NULL; los zapatos de Eleven
  llegan con costo 0) harian que un "valor a costo" a secas se leyera como
  "mi tienda vale $0"; por eso viaja con `piezas_sin_costo` / `skus_sin_costo`.

Vive aparte de `reports.py` (1,100+ lineas, todo ventas): aqui solo se lee
`stock_on_hand`. Se monta bajo el mismo prefijo `/api/reports` (app/main.py).

Sin instantanea diaria (decision abierta 8 del mega plan 2026-10): v1 calcula
en vivo. Sin costo promedio ni PEPS: el costo es el de la variante, hoy.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Branch, Brand, Department, Product, ProductVariant, StockOnHand, User,
)
from app.models.users import PlatformRole, Role
from app.schemas.reports import (
    ValuacionGrupo, ValuacionInventarioResponse, ValuacionTotales,
)

router = APIRouter()

Agrupar = Literal["sucursal", "departamento", "marca"]

# Variante "sin costo": NULL, 0 o negativo (captura mal hecha). Sus piezas
# cuentan en `valor_venta` y en `piezas_sin_costo`, nunca en `valor_costo`.
_SIN_COSTO = or_(ProductVariant.cost.is_(None), ProductVariant.cost <= 0)
_QTY = StockOnHand.qty_on_hand
_VALOR_VENTA = func.sum(_QTY * func.coalesce(ProductVariant.price, 0))

# Los seis agregados; `_fila_a_dict` los lee por etiqueta.
_AGREGADOS = (
    func.coalesce(func.sum(_QTY), 0).label("piezas"),
    func.count(func.distinct(StockOnHand.variant_id)).label("skus"),
    func.coalesce(_VALOR_VENTA, 0).label("valor_venta"),
    func.coalesce(
        func.sum(case((_SIN_COSTO, 0), else_=_QTY * ProductVariant.cost)), 0,
    ).label("valor_costo"),
    func.coalesce(func.sum(case((_SIN_COSTO, _QTY), else_=0)), 0).label("piezas_sin_costo"),
    func.count(func.distinct(
        case((_SIN_COSTO, StockOnHand.variant_id), else_=None),
    )).label("skus_sin_costo"),
)

# Criterio de agrupacion -> (columna id, columna nombre, outerjoin extra, nombre
# para los productos sin ese dato). La sucursal ya viene unida en `_consulta`.
_GRUPOS = {
    "sucursal": (Branch.id, Branch.name, None, "Sin sucursal"),
    "departamento": (
        Department.id, Department.name,
        (Department, Department.id == Product.department_id), "Sin departamento",
    ),
    "marca": (Brand.id, Brand.name, (Brand, Brand.id == Product.brand_id), "Sin marca"),
}


def _dinero(valor) -> float:
    """Decimal/float/None de la DB -> float a 2 decimales."""
    return float(Decimal(str(valor or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ambito(current_user: User) -> tuple[bool, bool]:
    """`(ve_costo, solo_su_sucursal)` segun el rol; 403 si el rol no ve valuacion.

    Decision abierta 9 del mega plan: el valor a costo es de ADMIN/DUEÑO; el
    gerente ve piezas y valor a venta de SU sucursal. El cajero no ve nada.
    """
    if current_user.platform_role == PlatformRole.SUPERADMIN:
        return True, False
    if current_user.role in (Role.ADMINISTRADOR, Role.DUEÑO):
        return True, False
    if current_user.role == Role.GERENTE:
        return False, True
    raise HTTPException(
        status_code=403,
        detail="Solo administrador, dueño o gerente pueden ver el valor de la tienda",
    )


def _consulta(db: Session, org_id: int, branch_id: Optional[int], columnas_grupo=()):
    """Existencias positivas de la org × variante × producto × sucursal.

    Sin productos ni variantes borrados (soft delete = `deleted_at`). Una
    existencia negativa (venta sin stock) es un error de inventario, no valor
    negativo: se excluye. Si no se pide sucursal, solo cuentan las que venden
    y siguen activas (`can_sell` e `is_active`): la bodega de una org multi-sucursal no es "la tienda"; con
    `branch_id` explicito se puede mirar cualquiera.
    """
    q = (
        db.query(*columnas_grupo, *_AGREGADOS)
        .select_from(StockOnHand)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            StockOnHand.organization_id == org_id,
            Product.organization_id == org_id,
            Branch.organization_id == org_id,
            StockOnHand.qty_on_hand > 0,
            ProductVariant.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
    )
    if branch_id is not None:
        return q.filter(Branch.id == branch_id)
    return q.filter(Branch.can_sell == True, Branch.is_active.is_(True))  # noqa: E712


def _fila_a_dict(fila, ve_costo: bool) -> dict:
    return {
        "piezas": _dinero(fila.piezas),
        "skus": int(fila.skus or 0),
        "valor_venta": _dinero(fila.valor_venta),
        "valor_costo": _dinero(fila.valor_costo) if ve_costo else None,
        "piezas_sin_costo": _dinero(fila.piezas_sin_costo),
    }


@router.get("/valor-inventario", response_model=ValuacionInventarioResponse)
def valor_inventario(
    agrupar: Agrupar = "sucursal",
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Valor de la tienda: totales de la organizacion (o de una sucursal) y
    desglose por sucursal, departamento o marca."""
    ve_costo, solo_su_sucursal = _ambito(current_user)
    if solo_su_sucursal:
        if not current_user.branch_id:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene una sucursal asignada")
        # El parametro se ignora: el gerente no mira otras tiendas.
        branch_id = current_user.branch_id
    elif branch_id is not None:
        existe = db.query(Branch.id).filter(
            Branch.id == branch_id, Branch.organization_id == org_id,
        ).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    fila = _consulta(db, org_id, branch_id).one()
    totales = ValuacionTotales(
        **_fila_a_dict(fila, ve_costo), skus_sin_costo=int(fila.skus_sin_costo or 0),
    )

    col_id, col_nombre, union, sin_nombre = _GRUPOS[agrupar]
    q = _consulta(db, org_id, branch_id, (col_id, col_nombre))
    if union is not None:
        q = q.outerjoin(*union)
    filas = q.group_by(col_id, col_nombre).order_by(desc("valor_venta"), col_nombre).all()
    grupos = [
        ValuacionGrupo(
            clave="" if f[0] is None else str(f[0]),
            nombre=f[1] or sin_nombre,
            **_fila_a_dict(f, ve_costo),
        )
        for f in filas
    ]

    return ValuacionInventarioResponse(
        agrupar=agrupar, branch_id=branch_id, ve_costo=ve_costo,
        totales=totales, grupos=grupos,
    )
