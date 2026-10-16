"""Empaques (PackagingUnit) y escalones de precio (ProductPrice) de una variante."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import PackagingUnit, ProductPrice, ProductVariant
from app.modules.products.schemas import PackagingUnitCreate, ProductPriceCreate

from .validaciones import validar_escalones


def armar_empaques(
    db: Session, org_id: int, variante: ProductVariant,
    empaques: Optional[list[PackagingUnitCreate]], *, reemplazar: bool = False,
) -> dict[str, str]:
    """Crea los empaques y devuelve el mapa para enlazar escalones:
    `temp_id -> id` (el formulario manda ids temporales) y `nombre -> id`.

    `reemplazar` (edición): primero se desenlazan los escalones que apuntan a
    un empaque (FK) y luego se borran los empaques viejos. Ambos pasos filtran
    solo por `variant_id`: la variante ya se cargó acotada a la org, y los
    registros viejos pueden tener `organization_id` NULL (TenantMixin lo
    permite); filtrar por org los dejaría vivos y el borrado fallaría por FK.
    """
    if reemplazar:
        # Sesión sincronizada (default): no deja objetos viejos en memoria.
        db.query(ProductPrice).filter(
            ProductPrice.variant_id == variante.id,
        ).update({ProductPrice.linked_package_id: None})
        db.query(PackagingUnit).filter(
            PackagingUnit.variant_id == variante.id,
        ).delete()
        db.flush()
        db.expire(variante, ["packaging_units", "prices"])
    mapa: dict[str, str] = {}
    for e in (empaques or []):
        nuevo = PackagingUnit(
            variant_id=variante.id,
            name=e.name,
            barcode=e.barcode,
            units_per_package=e.units_per_package,
            package_price=e.package_price,
            weight=e.weight,
            dimensions=e.dimensions,
            organization_id=org_id,
        )
        db.add(nuevo)
        db.flush()
        if e.temp_id:
            mapa[e.temp_id] = nuevo.id
        mapa[(e.name or "").lower()] = nuevo.id
    return mapa


def armar_escalones(
    db: Session, org_id: int, variante: ProductVariant,
    escalones: Optional[list[ProductPriceCreate]], mapa_empaques: dict[str, str], *,
    reemplazar: bool = False,
) -> None:
    """Escalones de la variante. Valida ANTES de borrar/escribir: un 422 a
    medio camino dejaría al producto sin escalones."""
    validar_escalones(escalones)
    if reemplazar:
        # Solo por variante (ya acotada a la org): los escalones legados con
        # `organization_id` NULL también deben salir, o se duplicarían en cada edición.
        db.query(ProductPrice).filter(
            ProductPrice.variant_id == variante.id,
        ).delete()
        db.flush()
        db.expire(variante, ["prices"])
    for e in (escalones or []):
        enlace = e.linked_package_id
        if enlace in mapa_empaques:
            enlace = mapa_empaques[enlace]
        elif not enlace and e.price_name:
            enlace = mapa_empaques.get(e.price_name.lower())
        db.add(ProductPrice(
            variant_id=variante.id,
            price_name=e.price_name,
            min_quantity=e.min_quantity,
            unit_price=e.unit_price,
            linked_package_id=enlace or None,
            organization_id=org_id,
        ))
    db.flush()
