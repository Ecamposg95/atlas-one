"""Prueba de concurrencia REAL del dinero (candados `FOR UPDATE`) contra Postgres.

`with_for_update()` es un no-op en SQLite, asi que la suite de pytest no puede
probar estos candados (CLAUDE.md, regla de oro #7). Este script levanta la app
en proceso, dispara peticiones simultaneas desde dos hilos contra un Postgres
DESECHABLE y cuenta que paso:

  1. venta        dos cajas cobran a la vez la ULTIMA pieza
  2. cancelacion  la misma venta se cancela dos veces a la vez
  3. abono        el mismo ticket fiado se liquida dos veces a la vez
  4. cotizacion   la misma cotizacion se convierte en venta dos veces a la vez
  5. devolucion   la misma devolucion se aprueba dos veces a la vez
  6. cancelar vs. aprobar   se cancela la venta mientras se aprueba su devolucion

Sin candados: se venden 2 piezas habiendo 1 (la existencia queda en 0 por
actualizacion perdida, no en negativo: lo vendido no cuadra con lo descontado),
la cancelacion repone el stock dos veces, el ticket se cobra dos veces y la
cotizacion se cobra dos veces.

NUNCA contra produccion: escribe datos. El script se niega a correr si la base
no es Postgres, si falta `--base-desechable` o si ya hay ventas que no creo el
mismo.

Como correrlo (red y contenedor propios; se borran al terminar):

    docker network create atlas-conc
    docker run -d --name atlas-conc-pg --network atlas-conc \
        -e POSTGRES_PASSWORD=x postgres:17
    docker run --rm --network atlas-conc -v "$PWD":/w -w /w \
        -e DATABASE_URL=postgresql://postgres:x@atlas-conc-pg:5432/postgres \
        -e ALLOWED_HOSTS=testserver atlas-one-backend:latest \
        sh -c "pip install -q httpx && python scripts/railway_init.py \
               && python scripts/prueba_concurrencia_ventas.py --base-desechable"
    docker rm -f atlas-conc-pg && docker network rm atlas-conc

Sale con codigo 0 si no hubo ninguna anomalia y 1 si la hubo.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ALLOWED_HOSTS", "testserver")

PREFIJO = "PRUEBA-CONCURRENCIA"


def _dos_a_la_vez(llamadas):
    """Corre las llamadas en hilos que arrancan juntos; devuelve sus respuestas."""
    barrera = threading.Barrier(len(llamadas))
    respuestas = [None] * len(llamadas)

    def _correr(i, fn):
        barrera.wait()
        try:
            respuestas[i] = fn()
        except Exception as exc:  # la app revento sin responder
            respuestas[i] = exc

    hilos = [threading.Thread(target=_correr, args=(i, fn)) for i, fn in enumerate(llamadas)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return respuestas


def _ok(r) -> bool:
    return not isinstance(r, Exception) and r.status_code in (200, 201)


def _codigos(rs):
    return [("EXC" if isinstance(r, Exception) else r.status_code) for r in rs]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-desechable", action="store_true",
                    help="confirma que DATABASE_URL apunta a una base que se puede ensuciar")
    ap.add_argument("--rondas", type=int, default=20)
    args = ap.parse_args()

    from app.core.database import SessionLocal, engine

    if engine.dialect.name != "postgresql":
        print("Solo tiene sentido en Postgres (en SQLite el candado es un no-op).")
        return 2
    if not args.base_desechable:
        print("Falta --base-desechable: este script ESCRIBE datos. Nunca en produccion.")
        return 2

    import logging
    logging.disable(logging.INFO)  # la bitacora por peticion tapa el resumen

    from fastapi.testclient import TestClient

    from app.core.security import create_access_token, get_password_hash
    from app.main import app
    from app.models.cash import CashSession
    from sqlalchemy import text

    from app.models.inventory import InventoryMovement, MovementType, StockOnHand
    from app.models.modules import Module, OrganizationModule
    from app.models.organization import Branch, BranchType, Organization
    from app.models.products import Product, ProductBranchStatus, ProductVariant
    from app.models.sales import Payment, SalesDocument
    from app.models.users import Role, User, UserOrganization
    from app.modules.customers.models import Customer

    db = SessionLocal()
    # `railway_init.py` siembra organizaciones de demostracion, pero ninguna
    # venta: una base con ventas que no son de este script es una base real.
    ajenas = (
        db.query(SalesDocument)
        .join(Organization, Organization.id == SalesDocument.organization_id)
        .filter(~Organization.name.like(f"{PREFIJO}%"))
        .count()
    )
    if ajenas:
        print(f"La base tiene {ajenas} ventas reales: no es desechable. Abortado.")
        return 2

    # ── Siembra ────────────────────────────────────────────────────────────
    marca = uuid.uuid4().hex[:8]
    org = Organization(name=f"{PREFIJO} {marca}", status="ACTIVE")
    db.add(org); db.flush()
    suc = Branch(name="Matriz", branch_type=BranchType.STORE, can_sell=True,
                 is_active=True, organization_id=org.id)
    db.add(suc); db.flush()
    for clave in ("pos", "crm", "quotes"):
        if db.query(Module).filter(Module.key == clave).first() is None:
            db.add(Module(key=clave, name=clave)); db.flush()
        db.add(OrganizationModule(organization_id=org.id, module_key=clave, is_enabled=True))
    cabeceras = []
    for n in (1, 2):
        u = User(username=f"conc_{marca}_{n}", password_hash=get_password_hash("x"),
                 role=Role.GERENTE, branch_id=suc.id, is_active=True)  # aprueba devoluciones
        db.add(u); db.flush()
        db.add(UserOrganization(user_id=u.id, organization_id=org.id,
                                org_role="MEMBER", is_active=True))
        db.add(CashSession(user_id=u.id, branch_id=suc.id, organization_id=org.id,
                           opening_balance=Decimal("0"), status="OPEN"))
        cabeceras.append({
            "Authorization": f"Bearer {create_access_token({'sub': u.username})}",
            "X-Organization-ID": str(org.id),
        })
    prod = Product(name="Pieza unica", organization_id=org.id, is_active=True)
    db.add(prod); db.flush()
    var = ProductVariant(product_id=prod.id, sku=f"CONC-{marca}", price=Decimal("100"),
                         cost=Decimal("60"), organization_id=org.id)
    db.add(var); db.flush()
    db.add(ProductBranchStatus(variant_id=var.id, branch_id=suc.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    existencia = StockOnHand(variant_id=var.id, branch_id=suc.id, organization_id=org.id,
                             qty_on_hand=Decimal("0"), is_active=True)
    db.add(existencia)
    cliente = Customer(name="Cliente fiado", organization_id=org.id, has_credit=True,
                       credit_limit=Decimal("100000"), current_balance=Decimal("0"))
    db.add(cliente)
    db.commit()
    org_id, stock_id, cliente_id, sku = org.id, existencia.id, cliente.id, var.sku
    variante_id = var.id
    db.close()

    clientes_http = [TestClient(app), TestClient(app)]

    def fijar_stock(qty):
        s = SessionLocal()
        s.query(StockOnHand).filter(StockOnHand.id == stock_id).update({"qty_on_hand": qty})
        s.commit(); s.close()

    def leer_stock() -> Decimal:
        s = SessionLocal()
        q = s.query(StockOnHand.qty_on_hand).filter(StockOnHand.id == stock_id).scalar()
        s.close()
        return Decimal(str(q))

    def vender(i, piezas=1, **extra):
        cuerpo = {"doc_type": "ORDER", "items": [{"sku": sku, "quantity": piezas}],
                  "payments": [{"method": "CASH", "amount": f"{100 * piezas}.00"}], **extra}
        return clientes_http[i].post("/api/sales/", json=cuerpo, headers=cabeceras[i])

    anomalias = {"venta": 0, "cancelacion": 0, "abono": 0, "cotizacion": 0,
                 "devolucion": 0, "cancelar_vs_aprobar": 0}
    errores_500 = 0

    # ── 1. Dos cajas, la ultima pieza ──────────────────────────────────────
    for ronda in range(args.rondas):
        fijar_stock(Decimal("1"))
        rs = _dos_a_la_vez([lambda: vender(0), lambda: vender(1)])
        vendidas = sum(1 for r in rs if _ok(r))
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        final = leer_stock()
        if vendidas != 1 or final != Decimal("0"):
            anomalias["venta"] += 1
            print(f"  [venta {ronda}] respuestas={_codigos(rs)} vendidas={vendidas} "
                  f"de 1 en existencia, existencia final={final}")

    # ── 2. Doble cancelacion de la misma venta ─────────────────────────────
    for ronda in range(args.rondas):
        fijar_stock(Decimal("5"))
        r = vender(0)
        assert _ok(r), r.text
        sale_id = r.json()["sale_id"]
        rs = _dos_a_la_vez([
            lambda: clientes_http[0].delete(f"/api/sales/{sale_id}", headers=cabeceras[0]),
            lambda: clientes_http[1].delete(f"/api/sales/{sale_id}", headers=cabeceras[1]),
        ])
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        final = leer_stock()
        if sum(1 for r in rs if _ok(r)) != 1 or final != Decimal("5"):
            anomalias["cancelacion"] += 1
            print(f"  [cancelacion {ronda}] respuestas={_codigos(rs)} "
                  f"existencia final={final} (debia volver a 5)")

    # ── 3. Doble abono que liquida el mismo ticket fiado ───────────────────
    for ronda in range(args.rondas):
        fijar_stock(Decimal("5"))
        s = SessionLocal()
        saldo_antes = Decimal(str(s.query(Customer.current_balance)
                                  .filter(Customer.id == cliente_id).scalar()))
        s.close()
        r = vender(0, customer_id=cliente_id, payments=[])
        assert _ok(r), r.text
        sale_id = r.json()["sale_id"]
        abono = {"amount": "100.00", "method": "CASH", "sales_document_id": sale_id}
        rs = _dos_a_la_vez([
            lambda: clientes_http[0].post(f"/api/customers/{cliente_id}/pay",
                                          json=abono, headers=cabeceras[0]),
            lambda: clientes_http[1].post(f"/api/customers/{cliente_id}/pay",
                                          json=abono, headers=cabeceras[1]),
        ])
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        s = SessionLocal()
        pagos = s.query(Payment).filter(Payment.sales_document_id == sale_id).count()
        saldo = Decimal(str(s.query(Customer.current_balance)
                            .filter(Customer.id == cliente_id).scalar()))
        s.close()
        if pagos != 1 or saldo != saldo_antes:
            anomalias["abono"] += 1
            print(f"  [abono {ronda}] respuestas={_codigos(rs)} pagos registrados={pagos} "
                  f"(debia ser 1), saldo del cliente {saldo_antes} -> {saldo}")

    # ── 4. Doble conversion de la misma cotizacion ─────────────────────────
    for ronda in range(args.rondas):
        fijar_stock(Decimal("5"))
        r = clientes_http[0].post("/api/quotes/", headers=cabeceras[0], json={
            "doc_type": "QUOTE", "items": [{"sku": sku, "quantity": 1}], "payments": []})
        assert _ok(r), r.text
        qid = r.json()["quote_id"]
        url = f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH"
        rs = _dos_a_la_vez([
            lambda: clientes_http[0].post(url, headers=cabeceras[0]),
            lambda: clientes_http[1].post(url, headers=cabeceras[1]),
        ])
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        s = SessionLocal()
        pagos = s.query(Payment).filter(Payment.sales_document_id == qid).count()
        s.close()
        final = leer_stock()
        if pagos != 1 or final != Decimal("4"):
            anomalias["cotizacion"] += 1
            print(f"  [cotizacion {ronda}] respuestas={_codigos(rs)} pagos registrados={pagos} "
                  f"(debia ser 1), existencia final={final} (debia quedar en 4)")

    # ── 5 y 6. Devolucion: doble aprobacion, y cancelar mientras se aprueba ─
    def venta_con_devolucion_pendiente(piezas=1):
        """Vende `piezas` y deja PENDING la devolucion de UNA."""
        fijar_stock(Decimal("5"))
        r = vender(0, piezas=piezas)
        assert _ok(r), r.text
        sale_id = r.json()["sale_id"]
        r = clientes_http[0].post("/api/returns/", headers=cabeceras[0], json={
            "sale_id": sale_id, "reason": "prueba de concurrencia",
            "total_refunded": "100.00", "refund_method": "CASH",
            "items": [{"variant_id": variante_id, "quantity": "1",
                       "refund_amount": "100.00", "is_inventory_reentry": True}]})
        assert _ok(r), r.text
        return sale_id, r.json()["id"]

    def reingresos(sale_id) -> int:
        """Movimientos de entrada al inventario que dejo esta venta al deshacerse."""
        s = SessionLocal()
        n = s.query(InventoryMovement).filter(
            InventoryMovement.variant_id == variante_id,
            InventoryMovement.movement_type == MovementType.SALE_RETURN,
            InventoryMovement.created_at >= marca_tiempo[0],
        ).count()
        s.close()
        return n

    marca_tiempo = [None]
    for ronda in range(args.rondas):
        # Devolucion PARCIAL (1 de 2): en una total, la segunda aprobacion ya
        # la frenaba el guard de "excede el restante de la venta".
        sale_id, ret_id = venta_con_devolucion_pendiente(piezas=2)
        s = SessionLocal(); marca_tiempo[0] = s.execute(text("SELECT now()")).scalar(); s.close()
        url = f"/api/returns/{ret_id}/approve"
        rs = _dos_a_la_vez([
            lambda: clientes_http[0].post(url, headers=cabeceras[0]),
            lambda: clientes_http[1].post(url, headers=cabeceras[1]),
        ])
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        final, entradas = leer_stock(), reingresos(sale_id)
        if final != Decimal("4") or entradas != 1:
            anomalias["devolucion"] += 1
            print(f"  [devolucion {ronda}] respuestas={_codigos(rs)} existencia final={final} "
                  f"(debia quedar en 4), reingresos al inventario={entradas} (debia ser 1)")

    for ronda in range(args.rondas):
        sale_id, ret_id = venta_con_devolucion_pendiente()
        s = SessionLocal(); marca_tiempo[0] = s.execute(text("SELECT now()")).scalar(); s.close()
        rs = _dos_a_la_vez([
            lambda: clientes_http[0].post(f"/api/returns/{ret_id}/approve", headers=cabeceras[0]),
            lambda: clientes_http[1].delete(f"/api/sales/{sale_id}", headers=cabeceras[1]),
        ])
        errores_500 += sum(1 for c in _codigos(rs) if c in ("EXC", 500))
        # En serie solo hay dos desenlaces: se aprueba y luego se cancela, o
        # se cancela y entonces la aprobacion se RECHAZA (venta cancelada). Lo
        # que no puede pasar es que la aprobacion entre sobre una venta que ya
        # estaba cancelada: se ve en que el reingreso de la cancelacion quedo
        # asentado antes que el de la devolucion y aun asi las dos dijeron OK.
        s = SessionLocal()
        movs = s.query(InventoryMovement.reference).filter(
            InventoryMovement.variant_id == variante_id,
            InventoryMovement.movement_type == MovementType.SALE_RETURN,
            InventoryMovement.created_at >= marca_tiempo[0],
        ).order_by(InventoryMovement.id).all()
        s.close()
        refs = [(m[0] or "") for m in movs]
        cancelo_primero = bool(refs) and refs[0].startswith("Cancelación")
        if _ok(rs[0]) and _ok(rs[1]) and cancelo_primero:
            anomalias["cancelar_vs_aprobar"] += 1
            print(f"  [cancelar_vs_aprobar {ronda}] respuestas={_codigos(rs)} "
                  f"la devolucion se aprobo sobre una venta ya cancelada; "
                  f"existencia final={leer_stock()}")

    s = SessionLocal()
    total_ventas = s.query(SalesDocument).filter(SalesDocument.organization_id == org_id).count()
    s.close()

    print(f"\nRondas por escenario: {args.rondas} · documentos creados: {total_ventas}")
    print(f"  sobreventa de la ultima pieza : {anomalias['venta']} de {args.rondas}")
    print(f"  doble reposicion al cancelar  : {anomalias['cancelacion']} de {args.rondas}")
    print(f"  doble cobro del mismo ticket  : {anomalias['abono']} de {args.rondas}")
    print(f"  doble conversion de cotizacion: {anomalias['cotizacion']} de {args.rondas}")
    print(f"  doble aprobacion de devolucion: {anomalias['devolucion']} de {args.rondas}")
    print(f"  cancelar vs. aprobar devolucion: {anomalias['cancelar_vs_aprobar']} de {args.rondas}")
    print(f"  respuestas 500 / excepciones  : {errores_500}")
    hubo = any(anomalias.values()) or errores_500
    print("RESULTADO:", "ANOMALIAS DE CONCURRENCIA" if hubo else "OK, sin anomalias")
    return 1 if hubo else 0


if __name__ == "__main__":
    raise SystemExit(main())
