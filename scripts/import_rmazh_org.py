"""Muda una organizacion completa de rmazh (Data X POS) a Atlas ONE, con historial.

Lee la salida de `scripts/export_rmazh_org.py` y crea la organizacion en Atlas
ONE con sus sucursales, usuarios (con su contrasena y PIN de siempre), catalogo,
existencias, cortes de caja con su bitacora, ventas con partidas y pagos,
devoluciones y movimientos de inventario. Todo en UNA transaccion: si algo no
cuadra al final, se deshace entero.

Los esquemas de rmazh y Atlas ONE son casi iguales, pero los ids enteros
(`branches`, `users`, `cash_sessions`, `inventory_movements`…) son secuencias
compartidas por todas las organizaciones de cada base: los de rmazh chocan con
los de otros clientes de Atlas ONE. Por eso esas filas reciben id nuevo y cada
referencia a ellas se traduce. Los ids de texto (UUID: productos, variantes,
ventas, partidas, pagos) se conservan.

Reglas:
  - Solo se copian las columnas que existen en Atlas ONE; las que solo tiene
    rmazh se listan como AVISO (`reprint_count`, `price_tier_name`…). Las que
    solo tiene Atlas ONE toman su valor por omision.
  - `payments.cash_session_id` (no existe en rmazh) se llena con la caja de su
    venta: el corte de Atlas ONE agrupa por esa columna.
  - Los folios se conservan por sucursal; el siguiente lo da `get_next_folio`
    (maximo + 1), sin tocar `branches.folio_inicial`.
  - Los modulos NO se copian: los pone el preset del giro (`--giro`).
  - El autor de un producto o de una entrada de la bitacora de caja que apunte
    fuera de la org (el superadmin de rmazh) se anula (AVISO).
    Cualquier otra referencia sin traduccion es BLOQUEO.
  - Toda columna `*_id` que el importador no sepa traducir es BLOQUEO: copiar un
    entero ajeno en silencio ligaria la fila a otro cliente.

Bloqueos (ninguno se puede forzar, salvo la caja abierta en un ensayo):
  - una caja OPEN en la exportacion. Con `--permitir-cajas-abiertas` llega abierta
    y la cajera la corta en Atlas ONE; con `--ejecutar` fuera de una base *ensayo*
    exige `--rmazh-apagado` (los usuarios ya no venden en rmazh y se exporto despues);
  - una organizacion con el mismo nombre en Atlas ONE;
  - un `username` que ya existe, o un usuario con rol de plataforma;
  - un UUID que ya existe en Atlas ONE;
  - un valor de enum que Atlas ONE no conoce;
  - una tabla con filas que Atlas ONE no tiene.

Verificacion antes de confirmar: conteo por tabla, suma de ventas, pagos,
efectivo por corte, existencias y movimientos, y folio maximo por sucursal.

`--sucursales 12,13` muda solo esas sucursales de rmazh (catalogo completo; los
usuarios de las otras llegan inactivos y sin sucursal).

Uso (dentro del contenedor de Atlas ONE):
    python scripts/import_rmazh_org.py org5.txt --nombre "Novedades America" \
        --plan PRO --giro ATLAS_POS                 # ensayo: escribe y deshace
    python scripts/import_rmazh_org.py org5.txt --nombre "Novedades America" \
        --plan PRO --giro ATLAS_POS --ejecutar      # confirma
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import enum
import gzip
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, Table, text
from sqlalchemy.sql import sqltypes

# Orden de insercion: cada tabla despues de las que referencia.
ORDEN = [
    "organization",
    "branches",
    "users",
    "user_organizations",
    "employees",
    "customers",
    "departments",
    "brands",
    "products",
    "product_variants",
    "packaging_units",
    "product_prices",
    "product_branch_status",
    "stock_on_hand",
    "cash_sessions",
    "cash_movements",
    "cash_audit_log",
    "sales_documents",
    "sales_lines",
    "payments",
    "sale_returns",
    "sale_return_items",
    "inventory_movements",
]

# Tablas con PK entera: reciben id nuevo.
PK_ENTERA = {
    "organization", "branches", "users", "employees", "customers",
    "stock_on_hand", "cash_sessions", "cash_movements", "cash_audit_log",
    "inventory_movements",
}

# Columna -> tabla cuyo mapa de ids la traduce.
REFERENCIAS = {
    "organization_id": "organization",
    "branch_id": "branches",
    "base_branch_id": "branches",
    "from_branch_id": "branches",
    "to_branch_id": "branches",
    "hq_branch_id": "branches",
    "user_id": "users",
    "seller_id": "users",
    "created_by_id": "users",
    "created_by_user_id": "users",
    "server_user_id": "users",
    "session_id": "cash_sessions",
    "cash_session_id": "cash_sessions",
    "customer_id": "customers",
}

# Autores que, si apuntan fuera de la org (p. ej. el superadmin de rmazh que cerro
# un corte), se anulan en vez de bloquear: no ligan la fila a otro cliente.
ANULABLES = {("products", "created_by_user_id"), ("cash_audit_log", "user_id")}

# Columnas `*_id` que apuntan a UUID conservados (o no son llaves): se copian tal cual.
CONSERVADAS = {
    "product_id", "variant_id", "document_id", "sales_document_id", "brand_id",
    "department_id", "linked_package_id", "return_id", "sale_id", "client_uuid",
    "place_id", "related_id", "parent_id", "tax_id",
}

# Rol de rmazh -> org_role de Atlas ONE (igual que import_rmazh_users.py).
ORG_ROLE = {"ADMINISTRADOR": "ADMIN", "DUEÑO": "OWNER"}


class Bloqueo(Exception):
    """La importacion no puede seguir; el mensaje lista los motivos."""


# ── Lectura de la exportacion ────────────────────────────────────────────────
def leer_exportacion(ruta: str) -> Dict[str, Any]:
    """Acepta el archivo completo de `railway ssh` (con ruido alrededor)."""
    contenido = Path(ruta).read_text(encoding="utf-8", errors="replace")
    inicio = contenido.index("###RMAZH_ORG_B64###") + len("###RMAZH_ORG_B64###")
    fin = contenido.index("###FIN###", inicio)
    crudo = base64.b64decode("".join(contenido[inicio:fin].split()))
    return json.loads(gzip.decompress(crudo).decode("utf-8"))


# ── Utilidades de base ───────────────────────────────────────────────────────
def _es_pg(db) -> bool:
    return db.bind.dialect.name == "postgresql"


def _reflejar(db, nombre: str) -> Optional[Table]:
    try:
        return Table(nombre, MetaData(), autoload_with=db.connection())
    except Exception:
        return None


def _reservar_ids(db, tabla: str, n: int) -> List[int]:
    """n ids nuevos para `tabla`, sin chocar con nadie."""
    if n == 0:
        return []
    if _es_pg(db):
        seq = db.execute(text("select pg_get_serial_sequence(:t, 'id')"), {"t": tabla}).scalar()
        if not seq:
            raise Bloqueo(f"{tabla}.id no tiene secuencia en Postgres")
        filas = db.execute(
            text("select nextval(cast(:s as regclass)) from generate_series(1, :n)"),
            {"s": seq, "n": n},
        )
        return [r[0] for r in filas]
    base = db.execute(text(f"select coalesce(max(id), 0) from {tabla}")).scalar()
    return list(range(base + 1, base + n + 1))


def _defaults_del_modelo(nombre: str) -> Dict[str, Any]:
    """Valores por omision que solo viven en el modelo de Python (no en la base).

    Una insercion con la tabla reflejada no los aplica, y varias columnas NOT
    NULL dependen de ellos (`branches.open_drawer_on_print`…).
    """
    from app.core.database import Base

    modelo = Base.metadata.tables.get(nombre)
    if modelo is None:
        return {}
    salida: Dict[str, Any] = {}
    for c in modelo.columns:
        d = c.default
        if d is None or c.primary_key:
            continue
        if d.is_scalar:
            salida[c.name] = d.arg
        elif d.is_callable:
            salida[c.name] = d.arg(None)
    return salida


def _convertir(valor: Any, columna) -> Any:
    """Del JSON de la exportacion al tipo de la columna destino."""
    if valor is None:
        return None
    tipo = columna.type
    if isinstance(valor, enum.Enum):
        etiquetas = getattr(tipo, "enums", None) or []
        valor = valor.name if valor.name in etiquetas or not etiquetas else valor.value
    if isinstance(tipo, sqltypes.DateTime):
        return _dt.datetime.fromisoformat(valor) if isinstance(valor, str) else valor
    if isinstance(tipo, sqltypes.Date):
        return _dt.date.fromisoformat(valor[:10]) if isinstance(valor, str) else valor
    if isinstance(tipo, sqltypes.Boolean):
        return bool(valor)
    if isinstance(tipo, sqltypes.Integer):
        return int(valor)
    if isinstance(tipo, (sqltypes.Numeric, sqltypes.Float)):
        return Decimal(str(valor))
    if isinstance(tipo, sqltypes.JSON):
        return valor
    if isinstance(tipo, sqltypes.String) and isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(tipo, sqltypes.String) and not isinstance(valor, str):
        return str(valor)
    return valor


def _modulos_del_preset(db, giro: str) -> List[str]:
    """Lo mismo que apply_industry_preset, sin su commit."""
    from app.models.modules import IndustryPreset, Module
    from app.modules.tenants.models import IndustryType
    from app.services.capabilities_service import INDUSTRY_PRESETS, MOD_CORE

    tipo = IndustryType[giro]
    preset = db.query(IndustryPreset).filter(IndustryPreset.industry_type == tipo.value).first()
    modulos = preset.modules if preset else INDUSTRY_PRESETS.get(tipo, [MOD_CORE])
    validos = {k for (k,) in db.query(Module.key).all()}
    return [k for k in modulos if k in validos]


# ── Solo algunas sucursales ─────────────────────────────────────────────────
def filtrar_sucursales(datos: Dict[str, Any], sucursales: set) -> Dict[str, Any]:
    """Deja solo lo de `sucursales` (ids de rmazh); el resto se queda en rmazh.

    El catalogo es de toda la org y viaja completo. Los usuarios tambien (las
    ventas viejas los referencian), pero los que trabajan en una sucursal que
    no viaja llegan INACTIVOS y sin sucursal: siguen vendiendo en rmazh.
    """
    t = {k: list(v) for k, v in datos["tablas"].items()}
    t["branches"] = [b for b in t.get("branches", []) if b["id"] in sucursales]

    def de_aqui(f):
        return f.get("branch_id") in sucursales

    for tabla in ("product_branch_status", "stock_on_hand", "cash_sessions",
                  "inventory_movements", "sales_documents"):
        t[tabla] = [f for f in t.get(tabla, []) if de_aqui(f)]
    cajas = {c["id"] for c in t["cash_sessions"]}
    docs = {d["id"] for d in t["sales_documents"]}
    t["cash_movements"] = [m for m in t.get("cash_movements", []) if m.get("session_id") in cajas]
    t["cash_audit_log"] = [a for a in t.get("cash_audit_log", [])
                           if (a.get("session_id") in cajas if a.get("session_id") is not None
                               else de_aqui(a))]
    t["sales_lines"] = [x for x in t.get("sales_lines", []) if x.get("document_id") in docs]
    t["payments"] = [x for x in t.get("payments", []) if x.get("sales_document_id") in docs]
    t["sale_returns"] = [x for x in t.get("sale_returns", []) if x.get("sale_id") in docs]
    devs = {x["id"] for x in t["sale_returns"]}
    t["sale_return_items"] = [x for x in t.get("sale_return_items", []) if x.get("return_id") in devs]
    t["employees"] = [e for e in t.get("employees", [])
                      if e.get("base_branch_id") is None or e.get("base_branch_id") in sucursales]
    usuarios = []
    for u in t.get("users", []):
        if u.get("branch_id") is not None and u["branch_id"] not in sucursales:
            u = dict(u, branch_id=None, is_active=False)
        usuarios.append(u)
    t["users"] = usuarios
    return dict(datos, tablas=t)


# ── Importacion ──────────────────────────────────────────────────────────────
def importar(
    db,
    datos: Dict[str, Any],
    *,
    nombre: str,
    plan: str,
    giro: str,
    permitir_cajas_abiertas: bool = False,
) -> Dict[str, Any]:
    """Inserta la org en la sesion SIN confirmar. Lanza Bloqueo si no se puede.

    Devuelve el resumen; quien llama decide commit (--ejecutar) o rollback.
    """
    from app.modules.tenants.models import IndustryType
    from app.services.plans import es_plan_valido

    if not es_plan_valido(plan):
        raise Bloqueo(f"plan desconocido {plan!r}")
    if giro not in IndustryType.__members__:
        raise Bloqueo(f"giro desconocido {giro!r}")

    tablas: Dict[str, List[dict]] = datos["tablas"]
    org_origen = datos["org_id"]
    bloqueos: List[str] = []
    avisos: List[str] = []

    destino: Dict[str, Table] = {}
    for t in ORDEN:
        filas = tablas.get(t, [])
        tabla = _reflejar(db, t)
        if tabla is None:
            (bloqueos if filas else avisos).append(f"Atlas ONE no tiene la tabla {t} ({len(filas)} filas)")
            continue
        destino[t] = tabla
        if filas:
            sobran = sorted(set(filas[0]) - set(tabla.c.keys()))
            if sobran:
                avisos.append(f"{t}: columnas que solo tiene rmazh, no viajan: {', '.join(sobran)}")

    # Caja abierta
    abiertas = [c["id"] for c in tablas.get("cash_sessions", []) if c.get("status") == "OPEN"]
    if abiertas:
        msg = f"cajas abiertas en rmazh: {abiertas} (cortarlas antes de mudar)"
        (avisos if permitir_cajas_abiertas else bloqueos).append(msg)

    # Nombre de la org y usernames
    if db.execute(text("select count(*) from organization where name = :n"), {"n": nombre}).scalar():
        bloqueos.append(f"ya existe una organizacion llamada {nombre!r}")
    for u in tablas.get("users", []):
        if db.execute(text("select count(*) from users where username = :u"), {"u": u["username"]}).scalar():
            bloqueos.append(f"el usuario {u['username']!r} ya existe en Atlas ONE")
        if (u.get("platform_role") or "NONE") != "NONE":
            bloqueos.append(f"el usuario {u['username']!r} tiene rol de plataforma {u['platform_role']}")

    # UUIDs que ya existen
    for t in ORDEN:
        if t in PK_ENTERA or t not in destino or "id" not in destino[t].c:
            continue
        ids = [f["id"] for f in tablas.get(t, []) if f.get("id") is not None]
        for i in range(0, len(ids), 500):
            lote = ids[i:i + 500]
            n = db.execute(destino[t].select().with_only_columns(destino[t].c.id)
                           .where(destino[t].c.id.in_(lote))).fetchall()
            if n:
                bloqueos.append(f"{t}: {len(n)} ids ya existen en Atlas ONE (p. ej. {n[0][0]})")
                break

    # Enums y columnas *_id desconocidas
    for t, tabla in destino.items():
        filas = tablas.get(t, [])
        if not filas:
            continue
        for col in tabla.c:
            if col.name not in filas[0]:
                continue
            valores_enum = getattr(col.type, "enums", None)
            if valores_enum:
                raros = {f[col.name] for f in filas if f.get(col.name) is not None} - set(valores_enum)
                if raros:
                    bloqueos.append(f"{t}.{col.name}: valores que Atlas ONE no conoce: {sorted(raros)}")
            if (col.name.endswith("_id") and col.name not in REFERENCIAS
                    and col.name not in CONSERVADAS and col.name != "id"
                    and any(f.get(col.name) is not None for f in filas)):
                bloqueos.append(f"{t}.{col.name}: columna de referencia sin traduccion")

    if bloqueos:
        raise Bloqueo("\n".join(bloqueos))

    # ── Mapas de ids enteros ─────────────────────────────────────────────────
    mapas: Dict[str, Dict[Any, int]] = {}
    for t in ORDEN:
        if t in PK_ENTERA and t in destino:
            origen = [f["id"] for f in tablas.get(t, [])]
            mapas[t] = dict(zip(origen, _reservar_ids(db, t, len(origen))))
    org_nueva = mapas["organization"][org_origen]

    huerfanas: Dict[str, int] = defaultdict(int)

    def traducir(t: str, fila: dict) -> dict:
        nueva = dict(fila)
        if t in PK_ENTERA:
            nueva["id"] = mapas[t][fila["id"]]
        for col, ref in REFERENCIAS.items():
            if t == "organization" and col == "organization_id":
                continue
            if col not in nueva or nueva[col] is None:
                continue
            if ref == "organization" and t != "organization":
                nueva[col] = org_nueva
                continue
            valor = mapas.get(ref, {}).get(nueva[col])
            if valor is None:
                if (t, col) in ANULABLES:
                    huerfanas[f"{t}.{col}"] += 1
                    nueva[col] = None
                    continue
                raise Bloqueo(f"{t}.{col}={fila[col]} apunta fuera de la organizacion (fila {fila.get('id')})")
            nueva[col] = valor
        return nueva

    # Caja de cada venta, para los pagos.
    caja_de_venta = {d["id"]: d.get("cash_session_id") for d in tablas.get("sales_documents", [])}
    rol_de_usuario = {u["id"]: u.get("role") for u in tablas.get("users", [])}

    insertadas: Dict[str, int] = {}
    for t in ORDEN:
        if t not in destino:
            continue
        tabla = destino[t]
        columnas = set(tabla.c.keys())
        por_omision = {k: v for k, v in _defaults_del_modelo(t).items() if k in columnas}
        filas = []
        for fila in tablas.get(t, []):
            if t == "organization":
                fila = {k: v for k, v in fila.items() if k not in ("hq_branch_id", "branding_config", "created_at", "updated_at")}
                fila.update(name=nombre, plan=plan, industry_type=giro, status="ACTIVE", is_active=True)
            if t == "payments" and fila.get("cash_session_id") is None:
                fila = dict(fila, cash_session_id=caja_de_venta.get(fila.get("sales_document_id")))
            if t == "user_organizations":
                fila = dict(fila, org_role=ORG_ROLE.get(rol_de_usuario.get(fila["user_id"]), fila.get("org_role") or "MEMBER"))
            if t == "cash_audit_log" and fila.get("related_table") in mapas and fila.get("related_id") is not None:
                nuevo = mapas[fila["related_table"]].get(int(fila["related_id"]))
                fila = dict(fila, related_id=str(nuevo) if nuevo is not None else fila["related_id"])
            nueva = traducir(t, fila)
            if t != "organization" and "organization_id" in columnas:
                # Hijas con organization_id NULL en rmazh (TenantMixin es nullable).
                nueva["organization_id"] = org_nueva
            for k, v in por_omision.items():
                nueva.setdefault(k, v)
            filas.append({k: _convertir(v, tabla.c[k]) for k, v in nueva.items() if k in columnas})
        # Un executemany exige las mismas llaves en cada fila del lote.
        llaves = set().union(*filas) if filas else set()
        filas = [{k: f.get(k) for k in llaves} for f in filas]
        for i in range(0, len(filas), 1000):
            db.execute(tabla.insert(), filas[i:i + 1000])
        insertadas[t] = len(filas)

    # Matriz de la org
    matriz = next((b for b in tablas.get("branches", []) if b.get("is_headquarters")), None)
    if matriz is not None:
        db.execute(text("update organization set hq_branch_id = :b where id = :o"),
                   {"b": mapas["branches"][matriz["id"]], "o": org_nueva})

    # Modulos del preset
    modulos = _modulos_del_preset(db, giro)
    for clave in modulos:
        db.execute(text(
            "insert into organization_modules (organization_id, module_key, is_enabled) "
            "values (:o, :k, :e)"), {"o": org_nueva, "k": clave, "e": True})

    for nombre_col, n in huerfanas.items():
        avisos.append(f"{nombre_col}: {n} filas apuntaban fuera de la org y quedaron en NULL")

    verificar(db, datos, org_nueva, mapas, destino)
    return {
        "organization_id": org_nueva,
        "insertadas": insertadas,
        "modulos": modulos,
        "sucursales": {o: n for o, n in mapas.get("branches", {}).items()},
        "usuarios": {u["username"]: mapas["users"][u["id"]] for u in tablas.get("users", [])},
        "avisos": avisos,
    }


# ── Verificacion ─────────────────────────────────────────────────────────────
def _sumar(filas, campo) -> Decimal:
    return sum((Decimal(str(f[campo])) for f in filas if f.get(campo) is not None), Decimal("0"))


def verificar(db, datos: Dict[str, Any], org: int, mapas: Dict[str, Dict[Any, int]],
              destino: Dict[str, Table]) -> None:
    """Compara Atlas ONE contra la exportacion; lanza Bloqueo si algo no cuadra."""
    t = datos["tablas"]
    fallas: List[str] = []

    def uno(sql: str, **kw):
        return db.execute(text(sql), dict(kw, o=org)).scalar()

    def igual(etiqueta, esperado, real):
        a = round(Decimal(str(esperado or 0)), 2)
        b = round(Decimal(str(real or 0)), 2)
        if a != b:
            fallas.append(f"{etiqueta}: rmazh {a} / Atlas ONE {b}")

    for tabla in ORDEN:
        if tabla == "organization" or tabla not in destino:
            continue
        if "organization_id" not in destino[tabla].c:
            continue
        igual(f"filas de {tabla}", len(t.get(tabla, [])),
              uno(f"select count(*) from {tabla} where organization_id = :o"))
    igual("usuarios", len(t.get("users", [])),
          uno("select count(*) from user_organizations where organization_id = :o"))

    igual("suma de ventas", _sumar(t.get("sales_documents", []), "total_amount"),
          uno("select coalesce(sum(total_amount), 0) from sales_documents where organization_id = :o"))
    igual("suma de partidas", _sumar(t.get("sales_lines", []), "total_line"),
          uno("select coalesce(sum(total_line), 0) from sales_lines where organization_id = :o"))
    igual("suma de pagos", _sumar(t.get("payments", []), "amount"),
          uno("select coalesce(sum(amount), 0) from payments where organization_id = :o"))
    igual("existencias", _sumar(t.get("stock_on_hand", []), "qty_on_hand"),
          uno("select coalesce(sum(qty_on_hand), 0) from stock_on_hand where organization_id = :o"))
    igual("movimientos de inventario", _sumar(t.get("inventory_movements", []), "qty_change"),
          uno("select coalesce(sum(qty_change), 0) from inventory_movements where organization_id = :o"))
    igual("pagos sin caja", 0, uno(
        "select count(*) from payments p join sales_documents s on s.id = p.sales_document_id "
        "where p.organization_id = :o and p.cash_session_id is null and s.cash_session_id is not null"))

    # Folio maximo por sucursal y serie
    maximos: Dict[tuple, int] = {}
    for d in t.get("sales_documents", []):
        if d.get("folio") is None:
            continue
        clave = (mapas["branches"][d["branch_id"]], d.get("series"))
        maximos[clave] = max(maximos.get(clave, 0), int(d["folio"]))
    for (sucursal, serie), folio in maximos.items():
        igual(f"folio maximo sucursal {sucursal} serie {serie}", folio, uno(
            "select max(folio) from sales_documents where organization_id = :o "
            "and branch_id = :b and series = :s", b=sucursal, s=serie))

    # Efectivo por corte
    venta_caja = {d["id"]: d.get("cash_session_id") for d in t.get("sales_documents", [])}
    efectivo: Dict[int, Decimal] = defaultdict(Decimal)
    for p in t.get("payments", []):
        caja = p.get("cash_session_id") or venta_caja.get(p.get("sales_document_id"))
        if caja is not None and p.get("method") == "CASH":
            efectivo[mapas["cash_sessions"][caja]] += Decimal(str(p["amount"]))
    reales = dict(db.execute(text(
        "select cash_session_id, sum(amount) from payments where organization_id = :o "
        "and method = 'CASH' and cash_session_id is not null group by 1"), {"o": org}).fetchall())
    distintas = [c for c in set(efectivo) | set(reales)
                 if Decimal(str(efectivo.get(c, 0))) != Decimal(str(reales.get(c) or 0))]
    distintas = [c for c in distintas
                 if round(Decimal(str(efectivo.get(c, 0))), 2) != round(Decimal(str(reales.get(c) or 0)), 2)]
    if distintas:
        fallas.append(f"efectivo distinto en {len(distintas)} cortes (p. ej. caja {distintas[0]})")

    if fallas:
        raise Bloqueo("la verificacion no cuadra:\n" + "\n".join(fallas))


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Muda una organizacion de rmazh a Atlas ONE")
    p.add_argument("exportacion")
    p.add_argument("--nombre", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--giro", required=True)
    p.add_argument("--ejecutar", action="store_true", help="confirma; sin esto escribe y deshace")
    p.add_argument("--permitir-cajas-abiertas", action="store_true",
                   help="las cajas abiertas llegan abiertas y la cajera corta en Atlas ONE; "
                        "con --ejecutar exige --rmazh-apagado")
    p.add_argument("--rmazh-apagado", action="store_true",
                   help="confirmo que los usuarios de estas sucursales ya no pueden vender en rmazh")
    p.add_argument("--sucursales", default=None,
                   help="ids de rmazh separados por coma; solo esas viajan (el resto se queda en rmazh)")
    args = p.parse_args()
    import app.models  # noqa: F401
    from app.core.database import SessionLocal, engine

    base = engine.url.database or ""
    if args.ejecutar and args.permitir_cajas_abiertas and "ensayo" not in base and not args.rmazh_apagado:
        # Una caja abierta que se muda solo es segura si en rmazh ya nadie puede
        # vender: una venta posterior a la exportacion se perderia.
        print(f"BLOQUEO: cajas abiertas con --ejecutar en {base!r} exige --rmazh-apagado "
              "(apaga primero a los usuarios en rmazh y exporta DESPUES)")
        return 1
    print(f"Base destino: {base}")

    datos = leer_exportacion(args.exportacion)
    print(f"Exportacion de rmazh org {datos['org_id']} tomada {datos['exportado']}")
    if args.sucursales:
        elegidas = {int(x) for x in args.sucursales.split(",") if x.strip()}
        conocidas = {b["id"] for b in datos["tablas"].get("branches", [])}
        if not elegidas <= conocidas:
            print(f"BLOQUEO: sucursales {sorted(elegidas - conocidas)} no son de la org")
            return 1
        datos = filtrar_sucursales(datos, elegidas)
        print(f"Solo sucursales {sorted(elegidas)}; se quedan en rmazh {sorted(conocidas - elegidas)}")
    db = SessionLocal()
    try:
        r = importar(db, datos, nombre=args.nombre, plan=args.plan, giro=args.giro,
                     permitir_cajas_abiertas=args.permitir_cajas_abiertas)
    except Bloqueo as e:
        db.rollback()
        print("BLOQUEO:\n" + str(e))
        return 1
    except Exception:
        db.rollback()
        raise
    for t, n in r["insertadas"].items():
        print(f"  {t:<24}{n:>8,}")
    print("Organizacion nueva:", r["organization_id"], "· sucursales", r["sucursales"])
    print("Usuarios:", r["usuarios"])
    print("Modulos:", ", ".join(r["modulos"]))
    for a in r["avisos"]:
        print("AVISO:", a)
    if args.ejecutar:
        db.commit()
        print("CONFIRMADO: la verificacion cuadro y la org quedo escrita.")
    else:
        db.rollback()
        print("ENSAYO: la verificacion cuadro; no se escribio nada (usa --ejecutar).")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
