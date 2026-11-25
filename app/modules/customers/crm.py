"""CRM de la tienda (2026-11-24): campos propios, ficha 360 y seguimiento.

El dinero del cliente (saldo, abonos, cobranza) sigue en `services.py`; aquí
solo vive lo que describe al cliente y lo que el equipo tiene pendiente con él."""
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer, CustomerFieldDef, CustomerFollowUp

MAX_CAMPOS_PROPIOS = 10
TIPOS_CLIENTE = ("MENUDEO", "MAYOREO")
TIPOS_CAMPO = ("TEXTO", "NUMERO", "FECHA", "LISTA", "SI_NO")
TIPOS_SEGUIMIENTO = ("LLAMADA", "WHATSAPP", "VISITA", "COBRANZA", "OTRO")

# Lo único que la caja (cajera / vendedor) captura o corrige de un cliente: el
# alta rápida del mostrador. Crédito, datos fiscales, tipo y campos propios son
# de gerente, administrador y dueño.
CAMPOS_DE_CAJA = ("name", "phone", "email", "notes")


def normalizar_tipo(tipo: Optional[str]) -> str:
    t = (tipo or "MENUDEO").strip().upper()
    if t not in TIPOS_CLIENTE:
        raise HTTPException(status_code=400, detail="Tipo de cliente desconocido (MENUDEO o MAYOREO).")
    return t


# ── Campos propios ────────────────────────────────────────────────────────
def _clave(label: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_")[:40] or "campo"


def campos_activos(db: Session, org_id: int) -> list[CustomerFieldDef]:
    return db.query(CustomerFieldDef).filter(
        CustomerFieldDef.organization_id == org_id, CustomerFieldDef.is_active == True,  # noqa: E712
    ).order_by(CustomerFieldDef.orden, CustomerFieldDef.id).all()


def _validar_def(tipo: str, opciones) -> tuple[str, Optional[list]]:
    tipo = (tipo or "TEXTO").strip().upper()
    if tipo not in TIPOS_CAMPO:
        raise HTTPException(status_code=400, detail="Tipo de campo desconocido.")
    if tipo == "LISTA":
        limpias = [o.strip() for o in (opciones or []) if o and o.strip()]
        if not limpias:
            raise HTTPException(status_code=400, detail="Un campo de lista necesita al menos una opción.")
        return tipo, limpias[:30]
    return tipo, None


def crear_campo(db: Session, org_id: int, *, label: str, tipo: str, opciones, orden: Optional[int]) -> CustomerFieldDef:
    activos = campos_activos(db, org_id)
    if len(activos) >= MAX_CAMPOS_PROPIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Ya tienes {MAX_CAMPOS_PROPIOS} campos propios, que es el tope. Quita uno para agregar otro.",
        )
    tipo, opciones = _validar_def(tipo, opciones)
    label = label.strip()
    base = _clave(label)
    usadas = {c.key for c in db.query(CustomerFieldDef.key).filter(CustomerFieldDef.organization_id == org_id)}
    clave, n = base, 2
    while clave in usadas:
        clave, n = f"{base[:37]}_{n}", n + 1
    campo = CustomerFieldDef(
        organization_id=org_id, key=clave, label=label, tipo=tipo, opciones=opciones,
        orden=orden if orden is not None else (max((c.orden for c in activos), default=0) + 1),
    )
    db.add(campo)
    return campo


def editar_campo(db: Session, campo: CustomerFieldDef, *, label: str, tipo: str, opciones, orden: Optional[int]) -> None:
    campo.tipo, campo.opciones = _validar_def(tipo, opciones)
    campo.label = label.strip()
    if orden is not None:
        campo.orden = orden


def limpiar_valores(db: Session, org_id: int, valores: Optional[dict]) -> dict:
    """Deja solo los valores de campos activos, con su tipo. Lo demás se tira
    en silencio (campo retirado, clave inventada)."""
    if not valores:
        return {}
    limpio: dict[str, Any] = {}
    for campo in campos_activos(db, org_id):
        if campo.key not in valores:
            continue
        v = valores[campo.key]
        if v is None or v == "":
            continue
        if campo.tipo == "NUMERO":
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"«{campo.label}» debe ser un número.")
        elif campo.tipo == "SI_NO":
            v = bool(v) if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "si", "sí")
        elif campo.tipo == "FECHA":
            try:
                v = date.fromisoformat(str(v)[:10]).isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail=f"«{campo.label}» debe ser una fecha.")
        elif campo.tipo == "LISTA":
            v = str(v)
            if v not in (campo.opciones or []):
                raise HTTPException(status_code=400, detail=f"«{campo.label}»: opción desconocida.")
        else:
            v = str(v).strip()[:200]
        limpio[campo.key] = v
    return limpio


# ── Seguimiento ───────────────────────────────────────────────────────────
def seguimiento_a_dict(s: CustomerFollowUp, nombres: Optional[dict] = None) -> dict:
    nombres = nombres or {}
    return {
        "id": s.id, "customer_id": s.customer_id,
        "customer_name": s.customer.name if s.customer is not None else None,
        "customer_phone": s.customer.phone if s.customer is not None else None,
        "tipo": s.tipo, "nota": s.nota, "due_date": s.due_date, "status": s.status,
        "resultado": s.resultado, "branch_id": s.branch_id,
        "assigned_user_id": s.assigned_user_id,
        "assigned_name": nombres.get(s.assigned_user_id),
        "created_by_user_id": s.created_by_user_id,
        "done_at": s.done_at, "created_at": s.created_at,
    }


