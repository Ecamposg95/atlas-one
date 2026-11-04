"""Devolver o cancelar un ticket fiado que ya está PAID no reabre deuda.

`conciliar_abonos_fifo.py` marca PAID los tickets que un abono suelto
(anterior a la auditoría 2026-10-28) ya cubrió, sin crear asientos: el cargo
del ticket queda en el ledger sin un abono enlazado. Devoluciones y
cancelaciones leían la deuda del ticket solo del ledger, así que veían el
cargo entero "vivo": la devolución lo aplicaba al saldo del cliente (que ya
había pagado) en vez de entregarle su dinero, y reabría el ticket como
PENDING; la cancelación le dejaba un saldo a favor por el importe completo.
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.conciliar_abonos_fifo import conciliar  # noqa: E402

from app.crud import returns as crud_returns  # noqa: E402
from app.models.cash import CashMovement  # noqa: E402
from app.models.sales import DocumentStatus, SalesDocument  # noqa: E402
from app.modules.customers.models import CustomerLedgerEntry  # noqa: E402
from app.modules.customers.services import documentos_abiertos, saldo_documento  # noqa: E402

from tests.test_crm_credito_auditoria import (  # noqa: E402
    _asientos, _cliente, _devolucion, _escenario, _fiar, _salidas_de_caja,
)


def _ticket_conciliado(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    """Venta fiada de 200 (2 piezas) liquidada con un abono suelto y conciliada."""
    h, variant = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    cliente = _cliente(db, org)
    venta = _fiar(client, h, cliente, variant.sku, qty=2)
    db.add(CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id,
                               amount=Decimal("-200"), description="PAGO RECIBIDO: Abono"))
    cliente.current_balance = Decimal("0")
    db.commit()
    conciliar(db, org_id=org.id, antes=date(2099, 1, 1), dry_run=False)
    db.expire_all()
    doc = db.query(SalesDocument).filter(SalesDocument.id == venta["sale_id"]).one()
    assert doc.status == DocumentStatus.PAID
    return h, variant, cliente, doc


def test_devolver_parte_de_un_ticket_conciliado_entrega_el_dinero_y_no_reabre_deuda(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, cliente, doc = _ticket_conciliado(
        client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    asientos_antes = len(_asientos(db, cliente))

    d = _devolucion(db, org, branch_a, cajero_a, doc.id, variant, Decimal("100.00"))
    crud_returns.approve_return(db, d.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()
    db.expire_all()
    db.refresh(cliente)

    assert Decimal(str(cliente.current_balance)) == Decimal("0.00"), "ya había pagado: no queda a favor"
    assert len(_asientos(db, cliente)) == asientos_antes, "nada se aplica al saldo"
    assert [Decimal(str(m.amount)) for m in _salidas_de_caja(db)] == [Decimal("100.00")], (
        "pagó la mercancía: se le devuelve su dinero"
    )
    doc = db.query(SalesDocument).filter(SalesDocument.id == doc.id).one()
    assert doc.status == DocumentStatus.REFUNDED_PARTIAL, "no vuelve a quedar por cobrar"
    assert saldo_documento(db, org_id=org.id, documento=doc, customer_id=cliente.id) == Decimal("0")
    assert documentos_abiertos(db, org_id=org.id, customer=cliente) == []

    d2 = _devolucion(db, org, branch_a, cajero_a, doc.id, variant, Decimal("100.00"))
    crud_returns.approve_return(db, d2.id, supervisor_id=cajero_a.id, organization_id=org.id)
    db.commit()
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00")
    assert [Decimal(str(m.amount)) for m in _salidas_de_caja(db)] == [Decimal("100.00")] * 2
    assert db.query(SalesDocument).filter(
        SalesDocument.id == doc.id).one().status == DocumentStatus.REFUNDED_TOTAL


def test_cancelar_un_ticket_conciliado_no_deja_saldo_a_favor(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    h, variant, cliente, doc = _ticket_conciliado(
        client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    asientos_antes = len(_asientos(db, cliente))

    r = client.delete(f"/api/sales/{doc.id}", params={"reason": "error de captura"}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("0.00"), "no se le regalan 200 a favor"
    assert len(_asientos(db, cliente)) == asientos_antes
