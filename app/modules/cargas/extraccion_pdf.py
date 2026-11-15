"""Extracción de renglones de un PDF de importación (pedimento, factura) por bloques de páginas."""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from pypdf import PasswordType, PdfReader, PdfWriter

from app.modules.ai.cliente_anthropic import ClienteEstructurado
from app.modules.cargas.lectura_excel import normalizar_numero
from app.modules.cargas.tipos import RenglonCrudo

PAGINAS_POR_BLOQUE = 15

_TXT_NULO = ["string", "null"]
_RENGLON = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "descripcion_original": {"type": "string"},
        "marca": {"type": _TXT_NULO},
        "tipo": {"type": _TXT_NULO},
        "material": {"type": _TXT_NULO},
        "color": {"type": _TXT_NULO},
        "talla": {"type": _TXT_NULO},
        "cantidad": {"type": "string"},
        "costo_unitario": {"type": _TXT_NULO},
        "precio": {"type": _TXT_NULO},
        "moneda": {"type": _TXT_NULO},
        "observacion": {"type": _TXT_NULO},
        "duda": {"type": _TXT_NULO},
        "pagina": {"type": ["integer", "null"]},
    },
    "required": ["descripcion_original", "marca", "tipo", "material", "color", "talla", "cantidad",
                 "costo_unitario", "precio", "moneda", "observacion", "duda", "pagina"],
}
ESQUEMA_PDF: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "renglones": {"type": "array", "items": _RENGLON},
        "monedas": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"codigo": {"type": "string"}, "tipo_cambio": {"type": _TXT_NULO}},
            "required": ["codigo", "tipo_cambio"],
        }},
        "continua_en_siguiente": {"type": "boolean"},
    },
    "required": ["renglones", "monedas", "continua_en_siguiente"],
}

_INSTRUCCIONES = (
    "Extrae TODOS los renglones de mercancía del documento adjunto (puede estar en español, inglés o chino). "
    "Reglas: traduce al español SOLO tipo, marca y color; conserva `descripcion_original` literal, "
    "tal como aparece. Pon en `duda` una nota breve cuando algo sea ilegible o ambiguo (no adivines). "
    "NO inventes precio de venta: `precio` solo si el documento lo trae como precio de venta; el costo va "
    "en `costo_unitario`. Cantidades y montos como texto numérico (p. ej. \"12\", \"3.50\"), sin símbolos. "
    "En `moneda` pon, en cada renglón, el código ISO de la moneda de su costo (USD, CNY, EUR, MXN…), "
    "aunque se repita en todos; null solo si el renglón no trae costo. "
    "`pagina` es el número de página dentro de este bloque (1 = primera página adjunta), o null. "
    "En `monedas` lista cada moneda que aparezca con su tipo de cambio si el documento lo indica (si no, null). "
    "`continua_en_siguiente` es true si el último renglón queda cortado al final de este bloque."
)


@dataclass
class ExtraccionPdf:
    renglones: list[RenglonCrudo] = field(default_factory=list)
    monedas: dict[str, Optional[Decimal]] = field(default_factory=dict)
    tokens_entrada: int = 0
    tokens_salida: int = 0


