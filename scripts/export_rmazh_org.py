"""Exporta una organizacion de rmazh (Data X POS) para mudarla a Atlas ONE.

Corre DENTRO del contenedor de rmazh y solo lee: no escribe una sola fila. Se
le pasa por la entrada estandar, asi que no hace falta copiarlo al servidor ni
conocer la URL de la base de Railway:

    cd /mnt/d/Devs/Atlas-Rmazh
    railway ssh -s Atlas-API -- 'cd /app && /opt/venv/bin/python - 5' \
        < /ruta/a/atlas-one/scripts/export_rmazh_org.py > salida.txt

La salida trae, entre `###RMAZH_ORG_B64###` y `###FIN###`, un JSON comprimido
con gzip y codificado en base64: `{"org_id", "exportado", "tablas": {tabla:
[filas]}}`. `scripts/import_rmazh_org.py` lo lee tal cual (acepta el archivo
completo, con el ruido de `railway ssh` alrededor).

El archivo trae los hashes de contrasena y de PIN de los usuarios: se guarda
fuera del repo y se borra al terminar la mudanza.

Se exportan tambien las filas hijas cuyo `organization_id` quedo en NULL pero
cuyo padre es de la org (TenantMixin es nullable en rmazh). No viajan:
`print_jobs` (bitacora de impresion), `parked_tickets` (tickets en espera) ni
`organization_modules` (en Atlas ONE los pone el preset del giro).
"""
import base64
import datetime as _dt
import decimal
import gzip
import json
import sys
import uuid

from sqlalchemy import text

from app.database import engine

ORG = int(sys.argv[1])

DOCS = "select id from sales_documents where organization_id=:o"
PRODS = "select id from products where organization_id=:o"
VARS = (
    "select id from product_variants where organization_id=:o "
    f"or product_id in ({PRODS})"
)
SUCS = "select id from branches where organization_id=:o"
CAJAS = (
    "select id from cash_sessions where organization_id=:o "
    f"or branch_id in ({SUCS})"
)
DEVS = "select id from sale_returns where organization_id=:o"
USUARIOS = "select user_id from user_organizations where organization_id=:o"

# (tabla, WHERE). El orden no importa aqui: el importador inserta por dependencias.
TABLAS = [
    ("organization", "id=:o"),
    ("branches", "organization_id=:o"),
    ("users", f"id in ({USUARIOS})"),
    ("user_organizations", "organization_id=:o"),
    ("employees", "organization_id=:o"),
    ("customers", "organization_id=:o"),
    ("departments", "organization_id=:o"),
    ("brands", "organization_id=:o"),
    ("products", "organization_id=:o"),
    ("product_variants", f"organization_id=:o or product_id in ({PRODS})"),
    ("product_prices", f"organization_id=:o or variant_id in ({VARS})"),
    ("packaging_units", f"organization_id=:o or variant_id in ({VARS})"),
    ("product_branch_status", f"organization_id=:o or variant_id in ({VARS})"),
    ("stock_on_hand", f"organization_id=:o or branch_id in ({SUCS})"),
    ("cash_sessions", f"organization_id=:o or branch_id in ({SUCS})"),
    ("cash_movements", f"session_id in ({CAJAS})"),
    ("cash_audit_log", f"organization_id=:o or session_id in ({CAJAS})"),
    ("sales_documents", "organization_id=:o"),
    ("sales_lines", f"organization_id=:o or document_id in ({DOCS})"),
    ("payments", f"organization_id=:o or sales_document_id in ({DOCS})"),
    ("sale_returns", "organization_id=:o"),
    ("sale_return_items", f"organization_id=:o or return_id in ({DEVS})"),
    ("inventory_movements", f"organization_id=:o or branch_id in ({SUCS})"),
]


def _valor(v):
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return None
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value  # enums de Python
    return v


def main():
    salida = {
        "org_id": ORG,
        "exportado": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "tablas": {},
    }
    with engine.connect() as c:
        for tabla, where in TABLAS:
            filas = c.execute(text(f"select * from {tabla} where {where}"), {"o": ORG})
            salida["tablas"][tabla] = [
                {k: _valor(v) for k, v in fila._mapping.items()} for fila in filas
            ]
    crudo = gzip.compress(json.dumps(salida, ensure_ascii=False).encode("utf-8"))
    for tabla, filas in salida["tablas"].items():
        print(f"CONTEO {tabla} {len(filas)}")
    print("###RMAZH_ORG_B64###")
    print(base64.b64encode(crudo).decode("ascii"))
    print("###FIN###")


main()
