"""Relleno OPCIONAL del desglose fiscal de ventas anteriores a la función.

NO corre en el deploy ni desde `railway_init.py`. Nadie lo ha ejecutado contra
ninguna base. Antes de correrlo en producción hace falta el visto bueno del
contador: el histórico queda desglosado con las claves y la tasa de IVA del
catálogo DE HOY, no las del día de la venta, y con la misma inferencia (16 %
cuando el producto no tiene tasa capturada). Por eso cada renglón rellenado
queda con `iva_inferido = True`, aunque el producto ya tenga tasa explícita.

Qué toca:
- Solo tickets cobrados (`doc_type` INVOICE u ORDER, `status` PAID o PENDING)
  cuyo desglose está en NULL (`iva_base_16 IS NULL`). Idempotente: una venta ya
  desglosada nunca se reescribe.
- Se saltan las ventas con devolución (`REFUNDED_*`): la devolución reescribió
  `total_amount` y sus renglones ya no suman lo cobrado. Esas necesitan
  criterio del contador.
- Se saltan, y se listan, las ventas cuyos renglones no suman su total por más
  de un peso (datos inconsistentes: mejor revisar que repartir).

Uso (ensayo por omisión; `--ejecutar` confirma, por lotes):

    python scripts/backfill_desglose_fiscal.py --org 7 [--desde 2026-11-01] [--ejecutar]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models.organization import Branch, Organization  # noqa: E402
from app.models.sales import DocumentStatus, DocumentType, SalesDocument  # noqa: E402
from app.services.desglose_fiscal import aplicar_desglose  # noqa: E402

LOTE = 500
TOLERANCIA = Decimal("1.00")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--desde", type=lambda s: datetime.fromisoformat(s), default=None)
    parser.add_argument("--ejecutar", action="store_true", help="escribe; sin esto solo ensaya")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == args.org).first()
        if org is None:
            print(f"No existe la organización {args.org}")
            return 1
        q = db.query(SalesDocument).filter(
            SalesDocument.organization_id == org.id,
            SalesDocument.doc_type.in_([DocumentType.INVOICE, DocumentType.ORDER]),
            SalesDocument.status.in_([DocumentStatus.PAID, DocumentStatus.PENDING]),
            SalesDocument.iva_base_16.is_(None),
        )
        if args.desde:
            q = q.filter(SalesDocument.created_at >= args.desde)
        sucursales = {b.id: b for b in db.query(Branch).filter(Branch.organization_id == org.id)}

        rellenadas, saltadas = 0, []
        for doc in q.order_by(SalesDocument.created_at).yield_per(LOTE):
            mercancia = Decimal(str(doc.total_amount or 0)) - Decimal(str(doc.tip_amount or 0))
            suma = sum((Decimal(str(l.total_line or 0)) for l in doc.lines), Decimal("0"))
            if not doc.lines or (suma - mercancia).copy_abs() > TOLERANCIA:
                saltadas.append((doc.id, f"{doc.series}-{doc.folio}", suma, mercancia))
                continue
            aplicar_desglose(
                doc, [(l, l.variant, l.total_line) for l in doc.lines],
                branch=sucursales.get(doc.branch_id), organization=org,
            )
            for linea in doc.lines:
                linea.iva_inferido = True
            rellenadas += 1
            if args.ejecutar and rellenadas % LOTE == 0:
                db.commit()
        if args.ejecutar:
            db.commit()
        else:
            db.rollback()
        print(f"{'Rellenadas' if args.ejecutar else 'Se rellenarían'}: {rellenadas}")
        print(f"Saltadas por no cuadrar: {len(saltadas)}")
        for sid, folio, suma, mercancia in saltadas[:50]:
            print(f"  {folio} ({sid}): renglones {suma} vs total {mercancia}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
