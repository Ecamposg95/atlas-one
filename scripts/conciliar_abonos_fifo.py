"""Concilia abonos viejos sin ticket (spec 2026-10-29 §6.2).

Antes de la auditoría 2026-10-28 un abono libre bajaba el saldo del cliente
pero no se ligaba a ningún ticket: esos tickets siguen PENDING aunque ya estén
pagados. Este script suma, por cliente, los abonos sueltos anteriores a
`--antes` y recorre sus tickets abiertos del más viejo al más nuevo marcando
PAID los que esa bolsa cubre por completo. No crea asientos ni toca
`current_balance` (el saldo ya es correcto); solo corrige el estado del ticket.
Un ticket PAID no debe nada para el CRM (`saldo_documento` devuelve 0): sale de
`unpaid-documents`, del selector de abono y del conteo de tickets abiertos, y un
abono libre posterior ya no cae sobre él.

Uso (dentro del contenedor de producción, donde vive la base):
    python scripts/conciliar_abonos_fifo.py --org 17 --dry-run
    python scripts/conciliar_abonos_fifo.py --org 17
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def conciliar(db, *, org_id: int, antes: date, dry_run: bool) -> list[dict]:
    """Idempotente: la bolsa de abonos sueltos se consume recorriendo TODOS los
    tickets con cargo del cliente (PENDING y PAID) del más viejo al más nuevo;
    un ticket ya PAID solo gasta bolsa, uno PENDING cubierto se marca."""
    from app.models.sales import DocumentStatus, SalesDocument
    from app.modules.customers.models import Customer, CustomerLedgerEntry
    from app.modules.customers.services import DocumentoAbierto, deuda_cargada_por_documento, es_abono

    limite = datetime.combine(antes, datetime.min.time(), tzinfo=timezone.utc)

    def _utc(t):
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t

    acciones: list[dict] = []
    for c in db.query(Customer).filter(Customer.organization_id == org_id).order_by(Customer.id).all():
        sueltos = [
            a for a in db.query(CustomerLedgerEntry).filter(
                CustomerLedgerEntry.organization_id == org_id,
                CustomerLedgerEntry.customer_id == c.id,
                CustomerLedgerEntry.sales_document_id.is_(None),
            ).all()
            if es_abono(a) and a.created_at is not None and _utc(a.created_at) < limite
        ]
        bolsa = sum((-Decimal(str(a.amount)) for a in sueltos), Decimal("0"))
        if bolsa <= 0:
            continue
        docs = (
            db.query(SalesDocument)
            .filter(SalesDocument.organization_id == org_id, SalesDocument.customer_id == c.id,
                    SalesDocument.status.in_((DocumentStatus.PENDING, DocumentStatus.PAID)))
            .order_by(SalesDocument.created_at.asc(), SalesDocument.folio.asc())
            .all()
        )
        for d in docs:
            faltante = deuda_cargada_por_documento(db, org_id=org_id, documento=d, customer_id=c.id)
            if faltante <= 0:
                continue           # pagado al cobrar o ya cubierto por abonos ligados
            if bolsa < faltante:
                break
            bolsa -= faltante
            if d.status == DocumentStatus.PENDING:
                acciones.append({"customer_id": c.id, "cliente": c.name,
                                 "folio": DocumentoAbierto(documento=d, saldo=faltante).folio, "saldo": faltante})
                if not dry_run:
                    d.status = DocumentStatus.PAID
    if not dry_run:
        db.commit()
    return acciones


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--org", type=int, required=True, help="organization_id")
    p.add_argument("--antes", default="2026-10-28", help="solo abonos anteriores a esta fecha (ISO); default: día de la auditoría")
    p.add_argument("--dry-run", action="store_true", help="solo imprime lo que haría")
    args = p.parse_args()

    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        acciones = conciliar(db, org_id=args.org, antes=date.fromisoformat(args.antes), dry_run=args.dry_run)
    finally:
        db.close()
    modo = "HARÍA" if args.dry_run else "HECHO"
    for a in acciones:
        print(f"{modo}: cliente {a['customer_id']} ({a['cliente']}): ticket {a['folio']} por {a['saldo']} → PAID")
    print(f"{len(acciones)} ticket(s) {'por marcar' if args.dry_run else 'marcados'} PAID")


if __name__ == "__main__":
    main()
