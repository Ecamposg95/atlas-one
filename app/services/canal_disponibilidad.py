"""Disponibilidad web materializada (canal «Tienda en línea»).

Regla: una variante está disponible ⇔ la suma de `qty_on_hand` en las
sucursales web es > 0, la variante no está borrada y su producto está activo,
no borrado y con `approval_status = 'APPROVED'`. Se guarda en
`channel_availability`; sin fila = no disponible. Solo se escribe cuando el
booleano cambia, así `changed_at` le sirve de cursor a la tienda.

Cómo se entera sin tocar `create_sale` ni los routers de inventario: un
listener `before_flush` global junta, del propio flush, las existencias nuevas
o con `qty_on_hand` cambiado y las variantes/productos cuyo estado de venta
cambió, y recalcula solo esas variantes en el mismo flush (misma transacción:
si la venta hace rollback, esto también).

Reglas duras del listener (corre dentro del cobro):
- Org sin el módulo → sale sin consultar nada (cache de `canal_activo`).
- Costo constante por flush, no por fila: consultas en lote por org.
- Nunca lanza: todo va en un SAVEPOINT propio; si algo falla se registra
  y la transacción del negocio sigue sana.

Lo que el listener no ve (UPDATE en bloque, SQL crudo de scripts, cambio de
sucursales web, activar el módulo) lo corrige `recalcular_disponibilidad`.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from app.core.security.channel_keys import MODULO_CANAL, canal_activo, canal_activo_en_cache
from app.models.inventory import StockOnHand
from app.models.modules import OrganizationModule
from app.models.organization import Branch
from app.models.products import Product, ProductVariant
from app.modules.canal.models import ChannelAvailability

logger = logging.getLogger(__name__)

_LOTE = 500
_CAMPOS_PRODUCTO = ("is_active", "approval_status", "deleted_at")

# branch_id → organization_id. Una sucursal nunca cambia de org; algunas filas
# viejas de stock_on_hand no traen organization_id y se deduce de aquí.
_org_por_sucursal: dict[int, int] = {}
_org_lock = threading.Lock()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _lotes(valores: Iterable, n: int = _LOTE):
    lista = list(valores)
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


def _disponible(variante_borrada, producto_activo, aprobacion, producto_borrado, suma) -> bool:
    return (
        variante_borrada is None
        and producto_borrado is None
        and producto_activo is not False
        # NULL = valor por omisión de la columna ('APPROVED').
        and (aprobacion or "APPROVED") == "APPROVED"
        and Decimal(str(suma or 0)) > 0
    )


# ── Consultas públicas ───────────────────────────────────────────────────────
def sucursales_web(db: Session, org_id: int) -> list[int]:
    """Sucursales que alimentan la tienda: `config_json.sucursales_web` o, si
    no está fijado, todas las activas que venden."""
    fila = (
        db.query(OrganizationModule)
        .filter(OrganizationModule.organization_id == org_id,
                OrganizationModule.module_key == MODULO_CANAL)
        .first()
    )
    ids = ((fila.config_json if fila else None) or {}).get("sucursales_web")
    q = db.query(Branch.id).filter(Branch.organization_id == org_id)
    if ids is None:
        q = q.filter(Branch.can_sell.is_(True), Branch.is_active.is_(True))
    else:
        if not ids:
            return []
        q = q.filter(Branch.id.in_([int(i) for i in ids]))
    return sorted(b for (b,) in q.all())


def variante_disponible(db: Session, org_id: int, variant_id: str) -> bool:
    """Cálculo en vivo (no lee la tabla); ve los cambios aún sin flush."""
    web = sucursales_web(db, org_id)
    with db.no_autoflush:
        return _calcular(db, org_id, {variant_id}, web).get(variant_id, (None, False))[1]


# ── Cálculo con la sesión (ve lo pendiente de flush) ─────────────────────────
def _calcular(session: Session, org_id: int, variant_ids: set,
              web: list[int]) -> dict[str, tuple[Optional[str], bool]]:
    """{variant_id: (product_id, disponible)} con los valores en memoria de la
    sesión: las consultas por entidad devuelven las instancias del identity
    map con sus cambios aún no escritos, y las filas nuevas se suman a mano."""
    borrados = set(session.deleted)
    resultado: dict[str, tuple[Optional[str], bool]] = {}
    web_set = set(web)
    nuevos = [o for o in session.new if isinstance(o, StockOnHand)]
    for lote in _lotes(variant_ids):
        estado = {}
        for v, p in (
            session.query(ProductVariant, Product)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(ProductVariant.id.in_(lote), Product.organization_id == org_id)
        ):
            vivo = v not in borrados and p not in borrados
            estado[v.id] = (p.id, vivo, v.deleted_at, p.is_active, p.approval_status, p.deleted_at)
        sumas: dict[str, Decimal] = defaultdict(Decimal)
        if web_set and estado:
            for s in (
                session.query(StockOnHand)
                .filter(StockOnHand.variant_id.in_(list(estado)), StockOnHand.branch_id.in_(web))
            ):
                if s not in borrados:
                    sumas[s.variant_id] += Decimal(str(s.qty_on_hand or 0))
            for s in nuevos:
                if s.variant_id in estado and s.branch_id in web_set:
                    sumas[s.variant_id] += Decimal(str(s.qty_on_hand or 0))
        for vid in lote:
            if vid not in estado:
                resultado[vid] = (None, False)
                continue
            pid, vivo, vb, pa, ap, pb = estado[vid]
            resultado[vid] = (pid, vivo and _disponible(vb, pa, ap, pb, sumas.get(vid)))
    return resultado


def _filas_actuales(session: Session, org_id: int, variant_ids) -> dict[str, tuple[str, bool]]:
    actuales = {}
    for lote in _lotes(variant_ids):
        for vid, pid, disp in session.execute(
            select(ChannelAvailability.variant_id, ChannelAvailability.product_id,
                   ChannelAvailability.available)
            .where(ChannelAvailability.organization_id == org_id,
                   ChannelAvailability.variant_id.in_(lote))
        ):
            actuales[vid] = (pid, bool(disp))
    return actuales


def _cambios(org_id: int, calculado: dict, actuales: dict) -> list[dict]:
    """Solo lo que cambia el booleano. Sin fila y no disponible = sin cambio."""
    ahora = _ahora()
    filas = []
    for vid, (pid, disp) in calculado.items():
        previo = actuales.get(vid)
        if previo is None and not disp:
            continue
        if previo is not None and previo[1] == disp:
            continue
        filas.append({
            "organization_id": org_id, "variant_id": vid,
            "product_id": pid or (previo[0] if previo else ""),
            "available": disp, "changed_at": ahora,
        })
    return filas


def _escribir(session: Session, filas: list[dict]) -> None:
    """UPSERT: dos transacciones que crean la misma fila a la vez (dos ventas
    de la misma variante) no deben tumbar el cobro con un IntegrityError."""
    if not filas:
        return
    if session.connection().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    tabla = ChannelAvailability.__table__
    # Orden fijo (org, variante): dos transacciones que tocan las mismas filas
    # toman los locks en el mismo orden y no se bloquean en cruz.
    filas = sorted(filas, key=lambda f: (f["organization_id"], f["variant_id"]))
    for lote in _lotes(filas):
        stmt = insert(tabla).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=[tabla.c.organization_id, tabla.c.variant_id],
            set_={"available": stmt.excluded.available,
                  "product_id": stmt.excluded.product_id,
                  "changed_at": stmt.excluded.changed_at},
        )
        session.execute(stmt)


# ── Listener before_flush ────────────────────────────────────────────────────
def _org_de_sucursal_en_cache(branch_id: Optional[int]) -> Optional[int]:
    with _org_lock:
        return _org_por_sucursal.get(branch_id)


def _org_de_sucursal(session: Session, branch_id: int) -> Optional[int]:
    """Consulta la sucursal (solo dentro del SAVEPOINT) y la recuerda."""
    org = _org_de_sucursal_en_cache(branch_id)
    if org is not None:
        return org
    b = session.get(Branch, branch_id)
    if b is None or b.organization_id is None:
        return None
    with _org_lock:
        _org_por_sucursal[branch_id] = b.organization_id
    return b.organization_id


def _cambio(obj, campo: str) -> bool:
    return inspect(obj).attrs[campo].history.has_changes()


class _Toques:
    """Lo que tocó un flush. `_recolectar` lo llena SIN SQL; lo que necesita
    la base para saber su org queda en `sin_org` y se resuelve ya dentro del
    SAVEPOINT."""

    def __init__(self):
        self.stock = defaultdict(set)      # org → {(branch_id, variant_id)}
        self.variantes = defaultdict(set)  # org → {variant_id}
        self.productos = defaultdict(set)  # org → {product_id}
        self.stock_sin_org: list[tuple[int, str]] = []        # (branch_id, variant_id)
        self.variantes_sin_org: list[ProductVariant] = []

    def orgs(self) -> set:
        return set(self.stock) | set(self.variantes) | set(self.productos)

    def resolver(self, session: Session) -> None:
        for bid, vid in self.stock_sin_org:
            org = _org_de_sucursal(session, bid)
            if org is not None:
                self.stock[org].add((bid, vid))
        for v in self.variantes_sin_org:
            p = v.product  # carga perezosa: solo aquí, dentro del SAVEPOINT
            if p is not None and p.organization_id is not None:
                self.variantes[p.organization_id].add(v.id)
        self.stock_sin_org, self.variantes_sin_org = [], []


def _recolectar(session: Session) -> _Toques:
    t = _Toques()

    def _stock(obj):
        if obj.variant_id is None or obj.branch_id is None:
            return
        org = obj.organization_id or _org_de_sucursal_en_cache(obj.branch_id)
        if org is not None:
            t.stock[org].add((obj.branch_id, obj.variant_id))
        else:
            t.stock_sin_org.append((obj.branch_id, obj.variant_id))

    def _variante(obj):
        org = obj.organization_id
        if org is None and "product" in obj.__dict__ and obj.product is not None:
            org = obj.product.organization_id
        if org is not None:
            t.variantes[org].add(obj.id)
        else:
            t.variantes_sin_org.append(obj)

    for obj in session.new:
        if isinstance(obj, StockOnHand) and obj.qty_on_hand:
            _stock(obj)
    for obj in session.dirty:
        if isinstance(obj, StockOnHand):
            if _cambio(obj, "qty_on_hand"):
                _stock(obj)
        elif isinstance(obj, ProductVariant):
            if _cambio(obj, "deleted_at"):
                _variante(obj)
        elif isinstance(obj, Product):
            if any(_cambio(obj, c) for c in _CAMPOS_PRODUCTO) and obj.organization_id is not None:
                t.productos[obj.organization_id].add(obj.id)
    for obj in session.deleted:
        if isinstance(obj, StockOnHand):
            _stock(obj)
        elif isinstance(obj, ProductVariant):
            _variante(obj)
        elif isinstance(obj, Product) and obj.organization_id is not None:
            t.productos[obj.organization_id].add(obj.id)
    return t


def _procesar_org(session: Session, org_id: int, stock: set, variantes: set, productos: set) -> None:
    tocadas = set(variantes)
    if stock:
        web = set(sucursales_web(session, org_id))
        tocadas |= {vid for bid, vid in stock if bid in web}
    else:
        web = None
    if productos:
        for lote in _lotes(productos):
            tocadas |= {vid for (vid,) in session.execute(
                select(ProductVariant.id).where(ProductVariant.product_id.in_(lote)))}
        # Variantes nuevas (pendientes) de un producto tocado no tienen
        # existencias todavía: no hay nada que publicar.
    if not tocadas:
        return
    if web is None:
        web = set(sucursales_web(session, org_id))
    calculado = _calcular(session, org_id, tocadas, sorted(web))
    _escribir(session, _cambios(org_id, calculado, _filas_actuales(session, org_id, tocadas)))


def _procesar_flush(session: Session, flush_context, instances) -> None:
    try:
        with session.no_autoflush:
            t = _recolectar(session)  # solo Python
            if not t.orgs() and not t.stock_sin_org and not t.variantes_sin_org:
                return
            # Atajo: si todo lo tocado es de orgs que el cache ya sabe sin el
            # módulo, se sale sin una sola consulta (ni SAVEPOINT).
            if (not t.stock_sin_org and not t.variantes_sin_org
                    and all(canal_activo_en_cache(o) is False for o in t.orgs())):
                return
            # Todo lo que toca la base va en un SAVEPOINT propio: si algo
            # revienta en Postgres, solo se pierde esto y el cobro sigue con
            # su transacción sana.
            with session.connection().begin_nested():
                t.resolver(session)
                for org_id in t.orgs():
                    if not canal_activo(session, org_id):
                        continue
                    _procesar_org(session, org_id, t.stock.get(org_id, set()),
                                  t.variantes.get(org_id, set()), t.productos.get(org_id, set()))
    except Exception:  # noqa: BLE001 — jamás tumbar el negocio
        logger.exception("CANAL_DISPONIBILIDAD_FALLO")


# El registro (registrar_listener/quitar_listener/_antes_del_flush) vive en
# app/services/canal_listener.py; se re-exporta aquí.
from app.services.canal_listener import (  # noqa: E402,F401
    _antes_del_flush,
    quitar_listener,
    registrar_listener,
)


# ── Red de seguridad ─────────────────────────────────────────────────────────
def _corregir_sql(db: Session, org_id: int, web: list[int],
                  product_ids: Optional[list] = None) -> int:
    """Recalcula contra la base (SQL puro) las variantes de la org, o solo las
    de `product_ids`, y escribe lo que cambió."""
    filtro_p = [Product.organization_id == org_id]
    filtro_ca = [ChannelAvailability.organization_id == org_id]
    if product_ids is not None:
        filtro_p.append(Product.id.in_(product_ids))
        filtro_ca.append(ChannelAvailability.product_id.in_(product_ids))
    estado = {
        vid: (pid, vb, pa, ap, pb)
        for vid, pid, vb, pa, ap, pb in db.execute(
            select(ProductVariant.id, ProductVariant.product_id, ProductVariant.deleted_at,
                   Product.is_active, Product.approval_status, Product.deleted_at)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(*filtro_p)
        )
    }
    sumas = {}
    if web and estado:
        sumas = dict(db.execute(
            select(StockOnHand.variant_id, func.sum(StockOnHand.qty_on_hand))
            .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(*filtro_p, StockOnHand.branch_id.in_(web))
            .group_by(StockOnHand.variant_id)
        ).all())
    actuales = {
        vid: (pid, bool(disp))
        for vid, pid, disp in db.execute(
            select(ChannelAvailability.variant_id, ChannelAvailability.product_id,
                   ChannelAvailability.available)
            .where(*filtro_ca)
        )
    }
    calculado = {
        vid: (pid, _disponible(vb, pa, ap, pb, sumas.get(vid)))
        for vid, (pid, vb, pa, ap, pb) in estado.items()
    }
    for vid, (pid, _disp) in actuales.items():
        calculado.setdefault(vid, (pid, False))  # variante que ya no existe
    filas = _cambios(org_id, calculado, actuales)
    _escribir(db, filas)
    return len(filas)


def recalcular_productos(db: Session, org_id: int, product_ids) -> int:
    """Recalcula solo las variantes de esos productos (p. ej. tras un UPDATE en
    bloque que el listener no ve). Devuelve filas cambiadas. Sin commit."""
    db.flush()  # lo pendiente de la sesión a la base: aquí se lee solo SQL
    web = sucursales_web(db, org_id)
    return sum(_corregir_sql(db, org_id, web, lote) for lote in _lotes(set(product_ids)))


def recalcular_disponibilidad(db: Session, org_id: int) -> int:
    """Recorre toda la org y corrige diferencias contra la base (ve SQL crudo).
    Devuelve las filas que cambiaron. Sin commit."""
    db.flush()
    return _corregir_sql(db, org_id, sucursales_web(db, org_id))
