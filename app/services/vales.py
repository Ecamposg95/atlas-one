"""Vale de tienda: emitirlo al devolver, cobrarlo en el POS y restituirlo si la
venta que lo usó se cancela (2026-11-24).

En el cobro el vale viaja como un pago `OTHER` con `reference = "VALE:<código>"`
(no hay método de pago nuevo: `paymentmethod` es un enum de Postgres y el corte
ya lo agrupa en «otros»). `aplicar_vales_en_venta` corre dentro de la misma
transacción de `create_sale`; si no hay pagos con vale no hace nada."""
import secrets
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.vales import (
    MOV_CANCELACION, MOV_EMISION, MOV_RESTITUCION, MOV_USO,
    VALE_ACTIVO, VALE_AGOTADO, VALE_CANCELADO,
    StoreVoucher, StoreVoucherMovement,
)

PREFIJO = "VALE:"
# Sin 0/O ni 1/I/L: el código se dicta y se teclea en el mostrador.
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CENT = Decimal("0.01")


def normalizar_codigo(texto: Optional[str]) -> str:
    codigo = (texto or "").strip().upper()
    if codigo.startswith(PREFIJO):
        codigo = codigo[len(PREFIJO):]
    return codigo.replace("-", "").replace(" ", "")


def codigo_de_referencia(reference: Optional[str]) -> Optional[str]:
    """Código del vale si la referencia de un pago es `VALE:<código>`."""
    ref = (reference or "").strip().upper()
    if not ref.startswith(PREFIJO):
        return None
    return normalizar_codigo(ref) or None


def _codigo_nuevo(db: Session, org_id: int) -> str:
    for _ in range(20):
        codigo = "".join(secrets.choice(_ALFABETO) for _ in range(8))
        existe = db.query(StoreVoucher.id).filter(
            StoreVoucher.organization_id == org_id, StoreVoucher.code == codigo,
        ).first()
        if not existe:
            return codigo
    raise HTTPException(status_code=500, detail="No se pudo generar el código del vale. Intenta de nuevo.")


def emitir_vale(db: Session, *, org_id: int, amount: Decimal, branch_id: Optional[int] = None,
                customer_id: Optional[int] = None, customer_name: Optional[str] = None,
                return_id: Optional[str] = None, user_id: Optional[int] = None) -> StoreVoucher:
    """Crea el vale y su movimiento de emisión. No hace commit."""
    monto = Decimal(str(amount)).quantize(_CENT)
    if monto <= 0:
        raise ValueError("El vale debe ser por un monto mayor a cero.")
    vale = StoreVoucher(
        organization_id=org_id, code=_codigo_nuevo(db, org_id), branch_id=branch_id,
        customer_id=customer_id, customer_name=customer_name,
        initial_amount=monto, balance=monto, status=VALE_ACTIVO,
        return_id=return_id, created_by_user_id=user_id,
    )
    db.add(vale)
    db.flush()
    db.add(StoreVoucherMovement(
        organization_id=org_id, voucher_id=vale.id, kind=MOV_EMISION, amount=monto, user_id=user_id,
    ))
    return vale


def buscar_vale(db: Session, org_id: int, codigo: str, *, candado: bool = False) -> Optional[StoreVoucher]:
    q = db.query(StoreVoucher).filter(
        StoreVoucher.organization_id == org_id,
        StoreVoucher.code == normalizar_codigo(codigo),
    )
    if candado:
        q = q.populate_existing().with_for_update()
    return q.first()


