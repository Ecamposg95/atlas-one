"""Configuracion de la comision de tarjeta: lectura para cualquiera de la org,
escritura solo ADMINISTRADOR/DUEÑO."""
from decimal import Decimal


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestLectura:
    def test_la_organizacion_arranca_apagada(self, client, org, auth_cajero_a):
        # Neutralidad: ninguna de las organizaciones vivas ve nada nuevo.
        r = client.get("/api/organization/card-surcharge", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert Decimal(str(r.json()["pct"])) == Decimal("0")

    def test_la_cajera_puede_leer_el_porcentaje(self, client, db, org, auth_cajero_a):
        # Lo consume el POS, y ahi no hay administradores.
        org.card_surcharge_pct = Decimal("3.5")
        db.commit()
        r = client.get("/api/organization/card-surcharge", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert Decimal(str(r.json()["pct"])) == Decimal("3.50")


class TestEscritura:
    def test_admin_configura_el_porcentaje(self, client, db, org, auth_admin):
        r = client.put("/api/organization/", json={"card_surcharge_pct": "3.5"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert Decimal(str(r.json()["card_surcharge_pct"])) == Decimal("3.50")
        db.refresh(org)
        assert Decimal(str(org.card_surcharge_pct)) == Decimal("3.50")

    def test_cero_apaga_la_funcion(self, client, db, org, auth_admin):
        org.card_surcharge_pct = Decimal("3.5")
        db.commit()
        r = client.put("/api/organization/", json={"card_surcharge_pct": "0"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert Decimal(str(org.card_surcharge_pct)) == Decimal("0")

    def test_negativo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"card_surcharge_pct": "-1"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text

    def test_porcentaje_absurdo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"card_surcharge_pct": "35"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422
        assert "20" in str(r.json()["detail"])

    def test_null_no_borra_la_columna(self, client, db, org, auth_admin):
        # La columna es NOT NULL: un panel que mande el objeto completo con el
        # campo en null no puede dejar la venta sin poder cobrarse (500).
        org.card_surcharge_pct = Decimal("3.5")
        db.commit()
        r = client.put("/api/organization/", json={"card_surcharge_pct": None},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert Decimal(str(org.card_surcharge_pct)) == Decimal("3.50")

    def test_cajero_no_puede_configurar(self, client, org, auth_cajero_a):
        r = client.put("/api/organization/", json={"card_surcharge_pct": "3.5"},
                       headers=_h(auth_cajero_a, org))
        assert r.status_code == 403

    def test_guardar_otro_campo_no_toca_la_comision(self, client, db, org, auth_admin):
        # El panel manda el objeto completo al guardar la razon social: eso NO
        # debe disparar la validacion ni cambiar el porcentaje.
        r = client.put("/api/organization/", json={"name": "Otra Razon"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert Decimal(str(org.card_surcharge_pct)) == Decimal("0")
