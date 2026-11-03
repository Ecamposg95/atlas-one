"""Trae a Atlas ONE lo que una tienda ya mudada siguio vendiendo en rmazh.

Despues de `import_rmazh_org.py`, si alguien vuelve a vender en rmazh (una
cajera reactivada unos minutos), esas ventas faltan en Atlas ONE. Esta
herramienta toma una exportacion NUEVA de `export_rmazh_org.py` y AGREGA lo que
falta; nunca borra ni modifica ventas que Atlas ONE ya tiene. Es idempotente:
repetirla con la misma exportacion no duplica nada.

Como se reconoce lo ya mudado (el importador no guarda un mapa de ids):
  - sucursal: mismo nombre dentro de la org destino (las que no existen, p. ej.
    una sucursal que sigue en rmazh, se ignoran);
  - usuario: mismo `username`;
  - caja: mismo usuario, sucursal y `opened_at`;
  - ventas, partidas, pagos y catalogo: mismo UUID.
Los movimientos de inventario, la bitacora y los movimientos de caja (ids
enteros) se traen solo si son posteriores a `--desde` (la hora de la
exportacion del corte). Para que repetir sea inocuo, cada movimiento de
inventario traido guarda "[rmazh#<id>]" en `notes`, y la bitacora y los
movimientos de caja se saltan si ya hay uno con la misma caja y hora.

Existencias: Atlas ONE + suma de `qty_change` de los movimientos traidos (Atlas
pudo vender entretanto; no se pisa su existencia con la de rmazh).

Folio repetido: si Atlas ONE ya uso el folio de una venta de rmazh en esa
sucursal, la venta recibe el siguiente folio libre y su nota guarda el original
("[rmazh A-14495]") — AVISO.

Uso (dentro del contenedor de Atlas ONE):
    python scripts/fusionar_rmazh_ventas.py nueva.txt --org 21 \
        --desde 2026-11-03T18:25:50+00:00            # ensayo
    ... --ejecutar                                    # confirma
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from scripts.import_rmazh_org import (
    ANULABLES,
    REFERENCIAS,
    Bloqueo,
    _convertir,
    _defaults_del_modelo,
    _reflejar,
    _reservar_ids,
    leer_exportacion,
)


def _fecha(v) -> _dt.datetime | None:
    if v is None:
        return None
    d = _dt.datetime.fromisoformat(v) if isinstance(v, str) else v
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


def fusionar(db, datos: Dict[str, Any], *, org: int, desde: _dt.datetime) -> Dict[str, Any]:
    """Agrega en la sesion SIN confirmar. Lanza Bloqueo si algo no cuadra."""
    t = datos["tablas"]
    avisos: List[str] = []
    traidas: Dict[str, int] = defaultdict(int)

    # ── Mapas desde lo que ya existe ─────────────────────────────────────────
    suc_atlas = {n: i for i, n in db.execute(
        text("select id, name from branches where organization_id = :o"), {"o": org})}
    m_suc = {b["id"]: suc_atlas[b["name"]] for b in t.get("branches", []) if b["name"] in suc_atlas}
    if not m_suc:
        raise Bloqueo(f"ninguna sucursal de la exportacion existe en la org {org}")
    ignoradas = [b["name"] for b in t.get("branches", []) if b["id"] not in m_suc]
    if ignoradas:
        avisos.append(f"sucursales que siguen en rmazh, se ignoran: {ignoradas}")

    usr_atlas = {}
    for u in t.get("users", []):
        fila = db.execute(text("select u.id from users u join user_organizations uo on uo.user_id = u.id "
                               "where u.username = :u and uo.organization_id = :o"),
                          {"u": u["username"], "o": org}).first()
        if fila:
            usr_atlas[u["id"]] = fila[0]
    m_cajas: Dict[int, int] = {}
    cajas_atlas = {}
    for cid, uid, bid, abierta, status in db.execute(text(
            "select id, user_id, branch_id, opened_at, status from cash_sessions where organization_id = :o"),
            {"o": org}):
        cajas_atlas[(uid, bid, _fecha(abierta))] = (cid, str(status).split(".")[-1])
    for c in t.get("cash_sessions", []):
        if c.get("branch_id") not in m_suc:
            continue
        clave = (usr_atlas.get(c["user_id"]), m_suc[c["branch_id"]], _fecha(c["opened_at"]))
        if clave in cajas_atlas:
            m_cajas[c["id"]] = cajas_atlas[clave][0]
            if cajas_atlas[clave][1] != c.get("status"):
                avisos.append(f"caja rmazh {c['id']} esta {c.get('status')} en rmazh y "
                              f"{cajas_atlas[clave][1]} en Atlas ONE (caja {cajas_atlas[clave][0]}): se deja como esta")

    mapas = {"organization": {datos["org_id"]: org}, "branches": m_suc, "users": usr_atlas,
             "cash_sessions": m_cajas}

    def traducir(tabla: str, fila: dict) -> dict:
        nueva = dict(fila)
        for col, ref in REFERENCIAS.items():
            if col not in nueva or nueva[col] is None:
                continue
            if ref == "organization":
                nueva[col] = org
                continue
            valor = mapas.get(ref, {}).get(nueva[col])
            if valor is None:
                if (tabla, col) in ANULABLES:
                    nueva[col] = None
                    continue
                raise Bloqueo(f"{tabla}.{col}={fila[col]} no tiene equivalente en Atlas ONE (fila {fila.get('id')})")
            nueva[col] = valor
        if "organization_id" in fila or tabla != "users":
            nueva["organization_id"] = org
        return nueva

    def insertar(tabla: str, filas: List[dict]) -> None:
        if not filas:
            return
        destino = _reflejar(db, tabla)
        cols = set(destino.c.keys())
        omision = {k: v for k, v in _defaults_del_modelo(tabla).items() if k in cols}
        limpias = []
        for f in filas:
            for k, v in omision.items():
                f.setdefault(k, v)
            limpias.append({k: _convertir(v, destino.c[k]) for k, v in f.items() if k in cols})
        llaves = set().union(*limpias)
        db.execute(destino.insert(), [{k: f.get(k) for k in llaves} for f in limpias])
        traidas[tabla] += len(limpias)

    def faltan(tabla: str, filas: List[dict]) -> List[dict]:
        ids = [f["id"] for f in filas]
        existen = set()
        for i in range(0, len(ids), 500):
            existen |= {r[0] for r in db.execute(text(f"select id from {tabla} where id in :ids")
                                                  .bindparams(_expanding("ids")), {"ids": ids[i:i + 500]})}
        return [f for f in filas if f["id"] not in existen]

    # ── Catalogo nuevo (por UUID) ────────────────────────────────────────────
    for tabla in ("departments", "brands", "products", "product_variants", "packaging_units", "product_prices"):
        insertar(tabla, [traducir(tabla, f) for f in faltan(tabla, t.get(tabla, []))])
    pbs = [f for f in t.get("product_branch_status", []) if f.get("branch_id") in m_suc]
    insertar("product_branch_status", [traducir("product_branch_status", f) for f in faltan("product_branch_status", pbs)])

    # ── Cajas nuevas ─────────────────────────────────────────────────────────
    nuevas = [c for c in t.get("cash_sessions", []) if c.get("branch_id") in m_suc and c["id"] not in m_cajas]
    for c, nid in zip(nuevas, _reservar_ids(db, "cash_sessions", len(nuevas))):
        m_cajas[c["id"]] = nid
    insertar("cash_sessions", [dict(traducir("cash_sessions", c), id=m_cajas[c["id"]]) for c in nuevas])

    # ── Ventas, partidas, pagos (por UUID) ───────────────────────────────────
    ventas = faltan("sales_documents", [d for d in t.get("sales_documents", []) if d.get("branch_id") in m_suc])
    # Solo ventas de sucursales mudadas: las de una sucursal que sigue en rmazh no viajan.
    ventas_atlas = {d["id"] for d in t.get("sales_documents", []) if d.get("branch_id") in m_suc}
    filas_ventas = []
    for d in sorted(ventas, key=lambda x: (x.get("folio") or 0)):
        nueva = traducir("sales_documents", d)
        if nueva.get("folio") is not None:
            usado = db.execute(text("select 1 from sales_documents where branch_id = :b and series = :s "
                                    "and folio = :f"), {"b": nueva["branch_id"], "s": nueva.get("series"),
                                                        "f": nueva["folio"]}).first()
            if usado:
                libre = (db.execute(text("select coalesce(max(folio), 0) from sales_documents where branch_id = :b "
                                         "and series = :s"), {"b": nueva["branch_id"], "s": nueva.get("series")}).scalar()) + 1
                avisos.append(f"folio {nueva.get('series')}-{nueva['folio']} ya usado en Atlas ONE: "
                              f"la venta de rmazh queda como {nueva.get('series')}-{libre}")
                nueva["notes"] = ((nueva.get("notes") or "") + f" [rmazh {nueva.get('series')}-{nueva['folio']}]").strip()
                nueva["folio"] = libre
        filas_ventas.append(nueva)
        insertar("sales_documents", [nueva])
    docs = {d["id"] for d in ventas} | ventas_atlas
    caja_de_venta = {d["id"]: m_cajas.get(d.get("cash_session_id")) for d in t.get("sales_documents", [])}
    lineas = faltan("sales_lines", [x for x in t.get("sales_lines", []) if x.get("document_id") in docs])
    insertar("sales_lines", [traducir("sales_lines", x) for x in lineas])
    pagos = faltan("payments", [p for p in t.get("payments", []) if p.get("sales_document_id") in docs])
    filas_pagos = []
    for p in pagos:
        nueva = traducir("payments", p)
        if nueva.get("cash_session_id") is None:
            nueva["cash_session_id"] = caja_de_venta.get(p.get("sales_document_id"))
        filas_pagos.append(nueva)
    insertar("payments", filas_pagos)

    # ── Lo de ids enteros: solo lo posterior al corte ────────────────────────
    def posteriores(filas, campo):
        return [f for f in filas if _fecha(f.get(campo)) and _fecha(f.get(campo)) > desde]

    ya_log = {(sid, _fecha(ts), str(ev)) for sid, ts, ev in db.execute(text(
        "select session_id, ts, event_type from cash_audit_log where organization_id = :o"), {"o": org})}
    log = [a for a in posteriores(t.get("cash_audit_log", []), "ts") if a.get("session_id") in m_cajas
           and (m_cajas[a["session_id"]], _fecha(a["ts"]), str(a.get("event_type"))) not in ya_log]
    for a, nid in zip(log, _reservar_ids(db, "cash_audit_log", len(log))):
        nueva = dict(traducir("cash_audit_log", a), id=nid)
        if a.get("related_table") == "cash_sessions" and a.get("related_id") is not None:
            nueva["related_id"] = str(m_cajas.get(int(a["related_id"]), a["related_id"]))
        insertar("cash_audit_log", [nueva])
    ya_caja = {(sid, _fecha(c)) for sid, c in db.execute(text(
        "select m.session_id, m.created_at from cash_movements m join cash_sessions s on s.id = m.session_id "
        "where s.organization_id = :o"), {"o": org})}
    mov_caja = [m for m in posteriores(t.get("cash_movements", []), "created_at") if m.get("session_id") in m_cajas
                and (m_cajas[m["session_id"]], _fecha(m["created_at"])) not in ya_caja]
    insertar("cash_movements", [dict(traducir("cash_movements", m), id=n)
                                for m, n in zip(mov_caja, _reservar_ids(db, "cash_movements", len(mov_caja)))])

    # Cada movimiento traido lleva "[rmazh#<id>]" en notes: asi una segunda corrida
    # no lo vuelve a aplicar (descontaria la existencia dos veces).
    ya_movs = set()
    for (nota,) in db.execute(text("select notes from inventory_movements where organization_id = :o "
                                   "and notes like '%[rmazh#%'"), {"o": org}):
        for trozo in nota.split("[rmazh#")[1:]:
            ya_movs.add(int(trozo.split("]")[0]))
    movs = [m for m in posteriores(t.get("inventory_movements", []), "created_at")
            if m.get("branch_id") in m_suc and m["id"] not in ya_movs]
    insertar("inventory_movements", [
        dict(traducir("inventory_movements", m), id=n,
             notes=((m.get("notes") or "") + f" [rmazh#{m['id']}]").strip())
        for m, n in zip(movs, _reservar_ids(db, "inventory_movements", len(movs)))])
    delta: Dict[tuple, Decimal] = defaultdict(Decimal)
    for m in movs:
        delta[(m_suc[m["branch_id"]], m["variant_id"])] += Decimal(str(m.get("qty_change") or 0))
    soh = _reflejar(db, "stock_on_hand")
    for (sucursal, variante), cambio in delta.items():
        n = db.execute(soh.update()
                       .where(soh.c.branch_id == sucursal, soh.c.variant_id == variante)
                       .values(qty_on_hand=soh.c.qty_on_hand + cambio)).rowcount
        if not n:
            insertar("stock_on_hand", [{"id": _reservar_ids(db, "stock_on_hand", 1)[0], "branch_id": sucursal,
                                        "variant_id": variante, "qty_on_hand": cambio, "is_active": True,
                                        "organization_id": org}])

    return {"traidas": dict(traidas), "avisos": avisos,
            "ventas": [(v.get("series"), v.get("folio"), str(v.get("total_amount"))) for v in filas_ventas],
            "existencias_ajustadas": len(delta)}


def _expanding(nombre):
    from sqlalchemy import bindparam
    return bindparam(nombre, expanding=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Agrega a Atlas ONE lo vendido despues en rmazh")
    p.add_argument("exportacion")
    p.add_argument("--org", type=int, required=True, help="organizacion destino en Atlas ONE")
    p.add_argument("--desde", required=True, help="hora de la exportacion del corte (ISO, con zona)")
    p.add_argument("--ejecutar", action="store_true")
    args = p.parse_args()

    import app.models  # noqa: F401
    from app.core.database import SessionLocal, engine

    desde = _fecha(args.desde)
    datos = leer_exportacion(args.exportacion)
    print(f"Base destino: {engine.url.database} · exportacion {datos['exportado']} · desde {desde.isoformat()}")
    db = SessionLocal()
    try:
        r = fusionar(db, datos, org=args.org, desde=desde)
    except Bloqueo as e:
        db.rollback()
        print("BLOQUEO:\n" + str(e))
        return 1
    except Exception:
        db.rollback()
        raise
    for tabla, n in r["traidas"].items():
        print(f"  {tabla:<24}{n:>6}")
    print("Ventas traidas:", r["ventas"] or "ninguna")
    print("Existencias ajustadas:", r["existencias_ajustadas"])
    for a in r["avisos"]:
        print("AVISO:", a)
    if args.ejecutar:
        db.commit()
        print("CONFIRMADO.")
    else:
        db.rollback()
        print("ENSAYO: no se escribio nada (usa --ejecutar).")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
