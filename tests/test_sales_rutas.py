"""Dos rutas rotas por accidente: `POST /api/sales` sin barra caía en una función
auxiliar (422 "query.variant required") y `GET /hq/sales` redirigía a una ruta
de React que ya no existe ("Página no encontrada" al refrescar)."""


def test_post_sales_sin_barra_llega_a_create_sale(client, org, auth_admin_a):
    # ADMINISTRADOR salta el gating de módulo (app/core/permissions.py), así no hace falta habilitar `pos`.
    r = client.post("/api/sales", json={"items": [], "payments": []},
                    headers={**auth_admin_a, "X-Organization-ID": str(org.id)})
    # create_sale responde 400 "El ticket está vacío"; antes era 422 por un query param inexistente.
    assert r.status_code == 400, r.text
    assert "vacío" in r.json()["detail"]


def test_hq_sales_no_redirige_a_ruta_muerta(client):
    r = client.get("/hq/sales", follow_redirects=False)
    assert r.status_code != 302 or r.headers.get("location") != "/hq/sales-log"
