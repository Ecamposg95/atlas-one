"""Herramientas de solo lectura de la operación: ventas, conteos, faltantes y
valor de inventario. Ninguna escribe.

No definen reglas: consumen las que ya existen.

- Qué es una venta y el día de México: `app/services/metricas_ventas.py`.
- Lo que la cajera ve de sus ventas (hoy, su sucursal) y el conteo ciego:
  `app/services/ventas_cajero.py`.
- Valor de inventario: las consultas de `app/routers/reports_valuacion.py`.
- Avance de un conteo: `app/modules/conteos/services.py`.

La sucursal sale de `ambito_sucursal`: caja y gerencia, la suya; dirección, la
que nombre o toda la empresa.
"""
from __future__ import annotations

from datetime import date, timezone
from typing import Optional

from sqlalchemy import and_, desc, func

from app.models import Product, ProductVariant, StockOnHand
from app.models.organization import Branch
from app.models.sales import SalesDocument
from app.modules.conteos import services as conteos
from app.modules.conteos.models import ABIERTO, InventoryCount
from app.modules.products.models import ProductBranchStatus
from app.modules.products.services import sucursales_que_venden
from app.routers import reports_valuacion as valuacion
from app.services import metricas_ventas as mv
from app.services.ventas_cajero import MX_TZ, cajera_a_ciegas, venta_visible_para_cajero

from .contexto import Contexto, ErrorHerramienta, Herramienta, ambito_sucursal, sucursal_propia, tabla
from .datos import dato

TOPE_VENTAS = 40
TOPE_CONTEOS = 8
TOPE_FALTANTES = 30
TOPE_GRUPOS = 15
TOPE_DIAS = 366
SIN_PARAMETROS = {"type": "object", "properties": {}}

_PERIODO = {
    "periodo": {"type": "string", "enum": list(mv.PRESETS),
                "description": "hoy, ayer, 7d (últimos 7 días), 30d o mes (mes en curso). Por omisión: hoy."},
    "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (en vez de periodo)."},
    "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (en vez de periodo)."},
}


def _fecha(args: dict, clave: str) -> Optional[date]:
    crudo = args.get(clave)
    if crudo in (None, ""):
        return None
    try:
        return date.fromisoformat(str(crudo).strip())
    except ValueError:
        raise ErrorHerramienta(f"Fecha inválida en {clave}: usa AAAA-MM-DD.")


def _periodo(args: dict) -> mv.Periodo:
    desde, hasta = _fecha(args, "desde"), _fecha(args, "hasta")
    if desde or hasta:
        periodo = mv.periodo_de_query(desde, hasta)
    else:
        try:
            periodo = mv.periodo_preset(str(args.get("periodo") or "hoy").strip().lower())
        except ValueError as e:
            raise ErrorHerramienta(str(e))
    if periodo.dias > TOPE_DIAS:
        raise ErrorHerramienta("El periodo no puede pasar de un año.")
    return periodo


def _ambito(ctx: Contexto, args: dict) -> tuple[mv.Ambito, Optional[Branch]]:
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    if sucursal is None:
        return mv.Ambito(ctx.org_id, None, True), None
    rama = ctx.db.query(Branch).filter(Branch.id == sucursal, Branch.organization_id == ctx.org_id).first()
    return mv.Ambito(ctx.org_id, sucursal, False), rama


def _donde(rama: Optional[Branch]) -> str:
    return dato(rama.name) if rama is not None else "toda la empresa"


def _resumen(r: mv.Resumen) -> dict:
    return {
        "venta_neta": r.neta, "venta_bruta": r.bruta, "devuelto": r.devuelto,
        "tickets": r.tickets, "devoluciones": r.devoluciones, "ticket_promedio": r.ticket_promedio,
        "fiado": r.fiado, "cobranza": r.cobranza,
    }


# ── ventas ───────────────────────────────────────────────────────────────────

