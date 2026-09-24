"""El servidor resuelve las capacidades; la pantalla no hace cuentas de módulos."""
from app.models.modules import Module, OrganizationModule


def _prender(db, org, clave):
    if db.query(Module).filter(Module.key == clave).first() is None:
        db.add(Module(key=clave, name=clave))
        db.flush()
    fila = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == clave,
    ).first()
    if fila is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=clave, is_enabled=True))
    else:
        fila.is_enabled = True
    db.commit()


def test_sin_el_modulo_no_hay_capacidad(client, auth_admin, org):
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert "propina" not in r.json()["capacidades"]


def test_con_el_modulo_aparece_la_capacidad(client, db, auth_admin, org):
    _prender(db, org, "tips")
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert "propina" in r.json()["capacidades"]


def test_el_contexto_sigue_trayendo_modulos_y_preset(client, auth_admin, org):
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert "enabled_modules" in cuerpo and "preset" in cuerpo
