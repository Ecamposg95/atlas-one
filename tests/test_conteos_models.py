"""Las tablas del conteo existen y aceptan una sesión con sus líneas."""
from decimal import Decimal


def test_tablas_del_conteo_se_crean_y_guardan(db, org, branch_a):
    from app.modules.conteos.models import ABIERTO, InventoryCount, InventoryCountLine

    c = InventoryCount(organization_id=org.id, branch_id=branch_a.id, status=ABIERTO)
    db.add(c)
    db.flush()
    db.add(InventoryCountLine(organization_id=org.id, count_id=c.id, codigo="XYZ",
                              qty_contada=Decimal("2")))
    db.commit()
    db.refresh(c)
    assert c.status == "ABIERTO"
    assert len(c.lineas) == 1 and c.lineas[0].codigo == "XYZ"
