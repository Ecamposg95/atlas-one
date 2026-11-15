"""Aplicar una carga autorizada: el ÚNICO lugar de la carga que escribe catálogo
y existencias.

Todo o nada: marcas y departamentos nuevos, productos y variantes, entradas o
existencias fijas, precios actualizados y auditoría van dentro de un SAVEPOINT.
Si algo falla, el SAVEPOINT se revierte, la carga queda en `error` con un
mensaje legible (eso sí se confirma) y se responde 422. Ningún servicio de los
que se llaman aquí hace commit: el único es el del final.

Kardex de la carga: `reference = "carga:<id>"`, `notes = "Carga #<folio> · <archivo>"`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models import Product, ProductBranchStatus, ProductVariant, User
from app.models.organization import Branch
from app.models.platform import PlatformAuditLog
from app.modules.cargas.cruce import _depto_por_nombre, _marca_por_nombre
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.normalizar import _llave
from app.modules.cargas.operaciones import recalcular_plan
from app.modules.cargas.reglas import ReglasCarga, reglas_de_la_org
from app.modules.products.models import Brand, Department
from app.modules.products.schemas import ProductCreate, ProductVariantCreate
from app.modules.products.services.productos import crear_producto
from app.modules.products.services.sucursales import (
    armar_estado_por_sucursal, fijar_existencia, sucursales_que_venden,
)
from app.modules.products.services.variantes import crear_variantes
from app.modules.tenants.models import Organization
from app.routers.inventory import aplicar_ajuste
from app.services.barcodes import AsignadorDeCodigos

_APLICABLES = ("EXISTE", "SUMA", "NUEVO")


class ResumenAplicacion(BaseModel):
    productos_nuevos: int = 0
    variantes_nuevas: int = 0
    piezas: Decimal = Decimal(0)
    valor_costo: Decimal = Decimal(0)
    # {marca, producto, sku, talla, barcode, piezas, precio}; piezas = lo que entró.
    etiquetas: list[dict] = []


class _Falla(Exception):
    """Falla legible a media aplicación (se revierte todo)."""


def _detalle(e: Exception) -> str:
    if isinstance(e, HTTPException):
        return e.detail if isinstance(e.detail, str) else json.dumps(e.detail, ensure_ascii=False)
    return str(e) or e.__class__.__name__


def _piezas(valor: Decimal) -> str:
    """3.000 -> "3", 1.500 -> "1.5" (la columna guarda tres decimales)."""
    return format(Decimal(valor).normalize(), "f")


def _dinero(valor) -> Optional[str]:
    return None if valor is None else f"{Decimal(valor):.2f}"


def _renglones(db: Session, carga: CargaMercancia) -> list[CargaRenglon]:
    return (db.query(CargaRenglon)
            .filter(CargaRenglon.organization_id == carga.organization_id,
                    CargaRenglon.carga_id == carga.id)
            .order_by(CargaRenglon.orden).all())


def _dudas_abiertas(db: Session, carga: CargaMercancia) -> int:
    return (db.query(CargaDuda)
            .filter(CargaDuda.organization_id == carga.organization_id,
                    CargaDuda.carga_id == carga.id, CargaDuda.estado == "abierta")
            .count())


def _sucursal_que_recibe(db: Session, carga: CargaMercancia, reglas: ReglasCarga) -> int:
    branch_id = carga.sucursal_destino_id or reglas.sucursal_recibe
    if not branch_id:
        raise HTTPException(
            status_code=422,
            detail="Falta indicar en qué sucursal entra la mercancía: elígela en la carga "
                   "o configura la sucursal que recibe en las reglas de carga.")
    existe = db.query(Branch.id).filter(Branch.id == branch_id,
                                        Branch.organization_id == carga.organization_id).first()
    if existe is None:
        raise HTTPException(
            status_code=422,
            detail="La sucursal que recibe la mercancía no es de tu organización: elige otra.")
    return branch_id


# ── trabajo dentro del SAVEPOINT ──────────────────────────────────────────

@dataclass
class _Aplicador:
    db: Session
    carga: CargaMercancia
    user: User
    reglas: ReglasCarga
    branch_id: int
    org_id: int = 0
    referencia: str = ""
    nota: str = ""
    marcas: dict[str, Brand] = field(default_factory=dict)
    deptos: dict[str, Department] = field(default_factory=dict)
    marcas_nuevas: int = 0
    deptos_nuevos: int = 0
    productos_nuevos: int = 0
    variantes_nuevas: int = 0
    precios_actualizados: int = 0
    # variant_id -> piezas que entraron por esta carga (para etiquetas).
    piezas_por_variante: dict[str, Decimal] = field(default_factory=dict)
    # variant_id -> precio que le puso esta carga ("actualizar"): una vez por variante.
    precios_puestos: dict[str, Decimal] = field(default_factory=dict)
    # Variantes de productos que nacieron en esta carga (su activación la dictan las reglas).
    de_productos_nuevos: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.org_id = self.carga.organization_id
        self.referencia = f"carga:{self.carga.id}"
        self.nota = f"Carga #{self.carga.folio} · {self.carga.archivo_nombre}"
        self.asignador = AsignadorDeCodigos(self.db, self.org_id)
        if self.reglas.activar_en == "sucursal_recibe":
            self.activar = [self.branch_id]
        else:
            self.activar = sucursales_que_venden(self.db, self.org_id) or [self.branch_id]
        # `crear_producto` siempre suma la sucursal de quien da de alta; en una
        # carga la activación la deciden las reglas, no quien autoriza.
        self.autor = SimpleNamespace(id=self.user.id, role=self.user.role, branch_id=None)
        self.deptos_a_crear = _deptos_con_crear(self.db, self.carga)

    # catálogo de apoyo
    def marca(self, nombre: Optional[str]) -> Optional[str]:
        if not nombre:
            return None
        llave = _llave(nombre)
        if llave not in self.marcas:
            b = _marca_por_nombre(self.db, self.org_id, nombre)
            if b is None:  # la duda de marca se contestó con "crear"
                b = Brand(name=" ".join(nombre.split()), organization_id=self.org_id)
                self.db.add(b)
                self.db.flush()
                self.marcas_nuevas += 1
            self.marcas[llave] = b
        return self.marcas[llave].id

    def depto(self, nombre: Optional[str]) -> Optional[str]:
        if not nombre:
            return None
        llave = _llave(nombre)
        if llave not in self.deptos:
            d = _depto_por_nombre(self.db, self.org_id, nombre)
            if d is None:
                # Solo en migración y solo si el dueño contestó "crear" a su duda;
                # en entrada un departamento que no existe nunca se crea.
                if self.carga.proposito != "migracion" or llave not in self.deptos_a_crear:
                    raise _Falla(f'el departamento "{nombre}" no existe en tu catálogo; '
                                 "elige uno que exista en la pregunta de departamento")
                d = Department(name=" ".join(nombre.split()), organization_id=self.org_id)
                self.db.add(d)
                self.db.flush()
                self.deptos_nuevos += 1
            self.deptos[llave] = d
        return self.deptos[llave].id

    def variante(self, variant_id: str) -> ProductVariant:
        v = (self.db.query(ProductVariant)
             .join(Product, Product.id == ProductVariant.product_id)
             .filter(ProductVariant.id == variant_id, ProductVariant.organization_id == self.org_id,
                     Product.organization_id == self.org_id,
                     ProductVariant.deleted_at == None, Product.deleted_at == None)  # noqa: E711
             .first())
        if v is None:
            raise _Falla("la variante del plan ya no existe en tu catálogo")
        return v

    # precios
    @staticmethod
    def _exigir_precio_y_costo(filas: list[CargaRenglon]) -> tuple[Decimal, Decimal]:
        """Precio y costo de una talla: todos sus renglones deben traer los mismos."""
        f = filas[0]
        if f.precio is None or Decimal(f.precio) <= 0:
            raise _Falla("no tiene precio de venta (debió quedar como pregunta)")
        if f.costo is None:
            raise _Falla("no tiene costo (debió quedar como pregunta)")
        _mismos(filas)
        return Decimal(f.precio), Decimal(f.costo)

    def actualizar_precio(self, filas: list[CargaRenglon], v: ProductVariant) -> bool:
        """`accion_precio == "actualizar"`: precio y costo nuevos, una sola vez por variante."""
        pide = [f for f in filas
                if ((f.normalizado or {}).get("_usuario") or {}).get("accion_precio") == "actualizar"]
        if not pide:
            return False
        f = pide[0]
        if f.precio is None or Decimal(f.precio) <= 0:
            raise _Falla("no tiene el precio nuevo")
        _mismos(pide)
        if v.id in self.precios_puestos:
            if self.precios_puestos[v.id] != Decimal(f.precio):
                raise _Falla(f"dos renglones cambian el precio de {v.sku} a montos distintos")
            return True
        self.precios_puestos[v.id] = Decimal(f.precio)
        antes_precio, antes_costo = v.price, v.cost
        v.price = Decimal(f.precio)
        if f.costo is not None:
            v.cost = Decimal(f.costo)
        self.db.add(PlatformAuditLog(
            actor_user_id=self.user.id, action="CARGA_PRECIO_ACTUALIZADO",
            entity_type="ProductVariant", entity_id=str(v.id),
            payload=json.dumps({
                "carga_id": self.carga.id, "folio": self.carga.folio, "variant_id": v.id,
                "sku": v.sku, "precio_anterior": _dinero(antes_precio),
                "precio_nuevo": _dinero(v.price), "costo_anterior": _dinero(antes_costo),
                "costo_nuevo": _dinero(v.cost), "source": "ai",
            }),
        ))
        self.precios_actualizados += 1
        return True

    # altas
    def crear_producto(self, filas: list[CargaRenglon]) -> dict[str, ProductVariant]:
        """Producto nuevo con una variante por talla (la primera es la principal)."""
        por_talla = _por_talla(filas)
        n = filas[0].normalizado or {}
        color = _color_del_grupo(filas)
        principal, *hermanas = por_talla.items()
        precio, costo = self._exigir_precio_y_costo(principal[1])
        hermanas_crear = []
        for talla, fs in hermanas:
            p, c = self._exigir_precio_y_costo(fs)
            hermanas_crear.append(ProductVariantCreate(
                size=talla or None, color=color, sku=fs[0].sku, price=p, cost=c))
        datos = ProductCreate(
            name=n.get("tipo") or n.get("descripcion_original") or principal[1][0].sku,
            sku=principal[1][0].sku, size=principal[0] or None, color=color,
            price=precio, cost=costo, has_iva=self.reglas.iva,
            department_id=self.depto(next((f.normalizado.get("departamento") for f in filas
                                            if f.normalizado.get("departamento")), None)),
            brand_id=self.marca(n.get("marca")), gender=n.get("genero"),
            material=n.get("material"), initial_stock=Decimal(0), branch_id=self.branch_id,
            target_branch_ids=self.activar, extra_variants=hermanas_crear,
        )
        producto = crear_producto(self.db, self.org_id, self.autor, datos,
                                  asignador=self.asignador, kardex=(self.referencia, self.nota))
        self.productos_nuevos += 1
        self.variantes_nuevas += len(por_talla)
        vivas = {v.sku.lower(): v for v in self.db.query(ProductVariant).filter(
            ProductVariant.organization_id == self.org_id, ProductVariant.product_id == producto.id)}
        self.de_productos_nuevos |= {v.id for v in vivas.values()}
        return {talla: vivas[fs[0].sku.lower()] for talla, fs in por_talla.items()}

    def crear_tallas(self, product_id: str, filas: list[CargaRenglon]) -> dict[str, ProductVariant]:
        """Tallas que faltan en un producto que ya existe."""
        producto = (self.db.query(Product)
                    .filter(Product.id == product_id, Product.organization_id == self.org_id,
                            Product.deleted_at == None)  # noqa: E711
                    .first())
        if producto is None:
            raise _Falla("el producto del plan ya no existe en tu catálogo")
        por_talla = _por_talla(filas)
        color = _color_del_grupo(filas)
        entradas = []
        for talla, fs in por_talla.items():
            p, c = self._exigir_precio_y_costo(fs)
            entradas.append(ProductVariantCreate(size=talla or None, color=color, sku=fs[0].sku,
                                                 price=p, cost=c))
        nuevas = crear_variantes(self.db, self.org_id, producto, entradas, user_id=self.user.id,
                                 asignador=self.asignador)
        self.variantes_nuevas += len(nuevas)
        return dict(zip(por_talla, nuevas))

    # existencias
    def activar_en_la_que_recibe(self, v: ProductVariant) -> None:
        """Una prenda que ya existía y recibe piezas debe poder venderse en la
        sucursal que las recibe; las demás sucursales no se tocan."""
        if v.id in self.de_productos_nuevos:
            return
        pbs = (self.db.query(ProductBranchStatus)
               .filter(ProductBranchStatus.variant_id == v.id,
                       ProductBranchStatus.branch_id == self.branch_id)
               .first())
        if pbs is None:
            armar_estado_por_sucursal(self.db, self.org_id, v, [self.branch_id])
        elif not pbs.is_active_pos or not pbs.is_visible:
            pbs.is_active_pos = True
            pbs.is_visible = True

    def meter_piezas(self, filas_por_variante: dict[str, tuple[ProductVariant, list[CargaRenglon]]]) -> None:
        for v, filas in filas_por_variante.values():
            if any(Decimal(f.cantidad) > 0 for f in filas):
                self.activar_en_la_que_recibe(v)
            if self.carga.proposito == "migracion":
                total = sum((Decimal(f.cantidad) for f in filas if Decimal(f.cantidad) > 0), Decimal(0))
                if total > 0:
                    fijar_existencia(self.db, self.org_id, v, self.branch_id, total, self.user.id,
                                     referencia=self.referencia, notas=self.nota)
                    for f in filas:
                        self._contar(f, v, Decimal(f.cantidad) if Decimal(f.cantidad) > 0 else Decimal(0))
                else:
                    for f in filas:
                        self._contar(f, v, Decimal(0))
                continue
            for f in filas:
                cantidad = Decimal(f.cantidad)
                if cantidad <= 0:
                    self._contar(f, v, Decimal(0))
                    continue
                mov = aplicar_ajuste(self.db, org_id=self.org_id, branch_id=self.branch_id,
                                     variant_id=v.id, user_id=self.user.id, quantity=cantidad,
                                     reason=self.referencia, notes=self.nota, commit=False)
                self._contar(f, v, cantidad, mov.id if mov is not None else None)

    def _contar(self, f: CargaRenglon, v: ProductVariant, piezas: Decimal,
                movimiento: Optional[int] = None) -> None:
        resultado = dict(f.resultado or {})
        resultado.update({"product_id": v.product_id, "variant_id": v.id, "piezas": _piezas(piezas)})
        if movimiento is not None:
            resultado["movement_id"] = movimiento
        f.resultado = resultado
        if piezas > 0:
            self.piezas_por_variante[v.id] = self.piezas_por_variante.get(v.id, Decimal(0)) + piezas


def _mismos(filas: list[CargaRenglon]) -> None:
    """Los renglones de una misma talla (o variante) deben coincidir en precio y costo."""
    precios = {None if f.precio is None else Decimal(f.precio) for f in filas}
    costos = {None if f.costo is None else Decimal(f.costo) for f in filas}
    if len(precios) > 1 or len(costos) > 1:
        ordenes = ", ".join(str(f.orden) for f in filas)
        raise _Falla(f"los renglones {ordenes} son la misma prenda pero traen precio o costo "
                     "distintos; corrígelos para que coincidan")


def _color_del_grupo(filas: list[CargaRenglon]) -> Optional[str]:
    """El color de las variantes nuevas: el del grupo si todos sus renglones lo comparten."""
    colores = {_llave((f.normalizado or {}).get("color")) for f in filas}
    return (filas[0].normalizado or {}).get("color") if len(colores) == 1 else None


def _deptos_con_crear(db: Session, carga: CargaMercancia) -> set[str]:
    """Departamentos (por llave) cuya duda se contestó con "crear"."""
    salida: set[str] = set()
    for d in (db.query(CargaDuda)
              .filter(CargaDuda.organization_id == carga.organization_id,
                      CargaDuda.carga_id == carga.id, CargaDuda.tipo == "departamento",
                      CargaDuda.estado == "resuelta")):
        crear = next((o for o in (d.opciones or []) if o.get("clave") == "crear"), None)
        if crear is not None and d.respuesta == crear.get("etiqueta"):
            ctx = d.contexto or {}
            nombre = ctx.get("nombre") or ctx.get("tipo")
            if nombre:
                salida.add(_llave(nombre))
    return salida


def _por_talla(filas: list[CargaRenglon]) -> dict[str, list[CargaRenglon]]:
    """Renglones del mismo grupo por talla ("" = sin talla); el orden del plan manda."""
    salida: dict[str, list[CargaRenglon]] = {}
    for f in filas:
        salida.setdefault((f.normalizado or {}).get("talla") or "", []).append(f)
    return salida


def _aplicar(ap: _Aplicador, filas: list[CargaRenglon]) -> ResumenAplicacion:
    db = ap.db
    grupos: dict[str, list[CargaRenglon]] = {}
    for f in filas:
        if f.clase in _APLICABLES:
            grupos.setdefault(f.grupo or f.id, []).append(f)

    # variant_id -> (variante, renglones que le meten piezas), en orden del plan.
    destino: dict[str, tuple[ProductVariant, list[CargaRenglon]]] = {}
    for fs in grupos.values():
        primero = fs[0]
        try:
            nuevos = [f for f in fs if f.clase == "NUEVO"]
            existentes = [f for f in fs if f.clase != "NUEVO"]
            creadas: dict[str, ProductVariant] = {}
            if nuevos:
                product_id = next((f.product_id for f in nuevos if f.product_id), None)
                if product_id:
                    creadas = ap.crear_tallas(product_id, nuevos)
                    tipo = "variante"
                else:
                    creadas = ap.crear_producto(nuevos)
                    tipo = "producto"
                for f in nuevos:
                    primero = f
                    v = creadas[(f.normalizado or {}).get("talla") or ""]
                    f.resultado = {"creado": tipo, "product_id": v.product_id, "variant_id": v.id}
                    destino.setdefault(v.id, (v, []))[1].append(f)
            por_variante: dict[str, list[CargaRenglon]] = {}
            for f in existentes:
                primero = f
                if not f.variant_id:
                    raise _Falla("no tiene la variante del catálogo a la que suma")
                por_variante.setdefault(f.variant_id, []).append(f)
            for vid, fs_v in por_variante.items():
                primero = fs_v[0]
                v = ap.variante(vid)
                actualizado = ap.actualizar_precio(fs_v, v)
                for f in fs_v:
                    f.resultado = {"creado": None, "product_id": v.product_id, "variant_id": v.id,
                                   "precio_actualizado": actualizado}
                    destino.setdefault(v.id, (v, []))[1].append(f)
        except Exception as e:
            raise _Falla(f"renglón {primero.orden} ({primero.sku or 'sin SKU'}): {_detalle(e)}") from e

    try:
        ap.meter_piezas(destino)
    except _Falla:
        raise
    except Exception as e:
        raise _Falla(f"al meter las piezas: {_detalle(e)}") from e
    db.flush()

    etiquetas = []
    valor_costo = Decimal(0)
    for vid, piezas in ap.piezas_por_variante.items():
        v = destino[vid][0]
        # A costo del catálogo tal como queda (con "mantener", el costo de siempre).
        valor_costo += piezas * Decimal(v.cost or 0)
        producto = db.get(Product, v.product_id)
        marca = db.get(Brand, producto.brand_id) if producto and producto.brand_id else None
        etiquetas.append({
            "marca": marca.name if marca else None, "producto": producto.name if producto else None,
            "sku": v.sku, "talla": v.size, "barcode": v.barcode, "piezas": _piezas(piezas),
            "precio": _dinero(v.price),
        })
    return ResumenAplicacion(
        productos_nuevos=ap.productos_nuevos, variantes_nuevas=ap.variantes_nuevas,
        piezas=sum(ap.piezas_por_variante.values(), Decimal(0)),
        valor_costo=valor_costo, etiquetas=etiquetas,
    )


# ── entrada pública ───────────────────────────────────────────────────────

def aplicar_carga(db: Session, carga: CargaMercancia, user: User) -> ResumenAplicacion:
    """Aplica el plan autorizado en una transacción. 403 si no es ADMINISTRADOR/DUEÑO;
    409 si la carga no está en `plan` o tiene preguntas abiertas (también si el
    catálogo cambió y el plan recalculado trae preguntas nuevas); 422 sin sucursal
    que recibe o si algo falla a media aplicación (nada queda escrito)."""
    if not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Solo un administrador o el dueño puede autorizar una carga.")
    # Candado de la fila: una segunda autorización simultánea espera aquí y
    # luego ve la carga ya `aplicada` o en `error` (no-op en SQLite).
    carga = (db.query(CargaMercancia)
             .filter(CargaMercancia.id == carga.id,
                     CargaMercancia.organization_id == carga.organization_id)
             .with_for_update().populate_existing().one())
    if carga.estado != "plan":
        raise HTTPException(status_code=409,
                            detail=f"La carga #{carga.folio} no está lista para autorizarse "
                                   f"(estado: {carga.estado}).")
    reglas = reglas_de_la_org(db.get(Organization, carga.organization_id))
    branch_id = _sucursal_que_recibe(db, carga, reglas)
    abiertas = _dudas_abiertas(db, carga)
    if abiertas:
        raise HTTPException(status_code=409,
                            detail=f"Contesta las {abiertas} preguntas abiertas antes de autorizar."
                            if abiertas > 1 else "Contesta la pregunta abierta antes de autorizar.")

    # El catálogo pudo cambiar entre la revisión y la autorización.
    recalcular_plan(db, carga)
    if _dudas_abiertas(db, carga):
        db.commit()  # que el dueño vea las preguntas nuevas
        raise HTTPException(
            status_code=409,
            detail="El catálogo cambió desde que revisaste el plan y ahora hay preguntas nuevas. "
                   "Contéstalas y vuelve a autorizar.")

    carga.estado = "aplicando"
    db.flush()
    filas = _renglones(db, carga)
    try:
        with db.begin_nested():
            ap = _Aplicador(db=db, carga=carga, user=user, reglas=reglas, branch_id=branch_id)
            resumen = _aplicar(ap, filas)
            totales = {
                "productos_nuevos": resumen.productos_nuevos,
                "variantes_nuevas": resumen.variantes_nuevas,
                "piezas": _piezas(resumen.piezas),
                "valor_costo": _dinero(resumen.valor_costo),
                "marcas_nuevas": ap.marcas_nuevas,
                "departamentos_nuevos": ap.deptos_nuevos,
                "precios_actualizados": ap.precios_actualizados,
                "renglones_aplicados": sum(1 for f in filas if f.clase in _APLICABLES),
                "sucursal_id": branch_id,
            }
            carga.estado = "aplicada"
            carga.error = None
            carga.totales = totales
            carga.aplicada_por = user.id
            carga.aplicada_at = datetime.now(timezone.utc)
            db.add(PlatformAuditLog(
                actor_user_id=user.id, action="CARGA_APLICADA",
                entity_type="CargaMercancia", entity_id=str(carga.id),
                payload=json.dumps({"carga_id": carga.id, "folio": carga.folio,
                                    "totales": totales, "source": "ai"}),
            ))
            db.flush()
    except Exception as e:
        mensaje = (f"No se aplicó nada de la carga #{carga.folio}: {_detalle(e)}. "
                   "Corrige el plan y vuelve a autorizar.")
        carga.estado = "error"
        carga.error = mensaje
        db.commit()
        raise HTTPException(status_code=422, detail=mensaje) from e
    db.commit()
    return resumen


def volver_a_plan(db: Session, carga: CargaMercancia) -> None:
    """Tras una aplicación fallida, regresa la carga a revisión para corregirla."""
    if carga.estado != "error":
        raise HTTPException(status_code=409,
                            detail="Solo una carga que falló al aplicarse vuelve a revisión.")
    if not _renglones(db, carga):
        raise HTTPException(status_code=409,
                            detail="La carga no tiene renglones: vuelve a subir el archivo.")
    carga.estado = "plan"
    carga.error = None
    db.flush()
