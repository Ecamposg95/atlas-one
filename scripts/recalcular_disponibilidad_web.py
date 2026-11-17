"""Recalcula la disponibilidad web (`channel_availability`) de una org.

Red de seguridad para lo que el listener `before_flush` no ve: SQL crudo,
UPDATE en bloque, importaciones por script, restauraciones. Ensayo por
omisión: dice cuántas filas cambiarían y deshace; `--ejecutar` confirma.

Uso (dentro del contenedor, PYTHONPATH=/app):
    python scripts/recalcular_disponibilidad_web.py --org 17
    python scripts/recalcular_disponibilidad_web.py --org 17 --ejecutar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401,E402  (puebla la metadata antes de consultar)
from app.core.database import SessionLocal  # noqa: E402
from app.core.security.channel_keys import canal_activo  # noqa: E402
from app.services.canal_disponibilidad import recalcular_disponibilidad, sucursales_web  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--ejecutar", action="store_true", help="confirma (por omisión, ensayo)")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        if not canal_activo(db, args.org):
            print(f"org {args.org}: el módulo tienda_en_linea no está encendido (se recalcula igual)")
        print(f"org {args.org}: sucursales web {sucursales_web(db, args.org)}")
        cambiadas = recalcular_disponibilidad(db, args.org)
        if args.ejecutar:
            db.commit()
            print(f"org {args.org}: {cambiadas} filas corregidas")
        else:
            db.rollback()
            print(f"org {args.org}: {cambiadas} filas cambiarían (ensayo; --ejecutar para confirmar)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
