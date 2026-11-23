"""Precio por sucursal (2026-11-23).

Con `organization.precio_por_sucursal` encendido, cada sucursal tiene su propio
precio: lo que edita alguien con sucursal asignada (ficha del producto o una
talla) se guarda en el `price_override` de SU sucursal y el precio base —el que
cobran las sucursales sin precio propio— no cambia. La ficha le muestra a cada
quien ese mismo precio (`_compute_product_read`), así que edita lo que ve.

Apagado (lo normal), todo sigue como antes: el precio editado es el base.

Una talla solo recibe precio de sucursal si está dada de alta en esa sucursal
(tiene fila `ProductBranchStatus`); crear la fila la habilitaría en el POS.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Organization, ProductBranchStatus, ProductVariant, User


def precio_por_sucursal_activo(db: Session, org_id: Optional[int]) -> bool:
    if not org_id:
        return False
    # `db.get` sale del identity map si la org ya se cargó en la petición
    # (`get_current_active_organization`): sin query extra por producto.
    org = db.get(Organization, org_id)
    return bool(getattr(org, "precio_por_sucursal", False))


def _estado_en_sucursal(db: Session, org_id: int, variant_id: str, branch_id: int) -> Optional[ProductBranchStatus]:
    return db.query(ProductBranchStatus).filter(
        ProductBranchStatus.variant_id == variant_id,
        ProductBranchStatus.branch_id == branch_id,
        ProductBranchStatus.organization_id == org_id,
    ).first()


def sucursal_del_precio(db: Session, org_id: int, user: User, variante: Optional[ProductVariant]) -> Optional[int]:
    """Sucursal cuyo precio edita `user`, o None si edita el precio base.

    None cuando la org no usa precio por sucursal, cuando el usuario no tiene
    sucursal o cuando la talla no está dada de alta en su sucursal (no es un
    producto que venda: su precio ahí no existe)."""
    if variante is None or not user.branch_id or not precio_por_sucursal_activo(db, org_id):
        return None
    if _estado_en_sucursal(db, org_id, variante.id, user.branch_id) is None:
        return None
    return user.branch_id


def fijar_precio_de_sucursal(db: Session, org_id: int, branch_id: int,
                             variantes: Iterable[ProductVariant], precio: Decimal) -> int:
    """Pone `precio` como precio de la sucursal en cada talla dada de alta ahí.
    Las que no tienen fila en la sucursal se saltan. Devuelve cuántas cambió."""
    cambiadas = 0
    for v in variantes:
        estado = _estado_en_sucursal(db, org_id, v.id, branch_id)
        if estado is None:
            continue
        estado.price_override = precio
        cambiadas += 1
    return cambiadas
