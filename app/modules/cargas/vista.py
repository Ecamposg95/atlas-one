"""Cómo se le enseña una carga a la pantalla (contrato HTTP de /api/cargas).

Solo lee: arma los diccionarios de respuesta desde las tablas de la carga.
Decimales como texto, fechas ISO 8601.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models import Product, ProductVariant, User
from app.models.organization import Branch
from app.modules.cargas.cruce import _depto_por_nombre, ultimo_conteo_por_departamento
from app.modules.cargas.operaciones import titulo_grupo
from app.modules.cargas.models import CLASES, CargaCambio, CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.proceso import piezas_por_carga
from app.modules.products.models import Brand

# Dudas que la pantalla deja contestar escribiendo (contrato, última línea).
ACEPTAN_TEXTO = frozenset({"tipo_cambio", "precio_faltante", "sin_costo", "marca_nueva",
                           "precio_fuera_familia", "sin_tipo", "sin_marca"})
_INACTIVAS = ("YA_CARGADO", "IGNORADO")


def _piezas(valor) -> str:
    """Cantidad sin ceros de relleno: 3.000 -> "3", 2.500 -> "2.5"."""
    d = Decimal(str(valor or 0)).normalize()
    return format(d, "f") if d != 0 else "0"


def _dinero(valor) -> Optional[str]:
    return None if valor is None else f"{Decimal(str(valor)):.2f}"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.isoformat()


def _nombre(user: Optional[User]) -> str:
    if user is None:
        return ""
    return user.full_name or user.username or ""


def _usuarios(db: Session, ids) -> dict[int, User]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}


def _sucursales(db: Session, org_id: int, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {b.id: b.name for b in db.query(Branch).filter(
        Branch.organization_id == org_id, Branch.id.in_(ids)).all()}


def _resumen(c: CargaMercancia, piezas: Decimal, usuarios: dict, sucursales: dict) -> dict:
    return {
        "id": c.id, "folio": c.folio, "estado": c.estado, "proposito": c.proposito,
        "archivo_nombre": c.archivo_nombre or "", "archivo_tipo": c.archivo_tipo or "",
        "sucursal_destino_id": c.sucursal_destino_id,
        "sucursal_nombre": sucursales.get(c.sucursal_destino_id),
        "piezas": _piezas(piezas), "usuario": _nombre(usuarios.get(c.user_id)),
        "created_at": _iso(c.created_at), "aplicada_at": _iso(c.aplicada_at), "error": c.error,
    }


def alta(c: CargaMercancia) -> dict:
    return {"id": c.id, "folio": c.folio, "estado": c.estado}


def lista(db: Session, org_id: int, cargas: list[CargaMercancia]) -> list[dict]:
    piezas = piezas_por_carga(db, org_id, [c.id for c in cargas])
    usuarios = _usuarios(db, (c.user_id for c in cargas))
    sucursales = _sucursales(db, org_id, (c.sucursal_destino_id for c in cargas))
    return [_resumen(c, piezas.get(c.id, Decimal(0)), usuarios, sucursales) for c in cargas]


# ── grupos ────────────────────────────────────────────────────────────────

def _titulo_de_llave(llave: str) -> str:
    """Respaldo para un cambio guardado sin título: marca y tipo de la llave."""
    partes = [p.strip().title() for p in (llave or "").split("|")[:2] if p.strip()]
    return " · ".join(partes) or "Sin agrupar"


def _titulos(por_grupo: dict[str, list[CargaRenglon]]) -> dict[str, str]:
    """Etiqueta humana por llave técnica; si dos grupos se llaman igual (mismo
    producto a precios distintos), se distinguen por el precio."""
    base = {}
    for llave, filas in por_grupo.items():
        activas = [f for f in filas if f.clase not in _INACTIVAS] or filas
        base[llave] = (titulo_grupo(activas[0].normalizado or activas[0].crudo or {})
                       if llave else "Sin agrupar")
    repetidos = {t for t in base.values() if list(base.values()).count(t) > 1}
    salida = {}
    for llave, titulo in base.items():
        if titulo in repetidos and llave:
            precios = sorted({f.precio for f in por_grupo[llave] if f.precio is not None})
            if precios:
                titulo += " · " + " / ".join(f"${p:,.2f}" for p in precios)
        salida[llave] = titulo
    return salida


def _renglones(db: Session, carga: CargaMercancia) -> list[CargaRenglon]:
    return (db.query(CargaRenglon)
            .filter(CargaRenglon.organization_id == carga.organization_id,
                    CargaRenglon.carga_id == carga.id)
            .order_by(CargaRenglon.orden).all())


def _por_grupo(filas: list[CargaRenglon]) -> dict[str, list[CargaRenglon]]:
    salida: dict[str, list[CargaRenglon]] = {}
    for f in filas:
        salida.setdefault(f.grupo or "", []).append(f)
    return salida


def _grupo(llave: str, titulo: str, filas: list[CargaRenglon]) -> dict:
    activas = [f for f in filas if f.clase not in _INACTIVAS] or filas
    n = activas[0].normalizado or {}
    return {
        "grupo": llave, "titulo": titulo,
        "marca": n.get("marca"), "tipo": n.get("tipo"),
        "departamento": n.get("departamento"), "genero": n.get("genero"),
        "product_id": next((f.product_id for f in activas if f.product_id), None),
        "renglones": [{
            "orden": f.orden,
            "talla": (f.normalizado or {}).get("talla"),
            "color": (f.normalizado or {}).get("color"),
            "cantidad": _piezas(f.cantidad), "precio": _dinero(f.precio), "costo": _dinero(f.costo),
            "clase": f.clase or "NUEVO", "sku": f.sku,
            "origen": (f.crudo or {}).get("origen") or "",
            # Lo que decía el archivo: el dueño ve qué se juntó en cada producto.
            "descripcion": (f.crudo or {}).get("descripcion_original") or "",
        } for f in filas],
    }


# ── cambios ───────────────────────────────────────────────────────────────

def cambio(c: Optional[CargaCambio], titulos: dict[str, str], usuarios: dict,
           puede_deshacer: bool = False) -> Optional[dict]:
    if c is None:
        return None
    resumen = dict((c.despues or {}).get("resumen") or {})
    resumen["grupos"] = [
        {**g, "titulo": g.get("titulo") or titulos.get(g.get("grupo") or "")
         or _titulo_de_llave(g.get("grupo") or "")}
        for g in resumen.get("grupos") or []]
    resumen.setdefault("dudas_resueltas", [])
    resumen.setdefault("dudas_nuevas", [])
    return {
        "id": c.id, "secuencia": c.secuencia, "texto": c.texto, "resumen": resumen,
        "deshecho": bool(c.deshecho), "puede_deshacer": puede_deshacer,
        "usuario": _nombre(usuarios.get(c.user_id)), "created_at": _iso(c.created_at),
    }


def _cambios(db: Session, carga: CargaMercancia) -> list[CargaCambio]:
    return (db.query(CargaCambio)
            .filter(CargaCambio.organization_id == carga.organization_id,
                    CargaCambio.carga_id == carga.id)
            .order_by(CargaCambio.secuencia).all())


def _ultimo_deshacible(carga: CargaMercancia, cambios: list[CargaCambio]) -> Optional[str]:
    if carga.estado != "plan":
        return None
    vivos = [c for c in cambios if not c.deshecho]
    return max(vivos, key=lambda c: c.secuencia).id if vivos else None


def respuesta_cambio(db: Session, carga: CargaMercancia, c: Optional[CargaCambio],
                     rechazos: list[str]) -> dict:
    titulos = _titulos(_por_grupo(_renglones(db, carga)))
    usuarios = _usuarios(db, [c.user_id] if c else [])
    ultimo = _ultimo_deshacible(carga, _cambios(db, carga)) if c else None
    return {"cambio": cambio(c, titulos, usuarios, c is not None and c.id == ultimo),
            "rechazos": rechazos}


# ── detalle ───────────────────────────────────────────────────────────────

def _duda(d: CargaDuda) -> dict:
    return {
        "numero": d.numero, "tipo": d.tipo, "texto": d.texto,
        "opciones": [{"clave": str(o.get("clave")), "etiqueta": str(o.get("etiqueta"))}
                     for o in (d.opciones or [])],
        "recomendada": d.recomendada, "acepta_texto": d.tipo in ACEPTAN_TEXTO,
        "estado": d.estado, "respuesta": d.respuesta,
    }


def _conteos(db: Session, org_id: int, filas: list[CargaRenglon]) -> list[dict]:
    nombres = list(dict.fromkeys(
        (f.normalizado or {}).get("departamento") for f in filas
        if f.clase not in _INACTIVAS and (f.normalizado or {}).get("departamento")))
    deptos = {}
    for nombre in nombres:
        d = _depto_por_nombre(db, org_id, nombre)
        if d is not None:
            deptos[d.id] = d.name
    ultimos = ultimo_conteo_por_departamento(db, org_id, list(deptos))
    return [{"departamento": deptos[did], "numero": u["numero"], "cerrado_at": _iso(u["cerrado_at"])}
            for did, u in ultimos.items()]


def detalle(db: Session, carga: CargaMercancia, user: User) -> dict:
    org_id = carga.organization_id
    filas = _renglones(db, carga)
    dudas = (db.query(CargaDuda)
             .filter(CargaDuda.organization_id == org_id, CargaDuda.carga_id == carga.id)
             .order_by(CargaDuda.numero).all())
    cambios = _cambios(db, carga)
    usuarios = _usuarios(db, [carga.user_id, *(c.user_id for c in cambios)])
    sucursales = _sucursales(db, org_id, [carga.sucursal_destino_id])

    contadores: dict = {k: 0 for k in CLASES}
    piezas = Decimal(0)
    for f in filas:
        if f.clase in contadores:
            contadores[f.clase] += 1
        if f.clase not in _INACTIVAS:
            piezas += Decimal(str(f.cantidad or 0))
    contadores["piezas"] = _piezas(piezas)

    por_grupo = _por_grupo(filas)
    titulos = _titulos(por_grupo)
    ultimo = _ultimo_deshacible(carga, cambios)
    abiertas = any(d.estado == "abierta" for d in dudas)

    cabecera = _resumen(carga, piezas, usuarios, sucursales)
    cabecera["monedas"] = {k: (None if v is None else str(v)) for k, v in (carga.monedas or {}).items()}
    cabecera["totales"] = carga.totales
    return {
        "carga": cabecera,
        "contadores": contadores,
        "dudas": [_duda(d) for d in dudas],
        "grupos": [_grupo(llave, titulos[llave], fs) for llave, fs in por_grupo.items()],
        "cambios": [cambio(c, titulos, usuarios, c.id == ultimo) for c in cambios],
        "ultimos_conteos": _conteos(db, org_id, filas),
        "puede_autorizar": _is_admin(user) and carga.estado == "plan" and not abiertas,
    }


# ── etiquetas y resumen de la aplicación ──────────────────────────────────

def etiquetas(db: Session, carga: CargaMercancia) -> list[dict]:
    """Lo que la aplicación dejó en `CargaRenglon.resultado`: una etiqueta por
    variante que recibió piezas, en el orden del plan."""
    piezas: dict[str, Decimal] = {}
    for f in _renglones(db, carga):
        r = f.resultado or {}
        vid = r.get("variant_id")
        cuantas = Decimal(str(r.get("piezas") or 0))
        if vid and cuantas > 0:
            piezas[vid] = piezas.get(vid, Decimal(0)) + cuantas
    if not piezas:
        return []
    variantes = {v.id: v for v in db.query(ProductVariant).filter(
        ProductVariant.organization_id == carga.organization_id, ProductVariant.id.in_(list(piezas)))}
    productos = {p.id: p for p in db.query(Product).filter(
        Product.organization_id == carga.organization_id,
        Product.id.in_({v.product_id for v in variantes.values()}))}
    marcas = {b.id: b for b in db.query(Brand).filter(
        Brand.organization_id == carga.organization_id,
        Brand.id.in_({p.brand_id for p in productos.values() if p.brand_id}))}
    salida = []
    for vid, cuantas in piezas.items():
        v = variantes.get(vid)
        if v is None:
            continue
        p = productos.get(v.product_id)
        marca = marcas.get(p.brand_id) if p is not None and p.brand_id else None
        salida.append({
            "marca": marca.name if marca else "", "producto": p.name if p else "",
            "sku": v.sku or "", "talla": v.size, "barcode": v.barcode,
            "piezas": _piezas(cuantas), "precio": _dinero(v.price) or "0.00",
        })
    return salida


def resumen_aplicacion(db: Session, carga: CargaMercancia, resumen) -> dict:
    return {
        "productos_nuevos": resumen.productos_nuevos,
        "variantes_nuevas": resumen.variantes_nuevas,
        "piezas": _piezas(resumen.piezas),
        "valor_costo": _dinero(resumen.valor_costo) or "0.00",
        # Las mismas que dará después GET /etiquetas: salen de lo que quedó registrado.
        "etiquetas": etiquetas(db, carga),
    }
