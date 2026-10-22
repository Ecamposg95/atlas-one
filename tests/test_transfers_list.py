"""Regresión: /api/transfers/ devolvía 500 porque `TransferOrderRead.updated_at` era
obligatorio y el modelo solo lo llena en `onupdate` (una orden recién creada lo tiene
en NULL). Afectaba al GET y al POST (la orden quedaba creada tras el commit y el
cliente veía error, con riesgo de duplicarla al reintentar)."""
from app.models.logistics import TransferOrder, TransferStatus
from app.modules.products.models import Product, ProductVariant


def test_lista_transferencias_recien_creadas(client, auth_admin, db, org, branch_a):
    db.add(TransferOrder(organization_id=org.id, requesting_branch_id=branch_a.id, status=TransferStatus.REQUESTED, notes="x"))
    db.commit()
    r = client.get("/api/transfers/", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert any(t["notes"] == "x" and t["updated_at"] is None for t in r.json())


def test_crear_transferencia_responde_200(client, auth_admin, db, org, branch_a):
    p = Product(name="Playera", organization_id=org.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="PLA-1-M", price=100, organization_id=org.id)
    db.add(v)
    db.commit()
    r = client.post("/api/transfers/", headers=auth_admin,
                    json={"requesting_branch_id": branch_a.id, "notes": "urgente", "lines": [{"variant_id": v.id, "qty_requested": 3}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "REQUESTED" and r.json()["updated_at"] is None
