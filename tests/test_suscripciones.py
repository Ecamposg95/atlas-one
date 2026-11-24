"""Cobro de suscripciones (megaplan F3): cálculo de estado y servicios."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.platform import PlatformAuditLog
from app.modules.suscripciones import services as s
from app.modules.suscripciones.models import (
    AL_CORRIENTE, ANUAL, CANCELADO, CORTESIA, MENSUAL, PAGADO, PENDIENTE, POR_VENCER,
    SUSPENDIDA, VENCIDA, CargoSuscripcion, PagoSuscripcion,
)

HOY = date(2026, 11, 24)


def _estado(guardado=AL_CORRIENTE, precio="499", renovacion=date(2026, 12, 15), cargos=(), hoy=HOY):
    return s.calcular_estado(
        estado_guardado=guardado, precio=Decimal(precio), proxima_renovacion=renovacion,
        cargos=[s.CargoResumen(e, v) for e, v in cargos], hoy=hoy,
    )


class TestCalcularEstado:
    def test_renovacion_lejana_sin_cargos_al_corriente(self):
        assert _estado() == AL_CORRIENTE

    def test_renovacion_dentro_del_aviso_por_vencer(self):
        assert _estado(renovacion=date(2026, 12, 1)) == POR_VENCER      # justo a 7 días
        assert _estado(renovacion=date(2026, 12, 2)) == AL_CORRIENTE    # a 8
        assert _estado(renovacion=HOY) == POR_VENCER                    # vence hoy: aún no vencida

    def test_renovacion_pasada_sin_cargo_vencida(self):
        assert _estado(renovacion=date(2026, 11, 23)) == VENCIDA

    def test_cargo_pendiente_vencido_gana_a_la_renovacion(self):
        assert _estado(cargos=[(PENDIENTE, date(2026, 11, 20))]) == VENCIDA

    def test_cargo_pendiente_con_plazo_manda_sobre_renovacion_pasada(self):
        # La renovación ya pasó pero el cargo tiene plazo hasta diciembre.
        assert _estado(renovacion=date(2026, 11, 15), cargos=[(PENDIENTE, date(2026, 11, 28))]) == POR_VENCER
        assert _estado(renovacion=date(2026, 11, 15), cargos=[(PENDIENTE, date(2026, 12, 20))]) == AL_CORRIENTE

    def test_cargos_pagados_y_cancelados_no_cuentan(self):
        cargos = [(PAGADO, date(2026, 10, 1)), (CANCELADO, date(2026, 9, 1))]
        assert _estado(cargos=cargos) == AL_CORRIENTE

    def test_el_mas_atrasado_decide(self):
        cargos = [(PENDIENTE, date(2026, 12, 30)), (PENDIENTE, date(2026, 11, 1))]
        assert _estado(cargos=cargos) == VENCIDA

    @pytest.mark.parametrize("manual", [SUSPENDIDA, CORTESIA])
    def test_estado_manual_gana(self, manual):
        assert _estado(guardado=manual, renovacion=date(2026, 1, 1),
                       cargos=[(PENDIENTE, date(2026, 1, 1))]) == manual

    def test_precio_cero_siempre_al_corriente(self):
        assert _estado(precio="0", renovacion=date(2026, 1, 1)) == AL_CORRIENTE

    def test_foto_vieja_no_se_arrastra(self):
        # Lo guardado solo manda si es manual: una "vencida" vieja se recalcula.
        assert _estado(guardado=VENCIDA) == AL_CORRIENTE


class TestSiguienteCorte:
    def test_mensual(self):
        assert s.siguiente_corte(date(2026, 11, 15), MENSUAL, 15) == date(2026, 12, 15)

    def test_mensual_cruza_el_anio(self):
        assert s.siguiente_corte(date(2026, 12, 28), MENSUAL, 28) == date(2027, 1, 28)

    def test_anual(self):
        assert s.siguiente_corte(date(2026, 11, 15), ANUAL, 15) == date(2027, 11, 15)

    def test_inicio_fuera_del_dia_de_corte_se_alinea(self):
        assert s.siguiente_corte(date(2026, 11, 3), MENSUAL, 15) == date(2026, 12, 15)

    def test_precio_mensual_del_anual(self):
        assert s.precio_mensual(Decimal("12000"), ANUAL) == Decimal("1000.00")
        assert s.precio_mensual(Decimal("499"), MENSUAL) == Decimal("499.00")


# ───────────── Servicios (con base) ─────────────

@pytest.fixture()
def sus(db, org, superadmin):
    org.plan = "START"
    db.flush()
    sub, creada = s.guardar_suscripcion(
        db, org, {"fecha_inicio": date(2026, 11, 15)}, superadmin.id, hoy=date(2026, 11, 15),
    )
    assert creada
    return sub


def _acciones(db, org):
    db.flush()
    return [a.action for a in db.query(PlatformAuditLog)
            .filter(PlatformAuditLog.entity_type == "SUSCRIPCION", PlatformAuditLog.entity_id == str(org.id))
            .order_by(PlatformAuditLog.id)]


class TestAlta:
    def test_valores_por_omision(self, db, org, sus):
        assert sus.plan == "START"
        assert sus.precio_mxn == Decimal("499.00")       # el de lista
        assert sus.periodicidad == MENSUAL
        assert sus.dia_corte == 15
        assert sus.proxima_renovacion == date(2026, 11, 15)
        assert _acciones(db, org) == ["SUSCRIPCION_ALTA"]

    def test_una_sola_por_organizacion(self, db, org, sus, superadmin):
        otra, creada = s.guardar_suscripcion(db, org, {"precio_mxn": Decimal("350")}, superadmin.id, hoy=HOY)
        assert not creada and otra.id == sus.id
        assert sus.precio_mxn == Decimal("350.00")
        assert _acciones(db, org)[-1] == "SUSCRIPCION_EDICION"

    def test_validaciones(self, db, org, sus, superadmin):
        for datos in ({"periodicidad": "semanal"}, {"dia_corte": 31}, {"estado": "morosa"},
                      {"precio_mxn": Decimal("-1")}):
            with pytest.raises(s.ErrorSuscripcion):
                s.guardar_suscripcion(db, org, datos, superadmin.id, hoy=HOY)

    def test_estado_manual_y_regreso_a_automatico(self, db, org, sus, superadmin):
        s.guardar_suscripcion(db, org, {"estado": SUSPENDIDA}, superadmin.id, hoy=HOY)
        assert sus.estado == SUSPENDIDA
        assert s.estado_de(sus, [], HOY) == SUSPENDIDA
        s.guardar_suscripcion(db, org, {"estado": AL_CORRIENTE}, superadmin.id, hoy=HOY)
        # La renovación (15-nov) ya pasó y no hay pago: el cálculo dice vencida.
        assert sus.estado == VENCIDA


class TestPlan:
    def test_cambiar_plan_sincroniza_la_organizacion(self, db, org, sus, superadmin):
        s.guardar_suscripcion(db, org, {"plan": "PRO"}, superadmin.id, hoy=HOY)
        assert sus.plan == "PRO" and org.plan == "PRO"
        assert sus.precio_mxn == Decimal("499.00")   # el pactado no se mueve solo
        assert "SUSCRIPCION_CAMBIO_PLAN" in _acciones(db, org)

    def test_plan_desconocido(self, db, org, sus, superadmin):
        with pytest.raises(s.ErrorSuscripcion) as e:
            s.guardar_suscripcion(db, org, {"plan": "PLATINO"}, superadmin.id, hoy=HOY)
        assert e.value.status == 400
        assert org.plan == "START"

    def test_alta_con_plan_distinto_mueve_la_organizacion(self, db, org, superadmin):
        org.plan = "FREE"
        sub, _ = s.guardar_suscripcion(db, org, {"plan": "BUSINESS"}, superadmin.id, hoy=HOY)
        assert org.plan == "BUSINESS" and sub.precio_mxn == Decimal("5000.00")


class TestCargo:
    def test_genera_el_periodo_de_la_renovacion(self, db, org, sus, superadmin):
        cargo, creado = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        assert creado
        assert (cargo.periodo_desde, cargo.periodo_hasta) == (date(2026, 11, 15), date(2026, 12, 14))
        assert cargo.importe == Decimal("499.00") and cargo.vence_el == date(2026, 11, 15)
        assert cargo.estado == PENDIENTE
        assert sus.estado == VENCIDA   # vencía el 15 y hoy es 24

    def test_idempotente(self, db, org, sus, superadmin):
        uno, c1 = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        dos, c2 = s.generar_cargo(db, sus, superadmin.id, importe=Decimal("999"), hoy=HOY)
        assert c1 and not c2 and uno.id == dos.id
        assert dos.importe == Decimal("499.00")   # el existente no se toca
        assert db.query(CargoSuscripcion).filter_by(organization_id=org.id).count() == 1
        assert _acciones(db, org).count("SUSCRIPCION_CARGO") == 1

    def test_restriccion_unica_en_la_base(self, db, org, sus, superadmin):
        from sqlalchemy.exc import IntegrityError
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(CargoSuscripcion(
                    organization_id=org.id, suscripcion_id=sus.id, periodo_desde=cargo.periodo_desde,
                    periodo_hasta=cargo.periodo_hasta, importe=Decimal("1"), vence_el=HOY,
                ))
                db.flush()

    def test_periodo_explicito_e_importe(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, periodo_desde=date(2026, 12, 15),
                                   importe=Decimal("300.50"), vence_el=date(2026, 12, 20), hoy=HOY)
        assert cargo.periodo_hasta == date(2027, 1, 14)
        assert cargo.importe == Decimal("300.50") and cargo.vence_el == date(2026, 12, 20)

    def test_anual(self, db, org, sus, superadmin):
        s.guardar_suscripcion(db, org, {"periodicidad": ANUAL, "precio_mxn": Decimal("4990")}, superadmin.id, hoy=HOY)
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        assert cargo.periodo_hasta == date(2027, 11, 14) and cargo.importe == Decimal("4990.00")

    def test_precio_cero_no_genera_cargo(self, db, org, sus, superadmin):
        s.guardar_suscripcion(db, org, {"precio_mxn": Decimal("0")}, superadmin.id, hoy=HOY)
        with pytest.raises(s.ErrorSuscripcion):
            s.generar_cargo(db, sus, superadmin.id, hoy=HOY)

    def test_cancelar_y_reabrir(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.cancelar_cargo(db, cargo, superadmin.id, "se cobró de más", hoy=HOY)
        assert cargo.estado == CANCELADO and cargo.motivo_cancelacion == "se cobró de más"
        assert "SUSCRIPCION_CARGO_CANCELADO" in _acciones(db, org)
        otro, creado = s.generar_cargo(db, sus, superadmin.id, importe=Decimal("400"), hoy=HOY)
        assert creado and otro.id == cargo.id and otro.estado == PENDIENTE
        assert otro.importe == Decimal("400.00") and otro.cancelado_at is None

    def test_no_se_cancela_con_pagos(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("100"), metodo="efectivo", hoy=HOY)
        with pytest.raises(s.ErrorSuscripcion) as e:
            s.cancelar_cargo(db, cargo, superadmin.id, hoy=HOY)
        assert e.value.status == 409


class TestPago:
    def test_parcial_no_liquida(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        pago = s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("200"), metodo="transferencia",
                                referencia="SPEI 123", hoy=HOY)
        assert pago.registrado_por_user_id == superadmin.id and pago.referencia == "SPEI 123"
        assert cargo.estado == PENDIENTE
        assert s.saldo_de(cargo) == Decimal("299.00")
        assert sus.proxima_renovacion == date(2026, 11, 15)   # no avanza
        assert sus.estado == VENCIDA

    def test_dos_parciales_liquidan_y_avanzan_la_renovacion(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("200"), metodo="deposito", hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("299"), metodo="efectivo", hoy=HOY)
        assert cargo.estado == PAGADO and cargo.pagado_at is not None
        assert s.saldo_de(cargo) == Decimal("0.00")
        assert sus.proxima_renovacion == date(2026, 12, 15)
        assert sus.estado == AL_CORRIENTE
        assert db.query(PagoSuscripcion).filter_by(cargo_id=cargo.id).count() == 2
        assert _acciones(db, org).count("SUSCRIPCION_PAGO") == 2

    def test_total_de_un_golpe(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("499"), metodo="tarjeta", hoy=HOY)
        assert cargo.estado == PAGADO and sus.proxima_renovacion == date(2026, 12, 15)

    def test_no_admite_sobrepago_ni_ceros_ni_metodo_raro_ni_fecha_futura(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        casos = [
            dict(importe=Decimal("499.01"), metodo="efectivo"),
            dict(importe=Decimal("0"), metodo="efectivo"),
            dict(importe=Decimal("10"), metodo="bitcoin"),
            dict(importe=Decimal("10"), metodo="efectivo", fecha_pago=date(2026, 11, 25)),
        ]
        for caso in casos:
            with pytest.raises(s.ErrorSuscripcion):
                s.registrar_pago(db, cargo, superadmin.id, hoy=HOY, **caso)
        assert db.query(PagoSuscripcion).filter_by(cargo_id=cargo.id).count() == 0

    def test_cargo_pagado_o_cancelado_no_admite_pagos(self, db, org, sus, superadmin):
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("499"), metodo="efectivo", hoy=HOY)
        with pytest.raises(s.ErrorSuscripcion) as e:
            s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("1"), metodo="efectivo", hoy=HOY)
        assert e.value.status == 409

    def test_pagar_un_cargo_viejo_no_retrocede_la_renovacion(self, db, org, sus, superadmin):
        viejo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)                       # 15-nov → 14-dic
        nuevo, _ = s.generar_cargo(db, sus, superadmin.id, periodo_desde=date(2026, 12, 15), hoy=HOY)
        s.registrar_pago(db, nuevo, superadmin.id, importe=Decimal("499"), metodo="efectivo", hoy=HOY)
        assert sus.proxima_renovacion == date(2027, 1, 15)
        s.registrar_pago(db, viejo, superadmin.id, importe=Decimal("499"), metodo="efectivo", hoy=HOY)
        assert sus.proxima_renovacion == date(2027, 1, 15)


class TestCartera:
    def test_totales(self, db, org, sus, superadmin):
        from app.models.organization import Organization
        # org: START $499, cargo vencido con $200 abonados → vencida, saldo 299.
        cargo, _ = s.generar_cargo(db, sus, superadmin.id, hoy=HOY)
        s.registrar_pago(db, cargo, superadmin.id, importe=Decimal("200"), metodo="efectivo", hoy=HOY)
        # otra: anual $12,000 al corriente → MRR 1,000, con un cargo que aún no vence.
        otra = Organization(name="Otra SA", status="ACTIVE", plan="PRO")
        db.add(otra); db.flush()
        sub2, _ = s.guardar_suscripcion(db, otra, {
            "precio_mxn": Decimal("12000"), "periodicidad": ANUAL, "fecha_inicio": date(2026, 1, 10),
            "proxima_renovacion": date(2027, 1, 10),
        }, superadmin.id, hoy=HOY)
        s.generar_cargo(db, sub2, superadmin.id, hoy=HOY)
        # cortesía: no suma al ingreso recurrente.
        regalo = Organization(name="Regalo", status="ACTIVE", plan="PRO")
        db.add(regalo); db.flush()
        s.guardar_suscripcion(db, regalo, {"estado": CORTESIA}, superadmin.id, hoy=HOY)
        sin = Organization(name="Sin suscripción", status="ACTIVE")
        db.add(sin); db.flush()

        c = s.cartera(db, hoy=HOY)
        propias = {f.organizacion.id: f for f in c.filas if f.organizacion.id in (org.id, otra.id, regalo.id)}
        assert propias[org.id].estado == VENCIDA and propias[org.id].saldo_vencido == Decimal("299.00")
        assert propias[otra.id].estado == AL_CORRIENTE and propias[otra.id].saldo_por_vencer == Decimal("12000.00")
        assert propias[regalo.id].estado == CORTESIA
        assert c.cartera_vencida == Decimal("299.00")
        assert c.por_vencer == Decimal("12000.00")
        assert c.ingreso_mensual_recurrente == Decimal("1000.00")
        assert c.por_estado[VENCIDA] == 1 and c.por_estado[CORTESIA] == 1 and c.por_estado[AL_CORRIENTE] == 1
        assert c.sin_suscripcion >= 1
