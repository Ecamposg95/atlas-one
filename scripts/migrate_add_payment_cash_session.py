"""Columna `cash_session_id` en payments — envoltorio manual.

La DDL, el indice y el relleno historico viven en `scripts/railway_init.py`
(regla 3 de CLAUDE.md): ese es el unico script que corre en cada despliegue,
asi que una migracion que no este ahi no se aplica nunca en Railway. Este
archivo se conserva para aplicar SOLO esta columna a mano (por ejemplo en el
VPS, sin reiniciar la app) reusando exactamente la misma DDL — aqui no hay
copia del ALTER que se pueda desincronizar de la que corre en el arranque.

Contexto: hasta ahora el efectivo se atribuia por el DOCUMENTO de venta
(sales_documents.cash_session_id). Eso hace que liquidar una venta a credito
en otro turno mueva el efectivo de ayer al corte de hoy, y vacie
retroactivamente un corte ya cerrado. Esta columna permite atribuir el pago a
la caja que de verdad recibio el dinero.

El relleno historico es correcto: hasta este cambio el pago se creaba en la
misma transaccion que la venta, asi que la caja del documento SI era la caja
que recibio el dinero. Los pagos de ventas sin caja (sales_documents.
cash_session_id IS NULL) se quedan en NULL a proposito — no se les inventa
una sesion.

Despliegue en caliente: la tienda cobra en vivo mientras esto corre. La DDL
toma un candado exclusivo sobre payments que bloquea los INSERT de cobros
nuevos hasta el COMMIT. Por eso se fija `lock_timeout` antes: si el candado no
se consigue en unos segundos (p.ej. porque hay otra transaccion larga viva
sobre payments o cash_sessions), el ALTER falla ruidosamente en vez de encolar
los cobros indefinidamente, no se aplica ningun cambio y es seguro reintentar.
El relleno corre despues, ya sin el candado exclusivo, y es idempotente: si se
interrumpe a la mitad, un reintento retoma donde quedo (solo toca filas con
cash_session_id IS NULL).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.database import engine
from scripts.railway_init import (
    INDICES_PAYMENTS_CASH_SESSION,
    MIGRACIONES_PAYMENTS_CASH_SESSION,
    aplicar_migraciones_de_columna,
    aplicar_migraciones_de_indice,
    rellenar_payments_cash_session,
)

# Unos segundos bastan: en operacion normal el candado se consigue de
# inmediato. Si no, es porque algo mas lo tiene tomado y hay que enterarse
# ya, no encolar cobros detras de una espera indefinida.
LOCK_TIMEOUT = "5s"


def _run_ddl() -> None:
    """ALTER + indice. Es la unica parte que toma el candado sobre payments."""
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            # Falla rapido y ruidoso en vez de encolar los INSERT de cobros
            # nuevos detras de una espera indefinida por el candado. `SET` (no
            # `SET LOCAL`) es de sesion: sigue vigente para los COMMIT que hace
            # cada paso de la migracion.
            conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        aplicar_migraciones_de_columna(conn, MIGRACIONES_PAYMENTS_CASH_SESSION)
        aplicar_migraciones_de_indice(conn, INDICES_PAYMENTS_CASH_SESSION)


def main() -> None:
    try:
        _run_ddl()
    except OperationalError as exc:
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == "55P03":  # lock_not_available
            print(
                "[migrate] ERROR — no se pudo tomar el candado sobre payments "
                f"en {LOCK_TIMEOUT} (lock_timeout agotado). Probablemente hay "
                "otra transaccion larga viva sobre payments o cash_sessions. "
                "El paso que fallo se revirtio: es seguro reintentar la "
                "migracion cuando esa transaccion termine.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        raise

    rellenados, pendientes = rellenar_payments_cash_session(engine)

    print(f"[migrate] OK — payments.cash_session_id listo. "
          f"Rellenados: {rellenados}. Sin atribucion (nulo a proposito): {pendientes}.")


if __name__ == "__main__":
    main()
