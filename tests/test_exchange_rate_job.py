"""Job diario del FIX: idempotencia, horario y doble apagado. HTTP parcheado."""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core import exchange_rate_job as job
from app.models.exchange_rate import ExchangeRate
from app.services.banxico import BanxicoError

TZ_MX = ZoneInfo("America/Mexico_City")


def test_guarda_el_fix_una_sola_vez_por_dia(db, monkeypatch):
    monkeypatch.setattr(job, "fetch_fix", lambda token: (date(2026, 9, 17), Decimal("18.2345")))
    assert job.actualizar_fix_ahora(db, "tok")[0] is True
    monkeypatch.setattr(job, "fetch_fix", lambda token: (date(2026, 9, 17), Decimal("18.9999")))
    assert job.actualizar_fix_ahora(db, "tok")[0] is True

    filas = db.query(ExchangeRate).filter(ExchangeRate.rate_date == date(2026, 9, 17)).all()
    assert len(filas) == 1
    assert filas[0].rate == Decimal("18.9999")  # la segunda corrida actualiza


def test_banxico_caido_no_lanza_y_no_escribe(db, monkeypatch):
    def _revienta(token):
        raise BanxicoError("SIE caido")

    monkeypatch.setattr(job, "fetch_fix", _revienta)
    ok, mensaje = job.actualizar_fix_ahora(db, "tok")
    assert ok is False
    assert "SIE caido" in mensaje
    assert db.query(ExchangeRate).count() == 0


def test_hay_fix_de_hoy(db):
    assert job.hay_fix_de_hoy(db) is False
    db.add(ExchangeRate(currency="USD", rate_date=datetime.now(TZ_MX).date(),
                        rate=Decimal("18.20")))
    db.flush()
    assert job.hay_fix_de_hoy(db) is True


class TestHorario:
    def test_antes_de_las_1230_espera_hoy(self):
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 9, 0, tzinfo=TZ_MX)
        ) == 3.5 * 3600

    def test_despues_de_las_1230_espera_mañana(self):
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 13, 0, tzinfo=TZ_MX)
        ) == 23.5 * 3600

    def test_nunca_duerme_cero(self):
        # Justo en la hora: el siguiente tick es el de mañana, no un bucle
        # apretado quemando CPU.
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 12, 30, tzinfo=TZ_MX)
        ) == 24 * 3600


def test_apagado_en_sqlite(monkeypatch):
    # La suite corre en SQLite: arrancar el job aqui dejaria un task de fondo
    # tocando la base entre pruebas (mismo motivo que el worker del outbox).
    monkeypatch.setenv("BANXICO_TOKEN", "abc123")
    assert job.start_exchange_rate_job() is None


def test_apagado_sin_token(monkeypatch):
    monkeypatch.setattr(job, "_IS_SQLITE", False)
    monkeypatch.delenv("BANXICO_TOKEN", raising=False)
    assert job.start_exchange_rate_job() is None
