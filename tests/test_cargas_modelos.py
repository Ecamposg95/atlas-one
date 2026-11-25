"""Tablas de cargas y reglas_carga por organización."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.ai.limpieza import borrar_datos_ai_de_org
from app.modules.cargas.models import (
    CargaArchivo, CargaCambio, CargaDuda, CargaMercancia, CargaRenglon,
)
from app.modules.cargas.reglas import reglas_de_la_org


def _carga(db, org, folio=1):
    c = CargaMercancia(organization_id=org.id, folio=folio, archivo_nombre="lista.xlsx")
    db.add(c)
    db.flush()
    return c


def test_tablas_se_crean_y_fk_uuid_son_string36(db, org):
    assert CargaRenglon.__table__.c.carga_id.type.length == 36
    c = _carga(db, org)
    assert len(c.id) == 36
    assert c.estado == "leyendo" and c.proposito == "entrada"
    db.add(CargaRenglon(organization_id=org.id, carga_id=c.id, orden=1, cantidad=2))
    db.flush()


def test_folio_unico_por_org(db, org):
    _carga(db, org, folio=7)
    with pytest.raises(IntegrityError):
        _carga(db, org, folio=7)


def test_reglas_vacias_dan_defaults(org):
    r = reglas_de_la_org(org)
    assert r.costo_si_falta == "preguntar"
    assert r.ventana_ya_cargado_dias == 14


def test_reglas_invalidas_dan_422(client, auth_admin_a):
    r = client.put("/api/organization/", json={"reglas_carga": {"costo_si_falta": "x"}}, headers=auth_admin_a)
    assert r.status_code == 422


@pytest.mark.parametrize("campo, valor", [
    ("fraccion", "0"), ("fraccion", "-0.1"), ("fraccion", "1.5"),
    ("ventana_ya_cargado_dias", -1), ("ventana_ya_cargado_dias", 91),
])
def test_reglas_fuera_de_rango_dan_422_con_el_campo(client, auth_admin_a, campo, valor):
    r = client.put("/api/organization/", json={"reglas_carga": {campo: valor}}, headers=auth_admin_a)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == campo


@pytest.mark.parametrize("campo, valor", [("fraccion", "1"), ("fraccion", "0.01"),
                                          ("ventana_ya_cargado_dias", 0),
                                          ("ventana_ya_cargado_dias", 90)])
def test_reglas_en_los_bordes_se_aceptan(client, auth_admin_a, campo, valor):
    r = client.put("/api/organization/", json={"reglas_carga": {campo: valor}}, headers=auth_admin_a)
    assert r.status_code == 200, r.text


def test_reglas_validas_se_guardan_y_se_leen(client, auth_admin_a, db, org):
    r = client.put(
        "/api/organization/",
        json={"reglas_carga": {"costo_si_falta": "fraccion_precio", "fraccion": "0.6"}},
        headers=auth_admin_a,
    )
    assert r.status_code == 200, r.text
    assert r.json()["reglas_carga"]["costo_si_falta"] == "fraccion_precio"
    db.refresh(org)
    assert str(reglas_de_la_org(org).fraccion) == "0.6"


def test_limpieza_borra_cargas_de_la_org(db, org):
    c = _carga(db, org)
    db.add(CargaArchivo(organization_id=org.id, carga_id=c.id, contenido=b"x"))
    db.add(CargaRenglon(organization_id=org.id, carga_id=c.id, orden=1, cantidad=1))
    db.add(CargaDuda(organization_id=org.id, carga_id=c.id, numero=1, tipo="t", texto="?"))
    db.add(CargaCambio(organization_id=org.id, carga_id=c.id, operaciones=[]))
    db.flush()
    borrar_datos_ai_de_org(db, org.id)
    for m in (CargaMercancia, CargaArchivo, CargaRenglon, CargaDuda, CargaCambio):
        assert db.query(m).filter(m.organization_id == org.id).count() == 0


def test_numeracion_unica_por_carga(db, org):
    """Respaldo de la numeración: en Postgres el candado lo evita, aquí lo frena la base."""
    c = _carga(db, org)
    otra = _carga(db, org, folio=2)
    filas = [
        (CargaRenglon, dict(orden=1, cantidad=1)),
        (CargaDuda, dict(numero=1, tipo="t", texto="?")),
        (CargaCambio, dict(secuencia=1, operaciones=[])),
    ]
    for modelo, datos in filas:
        db.add(modelo(organization_id=org.id, carga_id=c.id, **datos))
        db.add(modelo(organization_id=org.id, carga_id=otra.id, **datos))  # otra carga: sí
        db.flush()
        sp = db.begin_nested()
        db.add(modelo(organization_id=org.id, carga_id=c.id, **datos))
        with pytest.raises(IntegrityError):
            db.flush()
        sp.rollback()