def aplicar_vales_en_venta(db: Session, *, org_id: int, sales_document_id: str,
                           payments: Iterable, user_id: Optional[int]) -> None:
    """Descuenta del saldo de cada vale lo que la venta paga con él. Lanza 400
    si el vale no existe, está cancelado o no le alcanza. No hace commit."""
    por_codigo: dict[str, Decimal] = {}
    for p in payments or []:
        codigo = codigo_de_referencia(getattr(p, "reference", None))
        monto = Decimal(str(getattr(p, "amount", 0) or 0))
        if codigo and monto > 0:
            por_codigo[codigo] = por_codigo.get(codigo, Decimal("0")) + monto
    # Orden fijo: dos cobros con los mismos vales toman los candados igual.
    for codigo in sorted(por_codigo):
        monto = por_codigo[codigo].quantize(_CENT)
        vale = buscar_vale(db, org_id, codigo, candado=True)
        if vale is None:
            raise HTTPException(status_code=400, detail=f"El vale {codigo} no existe.")
        if vale.status == VALE_CANCELADO:
            raise HTTPException(status_code=400, detail=f"El vale {codigo} está cancelado.")
        saldo = Decimal(str(vale.balance or 0))
        if monto > saldo:
            raise HTTPException(
                status_code=400,
                detail=f"Al vale {codigo} le quedan ${saldo:.2f}; no alcanza para ${monto:.2f}.",
            )
        vale.balance = saldo - monto
        vale.status = VALE_AGOTADO if vale.balance <= 0 else VALE_ACTIVO
        db.add(StoreVoucherMovement(
            organization_id=org_id, voucher_id=vale.id, kind=MOV_USO, amount=monto,
            sales_document_id=sales_document_id, user_id=user_id,
        ))


def restituir_vales_de_venta(db: Session, *, org_id: int, sales_document_id: str,
                             user_id: Optional[int]) -> Decimal:
    """Al cancelar una venta: regresa a cada vale lo que esa venta le había
    usado. Idempotente (no restituye dos veces). No hace commit."""
    movs = db.query(StoreVoucherMovement).filter(
        StoreVoucherMovement.organization_id == org_id,
        StoreVoucherMovement.sales_document_id == sales_document_id,
    ).all()
    usado: dict[str, Decimal] = {}
    for m in movs:
        signo = 1 if m.kind == MOV_USO else -1 if m.kind == MOV_RESTITUCION else 0
        usado[m.voucher_id] = usado.get(m.voucher_id, Decimal("0")) + signo * Decimal(str(m.amount))
    total = Decimal("0")
    for voucher_id in sorted(usado):
        pendiente = usado[voucher_id]
        if pendiente <= 0:
            continue
        vale = db.query(StoreVoucher).filter(
            StoreVoucher.id == voucher_id, StoreVoucher.organization_id == org_id,
        ).populate_existing().with_for_update().first()
        if vale is None:
            continue
        vale.balance = Decimal(str(vale.balance or 0)) + pendiente
        if vale.status == VALE_AGOTADO:
            vale.status = VALE_ACTIVO
        db.add(StoreVoucherMovement(
            organization_id=org_id, voucher_id=vale.id, kind=MOV_RESTITUCION, amount=pendiente,
            sales_document_id=sales_document_id, user_id=user_id,
        ))
        total += pendiente
    return total


def cancelar_vale(db: Session, vale: StoreVoucher, user_id: Optional[int]) -> StoreVoucher:
    """Anula el saldo que le quede al vale. No hace commit."""
    if vale.status == VALE_CANCELADO:
        return vale
    saldo = Decimal(str(vale.balance or 0))
    if saldo > 0:
        db.add(StoreVoucherMovement(
            organization_id=vale.organization_id, voucher_id=vale.id, kind=MOV_CANCELACION,
            amount=saldo, user_id=user_id,
        ))
    vale.balance = Decimal("0")
    vale.status = VALE_CANCELADO
    return vale


def a_dict(vale: StoreVoucher) -> dict:
    return {
        "id": vale.id,
        "code": vale.code,
        "status": vale.status,
        "initial_amount": Decimal(str(vale.initial_amount or 0)),
        "balance": Decimal(str(vale.balance or 0)),
        "customer_id": vale.customer_id,
        "customer_name": vale.customer_name,
        "branch_id": vale.branch_id,
        "return_id": vale.return_id,
        "created_at": vale.created_at,
    }
