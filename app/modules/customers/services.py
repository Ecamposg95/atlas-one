"""Atlas BOS modules/customers/services — lógica de crédito y abonos.

DOMAIN: Customer Relationship Management
STATUS: Stable (auditoría del crédito, 2026-10-28)

La cuenta del cliente la mueven varios caminos (checkout a crédito, abono en
mostrador, cancelación de venta, devolución) y `customer_ledger_entries` es la
única bitácora de qué documento cargó o abonó cuánto. Todo lo que necesite
saber "cuánto debe este ticket" o "a qué ticket se aplica este abono" pasa por
aquí, para que ventas, CRM, devoluciones y reportes no repitan la fórmula cada
uno a su manera (que es exactamente lo que encontró la auditoría).

Convención del ledger: `amount > 0` = cargo (la deuda sube), `amount < 0` =
abono (la deuda baja). `Customer.current_balance` es la suma viva del ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer, CustomerLedgerEntry

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


# --------------------------------------------------------------------------
# Deuda por documento
# --------------------------------------------------------------------------
def deuda_cargada_por_documento(
    db: Session, *, org_id: int, documento, customer_id: int
) -> Decimal:
    """Cuánto de la cuenta del cliente cargó ESTE documento y sigue vivo.

    Sumamos los asientos del documento: los cargos (+) menos lo ya abonado
    (−). Sin asientos, este documento nunca cargó nada — el caso de los
    pedidos que crea `app/routers/quotes.py`, que nacen PENDING con
    `customer_id` sin tocar el saldo.

    Un asiento de cargo nace hoy con `sales_document_id`. Los cargos
    anteriores a esa corrección quedaron sin enlace: si el documento solo
    tiene abonos, el cargo existió aunque no esté enlazado, y ahí caemos a la
    fórmula vieja (`total_amount`) para no dejarle al cliente una deuda que ya
    pagó. (Vivía en `app/routers/sales.py`; se movió aquí para que el CRM y
    las devoluciones usen la misma regla.)
    """
    cargos, abonos = db.query(
        func.coalesce(func.sum(case(
            (CustomerLedgerEntry.amount > 0, CustomerLedgerEntry.amount), else_=0)), 0),
        func.coalesce(func.sum(case(
            (CustomerLedgerEntry.amount < 0, -CustomerLedgerEntry.amount), else_=0)), 0),
    ).filter(
        CustomerLedgerEntry.organization_id == org_id,
        CustomerLedgerEntry.sales_document_id == documento.id,
        CustomerLedgerEntry.customer_id == customer_id,
    ).one()
    cargos = _dec(cargos)
    abonos = _dec(abonos)
    if cargos == 0 and abonos > 0:
        cargos = _dec(documento.total_amount)
    return max(CERO, cargos - abonos)


def saldo_documento(db: Session, *, org_id: int, documento, customer_id: int) -> Decimal:
    """Lo que el cliente todavía debe de ESTE documento, para el CRM.

    Misma lectura del ledger que `deuda_cargada_por_documento`, con un respaldo
    más: un documento PENDING sin ningún asiento (venta a crédito anterior a
    que el checkout escribiera el ledger, o cliente que entonces no tenía
    `has_credit`) debe `total_amount − pagos` — la fórmula con la que nació
    `unpaid-documents`. Cancelados y devueltos por completo no deben nada.
    """
    from app.models.sales import DocumentStatus, Payment

    estado = getattr(documento.status, "value", documento.status)
    if estado in (DocumentStatus.CANCELLED.value, DocumentStatus.REFUNDED_TOTAL.value):
        return CERO
    hay_asientos = db.query(CustomerLedgerEntry.id).filter(
        CustomerLedgerEntry.organization_id == org_id,
        CustomerLedgerEntry.sales_document_id == documento.id,
        CustomerLedgerEntry.customer_id == customer_id,
    ).first() is not None
    if hay_asientos:
        return deuda_cargada_por_documento(
            db, org_id=org_id, documento=documento, customer_id=customer_id)
    if estado != DocumentStatus.PENDING.value:
        return CERO
    pagos = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.sales_document_id == documento.id,
    ).scalar()
    return max(CERO, _dec(documento.total_amount) - _dec(pagos))


@dataclass(frozen=True)
class DocumentoAbierto:
    documento: object
    saldo: Decimal

    @property
    def folio(self) -> str:
        d = self.documento
        return f"{d.series}-{d.folio}" if d.series and d.folio else d.id


def documentos_abiertos(db: Session, *, org_id: int, customer: Customer) -> list[DocumentoAbierto]:
    """Documentos del cliente con saldo, del más viejo al más nuevo (FIFO)."""
    from app.models.sales import DocumentStatus, DocumentType, SalesDocument

    docs = db.query(SalesDocument).filter(
        SalesDocument.customer_id == customer.id,
        SalesDocument.organization_id == org_id,
        SalesDocument.doc_type.in_([DocumentType.ORDER, DocumentType.INVOICE]),
        SalesDocument.status.notin_([DocumentStatus.CANCELLED, DocumentStatus.REFUNDED_TOTAL]),
    ).order_by(SalesDocument.created_at.asc(), SalesDocument.folio.asc()).all()
    abiertos = []
    for doc in docs:
        saldo = saldo_documento(db, org_id=org_id, documento=doc, customer_id=customer.id)
        if saldo > CENTAVO / 2:
            abiertos.append(DocumentoAbierto(documento=doc, saldo=saldo))
    return abiertos


def _marcar_pagado_si_liquidado(db: Session, *, org_id: int, documento, customer_id: int) -> None:
    from app.models.sales import DocumentStatus

    estado = getattr(documento.status, "value", documento.status)
    if estado != DocumentStatus.PENDING.value:
        return
    db.flush()
    if saldo_documento(db, org_id=org_id, documento=documento, customer_id=customer_id) <= CENTAVO / 2:
        documento.status = DocumentStatus.PAID


# --------------------------------------------------------------------------
# Abonos
# --------------------------------------------------------------------------
def aplicar_abono(
    db: Session,
    *,
    org_id: int,
    customer: Customer,
    amount: Decimal,
    documento=None,
    referencia: Optional[str] = None,
) -> list[CustomerLedgerEntry]:
    """Baja la deuda del cliente y deja el rastro por documento.

    Con `documento`, el abono entero va a ese ticket. Sin documento ("abono
    libre": el cliente trae $500 y no dice de cuál ticket), se reparte del
    ticket más viejo al más nuevo y lo que sobra queda como saldo a favor —o
    cubre cargos viejos que nacieron sin enlace a documento—. Así el estado de
    cuenta dice a qué ticket fue cada peso, cada ticket pasa a PAID cuando se
    cubre, y la antigüedad de saldos cuadra con el saldo. Antes un abono libre
    bajaba el saldo pero dejaba todos los tickets PENDING para siempre.

    No hace commit; el que llama decide la transacción.
    """
    amount = _dec(amount)
    asientos: list[CustomerLedgerEntry] = []
    etiqueta = referencia or "Abono"

    def _asiento(monto: Decimal, doc, descripcion: str) -> None:
        e = CustomerLedgerEntry(
            customer_id=customer.id,
            sales_document_id=doc.id if doc is not None else None,
            amount=-monto,
            description=descripcion,
            organization_id=org_id,
        )
        db.add(e)
        asientos.append(e)

    if documento is not None:
        folio = DocumentoAbierto(documento=documento, saldo=CERO).folio
        _asiento(amount, documento, f"ABONO A TICKET {folio}: {etiqueta}")
        customer.current_balance = _dec(customer.current_balance) - amount
        _marcar_pagado_si_liquidado(
            db, org_id=org_id, documento=documento, customer_id=customer.id)
        return asientos

    resto = amount
    for abierto in documentos_abiertos(db, org_id=org_id, customer=customer):
        if resto <= CERO:
            break
        parte = min(resto, abierto.saldo)
        _asiento(parte, abierto.documento, f"ABONO A TICKET {abierto.folio}: {etiqueta}")
        resto -= parte
        customer.current_balance = _dec(customer.current_balance) - parte
        _marcar_pagado_si_liquidado(
            db, org_id=org_id, documento=abierto.documento, customer_id=customer.id)
    if resto > CERO:
        _asiento(resto, None, f"PAGO RECIBIDO: {etiqueta}")
        customer.current_balance = _dec(customer.current_balance) - resto
    return asientos


# --------------------------------------------------------------------------
# Cancelación y devolución
# --------------------------------------------------------------------------
def revertir_cargo_de_documento(
    db: Session, *, org_id: int, documento, descripcion: str
) -> Decimal:
    """Cancelar una venta a crédito: le quita al cliente lo que ESE documento
    todavía le carga (según el ledger, no `total − pagos`: un pedido de
    cotizaciones nunca cargó nada y no hay nada que devolverle). Devuelve el
    monto revertido (0 si no había cargo vivo)."""
    if not documento.customer_id:
        return CERO
    customer = db.query(Customer).filter(
        Customer.id == documento.customer_id,
        Customer.organization_id == org_id,
    ).first()
    if customer is None:
        return CERO
    vivo = deuda_cargada_por_documento(
        db, org_id=org_id, documento=documento, customer_id=customer.id)
    if vivo <= CERO:
        return CERO
    customer.current_balance = _dec(customer.current_balance) - vivo
    db.add(CustomerLedgerEntry(
        customer_id=customer.id,
        sales_document_id=documento.id,
        amount=-vivo,
        description=descripcion,
        organization_id=org_id,
    ))
    return vivo


def aplicar_devolucion_a_saldo(
    db: Session, *, org_id: int, documento, monto: Decimal, descripcion: str
) -> Decimal:
    """Devolución sobre una venta fiada: lo devuelto baja primero la deuda del
    cliente, y solo lo que exceda la deuda se le entrega en dinero. Devuelve
    cuánto se aplicó al saldo (0 si la venta no debe nada)."""
    if not documento.customer_id:
        return CERO
    customer = db.query(Customer).filter(
        Customer.id == documento.customer_id,
        Customer.organization_id == org_id,
    ).first()
    if customer is None:
        return CERO
    vivo = deuda_cargada_por_documento(
        db, org_id=org_id, documento=documento, customer_id=customer.id)
    aplicado = min(_dec(monto), vivo)
    if aplicado <= CERO:
        return CERO
    customer.current_balance = _dec(customer.current_balance) - aplicado
    db.add(CustomerLedgerEntry(
        customer_id=customer.id,
        sales_document_id=documento.id,
        amount=-aplicado,
        description=descripcion,
        organization_id=org_id,
    ))
    return aplicado


# --------------------------------------------------------------------------
# Antigüedad de saldos
# --------------------------------------------------------------------------
BUCKETS = ("current", "31_60", "61_90", "91_plus")


def _bucket(dias: int) -> str:
    if dias <= 30:
        return "current"
    if dias <= 60:
        return "31_60"
    if dias <= 90:
        return "61_90"
    return "91_plus"


def antiguedad_por_cargo(
    asientos: Iterable[CustomerLedgerEntry], *, ahora: Optional[datetime] = None
) -> dict[str, Decimal]:
    """Reparte lo que el cliente debe HOY por la edad del cargo que lo originó.

    Los abonos se aplican al cargo más viejo primero (FIFO), así que un cliente
    que compró $10,000 a lo largo del año y debe $100 reporta $100, no $10,000
    (que es lo que hacía el reporte al sumar todos los cargos históricos sin
    restar nada). Un abono anterior a cualquier cargo queda como crédito que
    consume el siguiente cargo.
    """
    ahora = ahora or datetime.now(timezone.utc)
    pendientes: list[list] = []  # [created_at, restante]
    credito = CERO
    for e in sorted(asientos, key=lambda x: (x.created_at or datetime.min.replace(tzinfo=timezone.utc), x.id or 0)):
        monto = _dec(e.amount)
        if monto > 0:
            if credito > 0:
                usado = min(credito, monto)
                credito -= usado
                monto -= usado
            if monto > 0:
                pendientes.append([e.created_at, monto])
        elif monto < 0:
            abono = -monto
            while abono > 0 and pendientes:
                cargo = pendientes[0]
                usado = min(abono, cargo[1])
                cargo[1] -= usado
                abono -= usado
                if cargo[1] <= CERO:
                    pendientes.pop(0)
            if abono > 0:
                credito += abono
    buckets = {k: CERO for k in BUCKETS}
    for creado, restante in pendientes:
        if creado is None:
            buckets["current"] += restante
            continue
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        buckets[_bucket((ahora - creado).days)] += restante
    return buckets


def asientos_del_cliente(db: Session, *, org_id: int, customer_id: int) -> list[CustomerLedgerEntry]:
    return db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.organization_id == org_id,
        CustomerLedgerEntry.customer_id == customer_id,
    ).order_by(CustomerLedgerEntry.created_at.asc(), CustomerLedgerEntry.id.asc()).all()


__all__ = [
    "deuda_cargada_por_documento",
    "saldo_documento",
    "documentos_abiertos",
    "DocumentoAbierto",
    "aplicar_abono",
    "revertir_cargo_de_documento",
    "aplicar_devolucion_a_saldo",
    "antiguedad_por_cargo",
    "asientos_del_cliente",
]
