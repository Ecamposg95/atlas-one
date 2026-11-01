"""Abonos libres anteriores a la auditoría (sin enlace a ticket) dejaban los
tickets PENDING aunque el saldo estuviera en cero (spec 2026-10-29 §6.2)."""
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.conciliar_abonos_fifo import conciliar  # noqa: E402

from app.models.sales import DocumentStatus, SalesDocument  # noqa: E402
from app.modules.customers.models import Customer, CustomerLedgerEntry  # noqa: E402


def _doc(db, org, branch, user, cliente, monto, folio, cuando):
    d = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, customer_id=cliente.id,
                      folio=folio, series="A", subtotal=Decimal(monto), tax_amount=Decimal("0"),
                      total_amount=Decimal(monto), status=DocumentStatus.PENDING, doc_type="ORDER")
    d.created_at = cuando
    db.add(d); db.flush()
    a = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=d.id, organization_id=org.id,
                            amount=Decimal(monto), description=f"Venta a crédito #{folio}")
    a.created_at = cuando
    db.add(a); db.commit()
    return d


def _escenario(db, org, branch_a, cajero_a):
    c = Customer(name="Legada", organization_id=org.id, current_balance=Decimal("30"))
    db.add(c); db.commit()
    viejo = _doc(db, org, branch_a, cajero_a, c, "100", 7001, datetime(2026, 9, 1, tzinfo=timezone.utc))
    nuevo = _doc(db, org, branch_a, cajero_a, c, "50", 7002, datetime(2026, 9, 15, tzinfo=timezone.utc))
    suelto = CustomerLedgerEntry(customer_id=c.id, organization_id=org.id, amount=Decimal("-120"),
                                 description="PAGO RECIBIDO: Abono")
    suelto.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.add(suelto); db.commit()
    return c, viejo, nuevo


def test_dry_run_no_cambia_nada(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    acciones = conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=True)
    assert [a["folio"] for a in acciones] == ["A-7001"]
    db.expire_all()
    assert viejo.status == DocumentStatus.PENDING and nuevo.status == DocumentStatus.PENDING


def test_marca_pagado_lo_que_los_abonos_sueltos_cubren_y_no_toca_el_saldo(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    acciones = conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=False)
    assert [(a["folio"], float(a["saldo"])) for a in acciones] == [("A-7001", 100.0)]
    db.expire_all()
    assert viejo.status == DocumentStatus.PAID
    assert nuevo.status == DocumentStatus.PENDING, "los 20 que sobran no cubren el ticket de 50"
    assert Decimal(str(c.current_balance)) == Decimal("30")
    assert conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=False) == [], "idempotente"


def test_un_abono_posterior_a_la_auditoria_no_cuenta(db, org, branch_a, cajero_a):
    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    assert conciliar(db, org_id=org.id, antes=date(2026, 9, 30), dry_run=True) == []


def test_el_ticket_conciliado_ya_no_debe_y_un_abono_libre_posterior_va_al_siguiente(db, org, branch_a, cajero_a):
    """PAID significa sin deuda: tras conciliar, A-7001 sale de `documentos_abiertos`
    y el siguiente abono libre cae sobre A-7002, no sobre el ticket ya pagado."""
    from app.modules.customers.services import aplicar_abono, documentos_abiertos, saldo_documento

    c, viejo, nuevo = _escenario(db, org, branch_a, cajero_a)
    conciliar(db, org_id=org.id, antes=date(2026, 10, 28), dry_run=False)
    db.expire_all()
    assert viejo.status == DocumentStatus.PAID
    assert saldo_documento(db, org_id=org.id, documento=viejo, customer_id=c.id) == Decimal("0")
    assert [x.documento.id for x in documentos_abiertos(db, org_id=org.id, customer=c)] == [nuevo.id]

    asientos = aplicar_abono(db, org_id=org.id, customer=c, amount=Decimal("30"))
    db.commit()
    assert [(a.sales_document_id, Decimal(str(a.amount))) for a in asientos] == [(nuevo.id, Decimal("-30"))]
