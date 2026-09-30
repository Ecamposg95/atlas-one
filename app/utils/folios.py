from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.models import SalesDocument
from app.models.organization import Branch


def get_next_folio(db: Session, branch_id: int, series: str = "A") -> int:
    """
    Siguiente folio disponible para una (sucursal, serie).

    Toma un advisory lock transaccional por (branch_id, series) antes de leer el
    MAX(folio). Sin él, dos ventas concurrentes de la misma sucursal leen el mismo
    máximo y emiten folios FISCALES duplicados: el `MAX(folio)+1` es un
    read-then-write sin protección. El lock serializa sólo esa (sucursal, serie)
    —no bloquea sucursales ni series distintas entre sí— y se libera solo al
    COMMIT/ROLLBACK de la transacción del checkout que llama aquí.

    El índice único `uq_sales_documents_branch_series_folio` (ver railway_init)
    es la garantía dura de respaldo por si algún código futuro omite este lock.
    """
    # pg_advisory_xact_lock es de Postgres; en SQLite (tests) las escrituras ya
    # están serializadas, así que se omite sin perder la garantía.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Dos claves int4: sucursal + hash de la serie → lock por (branch, series).
        db.execute(
            text("SELECT pg_advisory_xact_lock(:branch, hashtext(:series))"),
            {"branch": branch_id, "series": series},
        )

    max_folio = db.query(func.max(SalesDocument.folio)).filter(
        SalesDocument.branch_id == branch_id,
        SalesDocument.series == series,
    ).scalar()
    siguiente = 1 if max_folio is None else max_folio + 1

    # Una sucursal que llega de otro sistema puede pedir que su numeracion
    # arranque donde la dejo (Branch.folio_inicial). Solo empuja hacia arriba:
    # si ya hay ventas por encima, manda el maximo, nunca se repite un folio.
    folio_inicial = db.query(Branch.folio_inicial).filter(Branch.id == branch_id).scalar()
    if folio_inicial is not None and folio_inicial > siguiente:
        return folio_inicial
    return siguiente