def mis_ventas_hoy(ctx: Contexto, args: dict) -> dict:
    """Los tickets que la persona cobró hoy en su sucursal.

    Con el conteo ciego encendido la cajera recibe cuántos y cuáles, sin
    importes: los importes del turno son el efectivo esperado que la pantalla
    le esconde (`cajera_a_ciegas`)."""
    propia = sucursal_propia(ctx)
    hoy = mv.hoy_mx()
    filtros = (
        *mv.filtros_documentos(mv.Ambito(ctx.org_id, propia, False), mv.Periodo(hoy, hoy)),
        SalesDocument.seller_id == ctx.user.id,
    )
    documentos = [
        d for d in ctx.db.query(SalesDocument).filter(*filtros)
        .order_by(SalesDocument.created_at.desc()).limit(TOPE_VENTAS + 1).all()
        if venta_visible_para_cajero(d, ctx.user)
    ]
    cuantos = ctx.db.query(func.count(SalesDocument.id)).filter(*filtros).scalar() or 0
    a_ciegas = cajera_a_ciegas(ctx.db, ctx.user)

    ventas, filas = [], []
    for d in documentos[:TOPE_VENTAS]:
        creada = d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=timezone.utc)
        venta = {
            "folio": f"{d.series}-{d.folio}" if d.series else str(d.folio or ""),
            "hora": creada.astimezone(MX_TZ).strftime("%H:%M"),
        }
        renglon = [venta["folio"], venta["hora"]]
        if not a_ciegas:
            venta["total"] = round(float(d.total_amount or 0), 2)
            renglon.append(venta["total"])
        ventas.append(venta)
        filas.append(renglon)
    salida = {"fecha": hoy.isoformat(), "tickets": int(cuantos), "ventas": ventas,
              "truncado": len(documentos) > TOPE_VENTAS}
    if a_ciegas:
        salida["importes"] = "No disponibles: tu tienda usa conteo ciego. Solo se informa el número de tickets."
    else:
        salida["total"] = round(float(
            ctx.db.query(func.coalesce(func.sum(SalesDocument.total_amount), 0)).filter(*filtros).scalar() or 0), 2)
    salida["_tabla"] = tabla("Mis ventas de hoy", ["Folio", "Hora"] + ([] if a_ciegas else ["Total"]), filas)
    return salida


def resumen_ventas(ctx: Contexto, args: dict) -> dict:
    ambito, rama = _ambito(ctx, args)
    periodo = _periodo(args)
    r = mv.resumen(ctx.db, ambito, periodo)
    metodos = {k: {"total": m.total, "tickets": m.tickets} for k, m in mv.por_metodo(ctx.db, ambito, periodo).items()}
    return {
        "ambito": _donde(rama), "desde": periodo.inicio.isoformat(), "hasta": periodo.fin.isoformat(),
        **_resumen(r), "por_metodo": metodos,
        "_tabla": tabla(f"Ventas · {_donde(rama)}", ["Concepto", "Importe"], [
            ["Venta neta", r.neta], ["Devuelto", r.devuelto], ["Tickets", str(r.tickets)],
            ["Ticket promedio", r.ticket_promedio], ["Fiado", r.fiado], ["Cobranza", r.cobranza],
        ]),
    }


def comparar_sucursales(ctx: Contexto, args: dict) -> dict:
    periodo = _periodo(args)
    por = mv.por_sucursal(ctx.db, ctx.org_id, periodo)
    ids = set(sucursales_que_venden(ctx.db, ctx.org_id)) | {i for i in por if i is not None}
    ramas = ctx.db.query(Branch).filter(Branch.organization_id == ctx.org_id, Branch.id.in_(ids or [-1])).all()
    sucursales = sorted(
        ({"sucursal_id": b.id, "sucursal": dato(b.name), **_resumen(por.get(b.id, mv.RESUMEN_VACIO))} for b in ramas),
        key=lambda s: -s["venta_neta"],
    )
    return {
        "desde": periodo.inicio.isoformat(), "hasta": periodo.fin.isoformat(), "sucursales": sucursales,
        "_tabla": tabla("Comparativo de sucursales", ["Sucursal", "Venta neta", "Tickets", "Ticket promedio"],
                        [[s["sucursal"], s["venta_neta"], s["tickets"], s["ticket_promedio"]] for s in sucursales]),
    }


