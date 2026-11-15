"""Respuestas en texto libre: el modelo solo traduce el texto a operaciones.

El modelo ve las dudas abiertas (número, texto, opciones), un resumen del plan
por grupo y la respuesta del usuario; nunca usuarios, clientes ni ids de la
base salvo las claves de opción que ya traen las dudas. Lo que devuelve pasa
por la misma validación que cualquier operación (`validar_operaciones`).
"""
from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.ai.cliente_anthropic import ClienteEstructurado
from app.modules.ai.uso import registrar_uso, verificar_cupo
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.operaciones import CAMPOS, validar_operaciones
from app.modules.cargas.schemas import LIMITE_RESPUESTA

MAX_TOKENS = 8000


def _objeto(propiedades: dict) -> dict:
    """Objeto estricto: todas las propiedades requeridas, ninguna extra."""
    return {"type": "object", "properties": propiedades,
            "required": list(propiedades), "additionalProperties": False}


def _op(nombre: str, **propiedades) -> dict:
    return _objeto({"op": {"type": "string", "enum": [nombre]}, **propiedades})


_TEXTO = {"type": "string"}
_ENTERO = {"type": "integer"}
_ENTEROS = {"type": "array", "items": _ENTERO}

ESQUEMA_OPERACIONES: dict = _objeto({
    "operaciones": {"type": "array", "items": {"anyOf": [
        _op("fijar_campo", renglones={"type": ["array", "null"], "items": _ENTERO},
            grupo={"type": ["string", "null"]},
            campo={"type": "string", "enum": list(CAMPOS)}, valor=_TEXTO),
        _op("resolver_duda", numero=_ENTERO, opcion=_TEXTO, valor={"type": ["string", "null"]}),
        _op("usar_existente", grupo=_TEXTO, product_id=_TEXTO),
        _op("nuevo_producto", grupo=_TEXTO),
        _op("ignorar", renglones=_ENTEROS),
        _op("tipo_cambio", moneda=_TEXTO, valor=_TEXTO),
    ]}},
    "no_entendido": {"type": "array", "items": _objeto({
        "numero": {"type": ["integer", "null"]}, "texto": _TEXTO,
    })},
})

_SISTEMA = (
    "Eres el asistente que ayuda al dueño de una tienda a revisar una carga de mercancía. "
    "Recibes en JSON las preguntas abiertas del plan (`dudas_abiertas`), un resumen del plan "
    "por grupo de productos (`grupos`) y la respuesta que escribió el dueño (`respuesta`). "
    "Tu único trabajo es traducir esa respuesta a operaciones; no decides nada por tu cuenta.\n"
    "- Si contesta una pregunta numerada, usa `resolver_duda` con su `numero`: en `opcion` "
    "pon la clave de una de sus opciones, o \"\" y el texto en `valor` cuando contesta con "
    "un dato (un precio, un costo, un tipo de cambio, un nombre).\n"
    "- `fijar_campo` cambia un campo de unos renglones (`renglones`, por número) o de un "
    "grupo (`grupo`, su llave); usa solo uno de los dos y deja el otro en null.\n"
    "- `usar_existente` solo con un product_id que aparezca en una clave de opción "
    "\"usar:<id>\"; `nuevo_producto` para decir que un grupo es un producto nuevo; "
    "`ignorar` para renglones que no se cargan; `tipo_cambio` para el valor en pesos de una "
    "moneda.\n"
    "- Usa solo números de pregunta, números de renglón, llaves de grupo y claves que estén "
    "en los datos. Nunca inventes precios, costos ni ids: un precio solo sale de lo que "
    "escribió el dueño.\n"
    "- Lo que no entiendas va en `no_entendido`, con el número de la pregunta si lo mencionó "
    "(null si no) y el fragmento de su texto."
)


def _dudas_abiertas(db: Session, carga: CargaMercancia) -> list[dict]:
    dudas = (db.query(CargaDuda)
             .filter(CargaDuda.organization_id == carga.organization_id,
                     CargaDuda.carga_id == carga.id, CargaDuda.estado == "abierta")
             .order_by(CargaDuda.numero).all())
    return [{"numero": d.numero, "texto": d.texto, "renglones": d.renglones or [],
             "opciones": [{"clave": o.get("clave"), "etiqueta": o.get("etiqueta")}
                          for o in (d.opciones or [])]}
            for d in dudas]


def _unicos(valores) -> list:
    return list(dict.fromkeys(v for v in valores if v not in (None, "")))


def _grupos(db: Session, carga: CargaMercancia) -> tuple[list[dict], list[int]]:
    filas = (db.query(CargaRenglon)
             .filter(CargaRenglon.organization_id == carga.organization_id,
                     CargaRenglon.carga_id == carga.id)
             .order_by(CargaRenglon.orden).all())
    por_grupo: dict[str, list[CargaRenglon]] = {}
    ignorados: list[int] = []
    for f in filas:
        if f.clase == "IGNORADO":
            ignorados.append(f.orden)
        else:
            por_grupo.setdefault(f.grupo or "", []).append(f)
    resumen = []
    for llave, fs in por_grupo.items():
        norm = [f.normalizado or {} for f in fs]
        resumen.append({
            "llave": llave,
            "marca": norm[0].get("marca"),
            "tipo": norm[0].get("tipo"),
            "tallas": _unicos(n.get("talla") for n in norm),
            "precio": _unicos(None if f.precio is None else str(f.precio) for f in fs),
            "clase": _unicos(f.clase for f in fs),
            "renglones": [f.orden for f in fs],
        })
    return resumen, ignorados


def interpretar_respuesta(
    db: Session, carga: CargaMercancia, texto: str, cliente: ClienteEstructurado,
    instrucciones: str,
) -> tuple[list[dict], list[str], int, int]:
    """(operaciones válidas, rechazos legibles, tokens de entrada, tokens de salida)."""
    texto = texto or ""
    if len(texto) > LIMITE_RESPUESTA:
        raise HTTPException(status_code=422,
                            detail=f"La respuesta pasa de {LIMITE_RESPUESTA:,} caracteres.")
    if not texto.strip():
        raise HTTPException(status_code=422, detail="Escribe tu respuesta.")
    org_id = carga.organization_id
    verificar_cupo(db, org_id)

    grupos, ignorados = _grupos(db, carga)
    datos = {"dudas_abiertas": _dudas_abiertas(db, carga), "grupos": grupos,
             "renglones_ignorados": ignorados, "respuesta": texto}
    sistema = _SISTEMA
    if (instrucciones or "").strip():
        sistema += "\n\nContexto de la tienda, escrito por su dueño:\n" + instrucciones.strip()
    r = cliente.generar(
        sistema=sistema,
        contenido=[{"type": "text", "text": json.dumps(datos, ensure_ascii=False)}],
        esquema=ESQUEMA_OPERACIONES, max_tokens=MAX_TOKENS,
    )
    registrar_uso(db, org_id, r.tokens_entrada, r.tokens_salida)

    propuestas = [
        {k: v for k, v in op.items() if v is not None} if isinstance(op, dict) else op
        for op in (r.datos.get("operaciones") or [])
    ]
    operaciones, rechazos = validar_operaciones(db, carga, propuestas)
    for item in r.datos.get("no_entendido") or []:
        if not isinstance(item, dict):
            continue
        frase = str(item.get("texto") or "").strip()
        numero = item.get("numero")
        rechazos.append(f"No entendí el punto {numero}: {frase}" if numero is not None
                        else f"No entendí: {frase}")
    return operaciones, rechazos, r.tokens_entrada, r.tokens_salida
