# Comisión por pago con tarjeta — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una organización pueda configurar un porcentaje de comisión por pago con tarjeta (p. ej. 3.5 %) y que a partir de ese momento el POS, el ticket, el corte de caja y los reportes lo calculen, lo cobren y lo muestren por separado del total de la mercancía — aplicándolo solo a la parte que de verdad pasa por la terminal en un pago mixto. Si nadie lo configura, el porcentaje es 0 y no cambia absolutamente nada en ninguna pantalla, ningún ticket y ninguna respuesta de API.

**Architecture:** Una columna de política en `organization` (`card_surcharge_pct`); un servicio puro `app/services/card_surcharge.py` que es la **única** fuente del cálculo y del redondeo —igual que `app/services/tax.py` lo es del IVA y `app/services/exchange_rate.py` del tipo de cambio—; dos columnas de snapshot en `sales_documents` (`card_surcharge_pct`, `card_surcharge_amount`) que `create_sale` congela al cobrar; el `Payment` de `CARD` se guarda con la comisión incluida, de modo que el corte por método la refleja sin tocar `compute_expected_cash`; y en el frontend un endpoint barato con su store de Zustand más funciones puras en `src/pages/pos/cardSurcharge.ts` que solo pintan y proponen montos.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · Pydantic v2 · pytest (SQLite en memoria) · React 18 + TypeScript · Zustand · vitest · PostgreSQL

**Spec:** `docs/superpowers/specs/2026-09-17-comision-tarjeta-design.md`

## Global Constraints

