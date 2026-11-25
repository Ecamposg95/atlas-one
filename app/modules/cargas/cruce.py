"""Cruce de los grupos de una carga con el catálogo vivo y detección de
renglones ya cargados. Solo lee: nada de aquí escribe catálogo ni existencias."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.modules.cargas.models import CargaMercancia, CargaRenglon
from app.modules.cargas.normalizar import _limpia_sku, _llave, prefijo_de_marca, sku_para
from app.modules.cargas.reglas import ReglasCarga
from app.modules.cargas.tipos import Grupo, RenglonNormalizado
from app.modules.conteos.models import CERRADO, InventoryCount
from app.models.inventory import InventoryMovement
from app.modules.products.models import Brand, Department, Product, ProductVariant
from app.modules.products.sale_name import _marca_corta


class Coincidencia(BaseModel):
    product_id: str
    variante_por_talla: dict[str, str]  # talla ("" = sin talla) -> variant_id
    precio_actual: Decimal
    exacta: bool


def _variantes_vivas(db: Session, org_id: int, product_id: str) -> list[ProductVariant]:
    return (
        db.query(ProductVariant)
        .filter(
            ProductVariant.organization_id == org_id,
            ProductVariant.product_id == product_id,
            ProductVariant.deleted_at == None,  # noqa: E711
        )
        .order_by(ProductVariant.created_at, ProductVariant.id)
        .all()
    )


def _marca_por_nombre(db: Session, org_id: int, nombre: Optional[str]) -> Optional[Brand]:
    if not nombre:
        return None
    for b in db.query(Brand).filter(Brand.organization_id == org_id, Brand.deleted_at == None).all():  # noqa: E711
        if _llave(b.name) == _llave(nombre):
            return b
    return None


def _depto_por_nombre(db: Session, org_id: int, nombre: Optional[str]) -> Optional[Department]:
    if not nombre:
        return None
    for d in db.query(Department).filter(Department.organization_id == org_id, Department.deleted_at == None).all():  # noqa: E711
        if _llave(d.name) == _llave(nombre):
            return d
    return None


def _skus_de_marca(db: Session, org_id: int, brand_id: str) -> list[str]:
    filas = (
        db.query(ProductVariant.sku)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id, ProductVariant.organization_id == org_id,
            Product.brand_id == brand_id,
            Product.deleted_at == None, ProductVariant.deleted_at == None,  # noqa: E711
        )
        .all()
    )
    return [s for (s,) in filas if s]


def prefijos_de_marcas(db: Session, org_id: int, nombres: list[Optional[str]]) -> dict[str, Optional[str]]:
    """Prefijo de SKU por marca (llave sin acentos -> prefijo).

    Una marca con SKU vivos conserva su convención (el prefijo más común, o
    ninguno si sus SKU no lo llevan). Una marca sin SKU (nueva o sin productos)
    lo deriva como `sku_sugerido` (iniciales o 3 letras); si ese prefijo ya es
    de otra marca de la org o de otra marca nueva de esta carga, se le añade un
    dígito (2, 3…). Determinista: mismo catálogo y mismo orden, mismo prefijo."""
    skus_por_marca: dict[str, list[str]] = {}
    for brand_id, sku in (
        db.query(Product.brand_id, ProductVariant.sku)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.organization_id == org_id, ProductVariant.organization_id == org_id,
                Product.brand_id != None, ProductVariant.sku != None,  # noqa: E711
                Product.deleted_at == None, ProductVariant.deleted_at == None)  # noqa: E711
        .all()
    ):
        skus_por_marca.setdefault(brand_id, []).append(sku)
    marcas = {b.id: b for b in db.query(Brand).filter(
        Brand.organization_id == org_id, Brand.deleted_at == None)}  # noqa: E711
    por_llave = {_llave(b.name): b for b in sorted(marcas.values(), key=lambda b: (b.name, b.id))}
    # prefijo (mayúsculas) -> llave de la marca que lo usa
    usados: dict[str, str] = {}
    for bid, skus in skus_por_marca.items():
        p = prefijo_de_marca(skus)
        if p and bid in marcas:
            usados.setdefault(p.upper(), _llave(marcas[bid].name))
    resultado: dict[str, Optional[str]] = {}
    for nombre in nombres:
        llave = _llave(nombre)
        if not llave or llave in resultado:
            continue
        b = por_llave.get(llave)
        if b is not None and skus_por_marca.get(b.id):
            resultado[llave] = prefijo_de_marca(skus_por_marca[b.id])
            continue
        base = _limpia_sku(_marca_corta(nombre))
        if not base:
            resultado[llave] = None
            continue
        candidato, n = base, 2
        while usados.get(candidato.upper(), llave) != llave:
            candidato, n = f"{base}{n}", n + 1
        usados[candidato.upper()] = llave
        resultado[llave] = candidato
    return resultado


def _producto_vivo(db: Session, org_id: int, product_id: str) -> Optional[Product]:
    return (
        db.query(Product)
        .filter(Product.id == product_id, Product.organization_id == org_id,
                Product.deleted_at == None)  # noqa: E711
        .first()
    )


def _armar(db: Session, org_id: int, producto: Product, grupo: Grupo,
           por_sku: dict[str, str]) -> Coincidencia:
    """`por_sku`: talla -> variant_id ya hallado por SKU. Completa con la talla
    de la variante (mismo texto sin acentos ni mayúsculas) y calcula precio."""
    variantes = _variantes_vivas(db, org_id, producto.id)
    mapa = dict(por_sku)
    for talla in grupo.tallas:
        if talla in mapa:
            continue
        for v in variantes:
            if _llave(v.size) == _llave(talla) and v.id not in mapa.values():
                mapa[talla] = v.id
                break
    principal = variantes[0] if variantes else None
    precio_actual = (principal.price if principal and principal.price is not None else Decimal("0"))
    por_id = {v.id: v for v in variantes}
    con_precio = [(t, p) for t, p in grupo.tallas.items() if p is not None and t in mapa]
    exacta = bool(con_precio) and all(
        por_id[mapa[t]].price is not None and Decimal(por_id[mapa[t]].price) == Decimal(p)
        for t, p in con_precio
    )
    return Coincidencia(product_id=producto.id, variante_por_talla=mapa,
                        precio_actual=Decimal(precio_actual), exacta=exacta)


def cruzar_con_catalogo(
    db: Session, org_id: int, grupos: list[Grupo],
    renglones: list[RenglonNormalizado], reglas: ReglasCarga,
) -> dict[str, Optional[Coincidencia]]:
    """Por llave de grupo: el producto vivo que ya existe, o None."""
    resultado: dict[str, Optional[Coincidencia]] = {}
    prefijos: dict[str, Optional[str]] = {}
    for g in grupos:
        resultado[g.llave] = None
        marca = _marca_por_nombre(db, org_id, g.marca)
        if marca is None:
            continue
        if marca.id not in prefijos:
            prefijos[marca.id] = prefijo_de_marca(_skus_de_marca(db, org_id, marca.id))
        prefijo = prefijos[marca.id]

        # 1) Por SKU calculado, en cualquier departamento y solo de la misma marca.
        por_sku: dict[str, str] = {}
        producto_id: Optional[str] = None
        for talla in g.tallas or {"": None}:
            sku = sku_para(g, talla or None, reglas, prefijo)
            v = (
                db.query(ProductVariant)
                .filter(ProductVariant.organization_id == org_id, ProductVariant.sku == sku,
                        ProductVariant.deleted_at == None)  # noqa: E711
                .first()
            )
            if v is None:
                continue
            dueno = _producto_vivo(db, org_id, v.product_id)
            # Un SKU de la prenda de otra marca no es coincidencia (un SKU sin
            # prefijo de marca, "PLAY", puede repetirse entre marcas).
            if dueno is None or dueno.brand_id != marca.id:
                continue
            if producto_id is None:
                producto_id = v.product_id
            if v.product_id == producto_id:
                por_sku[talla] = v.id
        producto = _producto_vivo(db, org_id, producto_id) if producto_id else None

        # 2) Respaldo: marca + departamento + nombre que empieza con el tipo.
        if producto is None and g.tipo:
            depto_nombre = next((renglones[i].departamento for i in g.renglones
                                 if renglones[i].departamento), None)
            depto = _depto_por_nombre(db, org_id, depto_nombre)
            if depto is not None:
                candidatos = [
                    p for p in db.query(Product).filter(
                        Product.organization_id == org_id, Product.brand_id == marca.id,
                        Product.department_id == depto.id, Product.deleted_at == None,  # noqa: E711
                    ).all()
                    if _llave(p.name).startswith(_llave(g.tipo))
                ]
                if len(candidatos) == 1:  # ambiguo: sin coincidencia automática
                    producto = candidatos[0]
        if producto is not None:
            resultado[g.llave] = _armar(db, org_id, producto, g, por_sku)
    return resultado


def clasificar(
    grupo: Grupo, coincidencia: Optional[Coincidencia], proposito: str,
    renglones: list[RenglonNormalizado],
) -> list[tuple[int, str]]:
    """(índice de renglón, clase). `renglones` es la lista normalizada de la
    que `grupo.renglones` son índices (de ahí sale la talla de cada uno)."""
    salida: list[tuple[int, str]] = []
    for i in grupo.renglones:
        if coincidencia is None:
            salida.append((i, "NUEVO"))
            continue
        talla = renglones[i].talla or ""
        if talla in coincidencia.variante_por_talla:
            salida.append((i, "SUMA" if proposito == "entrada" else "EXISTE"))
        else:
            salida.append((i, "NUEVO"))
    return salida


def _forzado(r: CargaRenglon) -> bool:
    """El dueño contestó "cargarlos de todos modos" a la duda `ya_cargado`."""
    return bool(((r.normalizado or {}).get("_usuario") or {}).get("forzar"))


def marcar_ya_cargado(
    db: Session, org_id: int, carga: CargaMercancia,
    renglones_plan: list[CargaRenglon], ventana_dias: int,
    branch_id: Optional[int] = None,
) -> dict[str, list[CargaRenglon]]:
    """Marca `YA_CARGADO` los renglones que ya entraron antes (salvo los que el
    dueño forzó). Devuelve {id de la carga previa: renglones que coinciden}.

    Mismo archivo (sha256) que una carga aplicada: todos los renglones. Si no,
    mismo (SKU, cantidad) que una entrada de otra carga en la ventana, solo en
    la sucursal que recibe (sin sucursal no se compara)."""
    candidatos = [r for r in renglones_plan
                  if r.clase not in ("IGNORADO", "YA_CARGADO") and not _forzado(r)]
    por_carga: dict[str, list[CargaRenglon]] = {}

    if carga.archivo_sha256:
        repetida = (
            db.query(CargaMercancia.id)
            .filter(CargaMercancia.organization_id == org_id,
                    CargaMercancia.id != carga.id,
                    CargaMercancia.estado == "aplicada",
                    CargaMercancia.archivo_sha256 == carga.archivo_sha256)
            .order_by(CargaMercancia.aplicada_at.desc(), CargaMercancia.folio.desc())
            .first()
        )
        if repetida:
            for r in candidatos:
                r.clase = "YA_CARGADO"
            if candidatos:
                por_carga[repetida.id] = list(candidatos)
            db.flush()
            return por_carga

    if branch_id is None:
        return por_carga
    desde = datetime.now(timezone.utc) - timedelta(days=ventana_dias)
    movs = (
        db.query(ProductVariant.sku, InventoryMovement.qty_change, InventoryMovement.reference)
        .join(ProductVariant, ProductVariant.id == InventoryMovement.variant_id)
        .filter(InventoryMovement.organization_id == org_id,
                InventoryMovement.branch_id == branch_id,
                InventoryMovement.reference.like("carga:%"),
                InventoryMovement.reference != f"carga:{carga.id}",
                InventoryMovement.created_at >= desde)
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .all()
    )
    vistos: dict[tuple, str] = {}
    for sku, q, ref in movs:  # la carga más reciente gana
        vistos.setdefault((sku, Decimal(q)), ref.split(":", 1)[1])
    validas = {cid for (cid,) in db.query(CargaMercancia.id).filter(
        CargaMercancia.organization_id == org_id,
        CargaMercancia.id.in_(set(vistos.values())))} if vistos else set()
    for r in candidatos:
        previa = vistos.get((r.sku, Decimal(r.cantidad))) if r.sku else None
        if previa in validas:
            r.clase = "YA_CARGADO"
            por_carga.setdefault(previa, []).append(r)
    db.flush()
    return por_carga


def ultimo_conteo_por_departamento(
    db: Session, org_id: int, department_ids: list[str],
) -> dict[str, dict]:
    """El conteo CERRADO más reciente de cada departamento (contexto de pantalla)."""
    if not department_ids:
        return {}
    filas = (
        db.query(InventoryCount)
        .filter(InventoryCount.organization_id == org_id,
                InventoryCount.status == CERRADO,
                InventoryCount.closed_at != None,  # noqa: E711
                InventoryCount.department_id.in_(department_ids))
        .order_by(InventoryCount.closed_at.desc(), InventoryCount.id.desc())
        .all()
    )
    salida: dict[str, dict] = {}
    for c in filas:
        salida.setdefault(c.department_id, {
            "conteo_id": c.id, "numero": c.id, "cerrado_at": c.closed_at,
        })
    return salida
