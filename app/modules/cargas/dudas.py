"""Dudas por regla: lo que el dueño contesta antes de que se escriba nada.

`generar_dudas` mira el estado actual del plan y devuelve las dudas que ese
estado implica; no consulta dudas guardadas (suprimir las ya contestadas es
trabajo de quien recalcula, por `clave`). Una duda desaparece sola cuando
desaparece su causa. Solo lee la base; nunca cambia renglones ni precios.

Los renglones son los `CargaRenglon` del plan; `Grupo.renglones` son índices
en esa lista y las dudas/operaciones hablan de renglones por `orden`.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.cargas.cruce import Coincidencia
from app.modules.cargas.lectura_excel import normalizar_numero
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.normalizar import _llave, _material_efectivo
from app.modules.cargas.reglas import ReglasCarga
from app.modules.cargas.tipos import Grupo, RenglonNormalizado
from app.modules.products.models import Brand, Department, Product, ProductVariant

TIPOS_DUDA = (
    "columnas_dinero", "tipo_cambio", "marca_nueva", "marca_parecida", "casi_igual",
    "precio_faltante", "precio_fuera_familia", "precio_distinto_existente",
    "departamento", "genero", "sin_costo", "extraccion",
)

# Tipos que también aceptan una respuesta escrita (además de sus opciones).
_CON_TEXTO = {
    "tipo_cambio", "marca_nueva", "marca_parecida", "precio_faltante",
    "precio_fuera_familia", "departamento", "sin_costo",
}
_INACTIVAS = ("YA_CARGADO", "IGNORADO")
_SOLO_DIGITOS = re.compile(r"\d+(\.\d+)?")
_GENEROS = (("HOMBRE", "Hombre"), ("MUJER", "Mujer"), ("UNISEX", "Unisex"), ("NINO", "Niño"))


class DudaNueva(BaseModel):
    tipo: str
    texto: str
    opciones: list[dict] = Field(default_factory=list)  # [{"clave","etiqueta"}]
    recomendada: Optional[str] = None  # None: sin base para recomendar o se contesta con texto
    renglones: list[int] = Field(default_factory=list)  # `orden` de los renglones afectados
    clave: str
    contexto: dict[str, Any] = Field(default_factory=dict)


# ── utilidades ────────────────────────────────────────────────────────────

def levenshtein(a: str, b: str) -> int:
    """Distancia de edición clásica (inserción, borrado, sustitución)."""
    if len(a) < len(b):
        a, b = b, a
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (ca != cb)))
        previa = actual
    return previa[-1]


def _prefijo_comun(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _parecido(a: str, b: str) -> Optional[tuple[int, int]]:
    """(distancia, -prefijo) si `a` y `b` se parecen; None si no."""
    la, lb = _llave(a), _llave(b)
    dist = levenshtein(la, lb)
    pref = _prefijo_comun(la, lb)
    if dist <= 2 or pref >= 5:
        return (dist, -pref)
    return None


def _pesos(valor) -> str:
    return f"${Decimal(valor):,.2f}"


def _lista(cosas: list[str]) -> str:
    if len(cosas) <= 1:
        return "".join(cosas)
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


def _que(n: RenglonNormalizado, tallas: list[str]) -> str:
    """Cómo se le nombra el producto al dueño: "Playera Marca Uno talla M y G"."""
    partes = [n.tipo or n.descripcion_original]
    if n.marca:
        partes.append(n.marca)
    if n.material:
        partes.append(f"de {n.material}")
    texto = " ".join(partes)
    tallas = [t for t in tallas if t]
    if tallas:
        texto += (" talla " if len(tallas) == 1 else " tallas ") + _lista(tallas)
    return texto


def _monto(texto: Optional[str]) -> str:
    """Texto del usuario → monto en texto decimal ("$1,234.50" → "1234.50",
    "1.234,50" → "1234.50", "18,40" → "18.40"). ValueError si no es un número
    positivo escrito con dígitos (sin exponentes ni infinitos)."""
    limpio = normalizar_numero(texto or "")
    if not _SOLO_DIGITOS.fullmatch(limpio):
        raise ValueError(f'"{texto}" no es una cantidad')
    valor = Decimal(limpio)
    if valor <= 0:
        raise ValueError(f'"{texto}" no es una cantidad')
    return str(valor)


# ── generación ────────────────────────────────────────────────────────────

class _Plan:
    """Vista de trabajo: renglones normalizados y cuáles cuentan."""

    def __init__(self, renglones: list[CargaRenglon]):
        self.filas = renglones
        self.norm = [RenglonNormalizado.model_validate(r.normalizado or {}) for r in renglones]

    def activo(self, i: int) -> bool:
        return self.filas[i].clase not in _INACTIVAS

    def orden(self, i: int) -> int:
        return self.filas[i].orden

    def activos(self, idxs=None) -> list[int]:
        idxs = range(len(self.filas)) if idxs is None else idxs
        return [i for i in idxs if self.activo(i)]

    def tallas(self, idxs: list[int]) -> list[str]:
        vistas: list[str] = []
        for i in idxs:
            t = self.norm[i].talla or ""
            if t and t not in vistas:
                vistas.append(t)
        return vistas


def _columnas_dinero(carga: CargaMercancia) -> list[DudaNueva]:
    lectura = carga.lectura or {}
    recomendada = "precio" if carga.proposito == "migracion" else "costo"
    dudas: list[DudaNueva] = []
    for ti, tabla in enumerate(lectura.get("tablas") or []):
        roles = {str(k) for k in (tabla.get("rol_dinero") or {})}
        encabezados = tabla.get("encabezados") or []
        for col in (tabla.get("mapa") or {}).get("columnas_dinero") or []:
            if str(col) in roles:
                continue
            enc = str(encabezados[col]) if col < len(encabezados) else f"columna {col + 1}"
            dudas.append(DudaNueva(
                tipo="columnas_dinero",
                texto=(f'La columna "{enc}" de la pestaña "{tabla.get("pestana", "")}" trae '
                       "cantidades de dinero. ¿Es lo que te costó, el precio al que vendes, "
                       "o no se usa?"),
                opciones=[{"clave": "costo", "etiqueta": "Es lo que me costó"},
                          {"clave": "precio", "etiqueta": "Es el precio al que vendo"},
                          {"clave": "ignorar", "etiqueta": "No se usa"}],
                recomendada=recomendada,
                clave=f"columnas_dinero|{ti}|{col}",
                contexto={"tabla": ti, "columna": col, "encabezado": enc},
            ))
    return dudas


def _tipo_cambio(carga: CargaMercancia, plan: _Plan) -> list[DudaNueva]:
    conocidas = {k.strip().upper(): v for k, v in (carga.monedas or {}).items()}
    por_moneda: dict[str, list[int]] = {m: [] for m, v in conocidas.items() if v is None and m != "MXN"}
    for i in plan.activos():
        n = plan.norm[i]
        moneda = (n.moneda or "MXN").strip().upper()
        if moneda == "MXN" or n.costo_unitario is None:
            continue
        if conocidas.get(moneda) is None:
            por_moneda.setdefault(moneda, []).append(i)
    return [
        DudaNueva(
            tipo="tipo_cambio",
            texto=(f"Hay costos en {m}. ¿A cuántos pesos está el {m}? "
                   "Escríbelo, por ejemplo 18.40."),
            renglones=[plan.orden(i) for i in idxs],
            clave=f"tipo_cambio|{m}",
            contexto={"moneda": m},
        )
        for m, idxs in sorted(por_moneda.items())
    ]


def _marcas(db: Session, org_id: int, plan: _Plan) -> list[DudaNueva]:
    existentes = (db.query(Brand)
                  .filter(Brand.organization_id == org_id, Brand.deleted_at == None)  # noqa: E711
                  .all())
    nombres = {_llave(b.name) for b in existentes}
    por_marca: dict[str, list[int]] = {}
    for i in plan.activos():
        marca = plan.norm[i].marca
        if marca and _llave(marca) not in nombres:
            por_marca.setdefault(_llave(marca), []).append(i)

    dudas: list[DudaNueva] = []
    for llave, idxs in por_marca.items():
        marca = plan.norm[idxs[0]].marca
        orden = [plan.orden(i) for i in idxs]
        parecidas = sorted(
            ((p, b) for b in existentes if (p := _parecido(marca, b.name)) is not None),
            key=lambda x: (x[0], _llave(x[1].name)),
        )
        crear = {"clave": "crear", "etiqueta": f'Crear la marca "{marca}"'}
        if parecidas:
            # La etiqueta es el nombre exacto de la marca: de ahí sale el valor al contestar.
            opciones = [{"clave": f"usar:{b.id}", "etiqueta": b.name} for _, b in parecidas]
            dudas.append(DudaNueva(
                tipo="marca_parecida",
                texto=(f'La marca "{marca}" no está en tu catálogo, pero se parece a '
                       f'{_lista([chr(34) + b.name + chr(34) for _, b in parecidas])}. '
                       "¿Es la misma o la creo como marca nueva?"),
                opciones=opciones + [crear],
                recomendada=opciones[0]["clave"],
                renglones=orden, clave=f"marca_parecida|{llave}", contexto={"marca": marca},
            ))
        else:
            dudas.append(DudaNueva(
                tipo="marca_nueva",
                texto=(f'La marca "{marca}" no está en tu catálogo. ¿La creo como marca nueva? '
                       "Si está mal escrita, escribe el nombre correcto."),
                opciones=[crear], recomendada="crear",
                renglones=orden, clave=f"marca_nueva|{llave}", contexto={"marca": marca},
            ))
    return dudas


def _casi_igual(db: Session, org_id: int, plan: _Plan, grupos: list[Grupo],
                coincidencias: dict, reglas: ReglasCarga) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for g in grupos:
        idxs = plan.activos(g.renglones)
        if not idxs or coincidencias.get(g.llave) is not None or not g.marca or not g.tipo:
            continue
        marca = next((b for b in db.query(Brand).filter(
            Brand.organization_id == org_id, Brand.deleted_at == None).all()  # noqa: E711
            if _llave(b.name) == _llave(g.marca)), None)
        if marca is None:
            continue
        candidatos = sorted(
            (p for p in db.query(Product).filter(
                Product.organization_id == org_id, Product.brand_id == marca.id,
                Product.deleted_at == None).all()  # noqa: E711
             if _llave(p.name).startswith(_llave(g.tipo))),
            key=lambda p: (_llave(p.name), p.id),
        )
        if not candidatos:
            continue
        # "Solo difiere el material normal": mismo material para efectos de SKU
        # (ninguno de los dos es un material aparte, o es el mismo) y género compatible.
        mat_g = _material_efectivo(g.material, reglas)
        recomendada = "nuevo"
        for p in candidatos:
            mismo_genero = not g.genero or not p.gender or p.gender == g.genero
            if _material_efectivo(p.material, reglas) == mat_g and mismo_genero:
                recomendada = f"usar:{p.id}"
                break
        n = plan.norm[idxs[0]]
        dudas.append(DudaNueva(
            tipo="casi_igual",
            texto=(f"{_que(n, plan.tallas(idxs))} se parece a lo que ya tienes: "
                   f"{_lista([chr(34) + p.name + chr(34) for p in candidatos])}. "
                   "¿Es el mismo producto o es uno nuevo?"),
            opciones=[{"clave": f"usar:{p.id}", "etiqueta": f'Es "{p.name}"'} for p in candidatos]
            + [{"clave": "nuevo", "etiqueta": "Es un producto nuevo"}],
            recomendada=recomendada,
            renglones=[plan.orden(i) for i in idxs],
            clave=f"casi_igual|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _precio_faltante(plan: _Plan, grupos: list[Grupo]) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for g in grupos:
        idxs = [i for i in plan.activos(g.renglones) if plan.norm[i].precio is None]
        if not idxs:
            continue
        dudas.append(DudaNueva(
            tipo="precio_faltante",
            texto=(f"Falta el precio de venta de {_que(plan.norm[idxs[0]], plan.tallas(idxs))}. "
                   "¿A cuánto lo vas a vender?"),
            renglones=[plan.orden(i) for i in idxs],
            clave=f"precio_faltante|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _precios_de_familia(g: Grupo, reglas: ReglasCarga) -> list[Decimal]:
    """La regla de la marca gana sobre la de "cualquier marca"."""
    del_tipo = [r for r in reglas.precios_familia if _llave(r.tipo) == _llave(g.tipo) and r.precios]
    propia = next((r for r in del_tipo if r.marca and _llave(r.marca) == _llave(g.marca)), None)
    general = next((r for r in del_tipo if not r.marca), None)
    regla = propia or general
    return [Decimal(p) for p in regla.precios] if regla else []


def _precio_fuera_familia(plan: _Plan, grupos: list[Grupo], reglas: ReglasCarga) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for g in grupos:
        if not g.tipo:
            continue
        familia = _precios_de_familia(g, reglas)
        if not familia:
            continue
        idxs = [i for i in plan.activos(g.renglones)
                if plan.norm[i].precio is not None and Decimal(plan.norm[i].precio) not in familia]
        if not idxs:
            continue
        precios = sorted({Decimal(plan.norm[i].precio) for i in idxs})
        dudas.append(DudaNueva(
            tipo="precio_fuera_familia",
            texto=(f"{_que(plan.norm[idxs[0]], plan.tallas(idxs))} viene a "
                   f"{_lista([_pesos(p) for p in precios])}, y tus precios de {g.tipo} suelen ser "
                   f"{_lista([_pesos(p) for p in sorted(familia)])}. "
                   "¿Lo dejo así o escribes el precio que va?"),
            opciones=[{"clave": "mantener", "etiqueta": f"Dejar {_lista([_pesos(p) for p in precios])}"}],
            recomendada="mantener",
            renglones=[plan.orden(i) for i in idxs],
            clave=f"precio_fuera_familia|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _precio_distinto(db: Session, org_id: int, plan: _Plan, grupos: list[Grupo],
                     coincidencias: dict) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for g in grupos:
        c: Optional[Coincidencia] = coincidencias.get(g.llave)
        idxs = plan.activos(g.renglones)
        if c is None or c.exacta or not idxs:
            continue
        ids = list(c.variante_por_talla.values())
        precios_hoy = {
            v.id: v.price for v in db.query(ProductVariant).filter(
                ProductVariant.organization_id == org_id, ProductVariant.id.in_(ids)).all()
        } if ids else {}
        distintos = []  # (índice, precio de hoy, precio nuevo)
        for i in idxs:
            n = plan.norm[i]
            vid = c.variante_por_talla.get(n.talla or "")
            if n.precio is None or vid is None:
                continue
            hoy = precios_hoy.get(vid)
            if hoy is None or Decimal(hoy) != Decimal(n.precio):
                distintos.append((i, hoy, Decimal(n.precio)))
        if not distintos:
            continue
        hoy = sorted({Decimal(h) for _, h, _ in distintos if h is not None})
        if not hoy and c.precio_actual is not None:
            hoy = [Decimal(c.precio_actual)]
        nuevo = sorted({p for _, _, p in distintos})
        afectados = [i for i, _, _ in distintos]
        txt_hoy = _lista([_pesos(p) for p in hoy]) if hoy else "sin precio"
        en_catalogo = f"a {txt_hoy}" if hoy else "sin precio"
        txt_nuevo = _lista([_pesos(p) for p in nuevo])
        dudas.append(DudaNueva(
            tipo="precio_distinto_existente",
            texto=(f"{_que(plan.norm[afectados[0]], plan.tallas(afectados))} ya está en tu "
                   f"catálogo {en_catalogo}; aquí viene a {txt_nuevo}. ¿Qué hago con el precio?"),
            opciones=[
                {"clave": "mantener", "etiqueta": f"Dejar el precio de hoy ({txt_hoy})"},
                {"clave": "actualizar", "etiqueta": f"Cambiarlo a {txt_nuevo}"},
                {"clave": "aparte", "etiqueta": f"Darlo de alta aparte a {txt_nuevo}"},
            ],
            recomendada="mantener",
            renglones=[plan.orden(i) for i in afectados],
            clave=f"precio_distinto_existente|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _departamento(db: Session, org_id: int, carga: CargaMercancia, plan: _Plan) -> list[DudaNueva]:
    """Una duda por tipo de prenda sin departamento (no una por producto)."""
    por_tipo: dict[str, list[int]] = {}
    for i in plan.activos():
        if not plan.norm[i].departamento:
            por_tipo.setdefault(_llave(plan.norm[i].tipo), []).append(i)
    if not por_tipo:
        return []
    deptos = sorted(
        db.query(Department).filter(Department.organization_id == org_id,
                                    Department.deleted_at == None).all(),  # noqa: E711
        key=lambda d: (_llave(d.name), d.id),
    )
    dudas: list[DudaNueva] = []
    for llave, idxs in por_tipo.items():
        tipo = plan.norm[idxs[0]].tipo
        # La etiqueta es el nombre exacto del departamento: de ahí sale el valor.
        opciones = [{"clave": f"depto:{d.id}", "etiqueta": d.name} for d in deptos]
        if carga.proposito == "migracion" and tipo:
            # Sin tipo de prenda no hay nombre para el departamento nuevo: se contesta con texto.
            opciones.append({"clave": "crear", "etiqueta": f'Crear el departamento "{tipo}"'})
        parecidos = sorted(((p, d) for d in deptos if tipo and (p := _parecido(tipo, d.name))),
                           key=lambda x: x[0])
        if parecidos:
            recomendada = f"depto:{parecidos[0][1].id}"
        elif carga.proposito == "migracion" and tipo:
            recomendada = "crear"
        else:
            recomendada = None
        cual = f'"{tipo}"' if tipo else "los productos sin tipo de prenda"
        dudas.append(DudaNueva(
            tipo="departamento",
            texto=f"No sé en qué departamento va {cual}. ¿Dónde lo pongo?",
            opciones=opciones, recomendada=recomendada,
            renglones=[plan.orden(i) for i in idxs],
            clave=f"departamento|{llave}", contexto={"tipo": tipo},
        ))
    return dudas


def _genero(plan: _Plan, grupos: list[Grupo]) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for g in grupos:
        idxs = [i for i in plan.activos(g.renglones) if not plan.norm[i].genero]
        if not idxs:
            continue
        dudas.append(DudaNueva(
            tipo="genero",
            texto=f"¿{_que(plan.norm[idxs[0]], plan.tallas(idxs))} es de hombre, de mujer, unisex o de niño?",
            opciones=[{"clave": c, "etiqueta": e} for c, e in _GENEROS],
            renglones=[plan.orden(i) for i in idxs],
            clave=f"genero|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _sin_costo(carga: CargaMercancia, plan: _Plan, grupos: list[Grupo],
               reglas: ReglasCarga) -> list[DudaNueva]:
    if reglas.costo_si_falta != "preguntar":
        return []
    dudas: list[DudaNueva] = []
    for g in grupos:
        # Si viene costo en otra moneda y falta el tipo de cambio, eso lo pregunta `tipo_cambio`.
        idxs = [i for i in plan.activos(g.renglones)
                if plan.norm[i].costo_mxn is None and plan.norm[i].costo_unitario is None]
        if not idxs:
            continue
        dudas.append(DudaNueva(
            tipo="sin_costo",
            texto=(f"Falta el costo de {_que(plan.norm[idxs[0]], plan.tallas(idxs))}. "
                   "¿Cuánto te costó cada pieza?"),
            renglones=[plan.orden(i) for i in idxs],
            clave=f"sin_costo|{g.llave}", contexto={"grupo": g.llave},
        ))
    return dudas


def _extraccion(plan: _Plan) -> list[DudaNueva]:
    dudas: list[DudaNueva] = []
    for i in plan.activos():
        n = plan.norm[i]
        if not n.duda:
            continue
        orden = plan.orden(i)
        dudas.append(DudaNueva(
            tipo="extraccion",
            texto=(f'No estoy seguro de lo que leí en {n.origen} ("{n.descripcion_original}"): '
                   f"{n.duda}. ¿Está bien así?"),
            opciones=[{"clave": "confirmar", "etiqueta": "Sí, está bien"},
                      {"clave": "ignorar", "etiqueta": "No lo cargues"}],
            recomendada="confirmar",
            renglones=[orden], clave=f"extraccion|{orden}", contexto={"renglon": orden},
        ))
    return dudas


def generar_dudas(
    db: Session, org_id: int, carga: CargaMercancia, renglones: list[CargaRenglon],
    grupos: list[Grupo], coincidencias: dict[str, Optional[Coincidencia]], reglas: ReglasCarga,
) -> list[DudaNueva]:
    """Dudas que implica el plan actual, ordenadas por tipo según `TIPOS_DUDA`."""
    plan = _Plan(renglones)
    columnas = _columnas_dinero(carga)
    dudas = columnas + _tipo_cambio(carga, plan) + _marcas(db, org_id, plan)
    dudas += _casi_igual(db, org_id, plan, grupos, coincidencias, reglas)
    if not columnas:
        # Mientras no se sepa qué columna es costo y cuál precio, preguntar por
        # precios o costos faltantes sería prematuro.
        dudas += _precio_faltante(plan, grupos)
    dudas += _precio_fuera_familia(plan, grupos, reglas)
    dudas += _precio_distinto(db, org_id, plan, grupos, coincidencias)
    dudas += _departamento(db, org_id, carga, plan)
    dudas += _genero(plan, grupos)
    if not columnas:
        dudas += _sin_costo(carga, plan, grupos, reglas)
    dudas += _extraccion(plan)
    return sorted(dudas, key=lambda d: TIPOS_DUDA.index(d.tipo))


# ── respuestas → operaciones ──────────────────────────────────────────────

def _fijar(duda: CargaDuda, campo: str, valor: str) -> list[dict]:
    return [{"op": "fijar_campo", "renglones": list(duda.renglones or []),
             "campo": campo, "valor": valor}]


def opcion_a_operaciones(duda: CargaDuda, clave: str, valor_texto: Optional[str]) -> list[dict]:
    """Traduce una opción (o un texto) de la duda a operaciones sobre el plan.

    Lista vacía = la respuesta no cambia el plan (p. ej. "mantener"). ValueError
    con un mensaje legible si la opción no es de la duda o el texto no sirve."""
    tipo = duda.tipo
    ctx = duda.contexto or {}
    opciones = {o["clave"]: o for o in (duda.opciones or [])}
    clave = (clave or "").strip()

    if clave not in opciones:
        texto = (valor_texto or "").strip()
        if clave or not texto or tipo not in _CON_TEXTO:
            raise ValueError(f'"{clave or texto}" no es una respuesta válida para esta pregunta')
        if tipo == "tipo_cambio":
            return [{"op": "tipo_cambio", "moneda": ctx.get("moneda"), "valor": _monto(texto)}]
        if tipo in ("marca_nueva", "marca_parecida"):
            return _fijar(duda, "marca", texto)
        if tipo in ("precio_faltante", "precio_fuera_familia"):
            return _fijar(duda, "precio", _monto(texto))
        if tipo == "sin_costo":
            return _fijar(duda, "costo", _monto(texto))
        return _fijar(duda, "departamento", texto)  # departamento

    if tipo == "columnas_dinero":
        return [{"op": "rol_columna", "tabla": ctx["tabla"], "columna": ctx["columna"], "rol": clave}]
    if tipo in ("marca_nueva", "marca_parecida"):
        if clave == "crear":
            return []  # la marca se crea al aplicar la carga
        return _fijar(duda, "marca", opciones[clave]["etiqueta"])
    if tipo == "casi_igual":
        if clave == "nuevo":
            return [{"op": "nuevo_producto", "grupo": ctx["grupo"]}]
        return [{"op": "usar_existente", "grupo": ctx["grupo"], "product_id": clave.split(":", 1)[1]}]
    if tipo == "precio_fuera_familia":
        return []  # mantener
    if tipo == "precio_distinto_existente":
        return [{"op": "fijar_campo", "grupo": ctx["grupo"], "campo": "accion_precio", "valor": clave}]
    if tipo == "departamento":
        if clave == "crear":
            return _fijar(duda, "departamento", ctx.get("tipo") or "")
        return _fijar(duda, "departamento", opciones[clave]["etiqueta"])
    if tipo == "genero":
        return _fijar(duda, "genero", clave)
    if tipo == "extraccion":
        return [{"op": "ignorar", "renglones": list(duda.renglones or [])}] if clave == "ignorar" else []
    raise ValueError(f"No sé contestar dudas de tipo {tipo}")
