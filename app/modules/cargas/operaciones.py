"""Operaciones sobre el plan de una carga: validar, aplicar, recalcular y deshacer.

El dueño contesta las dudas con botones o con texto; cada respuesta se vuelve
una lista de operaciones (dicts con `op`). Aquí se validan contra la carga,
se guardan como correcciones del usuario en cada renglón y se recalcula el
plan completo. Nada de aquí toca catálogo ni existencias.

Las correcciones del usuario viven en `CargaRenglon.normalizado["_usuario"]`
(campo -> valor, más `usar_product_id`, `nuevo`, `ignorado`) y se vuelven a
aplicar en cada recálculo, así sobreviven a que el plan se rearme.

Contrato: toda mutación del plan pasa por un `CargaCambio` (`aplicar_operaciones`);
las tareas siguientes dependen de eso para deshacer.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Callable, Literal, Optional, Union

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from app.modules.cargas.cruce import (
    _armar, _producto_vivo, clasificar, cruzar_con_catalogo, marcar_ya_cargado,
    prefijos_de_marcas,
)
from app.modules.cargas.dudas import DudaNueva, generar_dudas, opcion_a_operaciones
from app.modules.cargas.lectura_excel import (
    MapaColumnas, leer_tablas, normalizar_numero, renglones_desde_excel,
)
from app.modules.cargas.models import CargaArchivo, CargaCambio, CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.normalizar import _llave, agrupar, normalizar_renglon, sku_para
from app.modules.cargas.reglas import reglas_de_la_org
from app.modules.cargas.tipos import RenglonCrudo, RenglonNormalizado
from app.modules.products.services.codigos import sku_en_uso
from app.modules.products.models import ProductVariant
from app.modules.tenants.models import Organization

CAMPOS = (
    "marca", "tipo", "material", "color", "talla", "precio", "costo", "genero",
    "departamento", "cantidad", "accion_precio", "moneda",
)
# Se aplican sobre el renglón leído antes de normalizar (cambian grupo, talla, costo…).
_ANTES_DE_NORMALIZAR = ("marca", "tipo", "material", "color", "talla", "precio", "cantidad", "moneda")
# Se aplican sobre el renglón ya normalizado (ganan sobre lo que dicten las reglas).
_DESPUES_DE_NORMALIZAR = ("genero", "departamento")
GENEROS = ("HOMBRE", "MUJER", "UNISEX", "NINO")
ACCIONES_PRECIO = ("mantener", "actualizar", "aparte")
ROLES_DINERO = ("costo", "precio", "ignorar")
_USUARIO = "_usuario"

_NO_EN_PLAN = "La carga ya no está en revisión; el plan no se puede cambiar."


# ── operaciones (unión discriminada por `op`) ─────────────────────────────

def _a_texto(v):
    """Un botón puede mandar `350` como número JSON: se trata igual que "350"."""
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return str(v)
    return v


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FijarCampo(_Op):
    op: Literal["fijar_campo"]
    renglones: Optional[list[int]] = None
    grupo: Optional[str] = None
    campo: Literal[CAMPOS]  # type: ignore[valid-type]
    valor: str

    @field_validator("valor", mode="before")
    @classmethod
    def _numero_a_texto(cls, v):
        return _a_texto(v)

    @model_validator(mode="after")
    def _un_destino(self):
        if bool(self.renglones) == bool(self.grupo):
            raise ValueError("indica los renglones o el grupo (uno de los dos)")
        return self


class ResolverDuda(_Op):
    op: Literal["resolver_duda"]
    numero: int
    opcion: str = ""
    valor: Optional[str] = None

    @field_validator("valor", mode="before")
    @classmethod
    def _numero_a_texto(cls, v):
        return _a_texto(v)


class UsarExistente(_Op):
    op: Literal["usar_existente"]
    grupo: str
    product_id: str


class NuevoProducto(_Op):
    op: Literal["nuevo_producto"]
    grupo: str


class Ignorar(_Op):
    op: Literal["ignorar"]
    renglones: list[int] = Field(min_length=1)


class Forzar(_Op):
    """Cargar renglones que coinciden con una carga previa (duda `ya_cargado`)."""
    op: Literal["forzar"]
    renglones: list[int] = Field(min_length=1)


class TipoCambio(_Op):
    op: Literal["tipo_cambio"]
    moneda: str
    valor: Decimal

    @field_validator("valor", mode="before")
    @classmethod
    def _texto_a_numero(cls, v):
        return normalizar_numero(v) if isinstance(v, str) else v


class RolColumna(_Op):
    op: Literal["rol_columna"]
    tabla: int
    columna: int
    rol: Literal[ROLES_DINERO]  # type: ignore[valid-type]


Operacion = Annotated[
    Union[FijarCampo, ResolverDuda, UsarExistente, NuevoProducto, Ignorar, TipoCambio, RolColumna,
          Forzar],
    Field(discriminator="op"),
]
_ADAPTADOR: TypeAdapter = TypeAdapter(Operacion)
NOMBRES_OP = ("fijar_campo", "resolver_duda", "usar_existente", "nuevo_producto",
              "ignorar", "tipo_cambio", "rol_columna", "forzar")


class _Rechazo(Exception):
    """Operación inválida; el mensaje se le enseña al usuario tal cual."""


def _parsear(op: Any) -> _Op:
    if not isinstance(op, dict):
        raise _Rechazo("no es una operación")
    nombre = op.get("op")
    if nombre not in NOMBRES_OP:
        raise _Rechazo(f'no sé hacer "{nombre}"')
    if nombre == "fijar_campo" and op.get("campo") not in CAMPOS:
        raise _Rechazo(f'el campo "{op.get("campo")}" no se puede cambiar')
    try:
        return _ADAPTADOR.validate_python(op)
    except ValidationError as e:
        err = e.errors()[0]
        dato = ".".join(str(x) for x in err["loc"][1:])
        if err["type"] == "extra_forbidden":
            raise _Rechazo(f'el dato "{dato}" no existe en {nombre}') from None
        if err["type"] == "missing":
            raise _Rechazo(f'falta "{dato}" en {nombre}') from None
        if not dato:  # validación del modelo completo
            raise _Rechazo(str(err["msg"]).removeprefix("Value error, ")) from None
        raise _Rechazo(f'"{dato}" no es válido en {nombre}') from None


def _numero(texto: str) -> Decimal:
    try:
        valor = Decimal(normalizar_numero(texto or ""))
    except InvalidOperation:
        raise _Rechazo(f'"{texto}" no es una cantidad') from None
    if not valor.is_finite():
        raise _Rechazo(f'"{texto}" no es una cantidad')
    return valor


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().upper()


def _valor_de_campo(campo: str, valor: str) -> str:
    """Valida el valor escrito por el usuario y lo devuelve en su forma guardada."""
    if campo in ("precio", "costo", "cantidad"):
        n = _numero(valor)
        if n < 0:
            raise _Rechazo(f"el {campo} no puede ser negativo")
        if campo != "costo" and n == 0:
            raise _Rechazo(f"el {campo} debe ser mayor que cero")
        return str(n)
    if campo == "genero":
        g = _sin_acentos(valor)
        if g not in GENEROS:
            raise _Rechazo(f'"{valor}" no es un género (hombre, mujer, unisex o niño)')
        return g
    if campo == "moneda":
        m = _sin_acentos(valor or "")
        if not re.fullmatch(r"[A-Z]{3}", m):
            raise _Rechazo(f'"{valor}" no es una moneda (escribe su código: USD, CNY, MXN…)')
        return m
    if campo == "accion_precio":
        a = (valor or "").strip().lower()
        if a not in ACCIONES_PRECIO:
            raise _Rechazo(f'"{valor}" no es una acción de precio (mantener, actualizar o aparte)')
        return a
    limpio = " ".join((valor or "").split())
    if not limpio:
        raise _Rechazo(f"falta el valor de {campo}")
    return limpio


# ── contexto de un lote ───────────────────────────────────────────────────

class _Contexto:
    def __init__(self, db: Session, carga: CargaMercancia, user_id: Optional[int]):
        self.db = db
        self.carga = carga
        self.org_id = carga.organization_id
        self.user_id = user_id
        filas = _renglones(db, carga)
        self.por_orden = {f.orden: f for f in filas}
        self.grupos: dict[str, list[CargaRenglon]] = {}
        for f in filas:
            if f.grupo and f.clase != "IGNORADO":
                self.grupos.setdefault(f.grupo, []).append(f)
        self.dudas = {d.numero: d for d in _dudas(db, carga)}

    def renglones(self, ordenes: list[int]) -> list[CargaRenglon]:
        for n in ordenes:
            if n not in self.por_orden:
                raise _Rechazo(f"renglón {n} no es de esta carga")
        return [self.por_orden[n] for n in dict.fromkeys(ordenes)]

    def grupo(self, llave: str) -> list[CargaRenglon]:
        if llave not in self.grupos:
            raise _Rechazo(f'el grupo "{llave}" no existe en esta carga')
        return self.grupos[llave]


def _renglones(db: Session, carga: CargaMercancia) -> list[CargaRenglon]:
    return (db.query(CargaRenglon)
            .filter(CargaRenglon.organization_id == carga.organization_id,
                    CargaRenglon.carga_id == carga.id)
            .order_by(CargaRenglon.orden).all())


def _dudas(db: Session, carga: CargaMercancia) -> list[CargaDuda]:
    return (db.query(CargaDuda)
            .filter(CargaDuda.organization_id == carga.organization_id,
                    CargaDuda.carga_id == carga.id)
            .order_by(CargaDuda.numero).all())


def _usuario(fila: CargaRenglon) -> dict:
    return dict((fila.normalizado or {}).get(_USUARIO) or {})


def _corregir(filas: list[CargaRenglon], poner: dict, quitar: tuple = ()) -> None:
    for f in filas:
        norm = dict(f.normalizado or {})
        u = dict(norm.get(_USUARIO) or {})
        for k in quitar:
            u.pop(k, None)
        u.update(poner)
        norm[_USUARIO] = u
        f.normalizado = norm  # objeto nuevo: SQLAlchemy ve el cambio


def _preparar(ctx: _Contexto, op: _Op) -> Callable[[], None]:
    """Valida `op` contra la carga y devuelve cómo aplicarla (sin aplicarla)."""
    if isinstance(op, FijarCampo):
        filas = ctx.renglones(op.renglones) if op.renglones else ctx.grupo(op.grupo)
        valor = _valor_de_campo(op.campo, op.valor)
        return lambda: _corregir(filas, {op.campo: valor})

    if isinstance(op, ResolverDuda):
        duda = ctx.dudas.get(op.numero)
        if duda is None:
            raise _Rechazo(f"la pregunta {op.numero} no existe")
        if duda.estado != "abierta":
            raise _Rechazo(f"la pregunta {op.numero} ya está contestada")
        try:
            hijas = opcion_a_operaciones(duda, op.opcion, op.valor)
        except ValueError as e:
            raise _Rechazo(f"pregunta {op.numero}: {e}") from None
        pasos = [_preparar(ctx, _parsear(h)) for h in hijas]
        etiqueta = next((o.get("etiqueta") for o in (duda.opciones or [])
                         if o.get("clave") == op.opcion), None)
        respuesta = etiqueta or op.valor or op.opcion

        def aplicar() -> None:
            for paso in pasos:
                paso()
            duda.estado = "resuelta"
            duda.respuesta = respuesta
            duda.resuelta_por = ctx.user_id
        return aplicar

    if isinstance(op, UsarExistente):
        filas = ctx.grupo(op.grupo)
        if _producto_vivo(ctx.db, ctx.org_id, op.product_id) is None:
            raise _Rechazo(f"el producto {op.product_id} no es de tu catálogo")
        return lambda: _corregir(filas, {"usar_product_id": op.product_id}, quitar=("nuevo",))

    if isinstance(op, NuevoProducto):
        filas = ctx.grupo(op.grupo)
        return lambda: _corregir(filas, {"nuevo": True}, quitar=("usar_product_id",))

    if isinstance(op, Ignorar):
        filas = ctx.renglones(op.renglones)

        def aplicar() -> None:
            _corregir(filas, {"ignorado": True})
            for f in filas:
                f.clase = "IGNORADO"
        return aplicar

    if isinstance(op, Forzar):
        filas = ctx.renglones(op.renglones)
        return lambda: _corregir(filas, {"forzar": True})

    if isinstance(op, TipoCambio):
        moneda = op.moneda.strip().upper()
        if not op.valor.is_finite() or op.valor <= 0:
            raise _Rechazo("el tipo de cambio debe ser mayor que cero")
        if moneda == "MXN":
            raise _Rechazo("el peso mexicano no lleva tipo de cambio")
        conocidas = {k.strip().upper() for k in (ctx.carga.monedas or {})}
        conocidas |= {str((f.crudo or {}).get("moneda") or "").strip().upper()
                      for f in ctx.por_orden.values()}
        if moneda not in conocidas:
            raise _Rechazo(f"la moneda {moneda} no aparece en esta carga")

        def aplicar() -> None:
            monedas = {k: v for k, v in (ctx.carga.monedas or {}).items()
                       if k.strip().upper() != moneda}
            monedas[moneda] = float(op.valor)
            ctx.carga.monedas = monedas
        return aplicar

    if isinstance(op, RolColumna):
        tablas = (ctx.carga.lectura or {}).get("tablas") or []
        if not 0 <= op.tabla < len(tablas):
            raise _Rechazo(f"la tabla {op.tabla} no existe en esta carga")
        dinero = ((tablas[op.tabla].get("mapa") or {}).get("columnas_dinero") or [])
        if op.columna not in dinero:
            raise _Rechazo(f"la columna {op.columna} de la tabla {op.tabla} no es una columna de dinero")

        def aplicar() -> None:
            lectura = copy.deepcopy(ctx.carga.lectura)
            tabla = lectura["tablas"][op.tabla]
            tabla["rol_dinero"] = {**(tabla.get("rol_dinero") or {}), str(op.columna): op.rol}
            ctx.carga.lectura = lectura
        return aplicar

    raise _Rechazo("operación desconocida")  # pragma: no cover


def validar_operaciones(db: Session, carga: CargaMercancia,
                        operaciones: list) -> tuple[list[dict], list[str]]:
    """Revisa sin aplicar. Devuelve las válidas (limpias) y los rechazos legibles."""
    ctx = _Contexto(db, carga, None)
    validas: list[dict] = []
    rechazos: list[str] = []
    for i, crudo in enumerate(operaciones, 1):
        try:
            op = _parsear(crudo)
            _preparar(ctx, op)
        except _Rechazo as e:
            rechazos.append(f"Operación {i}: {e}")
            continue
        validas.append(op.model_dump(mode="json", exclude_none=True))
    return validas, rechazos


# ── recálculo ─────────────────────────────────────────────────────────────

def _crudo_corregido(fila: CargaRenglon, usuario: dict) -> RenglonCrudo:
    base = dict(fila.crudo or fila.normalizado or {})
    for campo in _ANTES_DE_NORMALIZAR:
        if campo in usuario:
            base[campo] = usuario[campo]
    if "costo" in usuario:  # el costo que escribe el usuario es en pesos, por pieza
        base["costo_unitario"] = usuario["costo"]
        base["moneda"] = "MXN"
    return RenglonCrudo.model_validate(base)


def _moneda_por_omision(carga: CargaMercancia) -> tuple[Optional[str], Optional[str]]:
    """(moneda que heredan los costos sin moneda, moneda por omisión al normalizar).

    Excel: pesos. PDF que declara UNA moneda: esa. PDF con varias o ninguna:
    ninguna (el costo queda sin calcular y se pregunta con la duda `moneda`)."""
    if carga.archivo_tipo != "pdf":
        return None, "MXN"
    declaradas = list(dict.fromkeys(k.strip().upper() for k in (carga.monedas or {}) if k.strip()))
    if len(declaradas) == 1:
        return declaradas[0], declaradas[0]
    return None, None


def _contestada_por_el_usuario(d: DudaNueva, por_orden: dict[int, CargaRenglon]) -> bool:
    """Dudas cuya respuesta ya está en las correcciones de sus renglones.

    "Darlo de alta aparte" también contesta `casi_igual`: el dueño ya dijo que
    es un producto nuevo, aunque se parezca al que tiene."""
    llaves = {"casi_igual": ("nuevo", "usar_product_id"),
              "precio_distinto_existente": ("accion_precio",)}.get(d.tipo)
    if not llaves or not d.renglones:
        return False

    def contestada(u: dict) -> bool:
        if d.tipo == "casi_igual" and u.get("accion_precio") == "aparte":
            return True
        return any(u.get(k) for k in llaves)
    return all(contestada(_usuario(por_orden[n])) for n in d.renglones if n in por_orden)


def _skus_del_grupo(g, reglas, prefijo: Optional[str]) -> list[str]:
    return [sku_para(g, t or None, reglas, prefijo) for t in (g.tallas or {"": None})]


def _ocupado(db: Session, org_id: int, sku: str, tomados: set[str]) -> bool:
    return sku.lower() in tomados or sku_en_uso(db, org_id, sku)


def _sufijo_libre(db: Session, org_id: int, g, reglas, prefijo: Optional[str],
                  tomados: set[str]) -> str:
    """Primer "-N" (N ≥ 2) cuyos SKU no existen en la org (archivados incluidos)
    ni los tomó otro grupo de esta carga. Lo usan "darlo de alta aparte" y un
    producto nuevo cuyo SKU calculado ya está en uso."""
    original = g.sufijo
    try:
        for n in range(2, 100):
            g.sufijo = f"{original}-{n}"
            if not any(_ocupado(db, org_id, s, tomados) for s in _skus_del_grupo(g, reglas, prefijo)):
                return g.sufijo
    finally:
        g.sufijo = original
    raise ValueError(f'no hay SKU libre para dar de alta "{g.llave}"')


def _sku_libre(db: Session, org_id: int, sku: str, tomados: set[str]) -> str:
    """Talla nueva de un producto que ya existe cuyo SKU calculado está en uso."""
    for n in range(2, 100):
        candidato = f"{sku}-{n}"
        if not _ocupado(db, org_id, candidato, tomados):
            return candidato
    raise ValueError(f'no hay SKU libre para "{sku}"')


def _conciliar_dudas(db: Session, carga: CargaMercancia, nuevas: list[DudaNueva],
                     reabrir: frozenset | set = frozenset()) -> None:
    """Por `clave`: la abierta conserva su número, la contestada no se reabre
    (salvo las de `reabrir`, cuya respuesta dejó de valer), la abierta cuya causa
    desapareció se resuelve y la nueva toma el siguiente número."""
    guardadas = _dudas(db, carga)
    por_clave = {d.clave: d for d in guardadas}
    siguiente = max((d.numero for d in guardadas), default=0) + 1
    generadas: dict[str, DudaNueva] = {}
    for d in nuevas:
        generadas.setdefault(d.clave, d)
    for clave, d in generadas.items():
        g = por_clave.get(clave)
        datos = dict(tipo=d.tipo, texto=d.texto, opciones=d.opciones, recomendada=d.recomendada,
                     renglones=d.renglones, contexto=d.contexto)
        if g is None:
            db.add(CargaDuda(organization_id=carga.organization_id, carga_id=carga.id,
                             numero=siguiente, clave=clave, estado="abierta", **datos))
            siguiente += 1
        elif g.estado == "abierta" or clave in reabrir:
            for k, v in datos.items():
                setattr(g, k, v)
            if g.estado != "abierta":
                g.estado, g.respuesta, g.resuelta_por = "abierta", None, None
    for g in guardadas:
        if g.estado == "abierta" and g.clave not in generadas:
            g.estado = "resuelta"
    db.flush()


def recalcular_plan(db: Session, carga: CargaMercancia) -> None:
    """Rearma el plan desde lo leído + las correcciones del usuario: normaliza,
    agrupa, cruza con el catálogo, clasifica, detecta lo ya cargado y concilia
    las dudas. Los renglones IGNORADO siguen así."""
    org_id = carga.organization_id
    reglas = reglas_de_la_org(db.get(Organization, org_id))
    monedas = {k: (None if v is None else Decimal(str(v))) for k, v in (carga.monedas or {}).items()}

    heredada, por_omision = _moneda_por_omision(carga)
    filas = _renglones(db, carga)
    activos: list[CargaRenglon] = []
    norm: list[RenglonNormalizado] = []
    for f in filas:
        usuario = _usuario(f)
        crudo = _crudo_corregido(f, usuario)
        if heredada and crudo.costo_unitario is not None and not crudo.moneda:
            crudo.moneda = heredada
        n = normalizar_renglon(crudo, reglas, monedas, moneda_por_omision=por_omision)
        for campo in _DESPUES_DE_NORMALIZAR:
            if campo in usuario:
                setattr(n, campo, usuario[campo])
        f.normalizado = {**n.model_dump(mode="json"), **({_USUARIO: usuario} if usuario else {})}
        f.cantidad = n.cantidad
        f.precio = n.precio
        f.costo = n.costo_mxn
        if usuario.get("ignorado") or f.clase == "IGNORADO":
            f.clase = "IGNORADO"
            continue
        activos.append(f)
        norm.append(n)

    grupos = agrupar(norm)
    coincidencias = cruzar_con_catalogo(db, org_id, grupos, norm, reglas)
    prefijos = prefijos_de_marcas(db, org_id, [g.marca for g in grupos])
    # SKU que ya calcularon los grupos anteriores de esta carga (en este recálculo).
    tomados: set[str] = set()
    reabrir: set[str] = set()
    for g in grupos:
        correcciones = [_usuario(activos[i]) for i in g.renglones]
        usar = next((u["usar_product_id"] for u in correcciones if u.get("usar_product_id")), None)
        # "Darlo de alta aparte" (precio distinto a la prenda que ya existe):
        # producto nuevo con sufijo "-N" en el SKU, sin tocar al existente.
        aparte = any(u.get("accion_precio") == "aparte" for u in correcciones)
        if any(u.get("nuevo") for u in correcciones) or aparte:
            coincidencias[g.llave] = None
        elif usar:
            producto = _producto_vivo(db, org_id, usar)
            if producto is not None and producto.is_active is not False:
                coincidencias[g.llave] = _armar(db, org_id, producto, g, {})
            else:
                # El producto elegido ya no existe o se desactivó: se olvida la
                # elección y la pregunta "casi_igual" del grupo se reabre.
                _corregir([activos[i] for i in g.renglones], {}, quitar=("usar_product_id",))
                reabrir.add(f"casi_igual|{g.llave}")
        c = coincidencias.get(g.llave)

        prefijo = prefijos.get(_llave(g.marca))
        # Un producto nuevo nunca falla al aplicar por SKU repetido: si su SKU ya
        # existe en la org o lo calculó otro grupo de esta carga, toma "-N".
        if aparte or (c is None and any(_ocupado(db, org_id, sku, tomados)
                                        for sku in _skus_del_grupo(g, reglas, prefijo))):
            g.sufijo = _sufijo_libre(db, org_id, g, reglas, prefijo, tomados)
        ids = list(c.variante_por_talla.values()) if c else []
        sku_variante = {v.id: v.sku for v in db.query(ProductVariant).filter(
            ProductVariant.organization_id == org_id, ProductVariant.id.in_(ids))} if ids else {}

        for i, clase in clasificar(g, c, carga.proposito, norm):
            f = activos[i]
            vid = c.variante_por_talla.get(norm[i].talla or "") if c else None
            sku = sku_variante.get(vid) or sku_para(g, norm[i].talla, reglas, prefijo)
            if clase == "NUEVO" and c is not None and _ocupado(db, org_id, sku, tomados):
                sku = _sku_libre(db, org_id, sku, tomados)
            f.clase = clase
            f.grupo = g.llave
            f.product_id = c.product_id if c else None
            f.variant_id = vid
            f.sku = sku
        # Los SKU de este grupo quedan tomados para los grupos que siguen.
        tomados |= {(activos[i].sku or "").lower() for i in g.renglones if activos[i].sku}
    db.flush()

    ya_cargados = marcar_ya_cargado(db, org_id, carga, activos, reglas.ventana_ya_cargado_dias,
                                    branch_id=carga.sucursal_destino_id or reglas.sucursal_recibe)
    nuevas = generar_dudas(db, org_id, carga, activos, grupos, coincidencias, reglas,
                           ya_cargados={cid: [f.orden for f in fs] for cid, fs in ya_cargados.items()})
    por_orden = {f.orden: f for f in activos}
    if carga.proposito == "entrada":
        # En entrada no se crean departamentos: si la respuesta nombró uno que no
        # existe (o dejó de existir), la pregunta vuelve a abrirse.
        reabrir |= {d.clave for d in nuevas if d.tipo == "departamento"}
    _conciliar_dudas(db, carga, [d for d in nuevas if not _contestada_por_el_usuario(d, por_orden)],
                     reabrir)


# ── renglones del Excel ──────────────────────────────────────────────────

def roles_completos(lectura: Optional[dict]) -> bool:
    """True si toda columna de dinero de toda tabla ya tiene rol (costo, precio o ignorar)."""
    tablas = (lectura or {}).get("tablas") or []
    if not tablas:
        return False
    for t in tablas:
        roles = {str(k) for k in (t.get("rol_dinero") or {})}
        if any(str(c) not in roles for c in (t.get("mapa") or {}).get("columnas_dinero") or []):
            return False
    return True


def rearmar_renglones_excel(db: Session, carga: CargaMercancia) -> None:
    """Arma los renglones de un Excel/CSV desde el archivo guardado y el mapa de
    `carga.lectura` cuando ya se sabe qué es cada columna de dinero.

    Se actualizan en su lugar por `orden` (las correcciones del usuario en
    `normalizado` sobreviven a un cambio de rol). Mientras falte un rol, o si la
    carga no tiene archivo guardado, no hace nada."""
    if not roles_completos(carga.lectura):
        return
    archivo = (db.query(CargaArchivo)
               .filter(CargaArchivo.organization_id == carga.organization_id,
                       CargaArchivo.carga_id == carga.id)
               .first())
    if archivo is None:  # carga armada sin archivo (solo en pruebas): sus renglones quedan igual
        return
    por_pestana = {t.pestana: t for t in leer_tablas(archivo.contenido, carga.archivo_tipo or "")}
    crudos: list[RenglonCrudo] = []
    for t in carga.lectura["tablas"]:
        tabla = por_pestana.get(t.get("pestana"))
        if tabla is None:
            continue
        mapa = MapaColumnas.model_validate(t.get("mapa") or {})
        roles = {int(k): v for k, v in (t.get("rol_dinero") or {}).items()}
        crudos += renglones_desde_excel(tabla, mapa, roles)

    existentes = {f.orden: f for f in _renglones(db, carga)}
    for orden, c in enumerate(crudos, 1):
        datos = c.model_dump(mode="json")
        f = existentes.pop(orden, None)
        if f is None:
            db.add(CargaRenglon(organization_id=carga.organization_id, carga_id=carga.id,
                                orden=orden, crudo=datos, cantidad=c.cantidad))
        else:
            f.crudo = datos
    for f in existentes.values():
        db.delete(f)
    db.flush()


# ── foto, resumen y deshacer ──────────────────────────────────────────────

_CAMPOS_DUDA = ("numero", "tipo", "texto", "opciones", "recomendada", "renglones", "clave",
                "contexto", "estado", "respuesta", "resuelta_por")


def _texto_dec(v) -> Optional[str]:
    return None if v is None else str(v)


def _foto(db: Session, carga: CargaMercancia) -> dict:
    """Todo lo que una operación puede cambiar, en JSON, para restaurarlo exacto."""
    db.flush()
    return {
        "renglones": {
            f.id: {"orden": f.orden, "crudo": copy.deepcopy(f.crudo),
                   "normalizado": copy.deepcopy(f.normalizado), "clase": f.clase,
                   "grupo": f.grupo, "product_id": f.product_id, "variant_id": f.variant_id,
                   "sku": f.sku, "cantidad": _texto_dec(f.cantidad),
                   "precio": _texto_dec(f.precio), "costo": _texto_dec(f.costo)}
            for f in _renglones(db, carga)
        },
        "dudas": {d.id: {k: copy.deepcopy(getattr(d, k)) for k in _CAMPOS_DUDA}
                  for d in _dudas(db, carga)},
        "monedas": copy.deepcopy(carga.monedas),
        "lectura": copy.deepcopy(carga.lectura),
    }


_VISIBLES = ("marca", "tipo", "material", "color", "talla", "precio", "genero",
             "departamento", "cantidad")


def _vista(r: dict) -> dict:
    n = r.get("normalizado") or {}
    v = {k: n.get(k) for k in _VISIBLES}
    v["costo"] = n.get("costo_mxn")
    v["accion_precio"] = (n.get(_USUARIO) or {}).get("accion_precio")
    v["clase"] = r.get("clase")
    v["product_id"] = r.get("product_id")
    return v


def _uno_o_lista(valores: list):
    unicos = list(dict.fromkeys(valores))
    return unicos[0] if len(unicos) == 1 else unicos


def titulo_grupo(normalizado: dict) -> str:
    """Cómo se le nombra un grupo al usuario: "Marca Uno · Playera", más el
    material cuando separa el grupo (está en su llave). Nunca la llave técnica."""
    n = normalizado or {}
    partes = [p for p in (n.get("marca"), n.get("tipo")) if p]
    texto = " · ".join(partes) or (n.get("descripcion_original") or "Sin descripción")
    llave = (n.get("llave_grupo") or "").split("|")
    if len(llave) >= 3 and llave[2] and n.get("material"):
        texto += f" {n['material'].strip().lower()}"
    return texto


def _resumen(antes: dict, despues: dict) -> dict:
    """Lo que la pantalla enseña: por grupo afectado, campo: antes -> después."""
    por_grupo: dict[str, dict] = {}
    for rid, d in despues["renglones"].items():
        a = antes["renglones"].get(rid)
        if a is None:
            continue
        va, vd = _vista(a), _vista(d)
        cambios = {k: (va[k], vd[k]) for k in vd if va[k] != vd[k]}
        if not cambios:
            continue
        # El título humano se guarda ya: la llave del grupo (lleva el precio)
        # puede dejar de existir después de deshacer o de otro cambio.
        g = por_grupo.setdefault(d["grupo"] or a["grupo"] or "", {
            "renglones": [], "cambios": {},
            "titulo": titulo_grupo(d.get("normalizado") or a.get("normalizado") or {})})
        g["renglones"].append(d["orden"])
        for k, par in cambios.items():
            g["cambios"].setdefault(k, []).append(par)
    grupos = [
        {"grupo": llave, "titulo": g["titulo"], "renglones": sorted(g["renglones"]),
         "cambios": {k: {"antes": _uno_o_lista([p[0] for p in pares]),
                         "despues": _uno_o_lista([p[1] for p in pares])}
                     for k, pares in g["cambios"].items()}}
        for llave, g in por_grupo.items()
    ]
    estados_antes = {d["clave"]: d for d in antes["dudas"].values()}
    resueltas, nuevas = [], []
    for d in despues["dudas"].values():
        previa = estados_antes.get(d["clave"])
        if previa is None:
            nuevas.append(d["numero"])
        elif previa["estado"] == "abierta" and d["estado"] == "resuelta":
            resueltas.append(d["numero"])
    salida: dict[str, Any] = {"grupos": grupos, "dudas_resueltas": sorted(resueltas),
                              "dudas_nuevas": sorted(nuevas)}
    if antes["monedas"] != despues["monedas"]:
        salida["monedas"] = {"antes": antes["monedas"], "despues": despues["monedas"]}
    if antes["lectura"] != despues["lectura"]:
        salida["columnas"] = [
            {"tabla": i, "rol_dinero": (t or {}).get("rol_dinero") or {}}
            for i, t in enumerate((despues["lectura"] or {}).get("tablas") or [])
        ]
    return salida


def _exigir_plan(carga: CargaMercancia) -> None:
    if carga.estado != "plan":
        raise HTTPException(status_code=409, detail=_NO_EN_PLAN)


def _bloquear(db: Session, carga: CargaMercancia) -> CargaMercancia:
    """Relee la carga con candado de fila para que dos envíos (doble clic, dos
    pestañas) no rearmen el plan a la vez. El candado solo es real en Postgres;
    en SQLite (pruebas) `with_for_update()` no hace nada y la numeración la
    respaldan las restricciones únicas de las tablas."""
    db.flush()  # lo pendiente en memoria no se pierde al releer
    fila = (db.query(CargaMercancia)
            .filter(CargaMercancia.id == carga.id,
                    CargaMercancia.organization_id == carga.organization_id)
            .with_for_update().populate_existing().one())
    _exigir_plan(fila)
    return fila


def aplicar_operaciones(
    db: Session, carga: CargaMercancia, user, operaciones: list[dict], texto: Optional[str],
) -> tuple[Optional[CargaCambio], list[str]]:
    """Aplica las operaciones válidas, recalcula y deja el cambio en la bitácora.

    Devuelve (cambio, rechazos). Si todas se rechazan no se guarda nada: (None, rechazos)."""
    carga = _bloquear(db, carga)
    antes = _foto(db, carga)
    ctx = _Contexto(db, carga, getattr(user, "id", None))
    aplicadas: list[dict] = []
    rechazos: list[str] = []
    for i, crudo in enumerate(operaciones, 1):
        try:
            op = _parsear(crudo)
            paso = _preparar(ctx, op)
        except _Rechazo as e:
            rechazos.append(f"Operación {i}: {e}")
            continue
        paso()
        aplicadas.append(op.model_dump(mode="json", exclude_none=True))
    if not aplicadas:
        return None, rechazos

    if carga.lectura != antes["lectura"]:
        # Cambió el rol de una columna de dinero del Excel: los renglones se
        # (re)arman aquí, dentro del mismo cambio, para que deshacer los quite.
        rearmar_renglones_excel(db, carga)
    recalcular_plan(db, carga)
    despues = _foto(db, carga)
    previos = (db.query(CargaCambio.secuencia)
               .filter(CargaCambio.organization_id == carga.organization_id,
                       CargaCambio.carga_id == carga.id).all())
    cambio = CargaCambio(
        organization_id=carga.organization_id, carga_id=carga.id, user_id=ctx.user_id,
        secuencia=max((s for (s,) in previos), default=0) + 1,
        texto=texto, operaciones=aplicadas, antes=antes,
        despues={"resumen": _resumen(antes, despues)},
    )
    db.add(cambio)
    db.flush()
    return cambio, rechazos


def deshacer_cambio(db: Session, carga: CargaMercancia, cambio_id: str) -> None:
    """Restaura la foto `antes` del último cambio no deshecho y lo marca deshecho."""
    carga = _bloquear(db, carga)
    cambios = (db.query(CargaCambio)
               .filter(CargaCambio.organization_id == carga.organization_id,
                       CargaCambio.carga_id == carga.id).all())
    cambio = next((c for c in cambios if c.id == cambio_id), None)
    if cambio is None:
        raise HTTPException(status_code=404, detail="Ese cambio no existe en esta carga.")
    if cambio.deshecho:
        raise HTTPException(status_code=409, detail="Ese cambio ya se deshizo.")
    ultimo = max((c for c in cambios if not c.deshecho), key=lambda c: c.secuencia)
    if ultimo.id != cambio.id:
        raise HTTPException(status_code=409, detail="Solo se puede deshacer el último cambio.")

    foto = cambio.antes or {}
    renglones_foto = foto.get("renglones") or {}
    vivos = _renglones(db, carga)
    for f in vivos:
        if f.id not in renglones_foto:  # lo creó este cambio (renglones del Excel)
            db.delete(f)
    db.flush()
    presentes = {f.id for f in vivos}
    for rid, r in renglones_foto.items():
        if rid not in presentes and "crudo" in r:  # lo borró este cambio
            db.add(CargaRenglon(id=rid, organization_id=carga.organization_id, carga_id=carga.id,
                                orden=r["orden"], crudo=copy.deepcopy(r["crudo"]), cantidad=Decimal(0)))
    db.flush()
    for f in _renglones(db, carga):
        r = renglones_foto.get(f.id)
        if r is None:
            continue
        if "crudo" in r:
            f.crudo = copy.deepcopy(r["crudo"])
        f.normalizado = copy.deepcopy(r["normalizado"])
        for k in ("clase", "grupo", "product_id", "variant_id", "sku"):
            setattr(f, k, r[k])
        f.cantidad = Decimal(r["cantidad"]) if r["cantidad"] is not None else Decimal(0)
        f.precio = None if r["precio"] is None else Decimal(r["precio"])
        f.costo = None if r["costo"] is None else Decimal(r["costo"])
    dudas_foto = foto.get("dudas") or {}
    for d in _dudas(db, carga):
        previa = dudas_foto.get(d.id)
        if previa is None:  # la creó este cambio
            db.delete(d)
            continue
        for k in _CAMPOS_DUDA:
            setattr(d, k, copy.deepcopy(previa[k]))
    carga.monedas = copy.deepcopy(foto.get("monedas"))
    carga.lectura = copy.deepcopy(foto.get("lectura"))
    cambio.deshecho = True
    db.flush()
