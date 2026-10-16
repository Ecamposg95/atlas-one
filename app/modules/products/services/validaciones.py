"""Validaciones de negocio del alta/edición de productos (422).

Cada función levanta `HTTPException` con el MISMO texto que usaban los
handlers, para que la pantalla y los cuatro clientes vivos no vean mensajes
nuevos. Nada de aquí escribe en la base.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Brand, Department
from app.models.organization import Branch
from app.modules.products.schemas import ProductCreate, ProductPriceCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr


def exigir_campos_de_cajero(datos: ProductCreate) -> None:
    """CAJERO/GERENTE deben mandar name, sku, price y cost (marca y
    departamento NO: una tienda recién dada de alta no los tiene)."""
    requeridos = {"name": datos.name, "sku": datos.sku, "price": datos.price, "cost": datos.cost}
    faltan = [
        k for k, v in requeridos.items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail=f"Campos requeridos para CAJERO/GERENTE: {', '.join(faltan)}",
        )


def validar_precio(
    precio: Optional[Decimal],
    detalle: str = "El precio del producto debe ser mayor a cero.",
) -> None:
    """ATS-25: un producto a $0 es invendible (o regalado). None = no se valida
    (la edición manda None cuando no toca el precio)."""
    if precio is not None and precio <= 0:
        raise HTTPException(status_code=422, detail=detalle)


def validar_escalones(escalones: Optional[Iterable[ProductPriceCreate]]) -> None:
    """Un escalón en $0 también regala el producto: el POS elige el escalón
    más barato aplicable. Nombra el escalón culpable."""
    for e in (escalones or []):
        if e.unit_price is not None and e.unit_price <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"El precio del escalón '{e.price_name}' debe ser mayor a cero.",
            )


def validar_sucursales_de_la_org(db: Session, org_id: int, branch_ids: Iterable[int]) -> set[int]:
    """Guard cross-tenant: toda sucursal destino debe ser de esta org. Sin
    esto, `target_branch_ids` podría inyectar StockOnHand/PBS en otra tienda."""
    pedidas = set(branch_ids or [])
    if not pedidas:
        return set()
    propias = {
        b.id for b in db.query(Branch.id).filter(
            Branch.id.in_(pedidas), Branch.organization_id == org_id,
        ).all()
    }
    if propias != pedidas:
        raise HTTPException(
            status_code=422,
            detail="Una o más sucursales objetivo no pertenecen a tu organización.",
        )
    return propias


def validar_departamento_y_marca(
    db: Session, org_id: int, department_id: Optional[str], brand_id: Optional[str],
) -> None:
    if department_id and db.query(Department.id).filter(
        Department.id == department_id, Department.organization_id == org_id,
    ).first() is None:
        raise HTTPException(status_code=422, detail="Departamento no encontrado en tu organización.")
    if brand_id and db.query(Brand.id).filter(
        Brand.id == brand_id, Brand.organization_id == org_id,
    ).first() is None:
        raise HTTPException(status_code=422, detail="Marca no encontrada en tu organización.")


def atributos_principal(color: Optional[str], size: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Limpia color/talla de la variante principal o 422 nombrando el campo.

    `clean_attr` levanta ValueError cuando el texto excede el límite; sin este
    envoltorio Postgres truncaría (o reventaría) y el formulario no sabría cuál
    de los dos campos corregir.
    """
    salida = []
    for valor, tope, campo in ((color, COLOR_MAX, "color"), (size, SIZE_MAX, "talla")):
        try:
            salida.append(clean_attr(valor, tope))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"{campo}: {e}")
    return salida[0], salida[1]
