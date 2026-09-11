"""El audit log de una cancelación no puede tumbar la cancelación.

`audit_cash_event` promete ser failsafe, pero hacía `db.add` + `db.flush()`
sin savepoint: un flush fallido (deriva de esquema, error transitorio) deja la
sesión en pending-rollback, y el `db.commit()` de `cancel_sale`
(app/routers/sales.py) revienta con `PendingRollbackError`. Es decir, el
registro de auditoría —que promete no estorbar— tumbaba la operación de
negocio y devolvía 500 sobre una venta que el usuario pidió cancelar.

Arreglo: el insert va dentro de `with db.begin_nested()` (SAVEPOINT). Si
falla, se deshace SOLO él y la transacción padre sigue confirmable.
"""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, DocumentType, SalesDocument
from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.services import cash_audit


def _habilitar_pos(db, org):
    """`DELETE /api/sales/{id}` está detrás de `require_module('pos')`.

    Se llama DENTRO del test, no como fixture autouse: commitear antes de que
    `client` levante la app choca con su siembra de módulos en SQLite.
    """
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta"))
        db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "pos",
    ).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.commit()


def _venta(db, seller, branch, monto=250):
    v = SalesDocument(
        seller_id=seller.id, branch_id=branch.id, organization_id=branch.organization_id,
        total_amount=Decimal(str(monto)), subtotal=Decimal(str(monto)),
        tax_amount=Decimal("0"), status=DocumentStatus.PAID,
        doc_type=DocumentType.INVOICE, series="A", folio=7001,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_cancelar_deja_rastro_en_el_audit_log(client, db, org, branch_a, cajero_a, auth_cajero_a):
    """Camino feliz: sin este evento el pivote de cancelaciones nace vacío."""
    _habilitar_pos(db, org)
    venta = _venta(db, cajero_a, branch_a)
    r = client.delete(f"/api/sales/{venta.id}", params={"reason": "Ticket duplicado"},
                      headers=auth_cajero_a)
    assert r.status_code == 200, r.text

    evento = (
        db.query(CashAuditLog)
        .filter(CashAuditLog.event_type == CashAuditEvent.SALE_CANCELLED,
                CashAuditLog.related_id == str(venta.id))
        .one()
    )
    assert evento.branch_id == branch_a.id
    assert Decimal(str(evento.amount)) == Decimal("250")
    assert evento.payload_json["reason"] == "Ticket duplicado"
    assert evento.payload_json["prev_status"] == "PAID"


def test_si_el_audit_revienta_la_cancelacion_se_confirma_igual(
    client, db, org, branch_a, cajero_a, auth_cajero_a, monkeypatch,
):
    """El SAVEPOINT acota el daño: falla el audit, no la cancelación.

    El fallo se fuerza en el FLUSH (no al construir la fila): es el caso que
    envenenaba la sesión y hacía reventar el `commit()` de `cancel_sale`.
    """
    _habilitar_pos(db, org)
    venta = _venta(db, cajero_a, branch_a)

    class _AuditRoto(cash_audit.CashAuditLog):
        """Fila que el driver no sabe escribir: simula deriva de esquema."""
        def __init__(self, **kw):
            kw["payload_json"] = {"objeto": object()}   # no serializable a JSON
            super().__init__(**kw)

    monkeypatch.setattr(cash_audit, "CashAuditLog", _AuditRoto)

    r = client.delete(f"/api/sales/{venta.id}", params={"reason": "Cliente se arrepintió"},
                      headers=auth_cajero_a)
    assert r.status_code == 200, r.text

    db.expire_all()
    guardada = db.query(SalesDocument).filter(SalesDocument.id == venta.id).one()
    assert guardada.status == DocumentStatus.CANCELLED, "la cancelación no se confirmó"
    assert db.query(CashAuditLog).filter(
        CashAuditLog.related_id == str(venta.id)).count() == 0, "el savepoint no deshizo el audit"


def test_un_flush_fallido_no_deja_la_sesion_en_pending_rollback(db, org, branch_a, cajero_a):
    """La regresión exacta: tras un audit fallido, el commit del llamador vive.

    Sin savepoint, `db.flush()` reventado deja la sesión inutilizable y este
    `commit()` lanzaría `PendingRollbackError`.
    """
    venta = _venta(db, cajero_a, branch_a)
    venta.status = DocumentStatus.CANCELLED

    # Payload no serializable a JSON: el flush truena al escribir la columna.
    resultado = cash_audit.audit_cash_event(
        db,
        event_type=CashAuditEvent.SALE_CANCELLED,
        organization_id=org.id,
        branch_id=branch_a.id,
        user_id=cajero_a.id,
        amount=Decimal("250"),
        related_table="sales_documents",
        related_id=venta.id,
        payload={"objeto": object()},  # no serializable a JSON
    )
    assert resultado is None, "el audit debía fallar en silencio"

    db.commit()  # sin el savepoint, aquí saltaba PendingRollbackError
    db.expire_all()
    assert db.query(SalesDocument).filter(SalesDocument.id == venta.id).one().status \
        == DocumentStatus.CANCELLED