- **`main` es producción con clientes vivos** (Kaory en Railway; Ginebra, Imaltzin y Eleven en el VPS). Trabajar en rama `feat/comision-tarjeta`; no pushear `main` sin permiso del usuario.
- **Neutralidad absoluta por default.** `card_surcharge_pct = 0` para toda organización existente. Ninguna pantalla, ningún ticket, ningún corte y ninguna respuesta de API cambia visiblemente hasta que un dueño la encienda. Cualquier paso que rompa esto está mal implementado.
- **`app/routers/sales.py::create_sale` es el motor ATS-crítico** (regla de oro #8). Este plan le toca **cuatro puntos**, todos con salida temprana cuando la comisión es cero: la organización que ya se consulta en la línea 513 se conserva en una variable, se calcula `total_a_cobrar` junto a `total_paid`, `cash_needed` y la validación H-1 pasan a usar `total_a_cobrar`, y el documento guarda dos columnas nuevas. No se toca el folio, ni el stock, ni la caja, ni el outbox, ni `balance_diff` (la deuda a crédito sigue siendo por la mercancía).
- **`total_amount` NO cambia de significado.** Sigue siendo mercancía (+ IVA + propina). La comisión vive en su propia columna. Si un paso suma la comisión a `total_amount`, está mal.
- **`app/services/cash_reconciliation.py::compute_expected_cash` NO se toca.** La comisión nunca es efectivo. La Task 3 incluye una prueba que lo demuestra.
- **Sin Alembic.** Columnas nuevas = `ALTER TABLE … ADD COLUMN` idempotente en la lista `migrations` de `scripts/railway_init.py` (tuplas `(tabla, columna, ddl)`, líneas 51-112), **más** el atributo en el modelo para que `create_all` la cree en bases nuevas y en la SQLite de las pruebas.
- **Suite backend verde antes de cada commit:** `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` — hoy, medido en `main` @ `959be7d`: **774 pasan, 2 se saltan, 3 xfail** en ~122 s, cero `failed`. El conteo de `failed` **no puede subir**.
- **Suite frontend verde**, desde `frontend/`: `npx vitest run` (hoy **32 archivos, 296 pruebas, todas pasan**), `npx tsc --noEmit` y `npm run build`.
- **Las pruebas de frontend son solo de funciones puras** (`vitest` con `environment: 'node'`, patrón `src/**/*.test.ts`). Toda lógica nueva que valga la pena probar se extrae a un `.ts` sin React.
- **`tests/test_cash_complete.py` hace `sys.exit(1)` al importar**: siempre correr la suite con `--ignore=tests/test_cash_complete.py`.
- **El ancho del ticket es una restricción dura.** `app/pos_printer.py::_total_line` da `label_w = cols - 12 = 20` en papel de 58 mm y **no trunca**: una etiqueta más larga desborda el papel. Por eso `card_surcharge_pct` es `NUMERIC(5,2)` y la etiqueta es `COM. TARJETA {pct}%` (≤ 19 caracteres + los dos puntos). Hay pruebas de ancho a 58 y 80 mm, como en `tests/test_ticket_usd.py`.
- **Estilo:** comentarios en español, Pydantic v2, type hints en firmas nuevas, `HTTPException` con `detail` accionable. Sin `print()` de depuración.
- Mensajes de commit terminan con las líneas `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

## Mapa de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `app/services/card_surcharge.py` (nuevo) | fuente única: `calcular_comision`, `ComisionTarjeta`, `pct_de_organizacion`, `hay_pago_con_tarjeta`, `validar_pct` |
| `app/modules/tenants/models.py` | columna `card_surcharge_pct` en `Organization` |
| `app/modules/tenants/schemas.py` | `OrganizationUpdate`/`OrganizationRead` con el campo; `CardSurchargeRead` |
| `app/modules/tenants/router.py` | validación en `PUT /`; `GET /card-surcharge` |
| `app/models/sales.py` | `sales_documents.card_surcharge_pct` y `.card_surcharge_amount` |
| `app/routers/sales.py` | cálculo y cobro en `create_sale`; respuesta; `SaleRead`; columnas del CSV |
| `app/schemas/sales.py` | `SaleRead` con los dos campos |
| `app/routers/cash.py` | `card_surcharges` en `get_session_audit_data` |
| `app/pos_printer.py` | `_card_surcharge_lines` en el ticket y en el reemitido; renglón en el corte |
| `scripts/railway_init.py` | tres `ALTER TABLE` idempotentes |
| `tests/test_pos_printer.py` | `_make_sale` declara las dos columnas |
| `frontend/src/pages/pos/cardSurcharge.ts` (nuevo) | `surchargeFor`, `formatPct` (puras) |
| `frontend/src/store/cardSurchargeStore.ts` (nuevo) | caché del porcentaje para el POS |
| `frontend/src/api/organization.ts` | `card_surcharge_pct` y `getCardSurcharge` |
| `frontend/src/api/sales.ts` | `SaleCreateResponse` con los dos campos |
| `frontend/src/types/sales.ts` | `SalesDocument` con los dos campos |
| `frontend/src/pages/pos/POS.tsx` | carga del porcentaje; monto de tarjeta con comisión |
| `frontend/src/components/pos/modals/CardPaymentModal.tsx` | desglose y total a pagar |
| `frontend/src/components/pos/modals/MixedPaymentModal.tsx` | desglose, total a pagar y «Completar con tarjeta» |
| `frontend/src/pages/core/Organization.tsx` | sección "Comisión por pago con tarjeta" |
| `frontend/src/pages/sales/SalesHistory.tsx`, `frontend/src/pages/hq/HQSalesLog.tsx` | renglón en el detalle de la venta |

---

### Task 1: Columna de configuración, servicio puro y endpoints

**Files:**
- Create: `app/services/card_surcharge.py`
- Modify: `app/modules/tenants/models.py` (clase `Organization`, después de `usd_rate_margin` — línea 201)
- Modify: `app/modules/tenants/schemas.py` (`OrganizationUpdate` línea 77, `OrganizationRead` línea 91, `CardSurchargeRead` después de `ExchangeRateRead` línea 110)
- Modify: `app/modules/tenants/router.py` (import línea 16-21; `update_organization` después de la línea 102; endpoint nuevo después de la línea 156)
- Modify: `scripts/railway_init.py` (lista `migrations`, después de la entrada `("sales_documents", "usd_rate", …)` de la línea 111)
- Test: `tests/test_card_surcharge_service.py`, `tests/test_card_surcharge_config.py`

**Interfaces:**
- Produces: `Organization.card_surcharge_pct` (`NUMERIC(5,2)`, `NOT NULL DEFAULT 0`).
- Produces (puras): `ComisionTarjeta {base, pct, monto, pago_tarjeta, total_a_pagar}`, `calcular_comision(total, pagos, pct) -> ComisionTarjeta`, `pct_de_organizacion(org) -> Decimal`, `hay_pago_con_tarjeta(pagos) -> bool`, `validar_pct(pct) -> None`, constantes `METODO_TARJETA`, `PCT_MAXIMO`, `CENTAVOS`, `CERO`.
- Produces: `GET /api/organization/card-surcharge` → `CardSurchargeRead {pct}`; `PUT /api/organization/` valida el porcentaje.
- Las tareas 2, 3 y 4 consumen exactamente estos nombres.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_card_surcharge_service.py
"""Servicio puro de la comision por pago con tarjeta.

Sin base de datos: `calcular_comision` recibe los pagos duck-typed, asi que un
SimpleNamespace basta (mismo patron que tests/test_exchange_rate_service.py).

La invariante que sostiene todo el diseño: `total_a_pagar = total + monto` y
`pago_tarjeta = base + monto`. Si alguna de las dos deja de valer, el cajero
cobra de mas o de menos."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.card_surcharge import (
    CERO,
    PCT_MAXIMO,
    ComisionTarjeta,
    calcular_comision,
    hay_pago_con_tarjeta,
    pct_de_organizacion,
    validar_pct,
)


def _pago(method, amount):
    return SimpleNamespace(method=method, amount=Decimal(str(amount)))


class TestPctDeOrganizacion:
    def test_organizacion_sin_la_columna_es_cero(self):
        # Organizacion legada leida antes del ALTER: no debe reventar.
        assert pct_de_organizacion(SimpleNamespace()) == CERO

    def test_none_es_cero(self):
        assert pct_de_organizacion(None) == CERO
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=None)) == CERO

    def test_lee_el_porcentaje(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=Decimal("3.5"))) == Decimal("3.50")

    def test_el_float_de_sqlite_no_rompe_la_precision(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=3.5)) == Decimal("3.50")

    def test_un_porcentaje_negativo_se_trata_como_apagado(self):
        assert pct_de_organizacion(SimpleNamespace(card_surcharge_pct=Decimal("-1"))) == CERO


class TestHayPagoConTarjeta:
    def test_reconoce_el_enum_y_el_string(self):
        from app.models.sales import PaymentMethod

        assert hay_pago_con_tarjeta([_pago(PaymentMethod.CARD, "10")]) is True
        assert hay_pago_con_tarjeta([_pago("card", "10")]) is True
        assert hay_pago_con_tarjeta([_pago("CASH", "10")]) is False

    def test_lista_vacia_o_none(self):
        assert hay_pago_con_tarjeta([]) is False
        assert hay_pago_con_tarjeta(None) is False


class TestCalcularComision:
    def test_sin_porcentaje_no_hay_comision(self):
        # Neutralidad: es el estado de TODA organizacion existente.
        c = calcular_comision(Decimal("1000.00"), [_pago("CARD", "1000")], Decimal("0"))
        assert c == ComisionTarjeta(
            base=CERO, pct=CERO, monto=CERO,
            pago_tarjeta=CERO, total_a_pagar=Decimal("1000.00"),
        )

    def test_sin_pago_con_tarjeta_no_hay_comision(self):
        c = calcular_comision(Decimal("1000.00"), [_pago("CASH", "1000")], Decimal("3.5"))
        assert c.monto == CERO
        assert c.pct == CERO
        assert c.total_a_pagar == Decimal("1000.00")

    def test_sin_pagos_no_hay_comision(self):
        # Venta a credito puro: no hay nada que cobrar todavia.
        assert calcular_comision(Decimal("1000.00"), [], Decimal("3.5")).monto == CERO

    def test_cien_por_ciento_tarjeta(self):
        c = calcular_comision(Decimal("1000.00"), [_pago("CARD", "1035")], Decimal("3.5"))
        assert c.base == Decimal("1000.00")
        assert c.pct == Decimal("3.50")
        assert c.monto == Decimal("35.00")
        assert c.pago_tarjeta == Decimal("1035.00")
        assert c.total_a_pagar == Decimal("1035.00")

    def test_mixto_solo_cobra_la_parte_de_tarjeta(self):
        # Ejemplo B del diseño: $1,000 de mercancia, $400 en efectivo.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CASH", "400"), _pago("CARD", "621")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("600.00")
        assert c.monto == Decimal("21.00")
        assert c.pago_tarjeta == Decimal("621.00")
        assert c.total_a_pagar == Decimal("1021.00")

    def test_el_efectivo_que_cubre_todo_deja_la_base_en_cero(self):
        # El cajero teclea un billete grande: la base no puede irse a negativo.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CASH", "1200"), _pago("CARD", "50")],
            Decimal("3.5"),
        )
        assert c.base == CERO
        assert c.monto == CERO
        assert c.pct == CERO
        assert c.total_a_pagar == Decimal("1000.00")

    def test_la_transferencia_tambien_es_base_sin_comision(self):
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("TRANSFER", "700"), _pago("CARD", "310.50")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("300.00")
        assert c.monto == Decimal("10.50")

    def test_dos_renglones_de_tarjeta_suman_una_sola_base(self):
        # Dos terminales distintas en la misma venta: la comision se calcula
        # sobre lo que NO es tarjeta, no sobre cada renglon.
        c = calcular_comision(
            Decimal("1000.00"),
            [_pago("CARD", "500"), _pago("CARD", "535")],
            Decimal("3.5"),
        )
        assert c.base == Decimal("1000.00")
        assert c.monto == Decimal("35.00")

    def test_redondea_medio_centavo_hacia_arriba(self):
        # Ejemplo F del diseño: 333.33 x 3.5% = 11.66655 -> 11.67 (HALF_UP).
        c = calcular_comision(Decimal("333.33"), [_pago("CARD", "345")], Decimal("3.5"))
        assert c.monto == Decimal("11.67")
        assert c.total_a_pagar == Decimal("345.00")

    def test_acepta_strings_y_floats(self):
        c = calcular_comision("1000.00", [SimpleNamespace(method="CARD", amount=1035.0)], "3.5")
        assert c.monto == Decimal("35.00")

    def test_acepta_pagos_como_diccionarios(self):
        # `payments_detail` del router de impresion viaja como lista de dicts.
        c = calcular_comision(
            Decimal("1000.00"),
            [{"method": "CASH", "amount": "400"}, {"method": "CARD", "amount": "621"}],
            Decimal("3.5"),
        )
        assert c.monto == Decimal("21.00")

    def test_porcentaje_negativo_se_trata_como_cero(self):
        assert calcular_comision(Decimal("100"), [_pago("CARD", "100")], Decimal("-3")).monto == CERO

    @pytest.mark.parametrize("total,efectivo,pct", [
        ("1000.00", "0", "3.5"),
        ("1000.00", "400", "3.5"),
        ("333.33", "0", "2.9"),
        ("19.99", "5", "20"),
    ])
    def test_las_dos_invariantes_siempre_valen(self, total, efectivo, pct):
        pagos = [_pago("CARD", "0")]
        if Decimal(efectivo) > 0:
            pagos.append(_pago("CASH", efectivo))
        c = calcular_comision(Decimal(total), pagos, Decimal(pct))
        assert c.total_a_pagar == Decimal(total) + c.monto
        assert c.pago_tarjeta == c.base + c.monto


class TestValidarPct:
    def test_valores_validos(self):
        validar_pct(0)
        validar_pct(Decimal("3.5"))
        validar_pct(PCT_MAXIMO)

    def test_negativo(self):
        with pytest.raises(ValueError):
            validar_pct(Decimal("-0.01"))

    def test_por_encima_del_tope(self):
        # Guardarail contra el dedo gordo: 35 en vez de 3.5.
        with pytest.raises(ValueError):
            validar_pct(Decimal("35"))

    def test_no_numerico(self):
        with pytest.raises(ValueError):
            validar_pct("tres y medio")
```

```python
# tests/test_card_surcharge_config.py
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
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_card_surcharge_service.py tests/test_card_surcharge_config.py`
Expected: error de colección en el primero (`ModuleNotFoundError: No module named 'app.services.card_surcharge'`); en el segundo, 404 en `/api/organization/card-surcharge` y 200 sin validar en los `PUT`.

- [ ] **Step 3: Implementar**

`app/services/card_surcharge.py` (nuevo):

```python
"""Comision por pago con tarjeta: calculo, politica y validacion.

Fuente UNICA de la comision, igual que `app/services/tax.py` lo es del IVA y
`app/services/exchange_rate.py` del tipo de cambio. La consumen el checkout
(`app/routers/sales.py::create_sale`), el `PUT` de organizacion y —a traves de
`GET /api/organization/card-surcharge`— el POS, que tiene su espejo puro en
`frontend/src/pages/pos/cardSurcharge.ts`. Si cada uno redondeara por su
cuenta, la pantalla y el cobro discreparian en centavos con el dinero del
cliente en la mano.

Regla (ver el diseño §4):

    base_tarjeta  = max(0, total - suma de los pagos cuyo metodo NO es CARD)
    comision      = redondear(base_tarjeta * pct / 100)
    pago_tarjeta  = base_tarjeta + comision
    total_a_pagar = total + comision

`total_amount` de la venta NO incluye la comision: se persiste aparte
(`sales_documents.card_surcharge_amount`) para no inflar el reporte de ingresos
ni el histórico.

Todo aqui es PURO: sin base de datos, sin FastAPI. Redondeo HALF_UP a centavos,
el mismo redondeo fiscal mexicano de tax.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

CENTAVOS = Decimal("0.01")
CERO = Decimal("0.00")

# Unico metodo que causa comision. Los otros tres de `PaymentMethod`
# (CASH, TRANSFER, OTHER) son base sin comision.
METODO_TARJETA = "CARD"

# Tope del porcentaje. No es una regla fiscal, es un guardarail contra el dedo
# gordo: 35 en vez de 3.5 convertiria una venta de $1,000 en $1,350 cobrados.
PCT_MAXIMO = Decimal("20")


@dataclass(frozen=True)
class ComisionTarjeta:
    """Resultado del calculo. Invariantes que SIEMPRE valen:

        total_a_pagar == total + monto
        pago_tarjeta  == base + monto
        monto == 0  <=>  pct == 0
    """
    base: Decimal           # importe sobre el que se cobra la comision
    pct: Decimal            # porcentaje EFECTIVAMENTE aplicado (0 si no aplico)
    monto: Decimal          # la comision, a centavos
    pago_tarjeta: Decimal   # base + monto: lo que debe pasar por la terminal
    total_a_pagar: Decimal  # total + monto: lo que el cliente entrega


def _dec(valor) -> Optional[Decimal]:
    """Decimal tolerante con None, float y str (columnas nullable y SQLite)."""
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except Exception:  # noqa: BLE001 — basura en la columna != error de cobro
        return None


def _centavos(valor) -> Decimal:
    """Decimal cuantizado a centavos. Entrada invalida -> 0.00."""
    d = _dec(valor)
    if d is None:
        return CERO
    return d.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _metodo(pago) -> str:
    """Metodo del pago, normalizado. Acepta enum, string, objeto o dict."""
    if isinstance(pago, dict):
        crudo = pago.get("method")
    else:
        crudo = getattr(pago, "method", None)
    return (crudo.value if hasattr(crudo, "value") else str(crudo or "")).strip().upper()


def _monto_pago(pago) -> Decimal:
    if isinstance(pago, dict):
        return _centavos(pago.get("amount"))
    return _centavos(getattr(pago, "amount", None))


def pct_de_organizacion(org) -> Decimal:
    """Porcentaje configurado en la organizacion, leido a prueba de balas.

    Devuelve `CERO` —nunca lanza— si la organizacion es None, si todavia no
    tiene la columna (base legada leida antes del ALTER), si viene NULL o si
    trae un valor sin sentido. `CERO` significa "funcion apagada", que es el
    estado de toda organizacion existente.
    """
    if org is None:
        return CERO
    pct = _dec(getattr(org, "card_surcharge_pct", None))
    if pct is None or pct <= 0:
        return CERO
    return pct.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def hay_pago_con_tarjeta(pagos) -> bool:
    """¿Alguno de los pagos pasa por la terminal?"""
    return any(_metodo(p) == METODO_TARJETA for p in (pagos or []))


def calcular_comision(total, pagos, pct) -> ComisionTarjeta:
    """Comision que corresponde a esta venta. NUNCA lanza.

    `pagos` va duck-typed: cualquier objeto con `.method` y `.amount` sirve
    (`PaymentCreate` en produccion, `SimpleNamespace` o dict en las pruebas).

    Devuelve una comision de CERO —y `total_a_pagar` igual al total— en todos
    los casos en los que no hay nada que cobrar: porcentaje apagado, sin pagos,
    sin ningun pago con tarjeta, o efectivo que ya cubre el total entero.
    """
    total_q = _centavos(total)
    pct_q = _dec(pct) or CERO
    if pct_q < 0:
        pct_q = CERO

    pagos = list(pagos or [])
    _neutro = ComisionTarjeta(
        base=CERO, pct=CERO, monto=CERO, pago_tarjeta=CERO, total_a_pagar=total_q
    )
    if pct_q == 0 or not hay_pago_con_tarjeta(pagos):
        return _neutro

    no_tarjeta = sum(
        (_monto_pago(p) for p in pagos if _metodo(p) != METODO_TARJETA), CERO
    )
    # `max(0, ...)`: un billete grande tecleado como efectivo no puede empujar
    # la base a negativo y regalarle una comision negativa al cliente.
    base = total_q - no_tarjeta
    if base <= 0:
        return _neutro

    monto = (base * pct_q / Decimal("100")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if monto <= 0:
        return _neutro

    return ComisionTarjeta(
        base=base,
        pct=pct_q,
        monto=monto,
        pago_tarjeta=base + monto,
        total_a_pagar=total_q + monto,
    )


def validar_pct(pct) -> None:
    """Valida el porcentaje que quiere guardar el administrador. Lanza ValueError.

    El caller (el PUT de organizacion) lo convierte en 422 con el mensaje tal
    cual, en español y accionable.
    """
    valor = _dec(pct)
    if valor is None:
        raise ValueError("La comisión por pago con tarjeta debe ser un número.")
    if valor < 0 or valor > PCT_MAXIMO:
        raise ValueError(
            f"La comisión por pago con tarjeta debe estar entre 0 y {PCT_MAXIMO:.0f} %."
        )
```

`app/modules/tenants/models.py`, en `Organization`, justo después de `usd_rate_margin` (línea 201):

```python
    # Comision por pago con tarjeta (2026-09-17). Porcentaje que se suma a la
    # parte de la venta cobrada con TARJETA (solo `PaymentMethod.CARD`; en un
    # pago mixto, solo a esa parte). 0 = apagado, y es el DEFAULT para todas
    # las organizaciones ya existentes.
    #
    # NUMERIC(5,2) y no (6,3) a proposito: `app/pos_printer.py::_total_line` da
    # 20 columnas de etiqueta en papel de 58 mm y NO trunca, asi que un tercer
    # decimal desbordaria el renglon "COM. TARJETA 19.999%" del ticket.
    # La regla de calculo vive en app/services/card_surcharge.py.
    card_surcharge_pct = Column(Numeric(5, 2), default=0, server_default="0", nullable=False)
```

`app/modules/tenants/schemas.py` — en `OrganizationUpdate`, después de `usd_rate_margin` (línea 77):

```python
    # Comision por pago con tarjeta (2026-09-17). Cae FUERA de la whitelist de
    # no-admins del router (linea 76 de router.py), asi que solo
    # ADMINISTRADOR/DUEÑO puede cambiarla: no hace falta guardia nueva.
    card_surcharge_pct: Optional[Decimal] = None
```

en `OrganizationRead`, después de `usd_rate_margin` (línea 91):

```python
    # Comision por pago con tarjeta. Se expone en la lectura para que el panel
    # de Empresa arme el formulario sin un GET extra.
    card_surcharge_pct: Decimal = Decimal("0")
```

y una clase nueva al final del archivo, después de `ExchangeRateRead` (línea 110):

```python
class CardSurchargeRead(BaseModel):
    """Lo unico que el POS necesita para cobrar la comision de tarjeta.

    `pct = 0` significa "no mostrar ni cobrar nada", que es el estado de toda
    organizacion que no la configuro.
    """
    pct: Decimal = Decimal("0")
```

`app/modules/tenants/router.py`, línea 16-21, agregar `CardSurchargeRead` al import existente:

```python
from app.schemas.organization import (
    CardSurchargeRead,
    ExchangeRateRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
```

en `update_organization`, justo después del bloque de validación de `usd_rate_*` (línea 102) y **antes** del `for key, value in data_to_update.items()` de la línea 104:

```python
    # Comision por pago con tarjeta: se valida ANTES del setattr, para no dejar
    # la organizacion a medio escribir y tener que hacer rollback a media
    # peticion. `None` = "no tocar": la columna es NOT NULL y el panel manda el
    # objeto completo, asi que escribir None seria un 500 al commitear.
    if "card_surcharge_pct" in data_to_update:
        if data_to_update["card_surcharge_pct"] is None:
            data_to_update.pop("card_surcharge_pct")
        else:
            from app.services.card_surcharge import validar_pct

            try:
                validar_pct(data_to_update["card_surcharge_pct"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
```

y un endpoint nuevo justo después de `get_exchange_rate` (línea 156), antes de `refresh_exchange_rate`:

```python
# ═════════════════════════════════════════════════════════════════════════════
# COMISION POR PAGO CON TARJETA (2026-09-17)
# Endpoint propio y barato para el POS, por el mismo motivo que el del tipo de
# cambio: lo consume la cajera, que NO es admin y no tiene por que leer RFC ni
# configuracion fiscal solo para cobrar. Un SELECT y cero llamadas de red.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/card-surcharge", response_model=CardSurchargeRead)
def get_card_surcharge(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Porcentaje de comisión por pago con tarjeta. `pct = 0` = apagado."""
    from app.services.card_surcharge import pct_de_organizacion

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization context not found")

    return CardSurchargeRead(pct=pct_de_organizacion(org))
```

`scripts/railway_init.py`, en la lista `migrations`, después de la entrada `("sales_documents", "usd_rate", …)` de la línea 111:

```python
        # Comision por pago con tarjeta 2026-09-17. DEFAULT 0 a proposito:
        # ninguna organizacion viva cobra nada hasta que su dueño lo encienda.
        # `card_surcharge_amount` es NOT NULL DEFAULT 0 para que el histórico
        # entero quede en 0.00 sin backfill; en Postgres >= 11 un ADD COLUMN
        # NOT NULL con DEFAULT constante no reescribe la tabla.
        ("organization", "card_surcharge_pct", "ALTER TABLE organization ADD COLUMN card_surcharge_pct NUMERIC(5,2) NOT NULL DEFAULT 0;"),
        ("sales_documents", "card_surcharge_pct", "ALTER TABLE sales_documents ADD COLUMN card_surcharge_pct NUMERIC(5,2);"),
        ("sales_documents", "card_surcharge_amount", "ALTER TABLE sales_documents ADD COLUMN card_surcharge_amount NUMERIC(10,2) NOT NULL DEFAULT 0;"),
```

> Las dos columnas de `sales_documents` se declaran aquí, en la misma tanda, aunque el modelo las agregue la Task 2: `railway_init` corre en cada deploy y la lista es idempotente, así que tenerlas juntas evita un segundo ALTER suelto en el diff de la Task 2.

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_card_surcharge_service.py tests/test_card_surcharge_config.py`
Expected: todas PASSED — **36 pruebas** (27 del servicio contando los 4 casos parametrizados, 9 de configuración).

Comprobar que no se rompió el `PUT` de organización ni el tipo de cambio:
Run: `python3 -m pytest -q -p no:warnings tests/test_exchange_rate_endpoints.py -k "Escritura"`
Expected: sin `failed`.

Luego la suite completa:
Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: `810 passed, 2 skipped, 3 xfailed` (774 + 36), cero `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/card_surcharge.py app/modules/tenants/models.py app/modules/tenants/schemas.py app/modules/tenants/router.py scripts/railway_init.py tests/test_card_surcharge_service.py tests/test_card_surcharge_config.py
git commit -m "feat(comision): configuracion por organizacion y servicio de comision de tarjeta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 2: `create_sale` cobra y congela la comisión

**Files:**
- Modify: `app/models/sales.py:80` (`SalesDocument`, después de `usd_rate`)
- Modify: `app/routers/sales.py:62` (import), `:390-398` (`_respuesta_de_venta_existente`), `:513-515` (reutilizar la organización), `:717-733` (cálculo y `cash_needed`), `:741-742` (`expected_total`), `:851-853` (persistencia), `:993-1003` (respuesta)
- Test: `tests/test_venta_comision_tarjeta.py`

**Interfaces:**
- Consumes: `calcular_comision`, `pct_de_organizacion`, `ComisionTarjeta` (Task 1).
- Produces: `SalesDocument.card_surcharge_pct: Decimal | None`, `SalesDocument.card_surcharge_amount: Decimal`.
- Produces: la respuesta de `POST /api/sales/` incluye `"card_surcharge_amount"` (`float`) y `"card_surcharge_pct"` (`float | None`), con la misma forma en el alta y en el reenvío idempotente.
- Las tareas 3 y 4 consumen exactamente estos nombres.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_venta_comision_tarjeta.py
"""La venta cobra la comision de tarjeta, la congela y NO la mete en total_amount.

`create_sale` es el motor ATS-critico: la mitad de este archivo son pruebas de
NEUTRALIDAD -- con el porcentaje en 0, o sin pago con tarjeta, todo tiene que
quedar exactamente como estaba."""
from decimal import Decimal

from app.models.sales import Payment, PaymentMethod, SalesDocument
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _preparar(db, org, branch, cajero, precio="1000.00", pct=None):
    _habilitar_pos(db, org)
    _make_product(db, org, "Mercancia", "COM-01", Decimal(precio), [(branch.id, True)])
    _abrir_caja(db, org, branch, cajero)
    if pct is not None:
        org.card_surcharge_pct = Decimal(pct)
    db.commit()


def _vender(client, org, auth, pagos):
    return client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "COM-01", "quantity": 1}],
        "payments": pagos,
    }, headers={**auth, "X-Organization-ID": str(org.id)})