def nombres_de_usuarios(db: Session, ids) -> dict:
    from app.models.users import User
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: (u.full_name or u.username) for u in db.query(User).filter(User.id.in_(ids))}


# ── Ficha 360 ─────────────────────────────────────────────────────────────
def _f(x) -> float:
    return float(Decimal(str(x or 0)))


def ficha(db: Session, org_id: int, customer: Customer, *, user, de_caja: bool) -> dict:
    """Todo lo que la tienda sabe del cliente en una sola respuesta.

    La caja (cajera / vendedor) ve sus datos, su saldo y las compras que su
    regla de ventas le deja ver (su sucursal, el plazo de la tienda); los
    acumulados de por vida son de la gerencia."""
    from app.models.returns import SaleReturn
    from app.models.sales import DocumentStatus, SalesDocument, SalesLineItem
    from app.models.vales import VALE_ACTIVO, StoreVoucher
    from app.services.cash_reconciliation import filtro_venta_reconocida
    from app.services.ventas_cajero import rango_visible_cajero

    base = [
        SalesDocument.organization_id == org_id,
        SalesDocument.customer_id == customer.id,
        filtro_venta_reconocida(),
    ]
    if de_caja:
        desde, hasta = rango_visible_cajero(db, user)
        base += [SalesDocument.branch_id == user.branch_id,
                 SalesDocument.created_at >= desde, SalesDocument.created_at < hasta]

    ultimas = db.query(SalesDocument).filter(*base).order_by(SalesDocument.created_at.desc()).limit(10).all()
    compras = [{
        "id": d.id, "series": d.series, "folio": d.folio, "created_at": d.created_at,
        "total": _f(d.total_amount), "status": str(getattr(d.status, "value", d.status)),
        "branch_id": d.branch_id,
    } for d in ultimas]

    resumen = None
    productos = []
    if not de_caja:
        total, tickets, primera, ultima = db.query(
            func.coalesce(func.sum(SalesDocument.total_amount), 0), func.count(SalesDocument.id),
            func.min(SalesDocument.created_at), func.max(SalesDocument.created_at),
        ).filter(*base).one()
        devoluciones = db.query(func.count(SaleReturn.id)).join(
            SalesDocument, SalesDocument.id == SaleReturn.sale_id,
        ).filter(
            SaleReturn.organization_id == org_id, SaleReturn.status == "APPROVED",
            SalesDocument.customer_id == customer.id,
        ).scalar() or 0
        dias = None
        if ultima is not None:
            u = ultima if isinstance(ultima, datetime) else datetime.fromisoformat(str(ultima))
            dias = max((datetime.utcnow().date() - u.date()).days, 0)
        resumen = {
            "total_comprado": _f(total), "tickets": int(tickets or 0),
            "ticket_promedio": round(_f(total) / tickets, 2) if tickets else 0.0,
            "primera_compra": primera, "ultima_compra": ultima, "dias_sin_comprar": dias,
            "devoluciones": int(devoluciones),
        }
        filas = db.query(
            SalesLineItem.description, func.sum(SalesLineItem.quantity), func.sum(SalesLineItem.total_line),
        ).join(SalesDocument, SalesDocument.id == SalesLineItem.document_id).filter(*base).group_by(
            SalesLineItem.description,
        ).order_by(func.sum(SalesLineItem.quantity).desc()).limit(5).all()
        productos = [{"descripcion": d, "piezas": _f(q), "importe": _f(t)} for d, q, t in filas]

    vales = db.query(StoreVoucher).filter(
        StoreVoucher.organization_id == org_id, StoreVoucher.customer_id == customer.id,
        StoreVoucher.status == VALE_ACTIVO,
    ).order_by(StoreVoucher.created_at.desc()).all()

    pendientes = db.query(CustomerFollowUp).filter(
        CustomerFollowUp.organization_id == org_id, CustomerFollowUp.customer_id == customer.id,
    ).order_by(CustomerFollowUp.status.desc(), CustomerFollowUp.due_date.desc()).limit(20).all()
    nombres = nombres_de_usuarios(db, [s.assigned_user_id for s in pendientes])

    saldo = _f(customer.current_balance)
    limite = _f(customer.credit_limit)
    return {
        "limitado": de_caja,
        "saldo": saldo,
        "credito_disponible": max(limite - max(saldo, 0), 0) if customer.has_credit else 0.0,
        "resumen": resumen,
        "compras": compras,
        "productos": productos,
        "vales": [{"code": v.code, "balance": _f(v.balance), "created_at": v.created_at} for v in vales],
        "vales_saldo": sum(_f(v.balance) for v in vales),
        "seguimiento": [seguimiento_a_dict(s, nombres) for s in pendientes],
        "campos": [{"key": c.key, "label": c.label, "tipo": c.tipo, "opciones": c.opciones, "orden": c.orden, "id": c.id}
                   for c in campos_activos(db, org_id)],
    }