def _decimal(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        valor = str(valor)
    s = normalizar_numero(re.sub(r"[€¥]", "", str(valor)))
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _bloques(contenido: bytes) -> tuple[list[tuple[int, int, bytes]], int]:
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            # Muchos PDFs solo traen contraseña de propietario y abren con la de usuario vacía.
            if lector.decrypt("") == PasswordType.NOT_DECRYPTED:
                raise ValueError("El PDF está protegido con contraseña. Quítale la protección y vuelve a subirlo.")
        total = len(lector.pages)
        if total == 0:
            raise ValueError("El PDF no tiene páginas.")
        bloques = []
        for ini in range(0, total, PAGINAS_POR_BLOQUE):
            fin = min(ini + PAGINAS_POR_BLOQUE, total)
            w = PdfWriter()
            for i in range(ini, fin):
                w.add_page(lector.pages[i])
            buf = io.BytesIO()
            w.write(buf)
            bloques.append((ini, fin, buf.getvalue()))
        return bloques, total
    except ValueError:
        raise
    except Exception as e:  # pypdf lanza varias clases según el daño
        raise ValueError("No se pudo leer el PDF: el archivo está dañado o no es un PDF válido.") from e


def _a_renglon(d: dict, ini: int, fin: int) -> RenglonCrudo:
    dudas = [d["duda"]] if d.get("duda") else []
    cantidad = _decimal(d.get("cantidad"))
    if cantidad is None:
        dudas.append(f"Cantidad ilegible: {d.get('cantidad')!r}")
        cantidad = Decimal(0)
    montos = {}
    for campo in ("costo_unitario", "precio"):
        v = _decimal(d.get(campo))
        if v is None and d.get(campo) not in (None, ""):
            dudas.append(f"{campo} ilegible: {d.get(campo)!r}")
        montos[campo] = v
    pag = d.get("pagina")
    if isinstance(pag, int) and 1 <= pag <= fin - ini:
        origen = f"pág. {ini + pag}"
    else:
        origen = f"pág. {ini + 1}" if fin - ini == 1 else f"págs. {ini + 1}-{fin}"
    return RenglonCrudo(
        descripcion_original=d["descripcion_original"],
        marca=d.get("marca"), tipo=d.get("tipo"), material=d.get("material"),
        color=d.get("color"), talla=d.get("talla"), cantidad=cantidad,
        costo_unitario=montos["costo_unitario"], precio=montos["precio"],
        moneda=d.get("moneda"), observacion=d.get("observacion"),
        duda="; ".join(dudas) or None, origen=origen,
    )


def _unir(previo: RenglonCrudo, nuevo: RenglonCrudo) -> None:
    """Completa en `previo` lo que le falte con lo que trae la continuación."""
    for campo in ("marca", "tipo", "material", "color", "talla", "costo_unitario", "precio",
                  "moneda", "observacion"):
        if getattr(previo, campo) is None and getattr(nuevo, campo) is not None:
            setattr(previo, campo, getattr(nuevo, campo))
    if nuevo.duda and nuevo.duda not in (previo.duda or ""):
        previo.duda = "; ".join(x for x in (previo.duda, nuevo.duda) if x)


def extraer_pdf(contenido: bytes, cliente: ClienteEstructurado, instrucciones: str,
                al_terminar_bloque: Optional[Callable[[], None]] = None) -> ExtraccionPdf:
    """`al_terminar_bloque` se llama tras leer cada bloque (el latido de la carga)."""
    bloques, _ = _bloques(contenido)
    sistema = (
        "Eres un asistente que lee documentos de importación y facturas de mercancía para una tienda. "
        "Respondes únicamente con el JSON del esquema."
    )
    if (instrucciones or "").strip():
        sistema += f"\n\nContexto de la tienda (escrito por el dueño):\n{instrucciones.strip()}"

    res = ExtraccionPdf()
    contradichas: set[str] = set()
    anterior_continua = False
    ultimo: Optional[RenglonCrudo] = None
    for k, (ini, fin, datos) in enumerate(bloques):
        texto = _INSTRUCCIONES
        if k > 0 and ultimo is not None:
            texto += ("\n\nÚltimo renglón del bloque anterior"
                      + (" (quedó cortado; si este bloque abre con su continuación, repítelo completo)"
                         if anterior_continua else "")
                      + f": {ultimo.descripcion_original}")
        contenido_msg = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                             "data": base64.b64encode(datos).decode("ascii")}},
            {"type": "text", "text": texto},
        ]
        r = cliente.generar(sistema=sistema, contenido=contenido_msg, esquema=ESQUEMA_PDF)
        res.tokens_entrada += r.tokens_entrada
        res.tokens_salida += r.tokens_salida

        nuevos = [_a_renglon(d, ini, fin) for d in r.datos.get("renglones", [])]
        if (anterior_continua and nuevos and res.renglones
                and _norm(nuevos[0].descripcion_original) == _norm(res.renglones[-1].descripcion_original)):
            _unir(res.renglones[-1], nuevos.pop(0))
        res.renglones.extend(nuevos)
        ultimo = res.renglones[-1] if r.datos.get("renglones") else None
        anterior_continua = bool(r.datos.get("continua_en_siguiente"))

        for m in r.datos.get("monedas", []):
            cod, tc = m.get("codigo"), _decimal(m.get("tipo_cambio"))
            if not cod:
                continue
            if cod in contradichas:
                continue
            if cod not in res.monedas or res.monedas[cod] is None:
                res.monedas[cod] = tc
            elif tc is not None and res.monedas[cod] != tc:
                res.monedas[cod] = None
                contradichas.add(cod)
        if al_terminar_bloque is not None:
            al_terminar_bloque()
    return res

