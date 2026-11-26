"""Corre DENTRO de rmazh (Atlas-API). Apaga a los usuarios de la Taza; sin --ejecutar solo muestra."""
import sys
from sqlalchemy import text
from app.database import engine
IDS = (28, 29, 27)  # Fernanda, Ximena, America (con la Taza fuera, la org 5 de rmazh ya no vende)
ejecutar = "--ejecutar" in sys.argv
with engine.begin() as c:
    abiertas = c.execute(text("select id, user_id, opened_at from cash_sessions where branch_id = 18 and status = 'OPEN'")).fetchall()
    print("CAJAS ABIERTAS en la Taza:", abiertas or "ninguna")
    ultima = c.execute(text("select max(created_at) from sales_documents where branch_id = 18")).scalar()
    print("ultima venta de la Taza:", ultima)
    print("antes:", c.execute(text("select id, username, is_active from users where id in :i"), {"i": IDS}).fetchall())
    if ejecutar:
        c.execute(text("update users set is_active = false where id in :i"), {"i": IDS})
        print("despues:", c.execute(text("select id, username, is_active from users where id in :i"), {"i": IDS}).fetchall())
    else:
        print("ENSAYO: no se apago a nadie (usa --ejecutar)")
