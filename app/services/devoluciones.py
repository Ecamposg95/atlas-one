"""Reglas de la devolución en caja (2026-11-24): motivos de catálogo, qué
piezas de un ticket quedan por devolver, por qué método se regresa el dinero y
cuándo la caja puede devolver sin gerente.

El motor (crear / aprobar, inventario, caja, impuestos) sigue en
`app/crud/returns.py`; aquí solo vive lo que decide el mostrador."""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sales import PaymentMethod, SalesDocument, SalesLineItem

# code -> (texto que se imprime, ¿por omisión la pieza regresa a stock?)
MOTIVOS: dict[str, tuple[str, bool]] = {
    "DEFECTO": ("Defecto", False),          # dañada: a merma salvo que la caja diga otra cosa
    "TALLA": ("Talla o medida", True),
    "NO_GUSTO": ("No le gustó", True),
    "ERROR_COBRO": ("Error de cobro", True),
    "OTRO": ("Otro", True),
}

# Cómo quedó autorizada una devolución (`sale_returns.autorizacion`).
AUT_POLITICA = "POLITICA"      # la caja, dentro del monto libre de la tienda
AUT_PIN = "PIN"                # un gerente tecleó su PIN en la caja
AUT_SUPERVISOR = "SUPERVISOR"  # aprobada después desde Devoluciones


def catalogo_motivos() -> list[dict]:
    return [{"code": c, "label": t, "regresa_a_stock": s} for c, (t, s) in MOTIVOS.items()]


def texto_motivo(code: Optional[str], nota: Optional[str]) -> str:
    """Texto que se guarda en `reason` (y se imprime): etiqueta del catálogo más
    la nota libre de la caja, si la hay."""
    etiqueta = MOTIVOS[code][0] if code in MOTIVOS else None
    nota = (nota or "").strip()
    if etiqueta and nota and nota.lower() != etiqueta.lower():
        return f"{etiqueta}: {nota}"
    return etiqueta or nota or "Devolución"


def _valor(metodo) -> str:
    return str(getattr(metodo, "value", metodo))


def metodos_de_reembolso(sale: SalesDocument) -> list[str]:
    """Métodos por los que se puede regresar el dinero: los mismos con los que
    se pagó el ticket (efectivo solo si se pagó en efectivo). Una venta sin
    pagos (fiada) no entrega dinero: lo devuelto baja la deuda; se deja
    efectivo como etiqueta por si queda un excedente."""
    vistos: list[str] = []
    for p in sale.payments or []:
        m = _valor(p.method)
        if m not in vistos:
            vistos.append(m)
    return vistos or [PaymentMethod.CASH.value]


def piezas_del_ticket(db: Session, sale: SalesDocument) -> list[dict]:
    """Por variante: lo vendido, lo ya devuelto (aprobado), lo que está en una
    solicitud pendiente y lo que queda; más lo que se pagó por pieza (el mismo
    prorrateo de `create_return`: sobre `total_line`, no el precio de lista)."""
    devuelto: dict[str, Decimal] = {}
    en_tramite: dict[str, Decimal] = {}
    for item, estado in (
        db.query(SaleReturnItem, SaleReturn.status)
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
        .filter(SaleReturn.sale_id == sale.id, SaleReturn.status.in_(("APPROVED", "PENDING")))
        .all()
    ):
        destino = devuelto if estado == "APPROVED" else en_tramite
        destino[item.variant_id] = destino.get(item.variant_id, Decimal("0")) + Decimal(str(item.quantity or 0))

    piezas: dict[str, dict] = {}
    for linea in (
        db.query(SalesLineItem)
        .filter(SalesLineItem.document_id == sale.id)
        .order_by(SalesLineItem.id)
        .all()
    ):
        p = piezas.setdefault(linea.variant_id, {
            "variant_id": linea.variant_id,
            "descripcion": linea.description,
            "sku": getattr(linea.variant, "sku", None) if linea.variant is not None else None,
            "vendido": Decimal("0"),
            "_pagado": Decimal("0"),
        })
        p["vendido"] += Decimal(str(linea.quantity or 0))
        p["_pagado"] += Decimal(str(linea.total_line or 0))

    salida = []
    for vid, p in piezas.items():
        vendido = p["vendido"]
        ya = devuelto.get(vid, Decimal("0"))
        tramite = en_tramite.get(vid, Decimal("0"))
        pagado = p.pop("_pagado")
        salida.append({
            **p,
            "devuelto": ya,
            "en_tramite": tramite,
            "disponible": max(vendido - ya - tramite, Decimal("0")),
            "precio_pagado": (pagado / vendido).quantize(Decimal("0.01")) if vendido > 0 else Decimal("0"),
        })
    return salida


def monto_libre(db: Session, org_id: int) -> Decimal:
    """Monto hasta el que la caja devuelve sin autorización (0 = nunca)."""
    from app.models.organization import Organization
    valor = db.query(Organization.devolucion_libre_hasta).filter(Organization.id == org_id).scalar()
    return Decimal(str(valor or 0))


def sesion_abierta_de(db: Session, user_id: int, branch_id: Optional[int]) -> Optional[int]:
    """Id del turno de caja ABIERTO del usuario en la sucursal, o None."""
    from app.models.cash import CashSession, CashSessionStatus
    if branch_id is None:
        return None
    fila = db.query(CashSession.id).filter(
        CashSession.user_id == user_id,
        CashSession.branch_id == branch_id,
        CashSession.status == CashSessionStatus.OPEN,
    ).order_by(CashSession.opened_at.desc()).first()
    return fila[0] if fila else None
