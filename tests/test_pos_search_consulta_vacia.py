"""La pantalla inicial del POS (q vacío, mas vendidos) no revienta para ningun rol.

Regresion vista en produccion el 2026-09-12: un ADMINISTRADOR con q="" recibia 500
("missing FROM-clause entry for table product_variants") porque el helper de
visibilidad no unia ProductVariant y el outerjoin a PackagingUnit la referenciaba."""
import pytest


@pytest.mark.parametrize("params", [
    {"q": "", "order_by": "best_sellers"},
    {"q": ""},
    {"q": "", "order_by": "best_sellers", "branch_id": None},
])
def test_pos_search_vacio_no_revienta(client, auth_admin, params):
    p = {k: v for k, v in params.items() if v is not None}
    r = client.get("/api/products/pos/search", params=p, headers=auth_admin)
    assert r.status_code == 200, r.text


def test_pos_search_vacio_tambien_para_cajero(client, auth_cajero_a):
    r = client.get("/api/products/pos/search", params={"q": "", "order_by": "best_sellers"}, headers=auth_cajero_a)
    assert r.status_code == 200, r.text


def test_pos_search_con_sucursal_que_no_vende_devuelve_lista_vacia(client, auth_cajero_a, db, branch_a):
    """Sucursal con can_sell=False: cero productos, NO 500 (visto en produccion 2026-09-13)."""
    branch_a.can_sell = False
    db.commit()
    for params in ({"q": "", "order_by": "best_sellers"}, {"q": "cascada"}):
        r = client.get("/api/products/pos/search", params=params, headers=auth_cajero_a)
        assert r.status_code == 200, r.text
        assert r.json() == []
