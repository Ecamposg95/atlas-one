"""Regresión: GET /api/transfers/ devolvía 500 porque `TransferOrderRead.updated_at`
era obligatorio y el modelo solo lo llena en `onupdate` (una orden recién creada
lo tiene en NULL)."""


def _login(client, username, password="admin123"):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_lista_transferencias_recien_creadas(client, auth_admin, db, org, branch_a):
    from app.models.logistics import TransferOrder, TransferStatus

    db.add(TransferOrder(organization_id=org.id, requesting_branch_id=branch_a.id, status=TransferStatus.REQUESTED, notes="x"))
    db.commit()
    r = client.get("/api/transfers/", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert any(t["notes"] == "x" and t["updated_at"] is None for t in r.json())
