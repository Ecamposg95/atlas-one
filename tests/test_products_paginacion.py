"""Paginación de GET /api/products/: orden fijo, sin repetir ni saltar productos."""
from tests.conftest import _make_product


def test_listado_pagina_en_orden_fijo_sin_perder_productos(client, auth_admin, db, org):
    nombres = ["Bolsa", "Abrigo", "Camisa", "Bolsa", "Zapato", "Gorra", "Pantalón"]
    for i, nombre in enumerate(nombres):
        _make_product(db, org, nombre, f"PAG-{i}", 100 + i)
    db.commit()

    ids, vistos, skip, total = [], [], 0, None
    while True:
        resp = client.get(f"/api/products/?skip={skip}&limit=2", headers=auth_admin)
        assert resp.status_code == 200
        cuerpo = resp.json()
        total = cuerpo["total"]
        items = cuerpo["items"]
        if not items:
            break
        ids += [p["id"] for p in items]
        vistos += [p["name"] for p in items]
        skip += 2

    assert total == len(nombres)
    assert len(ids) == len(set(ids)), "hay productos repetidos entre paginas"
    assert len(set(ids)) == total, "se saltaron productos entre paginas"
    assert vistos == sorted(vistos), "el listado no sale ordenado por nombre"