def _doc(db, sale_id):
    return db.query(SalesDocument).filter(SalesDocument.id == sale_id).one()


class TestNeutralidad:
    def test_sin_porcentaje_nada_cambia(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a)
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1000.0
        assert cuerpo["change"] == 0.0
        assert cuerpo["card_surcharge_amount"] == 0.0
        assert cuerpo["card_surcharge_pct"] is None

        venta = _doc(db, cuerpo["sale_id"])
        assert venta.total_amount == Decimal("1000.00")
        assert venta.card_surcharge_amount == Decimal("0.00")
        assert venta.card_surcharge_pct is None

    def test_sin_pago_con_tarjeta_no_hay_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0
        assert _doc(db, r.json()["sale_id"]).card_surcharge_amount == Decimal("0.00")

    def test_el_efectivo_sigue_dando_cambio_igual(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Con comision configurada pero sin tarjeta, el billete grande de
        # siempre tiene que devolver exactamente el mismo cambio de siempre.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1200.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["change"] == 200.0
        assert _doc(db, r.json()["sale_id"]).change_given == Decimal("200.00")


class TestCobro:
    def test_cien_por_ciento_tarjeta(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo A del diseño.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1035.00"}])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 35.0
        assert cuerpo["card_surcharge_pct"] == 3.5
        # `total` es SOLO mercancia: la comision va aparte y no infla el
        # reporte de ingresos.
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1035.0
        assert cuerpo["change"] == 0.0

        venta = _doc(db, cuerpo["sale_id"])
        assert venta.total_amount == Decimal("1000.00")
        assert venta.card_surcharge_amount == Decimal("35.00")
        assert venta.card_surcharge_pct == Decimal("3.50")

        # El Payment de tarjeta lleva la comision DENTRO: es lo que paso por la
        # terminal y es lo que el corte por metodo tiene que reflejar.
        pago = db.query(Payment).filter(Payment.sales_document_id == venta.id).one()
        assert pago.method == PaymentMethod.CARD
        assert pago.amount == Decimal("1035.00")

    def test_pagar_solo_la_mercancia_es_422(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # El cajero NO puede quitar la comision: si cobra 1000 en vez de 1035,
        # el checkout lo rechaza con el importe correcto en el mensaje.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1000.00"}])
        assert r.status_code == 422, r.text
        assert "1035.00" in r.json()["detail"]

    def test_mixto_solo_cobra_la_parte_de_tarjeta(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo B del diseño: $400 en efectivo, el resto con tarjeta.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "400.00"},
            {"method": "CARD", "amount": "621.00"},
        ])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 21.0
        assert cuerpo["total"] == 1000.0
        assert cuerpo["paid"] == 1021.0
        # El cambio es CERO: si `cash_needed` no incluyera la comision, aqui
        # saldrian 21.00 de cambio -- justo lo que se le acaba de cobrar.
        assert cuerpo["change"] == 0.0
        assert _doc(db, cuerpo["sale_id"]).change_given == Decimal("0.00")

    def test_mixto_con_cambio_en_efectivo(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # Ejemplo C del diseño: el cliente da un billete de 600 y la tarjeta
        # quedo en 517.50. Comision sobre base 400 = 14.00.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "600.00"},
            {"method": "CARD", "amount": "517.50"},
        ])
        assert r.status_code in (200, 201), r.text
        cuerpo = r.json()
        assert cuerpo["card_surcharge_amount"] == 14.0
        assert cuerpo["paid"] == 1117.5
        assert cuerpo["change"] == 103.5
        # 1117.50 - 103.50 = 1014.00 = 1000.00 de mercancia + 14.00 de comision
        assert cuerpo["paid"] - cuerpo["change"] == cuerpo["total"] + cuerpo["card_surcharge_amount"]

    def test_el_efectivo_que_cubre_todo_no_genera_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "1200.00"},
            {"method": "CARD", "amount": "50.00"},
        ])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0

    def test_la_transferencia_no_causa_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        r = _vender(client, org, auth_cajero_a, [{"method": "TRANSFER", "amount": "1000.00"}])
        assert r.status_code in (200, 201), r.text
        assert r.json()["card_surcharge_amount"] == 0.0