# ── conteos ──────────────────────────────────────────────────────────────────

def _dia(momento) -> Optional[str]:
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(MX_TZ).date().isoformat()


def estado_conteos(ctx: Contexto, args: dict) -> dict:
    """Últimos conteos físicos. El avance (piezas esperadas contra contadas)
    solo se calcula para los abiertos."""
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    q = ctx.db.query(InventoryCount).filter(InventoryCount.organization_id == ctx.org_id)
    if sucursal is not None:
        q = q.filter(InventoryCount.branch_id == sucursal)
    salida, filas = [], []
    for c in q.order_by(InventoryCount.created_at.desc(), InventoryCount.id.desc()).limit(TOPE_CONTEOS).all():
        fila = {
            "conteo": c.id,
            "sucursal": dato(c.branch.name) if c.branch else None,
            "departamento": dato(c.department.name) if c.department else "Toda la tienda",
            "estado": c.status,
            "creado": _dia(c.created_at),
            "cerrado": _dia(c.closed_at),
            "ajustes_aplicados": c.aplicado_at is not None,
        }
        avance = ""
        if c.status == ABIERTO:
            a = conteos.avance(ctx.db, c)
            fila["avance"] = {
                "piezas_esperadas": float(a.esperadas_piezas), "piezas_contadas": float(a.contadas_piezas),
                "codigos_desconocidos": a.desconocidos,
            }
            avance = f"{float(a.contadas_piezas):g} de {float(a.esperadas_piezas):g}"
        salida.append(fila)
        filas.append([f"#{c.id}", fila["sucursal"], fila["departamento"], c.status, avance])
    return {
        "conteos": salida,
        "_tabla": tabla("Conteos", ["Conteo", "Sucursal", "Alcance", "Estado", "Avance"], filas),
    }


# ── faltantes ────────────────────────────────────────────────────────────────

def stock_bajo(ctx: Contexto, args: dict) -> dict:
    """Agotados (habilitados para venta con existencia en cero) y bajo mínimo
    (existencia menor a la alerta de la sucursal; misma regla del Inicio)."""
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    existencia = func.coalesce(StockOnHand.qty_on_hand, 0)
    base = (
        ctx.db.query(ProductVariant, Product, Branch, existencia, ProductBranchStatus.min_stock_alert)
        .select_from(ProductBranchStatus)
        .join(ProductVariant, ProductVariant.id == ProductBranchStatus.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == ProductBranchStatus.branch_id)
        .outerjoin(StockOnHand, and_(
            StockOnHand.variant_id == ProductBranchStatus.variant_id,
            StockOnHand.branch_id == ProductBranchStatus.branch_id,
        ))
        .filter(
            ProductBranchStatus.organization_id == ctx.org_id,
            Product.organization_id == ctx.org_id,
            Branch.organization_id == ctx.org_id,
            ProductBranchStatus.is_active_pos.is_(True),
            Product.is_active.is_(True),
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
        )
    )
    if sucursal is not None:
        base = base.filter(ProductBranchStatus.branch_id == sucursal)
    else:
        base = base.filter(Branch.can_sell.is_(True), Branch.is_active.is_(True))
    grupos = {
        "agotados": base.filter(existencia <= 0),
        "bajo_minimo": base.filter(
            ProductBranchStatus.min_stock_alert.isnot(None), ProductBranchStatus.min_stock_alert > 0,
            existencia > 0, existencia < ProductBranchStatus.min_stock_alert,
        ),
    }
    salida: dict = {}
    filas = []
    for clave, consulta in grupos.items():
        total = consulta.count()
        renglones = []
        for variante, producto, rama, cantidad, minimo in (
            consulta.order_by(existencia, Product.name).limit(TOPE_FALTANTES).all()
        ):
            marca = producto.brand.name if producto.brand else ""
            renglon = {
                "producto": dato(f"{marca} · {producto.name}" if marca else producto.name),
                "sku": dato(variante.sku), "color": dato(variante.color), "talla": dato(variante.size),
                "sucursal": dato(rama.name), "existencia": round(float(cantidad or 0), 2),
            }
            if clave == "bajo_minimo":
                renglon["minimo"] = round(float(minimo or 0), 2)
            renglones.append(renglon)
            detalle = " ".join(x for x in (renglon["color"], renglon["talla"]) if x)
            filas.append([renglon["producto"], detalle, renglon["sucursal"], renglon["existencia"],
                          "Agotado" if clave == "agotados" else f"Mínimo {renglon['minimo']:g}"])
        salida[clave] = {"total": total, "filas": renglones, "truncado": total > len(renglones)}
    salida["_tabla"] = tabla("Faltantes", ["Producto", "Color / talla", "Sucursal", "Existencia", "Motivo"], filas)
    return salida


