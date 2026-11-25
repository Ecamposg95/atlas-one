"""Lectura de Excel/CSV y mapeo de encabezados.

El modelo solo dice qué columna es cuál; cantidades y dinero salen de las
celdas (`celda_decimal`), nunca de la respuesta del modelo.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.modules.ai.proveedores import Proveedor
from app.modules.cargas.tipos import RenglonCrudo, TablaCruda
from app.modules.products.services.comun import celda_decimal, celda_vacia

MAX_MUESTRA = 20

# Campos de RenglonCrudo que se mapean a una columna (el dinero va aparte).
CAMPOS_MAPEABLES = (
    "descripcion_original", "marca", "tipo", "material", "color", "talla",
    "cantidad", "observacion",
)


class MapaColumnas(BaseModel):
    campos: dict[str, Optional[int]]
    columnas_dinero: list[int] = Field(default_factory=list)
    texto_libre: list[int] = Field(default_factory=list)


ESQUEMA_MAPA: dict = {
    "type": "object",
    "properties": {
        "campos": {
            "type": "object",
            "properties": {c: {"type": ["integer", "null"]} for c in CAMPOS_MAPEABLES},
            "required": list(CAMPOS_MAPEABLES),
            "additionalProperties": False,
        },
        "columnas_dinero": {"type": "array", "items": {"type": "integer"}},
        "texto_libre": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["campos", "columnas_dinero", "texto_libre"],
    "additionalProperties": False,
}


def _texto(v: Any) -> str:
    return "" if celda_vacia(v) else str(v).strip()


def _fila_vacia(fila: list[Any]) -> bool:
    return all(_texto(c) == "" for c in fila)


def _tabla(pestana: str, filas_brutas: list[tuple[int, list[Any]]]) -> Optional[TablaCruda]:
    """La primera fila con algo es el encabezado; las vacías se omiten."""
    it = iter(f for f in filas_brutas if not _fila_vacia(f[1]))
    enc = next(it, None)
    if enc is None:
        return None
    filas, origen = [], []
    for n, fila in it:
        filas.append(fila)
        origen.append(n)
    return TablaCruda(pestana=pestana, encabezados=[_texto(c) for c in enc[1]],
                      filas=filas, filas_origen=origen)


def _leer_xlsx(contenido: bytes) -> list[TablaCruda]:
    from openpyxl import load_workbook

    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    tablas = []
    try:
        for hoja in libro.worksheets:
            filas = [(i, list(f)) for i, f in enumerate(hoja.iter_rows(values_only=True), start=1)]
            t = _tabla(hoja.title, filas)
            if t is not None:
                tablas.append(t)
    finally:
        libro.close()
    return tablas


def _leer_csv(contenido: bytes) -> list[TablaCruda]:
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    filas = [(i, list(f)) for i, f in enumerate(csv.reader(io.StringIO(texto), dialecto), start=1)]
    t = _tabla("CSV", filas)
    return [t] if t is not None else []


def leer_tablas(contenido: bytes, archivo_tipo: str) -> list[TablaCruda]:
    tipo = (archivo_tipo or "").lower().lstrip(".")
    if tipo in ("xlsx", "xlsm"):
        return _leer_xlsx(contenido)
    if tipo in ("csv", "txt"):
        return _leer_csv(contenido)
    raise ValueError(f"Tipo de archivo no soportado: {archivo_tipo}")


def mapear_columnas(tabla: TablaCruda, cliente: Proveedor,
                    instrucciones: str) -> tuple[MapaColumnas, int, int]:
    """Pide al modelo qué columna es cuál. Ve encabezados y ≤20 filas de muestra."""
    muestra = [[_texto(c) for c in f] for f in tabla.filas[:MAX_MUESTRA]]
    sistema = (
        "Eres un asistente que identifica columnas de una hoja de inventario de una tienda. "
        "Recibes los encabezados (con su índice, desde 0) y unas filas de muestra. "
        "Devuelve en `campos` el índice de la columna que corresponde a cada campo "
        "(null si no existe). `columnas_dinero` lista los índices de columnas con importes "
        "(costos o precios); no decidas cuál es cuál. `texto_libre` lista columnas de notas "
        "o descripciones adicionales. No inventes columnas ni leas valores: solo mapea."
    )
    if (instrucciones or "").strip():
        sistema += "\n\nContexto de la tienda, escrito por su dueño:\n" + instrucciones.strip()
    carga = {
        "pestana": tabla.pestana,
        "encabezados": [{"indice": i, "nombre": n} for i, n in enumerate(tabla.encabezados)],
        "filas_muestra": muestra,
    }
    resp = cliente.generar_json(
        sistema=sistema,
        contenido=[{"type": "text", "text": json.dumps(carga, ensure_ascii=False)}],
        esquema=ESQUEMA_MAPA,
    )
    n = len(tabla.encabezados)

    def valido(i: Any) -> Optional[int]:
        return i if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n else None

    datos = resp.datos or {}
    campos_modelo = datos.get("campos") or {}
    campos = {c: valido(campos_modelo.get(c)) for c in CAMPOS_MAPEABLES}
    dinero = [i for i in (valido(x) for x in datos.get("columnas_dinero") or []) if i is not None]
    libre = [i for i in (valido(x) for x in datos.get("texto_libre") or []) if i is not None]
    return (MapaColumnas(campos=campos, columnas_dinero=dinero, texto_libre=libre),
            resp.tokens_entrada, resp.tokens_salida)


def normalizar_numero(v: str) -> str:
    """Quita $ y espacios y decide qué separador es el decimal.

    "10,5" -> 10.5 · "1,500" -> 1500 · "1,500.50" -> 1500.50 · "1.500,50" -> 1500.50.
    """
    v = v.strip().replace("$", "").replace(" ", "")
    if "," in v and "." in v:
        if v.rfind(",") > v.rfind("."):  # 1.500,50: la coma es el decimal
            return v.replace(".", "").replace(",", ".")
        return v.replace(",", "")
    if "," in v:
        entera, _, dec = v.rpartition(",")
        if v.count(",") == 1 and 1 <= len(dec) <= 2:
            return f"{entera}.{dec}"
        return v.replace(",", "")
    return v


def _importe(v: Any) -> Optional[Decimal]:
    """Dinero de una celda; vacío o basura -> None (nunca 0)."""
    if celda_vacia(v):
        return None
    if isinstance(v, str):
        v = normalizar_numero(v)
        if v == "":
            return None
    d = celda_decimal(v, default=None)
    if d is None or not d.is_finite():
        return None
    return d


def renglones_desde_excel(
    tabla: TablaCruda, mapa: MapaColumnas,
    rol_dinero: dict[int, Literal["costo", "precio", "ignorar"]],
) -> list[RenglonCrudo]:
    def celda(fila: list[Any], idx: Optional[int]) -> Any:
        return fila[idx] if idx is not None and 0 <= idx < len(fila) else None

    def txt(fila: list[Any], campo: str) -> Optional[str]:
        t = _texto(celda(fila, mapa.campos.get(campo)))
        return t or None

    renglones = []
    for pos, fila in enumerate(tabla.filas):
        n_fila = tabla.filas_origen[pos] if pos < len(tabla.filas_origen) else pos + 2
        costo = precio = None
        for idx, rol in rol_dinero.items():
            if rol == "costo" and costo is None:
                costo = _importe(celda(fila, idx))
            elif rol == "precio" and precio is None:
                precio = _importe(celda(fila, idx))

        bruto = celda(fila, mapa.campos.get("cantidad"))
        cantidad = _importe(bruto)
        dudas = []
        if cantidad is None or cantidad == 0:
            dudas.append("Cantidad vacía")
            cantidad = Decimal(0)
        descripcion = txt(fila, "descripcion_original") or ""
        if not descripcion:
            dudas.append("Sin descripción")

        observacion = txt(fila, "observacion")
        if observacion is None:
            extra = [t for t in (_texto(celda(fila, i)) for i in mapa.texto_libre) if t]
            observacion = " · ".join(extra) or None

        renglones.append(RenglonCrudo(
            descripcion_original=descripcion,
            marca=txt(fila, "marca"), tipo=txt(fila, "tipo"), material=txt(fila, "material"),
            color=txt(fila, "color"), talla=txt(fila, "talla"),
            cantidad=cantidad, costo_unitario=costo, precio=precio,
            observacion=observacion, duda="; ".join(dudas) or None,
            origen=f"{tabla.pestana}!R{n_fila}",
        ))
    return renglones
