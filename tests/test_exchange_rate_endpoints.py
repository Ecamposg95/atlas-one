"""Endpoints del tipo de cambio: lectura para cualquiera de la org, escritura
solo ADMINISTRADOR/DUEÑO, refresco manual con Banxico parcheado."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.exchange_rate import ExchangeRate


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def fix_de_hoy(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17),
                        rate=Decimal("18.2000"), source="banxico"))
    db.flush()


class TestLectura:
    def test_organizacion_apagada_no_devuelve_tipo(self, client, org, fix_de_hoy, auth_cajero_a):
        r = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "off"
        assert r.json()["rate"] is None

    def test_modo_auto_suma_el_margen(self, client, db, org, fix_de_hoy, auth_cajero_a):
        org.usd_rate_mode = "auto"
        org.usd_rate_margin = Decimal("0.30")
        db.flush()
        data = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org)).json()
        assert Decimal(str(data["rate"])) == Decimal("18.5000")
        assert data["source"] == "banxico"
        assert Decimal(str(data["fix_rate"])) == Decimal("18.2000")
        assert data["fix_date"] == "2026-09-17"

    def test_modo_manual(self, client, db, org, fix_de_hoy, auth_cajero_a):
        org.usd_rate_mode = "manual"
        org.usd_rate_manual = Decimal("19.5000")
        db.flush()
        data = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org)).json()
        assert Decimal(str(data["rate"])) == Decimal("19.5000")
        assert data["source"] == "manual"
        assert Decimal(str(data["manual_rate"])) == Decimal("19.5000")

    def test_auto_sin_fix_no_revienta(self, client, db, org, auth_cajero_a):
        org.usd_rate_mode = "auto"
        db.flush()
        r = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert r.json()["rate"] is None


class TestEscritura:
    def test_admin_configura_modo_auto(self, client, db, org, auth_admin):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "auto", "usd_rate_margin": "0.30"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "auto"
        assert Decimal(str(org.usd_rate_margin)) == Decimal("0.30")

    def test_el_modo_se_guarda_en_minusculas(self, client, db, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "AUTO"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "auto"

    def test_manual_sin_tipo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "manual"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text

    def test_modo_desconocido_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "euros"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_margen_absurdo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "auto", "usd_rate_margin": "80"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_cajero_no_puede_configurar(self, client, org, auth_cajero_a):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "manual", "usd_rate_manual": "19.5"},
                       headers=_h(auth_cajero_a, org))
        assert r.status_code == 403

    def test_guardar_otro_campo_no_toca_el_tipo_de_cambio(self, client, db, org, auth_admin):
        # Neutralidad: el panel manda el objeto completo al guardar la razon
        # social, y eso NO debe disparar la validacion ni cambiar el modo.
        r = client.put("/api/organization/", json={"name": "Otra Razon"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "off"


class TestRefrescoManual:
    def test_sin_token_es_503(self, client, org, auth_admin, monkeypatch):
        monkeypatch.delenv("BANXICO_TOKEN", raising=False)
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 503

    def test_admin_refresca_y_guarda(self, client, db, org, auth_admin, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        from app.core import exchange_rate_job as job
        monkeypatch.setattr(job, "fetch_fix",
                            lambda token: (date(2026, 9, 17), Decimal("18.4321")))
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["rate_date"] == "2026-09-17"
        assert db.query(ExchangeRate).filter(
            ExchangeRate.rate_date == date(2026, 9, 17)
        ).count() == 1

    def test_banxico_caido_es_503(self, client, org, auth_admin, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        from app.core import exchange_rate_job as job
        from app.services.banxico import BanxicoError

        def _revienta(token):
            raise BanxicoError("SIE caido")

        monkeypatch.setattr(job, "fetch_fix", _revienta)
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 503

    def test_cajero_no_puede_refrescar(self, client, org, auth_cajero_a, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_cajero_a, org))
        assert r.status_code == 403