# ── valor de inventario ──────────────────────────────────────────────────────

def valor_inventario(ctx: Contexto, args: dict) -> dict:
    """Mismas consultas que `GET /api/reports/valor-inventario` (dirección ve
    el valor a costo). Sin `sucursal_id` cuentan las sucursales que venden."""
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    agrupar = str(args.get("agrupar") or "sucursal").strip().lower()
    if agrupar not in valuacion._GRUPOS:
        raise ErrorHerramienta("agrupar debe ser sucursal, departamento o marca.")
    fila = valuacion._consulta(ctx.db, ctx.org_id, sucursal).one()
    totales = {**valuacion._fila_a_dict(fila, True), "skus_sin_costo": int(fila.skus_sin_costo or 0)}
    col_id, col_nombre, union, sin_nombre = valuacion._GRUPOS[agrupar]
    q = valuacion._consulta(ctx.db, ctx.org_id, sucursal, (col_id, col_nombre))
    if union is not None:
        q = q.outerjoin(*union)
    grupos = [
        {"nombre": dato(f[1]) or sin_nombre, **valuacion._fila_a_dict(f, True)}
        for f in q.group_by(col_id, col_nombre).order_by(desc("valor_venta"), col_nombre).limit(TOPE_GRUPOS).all()
    ]
    return {
        "totales": totales, "agrupado_por": agrupar, "grupos": grupos,
        "nota": "valor_costo solo suma las piezas con costo capturado; piezas_sin_costo dice cuántas faltan.",
        "_tabla": tabla(f"Valor de inventario por {agrupar}", ["Grupo", "Piezas", "A precio de venta", "A costo"],
                        [[g["nombre"], g["piezas"], g["valor_venta"], g["valor_costo"]] for g in grupos]),
    }


HERRAMIENTAS: dict[str, Herramienta] = {
    "mis_ventas_hoy": Herramienta(
        "Los tickets que cobraste hoy en tu sucursal.", SIN_PARAMETROS, mis_ventas_hoy,
    ),
    "resumen_ventas": Herramienta(
        "Ventas de un periodo: venta neta, devoluciones, tickets, ticket promedio, fiado, cobranza y cobros por método.",
        {"type": "object", "properties": dict(_PERIODO)}, resumen_ventas, elige_sucursal=True,
    ),
    "comparar_sucursales": Herramienta(
        "Ventas de un periodo sucursal por sucursal, de mayor a menor.",
        {"type": "object", "properties": dict(_PERIODO)}, comparar_sucursales,
    ),
    "estado_conteos": Herramienta(
        "Últimos conteos físicos de inventario: estado y avance de los abiertos.",
        SIN_PARAMETROS, estado_conteos, elige_sucursal=True,
    ),
    "stock_bajo": Herramienta(
        "Faltantes: productos agotados y productos por debajo de su mínimo.",
        SIN_PARAMETROS, stock_bajo, elige_sucursal=True,
    ),
    "valor_inventario": Herramienta(
        "Cuánto vale la existencia: piezas, valor a precio de venta y valor a costo, por sucursal, departamento o marca.",
        {"type": "object", "properties": {
            "agrupar": {"type": "string", "enum": ["sucursal", "departamento", "marca"]},
        }}, valor_inventario, elige_sucursal=True,
    ),
}