class TestIdempotencia:
    def test_el_reenvio_devuelve_la_comision_congelada_sin_duplicar(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        # La comision se LEE del documento, nunca se recalcula: si el POS
        # reintenta el cobro, el cliente no puede acabar pagandola dos veces.
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        cuerpo_venta = {
            "doc_type": "ORDER",
            "client_uuid": "reintento-comision-1",
            "items": [{"sku": "COM-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }
        cab = {**auth_cajero_a, "X-Organization-ID": str(org.id)}

        primera = client.post("/api/sales/", json=cuerpo_venta, headers=cab)
        assert primera.status_code in (200, 201), primera.text

        segunda = client.post("/api/sales/", json=cuerpo_venta, headers=cab)
        assert segunda.status_code in (200, 201), segunda.text
        assert segunda.json()["duplicate_ignored"] is True
        assert segunda.json()["sale_id"] == primera.json()["sale_id"]
        assert segunda.json()["card_surcharge_amount"] == 35.0
        assert segunda.json()["card_surcharge_pct"] == 3.5

        venta_id = primera.json()["sale_id"]
        assert db.query(Payment).filter(Payment.sales_document_id == venta_id).count() == 1
        assert _doc(db, venta_id).card_surcharge_amount == Decimal("35.00")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_venta_comision_tarjeta.py`
Expected: FAIL en todas — `KeyError: 'card_surcharge_amount'` en las respuestas y `AttributeError: 'SalesDocument' object has no attribute 'card_surcharge_amount'` donde se lee el documento.

- [ ] **Step 3: Implementar**

`app/models/sales.py`, en `SalesDocument` justo después de `usd_rate` (línea 80):

```python
    # Comision por pago con tarjeta (2026-09-17), CONGELADA al cobrar.
    # `total_amount` NO la incluye: es mercancia (+IVA +propina) y punto, para
    # que el reporte de ingresos y el histórico no se muevan. El total que el
    # cliente pago es `total_amount + card_surcharge_amount`.
    # `card_surcharge_pct` solo se guarda cuando la comision se aplico de
    # verdad; NULL = venta anterior a la funcion, organizacion sin comision, o
    # venta sin pago con tarjeta.
    # La regla de calculo vive en app/services/card_surcharge.py.
    card_surcharge_pct = Column(Numeric(5, 2), nullable=True)
    card_surcharge_amount = Column(Numeric(10, 2), default=0, server_default="0", nullable=False)
```

`app/routers/sales.py`, línea 62, junto al import de `tax`:

```python
from app.services.card_surcharge import calcular_comision, pct_de_organizacion
```

en `_respuesta_de_venta_existente`, dentro del `return` (después de `"credit_debt": 0.0,`, línea 397):

```python
        "credit_debt": 0.0,
        # Comision congelada en el documento: se LEE, nunca se recalcula. Un
        # reintento del POS no puede volver a cobrarsela al cliente.
        "card_surcharge_amount": float(Decimal(str(sale.card_surcharge_amount or 0)).quantize(Decimal("0.01"))),
        "card_surcharge_pct": float(sale.card_surcharge_pct) if sale.card_surcharge_pct is not None else None,
        # Misma forma que el alta normal: el POS no distingue.
        "usd_rate": float(sale.usd_rate) if sale.usd_rate is not None else None,
        "duplicate_ignored": True,
    }
```

líneas 513-515: la organización ya se consulta ahí y el resultado se tira; ahora se conserva:

```python
    # Modo de precio de la organización (neto vs. precio con IVA incluido). Se
    # resuelve una sola vez y lo consume compute_line_tax por renglón.
    # La organización se conserva en una variable porque más abajo también se
    # le lee `card_surcharge_pct`: una sola consulta, no dos.
    _org_venta = db.query(Organization).filter(Organization.id == org_id).first()
    price_includes_tax = resolve_org_tax_mode(_org_venta)
```

justo después de `total_paid` (línea 717) y **antes** del bloque de `cash_paid`:

```python
    # --- Comision por pago con tarjeta (2026-09-17) ---
    # Solo existe si la organizacion la configuro Y hay al menos un pago CARD;
    # en un mixto se cobra unicamente sobre la parte que pasa por la terminal.
    # En cualquier otro caso `comision.monto` es Decimal("0.00") y
    # `total_a_cobrar` ES `total_sale`: el resto del checkout no puede
    # distinguir esta venta de una anterior a la funcion.
    #
    # La comision NO se suma a `total_amount`: se persiste aparte para no
    # inflar el reporte de ingresos ni el histórico (diseño §2, decision 6).
    comision = calcular_comision(total_sale, sale_in.payments, pct_de_organizacion(_org_venta))
    total_a_cobrar = (total_sale + comision.monto) if comision.monto > 0 else total_sale
```

`cash_needed` (línea 732) pasa a usar el total con comisión:

```python
    # `total_a_cobrar`, no `total_sale`: si la comision no entrara aqui, en un
    # pago mixto el sistema le devolveria al cliente de cambio exactamente el
    # importe de la comision que le acaba de cobrar.
    cash_needed = max(Decimal(0), total_a_cobrar - non_cash_paid)
```

y la validación H-1 (línea 741-742):

```python
    if sale_in.payments:
        expected_total = total_a_cobrar
        tolerance = Decimal("0.01")
```

> El resto del bloque H-1 (mensaje de pagos insuficientes, guard de sobrepago ×10, aviso `PAYMENT_DISCREPANCY`) **no se toca**: todos leen `expected_total`. `balance_diff = total_sale - total_paid` (línea 773) tampoco se toca: la deuda a crédito es por la mercancía.

persistencia, en el mismo bloque donde se congela `usd_rate` (justo después de `db.add(sales_doc)` de la línea 851 y **antes** del bloque `if getattr(sales_doc, "usd_rate", None) is None:`):

```python
    # Comision por pago con tarjeta: se CONGELA en el documento. La
    # reimpresion y el reenvio idempotente la leen de aqui, jamas la
    # recalculan. El porcentaje solo se guarda si la comision se aplico de
    # verdad; si no, NULL -- asi una venta en efectivo de una organizacion con
    # 3.5% configurado no arrastra un porcentaje que nunca se cobro.
    sales_doc.card_surcharge_amount = comision.monto
    sales_doc.card_surcharge_pct = comision.pct if comision.monto > 0 else None
```

respuesta del alta (línea 993-1003), después de `credit_debt`:

```python
        "credit_debt": float(remaining_debt.quantize(Decimal("0.01"))),
        # Comision por pago con tarjeta. 0.00 / None = no aplico. `total` de
        # arriba es SOLO mercancia; lo que el cliente pago es la suma.
        "card_surcharge_amount": float(comision.monto),
        "card_surcharge_pct": float(comision.pct) if comision.monto > 0 else None,
        # Tipo de cambio congelado en la venta. None = la organizacion no tiene
        # equivalente en dolares configurado.
        "usd_rate": float(sales_doc.usd_rate) if sales_doc.usd_rate is not None else None,
    }
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_venta_comision_tarjeta.py`
Expected: todas PASSED — **10 pruebas** (3 de neutralidad, 6 de cobro, 1 de idempotencia).

Comprobar que el motor de cobro sigue intacto en todos sus caminos:
Run: `python3 -m pytest -q -p no:warnings tests/test_sale_variant_name_null.py tests/test_sale_by_variant_id.py tests/test_sales_idempotency.py tests/test_sales_sin_pagos_no_revienta.py tests/test_sales_cash_requires_session.py tests/test_iva_sale_integration.py tests/test_venta_usd_snapshot.py tests/test_cash_math.py tests/test_cash_invariants.py`
Expected: todas PASSED, cero `failed`.

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: `820 passed, 2 skipped, 3 xfailed` (810 + 10), cero `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/models/sales.py app/routers/sales.py tests/test_venta_comision_tarjeta.py
git commit -m "feat(comision): create_sale cobra la comision de tarjeta y la congela en la venta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 3: Ticket, corte de caja y reportes

**Files:**
- Modify: `app/pos_printer.py` (helpers de módulo junto a `_describe_variant`; `_card_surcharge_lines` después de `_usd_line` — línea 357; `build_ticket_bytes:200-206`; `build_reissued_ticket_bytes:460-465`; bloque `COBRADO POR METODO` de `build_cash_cut_bytes` — líneas 533-558)
- Modify: `app/routers/cash.py:640` (después de `methods_map`), `:858` (dict de retorno)
- Modify: `app/schemas/sales.py:101` (`SaleRead`)
- Modify: `app/routers/sales.py:1507` (encabezados del CSV), `:1534-1561` (renglón del CSV)
- Modify: `tests/test_pos_printer.py:69` (`_make_sale` declara las dos columnas)
- Test: `tests/test_ticket_comision_tarjeta.py`, `tests/test_corte_comision_tarjeta.py`

**Interfaces:**
- Consumes: `SalesDocument.card_surcharge_pct` / `.card_surcharge_amount` (Task 2).
- Produces: `PosPrinter._card_surcharge_lines(sale, net_total) -> bytes`; helpers de módulo `_card_surcharge_amount(sale) -> float` y `_fmt_pct(pct) -> str | None`.
- Produces: `get_session_audit_data(...)["card_surcharges"]` (`float`).
- Produces: `SaleRead.card_surcharge_pct` / `.card_surcharge_amount`; columnas «Comisión tarjeta» y «Total cobrado» en `GET /api/sales/export/csv`.
- La Task 4 consume `SaleRead`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_ticket_comision_tarjeta.py
"""Renglones de comision en el ticket y en el reemitido.

SimpleNamespace en vez de MagicMock a proposito: con MagicMock cualquier
atributo no declarado sale truthy y la prueba de "no imprime nada" mentiria
(mismo motivo documentado en tests/test_ticket_usd.py)."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.pos_printer import PosPrinter


def _org():
    return SimpleNamespace(
        name="Tienda Demo", legal_name=None, tax_id=None, tax_regime=None,
        address=None, phone=None, logo_url=None,
        ticket_header=None, ticket_footer=None, price_includes_tax=False,
    )


def _line(description, quantity, unit_price):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(description=description, quantity=qty, unit_price=unit,
                           total_line=qty * unit, variant_id="v1")


def _sale(pct=None, monto="0", total="1000.00", usd_rate=None):
    total_dec = Decimal(total)
    return SimpleNamespace(
        lines=[_line("Mercancia", 1, total_dec)],
        series="A", folio=123,
        subtotal=total_dec, tax_amount=Decimal("0"), total_amount=total_dec,
        customer_name="Cliente Test", customer=None,
        created_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        notes=None, requires_invoice=False,
        usd_rate=Decimal(usd_rate) if usd_rate is not None else None,
        card_surcharge_pct=Decimal(pct) if pct is not None else None,
        card_surcharge_amount=Decimal(monto),
    )


def _build_raw(sale, ancho=80) -> bytes:
    p = PosPrinter(paper_width_mm=ancho)
    return p.build_ticket_bytes(
        sale, paid=Decimal("0"), change=Decimal("0"), method="CARD",
        cashier="Cajero Test", is_reprint=False, organization=_org(),
        branch=None, returns=None, payments_detail=None,
    )


def _sin_comandos(raw: bytes, ancho: int) -> list:
    """Lineas tal como saldrian en el papel, sin los comandos ESC/POS.

    MISMO helper que `tests/test_ticket_usd.py::_lineas_visibles`, y por el
    mismo motivo: BOLD_ON/BOLD_OFF quedan pegados al texto sin un '\\n' de por
    medio (los renglones de TOTAL y TOTAL A PAGAR van en negritas), asi que
    medir la linea cruda daria 3 columnas de mas y la prueba de ancho mentiria.
    """
    p = PosPrinter(paper_width_mm=ancho)
    for nombre, secuencia in p.CMD.items():
        if nombre == "LF":  # el salto de linea SI se queda: es el separador
            continue
        raw = raw.replace(secuencia, b"")
    return [l.rstrip() for l in raw.decode("latin-1", "replace").split("\n")]


def _lineas(sale, ancho=80) -> list:
    return _sin_comandos(_build_raw(sale, ancho), ancho)


def _renglon(lineas, prefijo: str) -> str:
    return next(l for l in lineas if l.lstrip().startswith(prefijo))


def test_sin_comision_no_imprime_nada():
    # Neutralidad: una organizacion sin comision imprime el ticket de siempre.
    texto = "\n".join(_lineas(_sale()))
    assert "COM. TARJETA" not in texto
    assert "TOTAL A PAGAR" not in texto


def test_imprime_la_comision_y_el_total_a_pagar():
    lineas = _lineas(_sale(pct="3.50", monto="35.00"))
    assert _renglon(lineas, "COM. TARJETA 3.5%:").endswith("35.00")
    assert _renglon(lineas, "TOTAL A PAGAR:").endswith("1035.00")
    # El total de mercancia NO se mueve: la comision va aparte.
    assert _renglon(lineas, "TOTAL:").endswith("1000.00")


def test_el_porcentaje_entero_no_arrastra_decimales():
    assert _renglon(_lineas(_sale(pct="3.00", monto="30.00")), "COM. TARJETA 3%:")


def test_el_porcentaje_con_dos_decimales_se_conserva():
    assert _renglon(_lineas(_sale(pct="2.75", monto="27.50")), "COM. TARJETA 2.75%:")


@pytest.mark.parametrize("ancho,cols", [(58, 32), (80, 56)])
def test_los_renglones_caben_en_el_papel(ancho, cols):
    # `_total_line` NO trunca la etiqueta: si no cabe, desborda el papel. Se
    # usa el porcentaje mas largo posible (el tope de 20 %, dos decimales),
    # que a 58 mm ocupa las 32 columnas EXACTAS.
    lineas = _lineas(_sale(pct="19.99", monto="199.90"), ancho=ancho)
    assert len([l for l in lineas if "COM. TARJETA" in l or "TOTAL A PAGAR" in l]) == 2
    # Cobertura del ticket completo, no solo de los renglones nuevos.
    for l in lineas:
        assert len(l) <= cols, f"línea de {len(l)} columnas: {l!r}"


def test_comision_en_cero_no_imprime_aunque_haya_porcentaje():
    assert "COM. TARJETA" not in "\n".join(_lineas(_sale(pct="3.50", monto="0")))


def test_la_linea_usd_usa_el_total_a_pagar():
    # El equivalente en dolares es lo que el cliente entrega, comision incluida:
    # 1035.00 / 18.50 = 55.95
    lineas = _lineas(_sale(pct="3.50", monto="35.00", usd_rate="18.5000"))
    assert _renglon(lineas, "USD (T.C. 18.5000):").endswith("55.95")


def test_sin_comision_la_linea_usd_no_se_mueve():
    # Neutralidad de la Task anterior: 1000.00 / 18.50 = 54.05
    lineas = _lineas(_sale(usd_rate="18.5000"))
    assert _renglon(lineas, "USD (T.C. 18.5000):").endswith("54.05")


def test_el_reemitido_conserva_la_comision_original():
    # La comision NO se devuelve (diseño §7): el ticket reemitido baja el TOTAL
    # pero sigue mostrando la comision que el banco ya se quedo.
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        sale=_sale(pct="3.50", monto="35.00"), cashier="Cajero Test",
        organization=_org(), branch=None, returns=[],
    )
    lineas = _sin_comandos(raw, 80)
    assert _renglon(lineas, "COM. TARJETA 3.5%:").endswith("35.00")
    assert _renglon(lineas, "TOTAL A PAGAR:").endswith("1035.00")
```

```python
# tests/test_corte_comision_tarjeta.py
"""La comision de tarjeta en el corte de caja.

Dos cosas que NO pueden romperse: `Total cobrado` sigue siendo la suma exacta
de los metodos (la comision YA esta dentro de `card`), y `compute_expected_cash`
no se entera de que la comision existe."""
from decimal import Decimal

from app.models.sales import SalesDocument
from app.pos_printer import PosPrinter
from conftest import _make_product
from tests.test_cash_cut_detalle import _audit, _visible_text
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


class TestCorteImpreso:
    def test_sin_comision_no_imprime_el_renglon(self):
        p = PosPrinter("x", paper_width_mm=80)
        assert "incl. comision" not in _visible_text(p.build_cash_cut_bytes(_audit()), p)

    def test_imprime_la_comision_bajo_el_renglon_de_tarjeta(self):
        p = PosPrinter("x", paper_width_mm=80)
        t = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=67.22)), p)
        renglones = [l for l in t.split("\n") if l.strip()]
        i_tarjeta = next(i for i, l in enumerate(renglones) if l.lstrip().startswith("Tarjeta"))
        assert renglones[i_tarjeta + 1].lstrip().startswith("incl. comision")
        assert "67.22" in renglones[i_tarjeta + 1]

    def test_la_comision_no_se_suma_al_total_cobrado(self):
        # La comision YA viaja dentro de payments['card']['total']; sumarla
        # aparte romperia la invariante de que el desglose da el total.
        p = PosPrinter("x", paper_width_mm=80)
        sin = _visible_text(p.build_cash_cut_bytes(_audit()), p)
        con = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=67.22)), p)
        linea = lambda t: next(l for l in t.split("\n") if l.lstrip().startswith("Total cobrado"))
        assert linea(sin) == linea(con)

    def test_el_renglon_cabe_en_papel_de_58mm(self):
        p = PosPrinter("x", paper_width_mm=58)
        t = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=12345.67)), p)
        for l in t.split("\n"):
            assert len(l.rstrip()) <= 32, f"línea de {len(l.rstrip())} columnas: {l!r}"


class TestAuditData:
    def _venta(self, db, org, branch, cajero, client, auth, pct):
        _habilitar_pos(db, org)
        _make_product(db, org, "Mercancia", "CRT-01", Decimal("1000.00"), [(branch.id, True)])
        _abrir_caja(db, org, branch, cajero)
        org.card_surcharge_pct = Decimal(pct)
        db.commit()
        r = client.post("/api/sales/", json={
            "doc_type": "ORDER",
            "items": [{"sku": "CRT-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }, headers={**auth, "X-Organization-ID": str(org.id)})
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_suma_las_comisiones_del_turno(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        from app.models.cash import CashSession
        from app.routers.cash import get_session_audit_data

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "3.5")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()

        datos = get_session_audit_data(db, sesion.id)
        assert datos["card_surcharges"] == 35.0
        # La comision viaja DENTRO del importe de tarjeta, no aparte.
        assert datos["payments"]["card"]["total"] == 1035.0
        # Y `total_amount` sigue siendo solo mercancia.
        assert datos["kpis"]["total_sales"] == 1000.0

    def test_sin_comision_la_clave_es_cero(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        from app.models.cash import CashSession
        from app.routers.cash import get_session_audit_data

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "0")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()
        assert get_session_audit_data(db, sesion.id)["card_surcharges"] == 0.0

    def test_compute_expected_cash_no_ve_la_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # La comision entra por tarjeta: NO es efectivo y el arqueo no puede
        # moverse ni un centavo por su culpa.
        from app.models.cash import CashSession
        from app.services.cash_reconciliation import compute_expected_cash

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "3.5")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()
        antes = compute_expected_cash(db, sesion).expected

        venta = db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).one()
        assert venta.card_surcharge_amount == Decimal("35.00")
        assert antes == Decimal(str(sesion.opening_balance or 0))


class TestExportCsv:
    def test_columnas_nuevas(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _habilitar_pos(db, org)
        _make_product(db, org, "Mercancia", "CSV-01", Decimal("1000.00"), [(branch_a.id, True)])
        _abrir_caja(db, org, branch_a, cajero_a)
        org.card_surcharge_pct = Decimal("3.5")
        db.commit()
        client.post("/api/sales/", json={
            "doc_type": "ORDER",
            "items": [{"sku": "CSV-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})

        r = client.get("/api/sales/export/csv",
                       headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
        assert r.status_code == 200, r.text
        texto = r.content.decode("utf-8-sig")
        encabezado, renglon = texto.strip().split("\r\n")[:2]
        cols = encabezado.split(",")
        assert cols[4:7] == ["Total", "Comisión tarjeta", "Total cobrado"]
        valores = renglon.split(",")
        assert valores[4:7] == ["1000.00", "35.00", "1035.00"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ticket_comision_tarjeta.py tests/test_corte_comision_tarjeta.py`
Expected: FAIL — en el ticket, los siete casos que esperan `COM. TARJETA` / `TOTAL A PAGAR` / el USD recalculado; en el corte, `KeyError: 'card_surcharges'` en `get_session_audit_data`, el renglón ausente en el impreso y las columnas del CSV.

- [ ] **Step 3: Implementar**

`app/pos_printer.py` — dos helpers de módulo, junto a `_describe_variant` (arriba de la clase):

```python
def _card_surcharge_amount(sale) -> float:
    """Comision de tarjeta congelada en la venta, como float. 0.0 si no aplico.

    `getattr` defensivo y `try` alrededor del `float`: varias rutas arman el
    documento con SimpleNamespace (`tests/test_ticket_layout.py`) o MagicMock
    (`tests/test_pos_printer.py`), y una venta anterior a la funcion no tiene
    la columna poblada. Un atributo que no es un numero vale 0.0, nunca una
    excepcion en medio de una impresion.
    """
    valor = getattr(sale, "card_surcharge_amount", None)
    if valor is None:
        return 0.0
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return monto if monto > 0 else 0.0


def _fmt_pct(pct) -> "Optional[str]":
    """'3.5', '2.75', '3'. Sin ceros de relleno.

    La etiqueta del ticket tiene 20 columnas contadas en papel de 58 mm
    (`_total_line`), y `COM. TARJETA ` ya gasta 13: el porcentaje no puede
    pasar de 6 caracteres. Por eso `card_surcharge_pct` es NUMERIC(5,2) y aqui
    se formatea a dos decimales como maximo. `None` si el valor no es un
    numero, y entonces la etiqueta se imprime sin porcentaje.
    """
    try:
        texto = f"{Decimal(str(pct)):.2f}"
    except Exception:  # noqa: BLE001 — nunca reventar una impresion
        return None
    # "3.50" -> "3.5"; "3.00" -> "3"; "19.99" -> "19.99". El punto detiene el
    # rstrip, asi que "20.00" nunca se convierte en "2".
    return texto.rstrip("0").rstrip(".") or "0"
```

el método nuevo, inmediatamente después de `_usd_line` (línea 357):

```python
    def _card_surcharge_lines(self, sale, net_total: float) -> bytes:
        """'COM. TARJETA 3.5%' + 'TOTAL A PAGAR'. Vacio si la venta no trae comision.

        `net_total` es el total de MERCANCIA (ya neto de devoluciones); el
        renglon "TOTAL A PAGAR" le suma la comision, que es lo que el cliente
        entrego de verdad.

        La comision NO se devuelve en una devolucion (diseño §7): se imprime el
        importe congelado en la venta aunque `net_total` haya bajado. En una
        devolucion total eso imprime TOTAL $0.00 y la comision entera. Es feo, y
        es verdad: ese dinero se lo quedo el banco.
        """
        monto = _card_surcharge_amount(sale)
        if monto <= 0:
            return b""

        pct = _fmt_pct(getattr(sale, "card_surcharge_pct", None))
        etiqueta = f"COM. TARJETA {pct}%" if pct else "COM. TARJETA"
        raw = self._total_line(etiqueta, monto)
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL A PAGAR", net_total + monto)
        raw += self.CMD["BOLD_OFF"]
        return raw
```

en `build_ticket_bytes`, sustituir el bloque de las líneas 199-206:

```python
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", net_total)
        raw += self.CMD["BOLD_OFF"]

        # Comision por pago con tarjeta. Vacio si la venta no la trae, asi que
        # una organizacion sin comision imprime el ticket de siempre.
        raw += self._card_surcharge_lines(sale, net_total)

        # Equivalente en dolares. Solo si la venta trae el tipo congelado
        # (`sales_documents.usd_rate`); una organizacion sin tipo de cambio ve
        # el ticket de siempre. Va DESPUES de la comision y sobre el total a
        # pagar: el equivalente es lo que el cliente entrega, no la mercancia.
        raw += self._usd_line(getattr(sale, "usd_rate", None),
                              net_total + _card_surcharge_amount(sale))
```

en `build_reissued_ticket_bytes`, el bloque equivalente (líneas 459-465):

```python
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", new_final)
        raw += self.CMD["BOLD_OFF"]

        # Misma comision que el ticket original: viene congelada en la venta y
        # NO se devuelve (diseño §7).
        raw += self._card_surcharge_lines(sale, new_final)

        # Mismo tipo de cambio que el ticket original: viene congelado en la
        # venta, no se vuelve a resolver.
        raw += self._usd_line(getattr(sale, "usd_rate", None),
                              new_final + _card_surcharge_amount(sale))
```

en `build_cash_cut_bytes`, el bloque `COBRADO POR METODO` (sustituir el bucle de las líneas 551-558):

```python
        # Comision de tarjeta cobrada al cliente en el turno. Informativa: YA
        # esta dentro de `payments['card']['total']` (el Payment de CARD se
        # guarda con ella incluida). `.get` con default para que un corte
        # reimpreso de antes de la funcion siga funcionando.
        _comision_tarjeta = audit_data.get('card_surcharges', 0) or 0

        _total_cobrado = 0.0
        for m_key, m_label in _method_labels:
            data = payments.get(m_key, {"total": 0, "count": 0})
            _total_cobrado += data.get('total') or 0
            if data['count'] > 0 or data['total'] > 0:
                line = f"{m_label} ({data['count']})"
                raw += self._rline(line, data['total'])
                # NO se suma a `_total_cobrado`: ya esta contada dentro de
                # `card`. Sumarla romperia la invariante del bloque -- el
                # desglose tiene que dar EXACTAMENTE el total, ni un peso mas.
                if m_key == 'card' and _comision_tarjeta > 0:
                    raw += self._rline("  incl. comision", _comision_tarjeta)
        raw += self._rline("Total cobrado", _total_cobrado)
```

`app/routers/cash.py`, justo después de `methods_map` (línea 640):

```python
    # 1b. Comision por pago con tarjeta cobrada en el turno (2026-09-17).
    # MISMOS estatus que `payment_stats`: la comision viaja DENTRO de esos
    # Payment de CARD, asi que las dos cifras tienen que hablar del mismo
    # universo de ventas. NO es efectivo, asi que `compute_expected_cash` ni se
    # entera y NO se toca (ver tests/test_cash_math.py).
    card_surcharges = db.query(
        func.coalesce(func.sum(SalesDocument.card_surcharge_amount), 0)
    ).filter(
        _session_filter,
        SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
    ).scalar() or 0
```

y en el diccionario de retorno, justo después del bloque `"payments": {...},` (línea 865):

```python
        # Comision por pago con tarjeta cobrada en el turno. Informativa: YA
        # esta incluida en `payments["card"]["total"]`, no se suma aparte.
        "card_surcharges": float(card_surcharges),
```

`app/schemas/sales.py`, en `SaleRead` después de `total_amount` (línea 101):

```python
    # Comision por pago con tarjeta (2026-09-17). `total_amount` NO la incluye:
    # lo que el cliente pago es la suma de los dos. `card_surcharge_pct` es
    # NULL cuando no aplico.
    card_surcharge_pct: Optional[Decimal] = None
    card_surcharge_amount: Decimal = Decimal("0")
```

`app/routers/sales.py::export_sales_csv`, encabezados (línea 1507):

```python
    writer.writerow([
        "Folio", "Fecha", "Hora", "Cliente", "Total",
        # `Total` es SOLO mercancia (ver el diseño §2): sin estas dos columnas
        # el CSV no explicaria por que el corte del dia suma mas.
        "Comisión tarjeta", "Total cobrado",
        "Estatus", "Método Pago", "Vendedor", "Notas",
    ])
```

el cálculo del renglón, justo después de `total = f"{sale.total_amount:.2f}"` (línea 1538):

```python
        total = f"{sale.total_amount:.2f}"
        comision_dec = Decimal(str(sale.card_surcharge_amount or 0))
        comision = f"{comision_dec:.2f}"
        total_cobrado = f"{Decimal(str(sale.total_amount or 0)) + comision_dec:.2f}"
```

y el `writer.writerow` final (línea 1561):

```python
        writer.writerow([folio, fecha, hora, cliente, total, comision, total_cobrado,
                         estatus, metodo_pago, vendedor, notas])
```

`tests/test_pos_printer.py`, en `_make_sale` justo después de la línea de `sale.usd_rate` (línea 69):

```python
    # Comision de tarjeta: EXPLICITA por el mismo motivo que `usd_rate` --
    # en un MagicMock cualquier atributo no declarado sale truthy. El
    # `try/except` de `_card_surcharge_amount` ya lo cubriria, pero dejarlo
    # escrito hace evidente que estas 12 pruebas cubren el ticket SIN comision.
    sale.card_surcharge_amount = Decimal(kwargs.get("card_surcharge_amount", "0"))
    sale.card_surcharge_pct = kwargs.get("card_surcharge_pct", None)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ticket_comision_tarjeta.py tests/test_corte_comision_tarjeta.py`
Expected: todas PASSED — **18 pruebas** (10 del ticket contando los 2 casos parametrizados de ancho, 4 del corte impreso, 3 de `audit_data`, 1 del CSV).

Comprobar que el ticket, el corte y el arqueo existentes siguen intactos:
Run: `python3 -m pytest -q -p no:warnings tests/test_pos_printer.py tests/test_ticket_layout.py tests/test_ticket_usd.py tests/test_cash_cut_detalle.py tests/test_cash_cut_historia.py tests/test_cash_math.py tests/test_cash_invariants.py tests/test_cash_close_guided.py`
Expected: todas PASSED, cero `failed`.

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: `838 passed, 2 skipped, 3 xfailed` (820 + 18), cero `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/pos_printer.py app/routers/cash.py app/routers/sales.py app/schemas/sales.py tests/test_pos_printer.py tests/test_ticket_comision_tarjeta.py tests/test_corte_comision_tarjeta.py
git commit -m "feat(comision): ticket, corte de caja y reportes muestran la comision de tarjeta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 4: El POS cobra la comisión y Empresa la configura

**Files:**
- Create: `frontend/src/pages/pos/cardSurcharge.ts`, `frontend/src/pages/pos/cardSurcharge.test.ts`
- Create: `frontend/src/store/cardSurchargeStore.ts`
- Modify: `frontend/src/api/organization.ts:3-19` (interfaz `Organization`), `:64-72` (`organizationApi`)
- Modify: `frontend/src/api/sales.ts:11-19` (`SaleCreateResponse`)
- Modify: `frontend/src/types/sales.ts:23-42` (`SalesDocument`)
- Modify: `frontend/src/pages/pos/POS.tsx` (import junto al de `useExchangeRateStore`; efecto de carga junto al de la línea 92; `handleCardPay` línea 332; props de los dos modales, líneas 615-635)
- Modify: `frontend/src/components/pos/modals/CardPaymentModal.tsx`
- Modify: `frontend/src/components/pos/modals/MixedPaymentModal.tsx`
- Modify: `frontend/src/pages/core/Organization.tsx` (import línea 2, `saveOrg` línea 46-63, sección nueva después de la `DaxCard` del tipo de cambio — línea 306)
- Modify: `frontend/src/pages/sales/SalesHistory.tsx:352-354`, `frontend/src/pages/hq/HQSalesLog.tsx:250-252`
- Test: `frontend/src/pages/pos/cardSurcharge.test.ts`

**Interfaces:**
- Consumes: `GET /api/organization/card-surcharge` (Task 1); `SaleRead.card_surcharge_*` y la respuesta del checkout (Tasks 2 y 3).
- Produces: `surchargeFor(total, nonCardPaid, pct) -> CardSurcharge {base, pct, amount, cardDue, totalDue}` y `formatPct(pct) -> string` en `frontend/src/pages/pos/cardSurcharge.ts`.
- Produces: `useCardSurchargeStore` con `{ pct: number, loadedAt, loading, load(force?), reset() }`.
- Produces: `organizationApi.getCardSurcharge()`.

- [ ] **Step 1: Escribir la prueba que falla**

```ts
// frontend/src/pages/pos/cardSurcharge.test.ts
import { describe, it, expect } from 'vitest'

import { formatPct, surchargeFor } from './cardSurcharge'

// Espejo en pantalla de `app/services/card_surcharge.py`: los dos tienen que
// dar EXACTAMENTE el mismo centavo, porque el cajero lee uno y el backend
// cobra el otro. Con el porcentaje en 0 el resultado es neutro: `totalDue`
// es el total y todo lo demás es 0.

describe('surchargeFor', () => {
  it('sin porcentaje no cobra nada', () => {
    expect(surchargeFor(1000, 0, 0)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
    expect(surchargeFor(1000, 0, null)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
  })

  it('cobra el 100 % de la venta cuando no hay otro pago', () => {
    // Ejemplo A del diseño.
    expect(surchargeFor(1000, 0, 3.5)).toEqual({
      base: 1000, pct: 3.5, amount: 35, cardDue: 1035, totalDue: 1035,
    })
  })

  it('en un mixto solo cobra la parte de tarjeta', () => {
    // Ejemplo B del diseño.
    expect(surchargeFor(1000, 400, 3.5)).toEqual({
      base: 600, pct: 3.5, amount: 21, cardDue: 621, totalDue: 1021,
    })
  })

  it('el efectivo que cubre todo deja la base en cero', () => {
    expect(surchargeFor(1000, 1200, 3.5)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
  })

  it('redondea medio centavo hacia arriba, igual que el backend', () => {
    // Ejemplo F: 333.33 × 3.5 % = 11.66655 → 11.67
    expect(surchargeFor(333.33, 0, 3.5).amount).toBe(11.67)
    expect(surchargeFor(1, 0, 2.5).amount).toBe(0.03)   // 0.025 → 0.03
  })

  it('acepta los strings decimales que manda el backend', () => {
    expect(surchargeFor('1000.00', '400.00', '3.50').amount).toBe(21)
  })

  it('nunca devuelve NaN con entradas basura', () => {
    expect(surchargeFor(null, null, 3.5)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 0,
    })
    expect(surchargeFor(1000, 0, 'abc').totalDue).toBe(1000)
    expect(surchargeFor(1000, 0, -3).amount).toBe(0)
  })

  it('las dos invariantes siempre valen', () => {
    for (const [total, efectivo, pct] of [[1000, 0, 3.5], [1000, 400, 3.5], [333.33, 0, 2.9], [19.99, 5, 20]]) {
      const s = surchargeFor(total, efectivo, pct)
      expect(s.totalDue).toBeCloseTo(total + s.amount, 2)
      expect(s.cardDue).toBeCloseTo(s.base + s.amount, 2)
    }
  })
})

describe('formatPct', () => {
  it('no arrastra ceros de relleno', () => {
    expect(formatPct(3.5)).toBe('3.5')
    expect(formatPct(3)).toBe('3')
    expect(formatPct(2.75)).toBe('2.75')
    expect(formatPct('20.00')).toBe('20')
  })

  it('entrada inválida devuelve 0', () => {
    expect(formatPct(null)).toBe('0')
    expect(formatPct('abc')).toBe('0')
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/pos/cardSurcharge.test.ts`
Expected: FAIL — `Failed to resolve import "./cardSurcharge"`.

- [ ] **Step 3: Implementar**

`frontend/src/pages/pos/cardSurcharge.ts` (nuevo):

```ts
/**
 * Comisión por pago con tarjeta — espejo en pantalla del servicio del backend.
 *
 * Funciones puras (sin React ni axios) para que `vitest` las pruebe: el
 * proyecto solo corre `src/**\/*.test.ts` con `environment: 'node'`.
 *
 * El número que se COBRA y se PERSISTE lo calcula `app/services/card_surcharge.py`
 * con `Decimal`; esto es lo que ve el cajero antes de confirmar. Las dos
 * implementaciones redondean a centavos hacia arriba en el medio, así que la
 * pantalla y el cargo coinciden al centavo. Si divergen, el cajero cobra un
 * importe y el ticket imprime otro, con el cliente delante.
 *
 * Regla (diseño §4):
 *     base    = max(0, total − pagos que NO son tarjeta)
 *     amount  = redondear(base × pct / 100)
 *     cardDue = base + amount
 *     totalDue = total + amount
 */

export interface CardSurcharge {
  /** Importe sobre el que se cobra la comisión. */
  base: number
  /** Porcentaje efectivamente aplicado (0 si no aplicó). */
  pct: number
  /** La comisión, en pesos. */
  amount: number
  /** Lo que debe pasar por la terminal: `base + amount`. */
  cardDue: number
  /** Lo que el cliente entrega en total: `total + amount`. */
  totalDue: number
}

type Numerico = number | string | null | undefined

/** Número redondeado a centavos. Entrada inválida → 0. */
function cents(value: Numerico): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

export function surchargeFor(
  total: Numerico,
  nonCardPaid: Numerico,
  pct: Numerico,
): CardSurcharge {
  const totalQ = cents(total)
  const pctQ = cents(pct)
  const neutro: CardSurcharge = { base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: totalQ }

  if (!(pctQ > 0)) return neutro

  // `base` nunca negativa: un billete grande tecleado como efectivo no puede
  // regalarle al cliente una comisión al revés.
  const base = cents(totalQ - cents(nonCardPaid))
  if (!(base > 0)) return neutro

  // `round(base × pct) / 100` es exactamente `round(base × pct / 100, 2)`, y
  // evita el error de coma flotante de dividir antes de redondear.
  const amount = Math.round(base * pctQ) / 100
  if (!(amount > 0)) return neutro

  return {
    base,
    pct: pctQ,
    amount,
    cardDue: cents(base + amount),
    totalDue: cents(totalQ + amount),
  }
}

/** `3.5`, `2.75`, `3`. Sin ceros de relleno, igual que la etiqueta del ticket. */
export function formatPct(pct: Numerico): string {
  const n = Number(pct)
  if (!Number.isFinite(n)) return '0'
  return String(Number(n.toFixed(2)))
}
```

`frontend/src/api/organization.ts`, en la interfaz `Organization` después de `usd_rate_margin` (línea 18):

```ts
  // Comisión por pago con tarjeta (2026-09-17). 0 = apagada: no se cobra ni se
  // muestra nada en el POS, el ticket, el corte ni los reportes.
  card_surcharge_pct?: number | string
```

y en `organizationApi`, después de `refreshExchangeRate` (línea 72):

```ts
  getCardSurcharge: async (): Promise<{ pct: number | string }> => {
    const { data } = await client.get<{ pct: number | string }>('/organization/card-surcharge')
    return data
  },
```

`frontend/src/store/cardSurchargeStore.ts` (nuevo):

```ts
import { create } from 'zustand'

import { organizationApi } from '../api/organization'

/**
 * Caché del porcentaje de comisión por pago con tarjeta de la organización.
 *
 * Lo llena `GET /api/organization/card-surcharge` — endpoint propio y barato,
 * por el mismo motivo que el del tipo de cambio: quien lo consume es la cajera,
 * que no es admin y no debe leer la configuración fiscal completa para cobrar.
 *
 * `pct === 0` significa "no cobrar ni mostrar nada": es el estado de toda
 * organización que no la configuró, y también el estado ante un error de red.
 * **Falla cerrado a propósito**: si el store no sabe cuánto es, el POS cobra
 * solo la mercancía y el backend responde 422 con el importe correcto en
 * español — preferible a inventar un cargo que el cliente no debe.
 */
const REFRESCO_MS = 30 * 60 * 1000 // configuración estática; no cambia sola

interface CardSurchargeStore {
  pct: number
  loadedAt: number | null
  loading: boolean
  load: (force?: boolean) => Promise<void>
  reset: () => void
}

export const useCardSurchargeStore = create<CardSurchargeStore>((set, get) => ({
  pct: 0,
  loadedAt: null,
  loading: false,

  load: async (force = false) => {
    const { loading, loadedAt } = get()
    if (loading) return
    if (!force && loadedAt !== null && Date.now() - loadedAt < REFRESCO_MS) return
    set({ loading: true })
    try {
      const info = await organizationApi.getCardSurcharge()
      const pct = Number(info?.pct)
      set({
        pct: Number.isFinite(pct) && pct > 0 ? pct : 0,
        loadedAt: Date.now(),
        loading: false,
      })
    } catch {
      set({ pct: 0, loadedAt: Date.now(), loading: false })
    }
  },

  reset: () => set({ pct: 0, loadedAt: null, loading: false }),
}))
```

`frontend/src/pages/pos/POS.tsx` — import junto al de `useExchangeRateStore`:

```ts
import { useCardSurchargeStore } from '../../store/cardSurchargeStore'
import { surchargeFor } from './cardSurcharge'
```

el hook y el efecto de carga, justo después del bloque de `loadUsdRate` (línea 92):

```ts
  // Comisión por pago con tarjeta. Se carga al entrar al POS; `pct = 0` (toda
  // organización que no la configuró) deja los modales exactamente como antes.
  const surchargePct = useCardSurchargeStore((s) => s.pct)
  const loadSurcharge = useCardSurchargeStore((s) => s.load)
  useEffect(() => { loadSurcharge() }, [loadSurcharge])
```

`handleCardPay` (línea 332):

```ts
  const handleCardPay = async (reference: string) => {
    // El importe que pasa por la terminal incluye la comisión. El backend lo
    // recalcula y rechaza cualquier otro con un 422 en español: el cajero no
    // puede quitarla.
    const { totalDue } = surchargeFor(total, 0, surchargePct)
    await submitSale([{ method: 'CARD', amount: totalDue, reference }])
  }
```

y los dos modales de pago (líneas 615-635) reciben el porcentaje:

```tsx
      {payModal === 'CARD' && (
        <CardPaymentModal
          total={total}
          surchargePct={surchargePct}
          onClose={() => setPayModal(null)}
          onConfirm={handleCardPay}
        />
      )}
```
```tsx
      {payModal === 'MIXED' && (
        <MixedPaymentModal
          total={total}
          surchargePct={surchargePct}
          onClose={() => setPayModal(null)}
          onConfirm={handleMixedPay}
        />
      )}
```

`frontend/src/components/pos/modals/CardPaymentModal.tsx` — imports, props y cabecera:

```tsx
import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { formatPct, surchargeFor } from '../../../pages/pos/cardSurcharge'

interface Props {
  total: number
  /** Comisión por pago con tarjeta de la organización. 0 = apagada. */
  surchargePct?: number
  onClose: () => void
  onConfirm: (reference: string) => Promise<void>
}

export function CardPaymentModal({ total, surchargePct = 0, onClose, onConfirm }: Props) {
  const [reference, setReference] = useState('')
  const [loading, setLoading] = useState(false)

  // 100 % tarjeta: no hay pagos de otro método, así que la comisión va sobre
  // el total completo. Con `surchargePct = 0` el desglose no se pinta y el
  // modal queda idéntico al de siempre.
  const cargo = surchargeFor(total, 0, surchargePct)

  const submit = async () => {
    setLoading(true)
    try { await onConfirm(reference) } finally { setLoading(false) }
  }
```

la cabecera pasa a mostrar el total a pagar y, debajo del recuadro de la terminal, el desglose (sustituye el `<p>` de la línea 30 y agrega un bloque tras el recuadro de la línea 34-37):

```tsx
            <p className="text-slate-500 text-sm">{formatCurrency(cargo.amount > 0 ? cargo.totalDue : total)}</p>
```
```tsx
        {cargo.amount > 0 && (
          <div className="rounded-xl p-3 mb-4 text-sm space-y-1" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
            <div className="flex justify-between text-slate-400">
              <span>Mercancía</span><span className="tabular-nums">{formatCurrency(total)}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Comisión tarjeta {formatPct(cargo.pct)}%</span>
              <span className="tabular-nums">{formatCurrency(cargo.amount)}</span>
            </div>
            <div className="flex justify-between font-bold text-white pt-1" style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
              <span>Total a pagar</span><span className="tabular-nums">{formatCurrency(cargo.totalDue)}</span>
            </div>
          </div>
        )}
```

`frontend/src/components/pos/modals/MixedPaymentModal.tsx` — imports, props y cálculo:

```tsx
import { useState } from 'react'
import { formatCurrency } from '../../../utils/currency'
import { formatPct, surchargeFor } from '../../../pages/pos/cardSurcharge'
```
```tsx
interface Props {
  total: number
  /** Comisión por pago con tarjeta de la organización. 0 = apagada. */
  surchargePct?: number
  onClose: () => void
  onConfirm: (payments: { method: string; amount: number; reference?: string }[]) => Promise<void>
}

export function MixedPaymentModal({ total, surchargePct = 0, onClose, onConfirm }: Props) {
  const [lines, setLines] = useState<PaymentLine[]>([
    { method: 'CASH', amount: String(total.toFixed(2)), reference: '' },
  ])
  const [loading, setLoading] = useState(false)

  const paid = lines.reduce((s, l) => s + (parseFloat(l.amount) || 0), 0)
  // La comisión se calcula sobre lo que NO se paga con tarjeta, en vivo: si el
  // cajero mueve el renglón de efectivo, el total a pagar se mueve con él.
  const nonCardPaid = lines
    .filter((l) => l.method !== 'CARD')
    .reduce((s, l) => s + (parseFloat(l.amount) || 0), 0)
  const cargo = surchargeFor(total, nonCardPaid, surchargePct)
  // Neutralidad: con la comisión apagada, `totalDue` es el `total` tal cual y
  // el modal se comporta exactamente como antes.
  const totalDue = cargo.amount > 0 ? cargo.totalDue : total
  const remaining = totalDue - paid
  const change = paid - totalDue
```

el botón para completar el renglón de tarjeta, justo antes del de «Agregar método» (línea 109):

```tsx
      {cargo.amount > 0 && (
        <button
          onClick={() => {
            const idx = lines.findIndex((l) => l.method === 'CARD')
            const monto = cargo.cardDue.toFixed(2)
            if (idx === -1) setLines((l) => [...l, { method: 'CARD', amount: monto, reference: '' }])
            else updateLine(idx, { amount: monto })
          }}
          className="dax-btn-secondary text-xs w-full justify-center mb-2"
          title="Pone en el renglón de tarjeta lo que falta, con la comisión incluida"
        >
          <i className="fa-solid fa-credit-card" /> Completar con tarjeta ({formatCurrency(cargo.cardDue)})
        </button>
      )}
```

y el recuadro de resumen (líneas 114-125) gana dos renglones:

```tsx
        <div className={`rounded-xl p-3 mb-4 text-sm space-y-1 ${remaining > 0.005 ? 'bg-red-600/10 border border-red-600/30' : 'bg-emerald-600/10 border border-emerald-600/30'}`}>
          <div className="flex justify-between text-slate-400">
            <span>{cargo.amount > 0 ? 'Mercancía' : 'Total'}</span><span>{formatCurrency(total)}</span>
          </div>
          {cargo.amount > 0 && (
            <>
              <div className="flex justify-between text-slate-400">
                <span>Comisión tarjeta {formatPct(cargo.pct)}%</span>
                <span>{formatCurrency(cargo.amount)}</span>
              </div>
              <div className="flex justify-between text-white font-semibold">
                <span>Total a pagar</span><span>{formatCurrency(totalDue)}</span>
              </div>
            </>
          )}
          <div className="flex justify-between text-slate-400">
            <span>Pagado</span><span>{formatCurrency(paid)}</span>
          </div>
          <div className={`flex justify-between font-bold pt-1 ${remaining > 0.005 ? 'text-red-400' : 'text-emerald-400'}`} style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
            <span>{remaining > 0.005 ? 'Pendiente' : change > 0.005 ? 'Cambio' : 'Exacto'}</span>
            <span>{formatCurrency(remaining > 0.005 ? remaining : change)}</span>
          </div>
        </div>
```

`frontend/src/api/sales.ts`, en `SaleCreateResponse` (línea 18):

```ts
  credit_debt: number
  /** Comisión por pago con tarjeta cobrada. 0 = no aplicó. `total` es solo mercancía. */
  card_surcharge_amount?: number
  card_surcharge_pct?: number | null
```

`frontend/src/types/sales.ts`, en `SalesDocument` después de `total_amount` (línea 36):

```ts
  total_amount: number
  /** Comisión por pago con tarjeta. `total_amount` NO la incluye. */
  card_surcharge_amount?: number
  card_surcharge_pct?: number | null
```

`frontend/src/pages/core/Organization.tsx` — en `saveOrg` (línea 52-55), normalizar el campo vacío igual que el margen del tipo de cambio:

```ts
      // Borrar el ajuste sobre el FIX o la comisión deja '' en el input
      // numérico, y el PUT responde 422 ("Input should be a valid decimal"):
      // vacío = sin ajuste / sin comisión.
      const margen = orgForm.usd_rate_margin
      const comision = orgForm.card_surcharge_pct
      const updated = await organizationApi.updateOrg({
        ...orgForm,
        usd_rate_margin: margen === '' || margen == null ? 0 : margen,
        card_surcharge_pct: comision === '' || comision == null ? 0 : comision,
      })
```

y una sección nueva después de la `DaxCard` del tipo de cambio (línea 306), antes de la de "Encabezado y Pie de Ticket":

```tsx
          {/* Comisión por pago con tarjeta */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-credit-card mr-1.5" />Comisión por pago con tarjeta
            </p>
            <p className="text-xs text-slate-400 mb-4">
              Se suma únicamente a la parte de la venta que se cobra con tarjeta; en un
              pago mixto, solo a esa parte. Aparece en el punto de venta, en el ticket,
              en el corte de caja y en los reportes, <b>separada del total de la
              mercancía</b>. <b>0 = sin comisión.</b>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="dax-label">Porcentaje (%)</label>
                <input
                  type="number" step="0.01" min="0" max="20"
                  value={orgForm.card_surcharge_pct ?? '0'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, card_surcharge_pct: e.target.value }))}
                  className="dax-input w-full tabular-nums"
                  placeholder="3.5"
                />
                <p className="text-[10px] mt-1 text-slate-600">0 = sin comisión. Máximo 20 %.</p>
              </div>
              <div className="sm:col-span-2 flex items-end">
                <p className="text-xs text-slate-400">
                  {Number(orgForm.card_surcharge_pct ?? 0) > 0 ? (
                    <>Una venta de <b className="tabular-nums text-slate-200">$1,000.00</b> pagada
                    con tarjeta se cobrará como <b className="tabular-nums text-emerald-400">
                    {(1000 * (1 + Number(orgForm.card_surcharge_pct) / 100)).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}</b>.</>
                  ) : (
                    <>La comisión está apagada: el punto de venta y el ticket no muestran nada.</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>
```

`frontend/src/pages/sales/SalesHistory.tsx`, en el bloque de totales del detalle, entre el renglón de IVA y el de Total (líneas 353-354):

```tsx
              <div className="flex justify-between font-black text-white text-base pt-1"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
              {Number(selected.card_surcharge_amount ?? 0) > 0 && (
                <>
                  <div className="flex justify-between text-slate-400">
                    <span>Comisión tarjeta {selected.card_surcharge_pct ?? ''}%</span>
                    <span>{formatCurrency(Number(selected.card_surcharge_amount))}</span>
                  </div>
                  <div className="flex justify-between font-black text-emerald-400 text-base">
                    <span>Total cobrado</span>
                    <span>{formatCurrency(Number(selected.total_amount) + Number(selected.card_surcharge_amount))}</span>
                  </div>
                </>
              )}
```

`frontend/src/pages/hq/HQSalesLog.tsx`: el mismo bloque, después del renglón de Total (línea 252).

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: vitest en verde (**296 + 10 = 306 pruebas, 33 archivos**), `tsc` sin errores, build ok.

Verificación manual mínima (backend corriendo, organización con la comisión en 0):
1. Entrar al POS y cobrar con tarjeta → el modal y el ticket se ven exactamente como antes. Esa es la prueba de neutralidad.
2. **Empresa → Comisión por pago con tarjeta**, escribir `3.5` y Guardar. Escribir `35` → el Guardar muestra el mensaje en español del 422.
3. Recargar el POS. Cobrar $1,000 con tarjeta: el modal muestra `Mercancía $1,000.00`, `Comisión tarjeta 3.5% $35.00`, `Total a pagar $1,035.00`. El ticket imprime `TOTAL $1,000.00`, `COM. TARJETA 3.5% $35.00`, `TOTAL A PAGAR $1,035.00`.
4. Cobro mixto: teclear $400 en efectivo, pulsar «Completar con tarjeta» → el renglón de tarjeta queda en $621.00 y el resumen en `Total a pagar $1,021.00`. Cobrar y verificar que el ticket no reporta cambio.
5. Historial de ventas → detalle: `Total $1,000.00`, `Comisión tarjeta 3.5 %`, `Total cobrado $1,035.00`. Exportar el CSV y comprobar las dos columnas.
6. Cerrar el turno e imprimir el corte: bajo `Tarjeta (2)` aparece `incl. comision $56.00` y `Total cobrado` sigue siendo la suma exacta de los métodos. Cancelar las ventas de prueba.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/pos/cardSurcharge.ts frontend/src/pages/pos/cardSurcharge.test.ts frontend/src/store/cardSurchargeStore.ts frontend/src/api/organization.ts frontend/src/api/sales.ts frontend/src/types/sales.ts frontend/src/pages/pos/POS.tsx frontend/src/components/pos/modals/CardPaymentModal.tsx frontend/src/components/pos/modals/MixedPaymentModal.tsx frontend/src/pages/core/Organization.tsx frontend/src/pages/sales/SalesHistory.tsx frontend/src/pages/hq/HQSalesLog.tsx
git commit -m "feat(comision): el POS cobra la comision de tarjeta y Empresa la configura

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

## Despliegue

1. Suite backend (`838 passed, 2 skipped, 3 xfailed`) y frontend (`306 passed`) en verde, más `npx tsc --noEmit` y `npm run build`.
2. Fusionar la rama a `main` **con permiso del usuario**; el push a `main` redespliega Railway (Kaory). `railway_init` aplica los tres `ALTER` idempotentes.
3. VPS: `git archive --format=tar HEAD | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'` y `ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'`. Verificar **dentro del contenedor**, no en `src/`.
4. **Orden obligatorio: backend antes que frontend.** El backend no depende del POS; el POS sí del endpoint nuevo. Aun así el store falla cerrado (`pct = 0`), así que el peor caso de un desfase es que el POS cobre solo la mercancía y el checkout responda 422 con el importe correcto en español.
5. Verificar que la función sigue **apagada** en todas las organizaciones:
   `GET /api/organization/card-surcharge` con cualquier sesión devuelve `{"pct": 0}`, una venta con tarjeta responde `card_surcharge_amount: 0.0` y el ticket se ve idéntico. Esa es la prueba de que el despliegue fue neutro.
6. En la organización que la pidió: **Empresa → Comisión por pago con tarjeta**, capturar el porcentaje, y validar con una venta de prueba que después se cancela — cobro con tarjeta, cobro mixto, ticket y corte.
7. Confirmar en base, no en el log (los registros de Railway son efímeros):
   `SELECT folio, total_amount, card_surcharge_pct, card_surcharge_amount FROM sales_documents WHERE card_surcharge_amount > 0 ORDER BY created_at DESC LIMIT 10;`

## Auto-revisión del plan

- **Cobertura del diseño.** Decisión 1 (porcentaje por organización) → Task 1; 2 (`NUMERIC(5,2)`) → Task 1 + prueba de ancho de la Task 3; 3 (rango 0-20 con 422) → Task 1, cuatro pruebas de `PUT`; 4 (solo ADMIN/DUEÑO sin guardia nueva) → Task 1, `test_cajero_no_puede_configurar`; 5 (solo `CARD`) → Task 1 (`test_la_transferencia_tambien_es_base_sin_comision`) y Task 2 (`test_la_transferencia_no_causa_comision`); 6 (`total_amount` no cambia) → Task 2, comprobado en la respuesta, en el documento y en `kpis.total_sales` del corte; 7 (el `Payment` de CARD lleva la comisión) → Task 2, `test_cien_por_ciento_tarjeta`; 8 (`compute_expected_cash` intacto) → Task 3, `test_compute_expected_cash_no_ve_la_comision`; 9 (servicio como fuente única) → Task 1, consumido por las Tasks 2, 3 y 4; 10 (snapshot congelado) → Task 2, `TestIdempotencia`, y Task 3, ticket reemitido; 11 (el cajero no puede quitarla) → Task 2, `test_pagar_solo_la_mercancia_es_422`; 12 (la devolución no la reintegra) → Task 3, `test_el_reemitido_conserva_la_comision_original`; 13 (endpoint dedicado, no `/me/context`) → Tasks 1 y 4; 14 (la columna del CSV va en `sales.py`) → Task 3, `TestExportCsv`; 15 (renglón informativo en el corte) → Task 3, `test_la_comision_no_se_suma_al_total_cobrado`; 16 («Completar con tarjeta» en vez de un efecto) → Task 4.
  El alcance "dentro" del diseño §8 queda cubierto entero: columna y validación (1), servicio (1), endpoint de lectura (1), dos columnas de venta (2), `create_sale` (2), ticket y reemitido (3), corte y `card_surcharges` (3), `SaleRead` y CSV (3), POS, Empresa e historial (4).
- **Consistencia de nombres entre tareas.** `calcular_comision`, `pct_de_organizacion`, `hay_pago_con_tarjeta`, `validar_pct`, `ComisionTarjeta`, `METODO_TARJETA`, `PCT_MAXIMO`, `CENTAVOS`, `CERO` (Task 1 → 2); `SalesDocument.card_surcharge_pct` / `.card_surcharge_amount` (Task 2 → 3 y 4); `_card_surcharge_amount`, `_fmt_pct`, `_card_surcharge_lines` (Task 3, internos de `pos_printer`); `card_surcharges` (Task 3, del `audit_data` al corte impreso); `CardSurchargeRead {pct}` en el backend ↔ `organizationApi.getCardSurcharge()` y `useCardSurchargeStore.pct` en el frontend; `surchargeFor`/`formatPct` y el tipo `CardSurcharge {base, pct, amount, cardDue, totalDue}` (Task 4, consumidos por `POS.tsx` y los dos modales); `surchargePct` es el único nombre con el que el porcentaje viaja como prop a los modales. Los campos del backend `ComisionTarjeta {base, pct, monto, pago_tarjeta, total_a_pagar}` y los del frontend `{base, pct, amount, cardDue, totalDue}` son el mismo concepto con nombres en su idioma respectivo — el resto del backend está en español y el frontend en inglés, igual que `to_usd` ↔ `usdEquivalent`.
- **Correcciones aplicadas tras la revisión.**
  - La columna es `NUMERIC(5,2)` y no `NUMERIC(6,3)`: `_total_line` da 20 columnas de etiqueta a 58 mm y **no trunca**, así que el tercer decimal rompería el ancho del papel. La prueba parametrizada con el tope de 19.99 % lo fija.
  - La columna del CSV va en `app/routers/sales.py::export_sales_csv`, no en `app/routers/reports.py`: el `/export/csv` de `reports.py` es un volcado de KPIs sin renglón por venta.
  - Se agregó una columna «Total cobrado» junto a «Comisión tarjeta»: con `total_amount` = mercancía, el CSV sin esa suma obligaría a quien lo lee a hacerla a mano.
  - El `PUT` descarta `card_surcharge_pct: null` en vez de escribirlo: la columna es `NOT NULL` y el panel manda el objeto completo, así que escribir `None` sería un 500 al commitear. Fijado por `test_null_no_borra_la_columna`.
  - `cash_needed` (no solo la validación) pasa a usar `total_a_cobrar`: si no, en un mixto el sistema devolvería de cambio exactamente la comisión que acaba de cobrar. `test_mixto_solo_cobra_la_parte_de_tarjeta` lo fija con `change == 0`.
  - `balance_diff` sigue usando `total_sale`: la deuda a crédito es por la mercancía, no por la comisión.
  - La consulta de `Organization` de la línea 513 se guarda en una variable en vez de agregar una segunda: el checkout no gana ni un `SELECT`.
  - La línea USD del ticket pasa a calcularse sobre el total a pagar y colocarse después de la comisión — el equivalente en dólares es lo que el cliente entrega. `test_sin_comision_la_linea_usd_no_se_mueve` fija que sin comisión el número no cambia.
  - `_card_surcharge_amount` envuelve el `float()` en `try`: eso ya hace inofensivo el `MagicMock` de `tests/test_pos_printer.py`, pero `_make_sale` declara las dos columnas igual, para que el lector vea que esas 12 pruebas cubren el ticket **sin** comisión.
  - El renglón del corte es `"  incl. comision"` (16 caracteres) y no `"  incl. comision tarj."` (22): con un importe de cinco cifras, `_rline` truncaría la etiqueta a 58 mm.
- **Fuera de alcance explícito de este plan** (ver el diseño §8): devolver la comisión; comisión por transferencia, cheque o crédito de tienda; tasa por terminal, por banco o por sucursal; IVA sobre la comisión y CFDI; `GET /api/sales/stats` y cualquier KPI de periodo; `quotes convert-to-sale`; cotizaciones, apartados y estado de cuenta; interruptor por venta para que el cajero la quite.
