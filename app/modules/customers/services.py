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

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer, CustomerLedgerEntry

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")
# Estados de ticket que no deben nada (valores de `DocumentStatus`; el import
# es perezoso en este módulo para no ciclar con app.models.sales).
_SIN_DEUDA = frozenset({"PAID", "CANCELLED", "REFUNDED_TOTAL", "REFUNDED_PARTIAL"})


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


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


def deuda_viva_del_documento(
    db: Session, *, org_id: int, documento, customer_id: int
) -> Decimal:
    """Lo que ESTE documento todavía le debe al negocio, para devolver o cancelar.

    Igual que `deuda_cargada_por_documento`, pero un ticket PAID o devuelto no
    debe nada aunque el ledger conserve su cargo sin abono enlazado: así quedan
    los tickets que `conciliar_abonos_fifo` cerró con abonos sueltos. Leer solo
    el ledger le aplicaba al saldo del cliente (que ya había pagado) la
    devolución que debía entregársele, reabría el ticket como PENDING, y la
    cancelación le dejaba el importe entero a favor.
    """
    estado = getattr(documento.status, "value", documento.status)
    if estado in _SIN_DEUDA:
        return CERO
    return deuda_cargada_por_documento(
        db, org_id=org_id, documento=documento, customer_id=customer_id)


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
    # PAID significa sin deuda, aunque el ledger conserve el cargo sin abono
    # enlazado (abonos libres anteriores a la auditoría, tickets cerrados por
    # `conciliar_abonos_fifo`): lo garantizan `_marcar_pagado_si_liquidado`,
    # `/pay` y el script de conciliación. REFUNDED_PARTIAL tampoco: una
    # devolución parcial que deja deuda mantiene el ticket PENDING
    # (`app/crud/returns.py`), así que el parcial solo nace sin deuda.
    if estado in _SIN_DEUDA:
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
    recibo: Optional[str] = None,
) -> list[CustomerLedgerEntry]:
    """Baja la deuda del cliente y deja el rastro por documento.

    Con `documento`, el abono entero va a ese ticket. Sin documento ("abono
    libre": el cliente trae $500 y no dice de cuál ticket), se reparte del
    ticket más viejo al más nuevo y lo que sobra queda como saldo a favor —o
    cubre cargos viejos que nacieron sin enlace a documento—. Así el estado de
    cuenta dice a qué ticket fue cada peso, cada ticket pasa a PAID cuando se
    cubre, y la antigüedad de saldos cuadra con el saldo. Antes un abono libre
    bajaba el saldo pero dejaba todos los tickets PENDING para siempre.

    `recibo` (folio `AB-XXXXXXXX` del Payment) se añade como sufijo
    ` [AB-XXXXXXXX]` a la descripción de cada asiento: es el enlace
    determinista entre un Payment y sus asientos (lo usa `detalle_del_abono`)
    y deja el folio del recibo en el estado de cuenta. Los prefijos
    `ABONO A TICKET` / `PAGO RECIBIDO` no cambian: la clasificación de
    asientos depende de ellos.

    No hace commit; el que llama decide la transacción.
    """
    amount = _dec(amount)
    asientos: list[CustomerLedgerEntry] = []
    etiqueta = referencia or "Abono"
    sufijo = f" [{recibo}]" if recibo else ""

    def _asiento(monto: Decimal, doc, descripcion: str) -> None:
        e = CustomerLedgerEntry(
            customer_id=customer.id,
            sales_document_id=doc.id if doc is not None else None,
            amount=-monto,
            description=descripcion + sufijo,
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
# Qué es cada asiento
# --------------------------------------------------------------------------
# Un asiento negativo es abono salvo que lo haya escrito una cancelación o una
# devolución (`revertir_cargo_de_documento` desde sales.py::cancel_sale y
# `aplicar_devolucion_a_saldo` desde crud/returns.py::approve_return). Este es
# el ÚNICO lugar que conoce los prefijos; `tests/test_cobranza_corte.py` los
# fija contra los textos reales.
PREFIJOS_REVERSION = ("Cancelación", "Devolución")


def es_reversion(asiento) -> bool:
    return _dec(asiento.amount) < 0 and (asiento.description or "").startswith(PREFIJOS_REVERSION)


def es_abono(asiento) -> bool:
    return _dec(asiento.amount) < 0 and not es_reversion(asiento)


def filtro_sql_reversion():
    return or_(*[CustomerLedgerEntry.description.like(f"{p}%") for p in PREFIJOS_REVERSION])


def filtro_sql_cargo_o_reversion():
    """Cargos (+) y sus reversiones (−): lo que suma al "fiado". Deja fuera los abonos."""
    return or_(CustomerLedgerEntry.amount > 0, filtro_sql_reversion())


def filtro_sql_abono():
    return and_(CustomerLedgerEntry.amount < 0, ~filtro_sql_reversion())


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
    vivo = deuda_viva_del_documento(
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
    vivo = deuda_viva_del_documento(
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


def cargos_pendientes(asientos: Iterable[CustomerLedgerEntry]) -> list[list]:
    """Los cargos que todavía deben algo, del más viejo al más nuevo, como
    `[created_at, restante]`. Un asiento negativo (abono, cancelación,
    devolución) con `sales_document_id` baja primero el cargo de ESE ticket;
    solo lo que exceda lo pendiente de su ticket, y todo asiento sin ticket
    (abono libre, `PAGO RECIBIDO`), se aplica al cargo más viejo (FIFO). Un
    abono anterior a cualquier cargo queda como crédito que consume el
    siguiente cargo."""
    pendientes: list[list] = []  # [created_at, restante, sales_document_id]

    def _aplicar(abono: Decimal, solo_doc) -> Decimal:
        for cargo in list(pendientes):
            if abono <= 0:
                break
            if solo_doc is not None and cargo[2] != solo_doc:
                continue
            usado = min(abono, cargo[1])
            cargo[1] -= usado
            abono -= usado
            if cargo[1] <= CERO:
                pendientes.remove(cargo)
        return abono

    credito = CERO
    for e in sorted(asientos, key=lambda x: (x.created_at or datetime.min.replace(tzinfo=timezone.utc), x.id or 0)):
        monto = _dec(e.amount)
        if monto > 0:
            if credito > 0:
                usado = min(credito, monto)
                credito -= usado
                monto -= usado
            if monto > 0:
                pendientes.append([e.created_at, monto, e.sales_document_id])
        elif monto < 0:
            abono = -monto
            if e.sales_document_id:
                abono = _aplicar(abono, e.sales_document_id)
            abono = _aplicar(abono, None)
            if abono > 0:
                credito += abono
    return [[creado, restante] for creado, restante, _ in pendientes]


def antiguedad_por_cargo(
    asientos: Iterable[CustomerLedgerEntry], *, ahora: Optional[datetime] = None
) -> dict[str, Decimal]:
    """Reparte lo que el cliente debe HOY por la edad del cargo que lo originó
    (ver `cargos_pendientes`). Un cliente que compró $10,000 en el año y debe
    $100 reporta $100, no $10,000."""
    ahora = ahora or datetime.now(timezone.utc)
    buckets = {k: CERO for k in BUCKETS}
    for creado, restante in cargos_pendientes(asientos):
        if creado is None:
            buckets["current"] += restante
            continue
        buckets[_bucket((ahora - _utc(creado)).days)] += restante
    return buckets


def asientos_del_cliente(db: Session, *, org_id: int, customer_id: int) -> list[CustomerLedgerEntry]:
    return db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.organization_id == org_id,
        CustomerLedgerEntry.customer_id == customer_id,
    ).order_by(CustomerLedgerEntry.created_at.asc(), CustomerLedgerEntry.id.asc()).all()


def detalle_del_abono(db: Session, *, org_id: int, pago) -> dict:
    """Reconstruye qué cubrió un abono a partir del ledger (spec 2026-10-29 §4.3).

    Sin columna nueva: los asientos de abono del mismo cliente nacidos en la
    misma transacción que el `Payment` (misma marca de tiempo, ±2 s) son los
    suyos. Los saldos se reconstruyen hacia atrás desde el saldo de hoy: se
    deshace todo asiento del cliente posterior al último asiento del abono
    (ventas fiadas, otros abonos, cancelaciones) para obtener "Saldo actual" y,
    sumando lo abonado, "Saldo anterior". Así una reimpresión repite el recibo
    original aunque el cliente haya movido su cuenta desde entonces.

    `paid_in_full` de cada renglón sí es "al momento de imprimir" (lee la deuda
    que le queda hoy al ticket), no al momento del abono.
    """
    from datetime import timedelta
    from app.models.sales import SalesDocument

    customer = db.query(Customer).filter(
        Customer.id == pago.customer_id, Customer.organization_id == org_id).one()

    # Enlace determinista: `aplicar_abono(recibo=...)` marca cada asiento con
    # el sufijo " [AB-XXXXXXXX]" del Payment.
    folio = f"AB-{pago.id[:8].upper()}"
    propios = db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.organization_id == org_id,
        CustomerLedgerEntry.customer_id == customer.id,
        CustomerLedgerEntry.description.like(f"% [{folio}]"),
    ).order_by(CustomerLedgerEntry.created_at.asc(), CustomerLedgerEntry.id.asc()).all()
    asientos = [a for a in propios if es_abono(a)]
    if not asientos:
        # Abonos registrados antes del sufijo no lo traen: se cae a la ventana
        # de tiempo (asientos de abono del cliente nacidos con el Payment, ±2 s).
        cuando = _utc(pago.created_at)
        asientos = [
            a for a in asientos_del_cliente(db, org_id=org_id, customer_id=customer.id)
            if es_abono(a) and a.created_at is not None
            and abs(_utc(a.created_at) - cuando) <= timedelta(seconds=2)
        ]
    ids = [a.sales_document_id for a in asientos if a.sales_document_id]
    docs = {
        d.id: d for d in db.query(SalesDocument).filter(
            SalesDocument.id.in_(ids), SalesDocument.organization_id == org_id).all()
    } if ids else {}
    applied = [
        {
            "sales_document_id": a.sales_document_id,
            "folio": DocumentoAbierto(documento=docs[a.sales_document_id], saldo=CERO).folio,
            "amount": -_dec(a.amount),
            # Liquidado según la deuda que queda, no por el estado: un ticket con
            # devolución parcial puede quedar en cero sin ser PAID.
            "paid_in_full": saldo_documento(
                db, org_id=org_id, documento=docs[a.sales_document_id], customer_id=customer.id,
            ) <= CENTAVO / 2,
        }
        for a in asientos if a.sales_document_id in docs
    ]
    unapplied = sum((-_dec(a.amount) for a in asientos if not a.sales_document_id), CERO)
    abonado = sum((-_dec(a.amount) for a in asientos), CERO)
    despues = _dec(customer.current_balance)
    if asientos:
        ultimo = max(a.id for a in asientos)
        posteriores = db.query(func.coalesce(func.sum(CustomerLedgerEntry.amount), 0)).filter(
            CustomerLedgerEntry.organization_id == org_id,
            CustomerLedgerEntry.customer_id == customer.id,
            CustomerLedgerEntry.id > ultimo,
        ).scalar()
        despues -= _dec(posteriores)
    return {"customer": customer, "applied": applied, "unapplied": unapplied,
            "balance_after": despues, "balance_before": despues + abonado}


# --------------------------------------------------------------------------
# Cuentas por cobrar (spec 2026-10-29 §3.1)
# --------------------------------------------------------------------------
@dataclass
class ClienteCobranza:
    customer: Customer
    balance: Decimal
    cargo_mas_viejo: Optional[datetime]
    dias: int
    ultimo_abono: Optional[datetime]
    branch_id: Optional[int]
    branch_name: Optional[str]
    tickets_abiertos: int
    antiguedad: dict[str, Decimal]


def cuentas_por_cobrar(
    db: Session, *, org_id: int, branch_id: Optional[int] = None, bucket: Optional[str] = None,
    search: Optional[str] = None, order: str = "saldo", ahora: Optional[datetime] = None,
) -> tuple[dict, list[ClienteCobranza]]:
    """Quién debe, cuánto y desde cuándo. Recorre asientos en Python por
    cliente (decenas en una boutique); `limit` lo acota el router. La sucursal
    de un cliente es la de su última venta. `a_favor` suma los saldos negativos
    del mismo filtro de búsqueda y va aparte: no se resta de `por_cobrar`."""
    from app.models.organization import Branch
    from app.models.sales import SalesDocument

    ahora = ahora or datetime.now(timezone.utc)
    q = db.query(Customer).filter(Customer.organization_id == org_id, Customer.current_balance != 0)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    clientes = q.all()
    a_favor = sum((-_dec(c.current_balance) for c in clientes if _dec(c.current_balance) < 0), CERO)

    filas: list[ClienteCobranza] = []
    for c in clientes:
        saldo = _dec(c.current_balance)
        if saldo <= 0:
            continue
        ultima = (
            db.query(SalesDocument.branch_id, Branch.name)
            .join(Branch, Branch.id == SalesDocument.branch_id)
            .filter(SalesDocument.customer_id == c.id, SalesDocument.organization_id == org_id)
            .order_by(SalesDocument.created_at.desc()).first()
        )
        b_id, b_name = (ultima[0], ultima[1]) if ultima else (None, None)
        if branch_id is not None and b_id != branch_id:
            continue
        asientos = asientos_del_cliente(db, org_id=org_id, customer_id=c.id)
        antig = antiguedad_por_cargo(asientos, ahora=ahora)
        if bucket and antig.get(bucket, CERO) <= 0:
            continue
        pendientes = cargos_pendientes(asientos)
        mas_viejo = next((creado for creado, _ in pendientes if creado is not None), None)
        abonos = [_utc(a.created_at) for a in asientos if es_abono(a) and a.created_at is not None]
        filas.append(ClienteCobranza(
            customer=c, balance=saldo, cargo_mas_viejo=mas_viejo,
            dias=(ahora - _utc(mas_viejo)).days if mas_viejo else 0,
            ultimo_abono=max(abonos) if abonos else None,
            branch_id=b_id, branch_name=b_name,
            tickets_abiertos=len(documentos_abiertos(db, org_id=org_id, customer=c)),
            antiguedad=antig,
        ))
    if order == "antiguedad":
        filas.sort(key=lambda f: (-f.dias, -f.balance, f.customer.name or ""))
    else:
        filas.sort(key=lambda f: (-f.balance, f.customer.name or ""))
    vencido = sum((f.antiguedad["31_60"] + f.antiguedad["61_90"] + f.antiguedad["91_plus"] for f in filas), CERO)
    resumen = {
        "por_cobrar": sum((f.balance for f in filas), CERO),
        "vencido_30": vencido,
        "clientes": len(filas),
        "a_favor": a_favor,
    }
    return resumen, filas


__all__ = [
    "deuda_cargada_por_documento",
    "deuda_viva_del_documento",
    "saldo_documento",
    "documentos_abiertos",
    "DocumentoAbierto",
    "aplicar_abono",
    "revertir_cargo_de_documento",
    "aplicar_devolucion_a_saldo",
    "cargos_pendientes",
    "antiguedad_por_cargo",
    "ClienteCobranza",
    "cuentas_por_cobrar",
    "asientos_del_cliente",
    "detalle_del_abono",
    "PREFIJOS_REVERSION",
    "es_reversion",
    "es_abono",
    "filtro_sql_reversion",
    "filtro_sql_cargo_o_reversion",
    "filtro_sql_abono",
]
