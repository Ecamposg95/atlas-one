"""Precio por sucursal (2026-11-23).

Con `organization.precio_por_sucursal` encendido, cada sucursal tiene su propio
precio: lo que edita alguien de una sucursal (CAJERO, GERENTE…) en la ficha del
producto o en una talla se guarda en el `price_override` de SU sucursal y el
precio base —el que cobran las sucursales sin precio propio— no cambia. La
ficha le muestra ese mismo precio (`_compute_product_read`): edita lo que ve.

ADMINISTRADOR y DUEÑO mandan en toda la organización aunque tengan una sucursal
asignada: su ficha muestra y edita el precio BASE (el de todas las sucursales
sin precio propio) y el de cada sucursal lo fijan en la matriz de sucursales
de la ficha ("Precio override").

Apagado (lo normal), todo sigue como antes: el precio editado es el base.

Una talla solo recibe precio de sucursal si está dada de alta en esa sucursal
(tiene fila `ProductBranchStatus`); crear la fila la habilitaría en el POS.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Organization, ProductBranchStatus, ProductVariant, User

# Editan el precio base aunque tengan sucursal (mismo criterio que `_is_admin`).
ROLES_DE_ORGANIZACION = frozenset({"ADMINISTRADOR", "DUEÑO"})


def edita_precio_base(user: User) -> bool:
    return getattr(user, "role", None) in ROLES_DE_ORGANIZACION


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

    None cuando la org no usa precio por sucursal, cuando quien edita es
    ADMINISTRADOR/DUEÑO o no tiene sucursal, o cuando la talla no está dada de
    alta en su sucursal (no es un producto que venda: su precio ahí no existe)."""
    if variante is None or not user.branch_id or edita_precio_base(user):
        return None
    if not precio_por_sucursal_activo(db, org_id):
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
