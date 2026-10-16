"""Estado comercial por sucursal (ProductBranchStatus) y existencias.

Antes estaba copiado a mano en `create_product`, `update_product`,
`duplicate_product`, `crear_variantes` y `upload_products`, cada uno con
pequeñas diferencias. Aquí hay una sola versión de cada operación; las
diferencias legítimas (texto del kardex, `is_active_hq`) son parámetros.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import (
    InventoryMovement, MovementType, ProductBranchStatus, ProductVariant, StockOnHand,
)
from app.models.organization import Branch


def sucursales_que_venden(db: Session, org_id: int) -> list[int]:
    """Sucursales activas con `can_sell=True`, por id (orden determinista)."""
    return [
        b.id for b in db.query(Branch.id).filter(
            Branch.organization_id == org_id,
            Branch.is_active == True,   # noqa: E712
            Branch.can_sell == True,    # noqa: E712
        ).order_by(Branch.id).all()
    ]


def resolver_sucursales_destino(
    db: Session, org_id: int, user, target_branch_ids: Optional[Iterable[int]],
) -> list[int]:
    """Dónde queda habilitado un producto nuevo.

    Las sucursales objetivo que mandó el formulario más la del usuario (un
    cajero/gerente siempre lleva la suya). Un usuario sin sucursal que no manda
    destinos (HQ puro) habilita el producto en TODAS las que venden (mega plan
    2026-10, §6.4); si la org no tiene ninguna que venda, queda sin PBS y el
    OUTER JOIN de ATS-11 lo muestra en todas, como antes.
    """
    destino = set(target_branch_ids or [])
    if user.branch_id:
        destino.add(user.branch_id)
    if not destino:
        destino = set(sucursales_que_venden(db, org_id))
    return sorted(destino)


def sucursal_de_existencia_inicial(user, branch_id: Optional[int], destinos: list[int]) -> Optional[int]:
    """Una sola sucursal recibe la existencia inicial: la que eligió el
    formulario, si no la del usuario, si no la primera destino."""
    if branch_id and branch_id in destinos:
        return branch_id
    if user.branch_id and user.branch_id in destinos:
        return user.branch_id
    return destinos[0] if destinos else None


def armar_estado_por_sucursal(
    db: Session, org_id: int, variante: ProductVariant, branch_ids: Iterable[int], *,
    is_active_hq: bool = False, reemplazar: bool = False,
) -> None:
    """Habilita la variante en `branch_ids` (POS sí, visible sí).

    Idempotente: a un PBS que ya existe solo le pone `is_visible=True` (es lo
    que hacía el upload). `reemplazar=True` (edición con `target_branch_ids`)
    borra primero todos los PBS de la variante. Hace `flush` para que
    `crear_variantes` —que lee el PBS de la principal— lo vea.
    """
    if reemplazar:
        db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variante.id,
            ProductBranchStatus.organization_id == org_id,
        ).delete()  # sincroniza la sesión, como el handler de edición
        # La colección ya cargada (backref de ProductVariant) quedaría vieja.
        db.expire(variante, ["branch_statuses"])
        existentes: dict[int, ProductBranchStatus] = {}
    else:
        existentes = {
            pbs.branch_id: pbs for pbs in db.query(ProductBranchStatus).filter(
                ProductBranchStatus.variant_id == variante.id,
                ProductBranchStatus.organization_id == org_id,
            ).all()
        }
    for bid in branch_ids:
        pbs = existentes.get(bid)
        if pbs is None:
            db.add(ProductBranchStatus(
                variant_id=variante.id,
                branch_id=bid,
                is_active_pos=True,
                is_active_hq=is_active_hq,
                is_visible=True,
                organization_id=org_id,
            ))
        else:
            pbs.is_visible = True
    db.flush()


def copiar_estado_por_sucursal(db: Session, org_id: int, origen: ProductVariant, destino: ProductVariant) -> None:
    """La copia hereda la misma configuración multi-sucursal (sin StockOnHand).

    Es para DUPLICAR un producto: copia también las políticas por sucursal
    (`price_override`, `min_stock_alert`, `max_stock_limit`). Las variantes
    hermanas NO deben usarla: ellas copian solo `is_active_pos`, `is_active_hq`
    e `is_visible`.
    """
    for src in db.query(ProductBranchStatus).filter(
        ProductBranchStatus.variant_id == origen.id,
        ProductBranchStatus.organization_id == org_id,
    ).all():
        db.add(ProductBranchStatus(
            organization_id=org_id,
            variant_id=destino.id,
            branch_id=src.branch_id,
            is_active_pos=src.is_active_pos,
            is_active_hq=src.is_active_hq,
            is_visible=src.is_visible,
            price_override=src.price_override,
            min_stock_alert=src.min_stock_alert,
            max_stock_limit=src.max_stock_limit,
        ))
    db.flush()


def registrar_stock_inicial(
    db: Session, org_id: int, variante: ProductVariant, branch_ids: Iterable[int],
    destino: Optional[int], qty: Decimal, user_id: Optional[int], *,
    referencia: str = "Alta Inicial", notas: str = "Creación de producto",
) -> None:
    """Un StockOnHand por sucursal habilitada; la existencia inicial cae en
    `destino` y las demás nacen en 0. Kardex de apertura solo si hay piezas:
    sin movimiento, el inventario arranca con una existencia que no aparece
    en ningún reporte."""
    for bid in branch_ids:
        cantidad = qty if bid == destino else Decimal(0)
        db.add(StockOnHand(
            branch_id=bid, variant_id=variante.id, qty_on_hand=cantidad,
            is_active=True, organization_id=org_id,
        ))
        if cantidad > 0:
            db.add(InventoryMovement(
                branch_id=bid, variant_id=variante.id, user_id=user_id,
                movement_type=MovementType.ADJUSTMENT_IN,
                qty_change=cantidad, qty_before=Decimal(0), qty_after=cantidad,
                reference=referencia, notes=notas, organization_id=org_id,
            ))
    db.flush()


def fijar_existencia(
    db: Session, org_id: int, variante: ProductVariant, branch_id: int,
    objetivo: Decimal, user_id: Optional[int], *,
    referencia: str = "Excel Upload", notas: str,
) -> None:
    """Existencia ABSOLUTA (el "Stock" del archivo es lo que hay, no lo que
    entra): ajusta por diferencia y deja kardex solo si cambió algo."""
    registro = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variante.id,
        StockOnHand.branch_id == branch_id,
        StockOnHand.organization_id == org_id,
    ).first()
    if registro is None:
        registro = StockOnHand(
            branch_id=branch_id, variant_id=variante.id, qty_on_hand=Decimal(0),
            is_active=True, organization_id=org_id,
        )
        db.add(registro)
        db.flush()
    anterior = Decimal(registro.qty_on_hand or 0)
    diferencia = objetivo - anterior
    if diferencia == 0:
        return
    registro.qty_on_hand = objetivo
    db.add(InventoryMovement(
        branch_id=branch_id, variant_id=variante.id, user_id=user_id,
        movement_type=MovementType.ADJUSTMENT_IN if diferencia > 0 else MovementType.ADJUSTMENT_OUT,
        qty_change=abs(diferencia), qty_before=anterior, qty_after=objetivo,
        reference=referencia, notes=notas, organization_id=org_id,
    ))
    db.flush()
