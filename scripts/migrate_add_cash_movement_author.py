"""Columna `created_by_user_id` en cash_movements — envoltorio manual.

La DDL y el indice viven en `scripts/railway_init.py` (regla 3 de CLAUDE.md):
ese es el unico script que corre en cada despliegue, asi que una migracion que
no este ahi no se aplica nunca en Railway. Este archivo se conserva para
aplicar SOLO esta columna a mano (por ejemplo en el VPS, sin reiniciar la app)
reusando exactamente la misma DDL.

Los movimientos no registraban quien los creaba. Las filas historicas quedan
en NULL a proposito: inventarles un autor seria peor que reconocer que no se
sabe.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import engine
from scripts.railway_init import (
    INDICES_CASH_MOVEMENT_AUTHOR,
    MIGRACIONES_CASH_MOVEMENT_AUTHOR,
    aplicar_migraciones_de_columna,
    aplicar_migraciones_de_indice,
)


def main() -> None:
    with engine.connect() as conn:
        aplicar_migraciones_de_columna(conn, MIGRACIONES_CASH_MOVEMENT_AUTHOR)
        aplicar_migraciones_de_indice(conn, INDICES_CASH_MOVEMENT_AUTHOR)
    print("[migrate] OK — cash_movements.created_by_user_id listo.")


if __name__ == "__main__":
    main()
