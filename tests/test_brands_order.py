"""GET /api/brands/ debe regresar las marcas en orden alfabetico,
insensible a mayusculas/minusculas (el formulario de producto las usa
para poblar un <select> y el dueño las espera ordenadas)."""


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def test_las_marcas_regresan_en_orden_alfabetico_case_insensitive(client, db, org, auth_admin):
    from app.modules.products.models import Brand

    for name in ["zapatos", "Bolsas", "abrigos"]:
        db.add(Brand(name=name, organization_id=org.id))
    db.commit()

    r = client.get("/api/brands/", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text

    names = [b["name"] for b in r.json()]
    assert names == ["abrigos", "Bolsas", "zapatos"]
