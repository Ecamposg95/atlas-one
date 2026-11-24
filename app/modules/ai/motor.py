"""Motor de conversación del agente (fase A1: consultas, sin streaming).

`responder(db, ctx, conversacion, mensaje)` atiende un turno:

1. Cupo (`uso.verificar_cupo`, por organización y por persona) → 429.
2. Proveedor de la tarea `consulta` (`tareas.proveedor_para`) → 503 sin llave.
3. Guarda el mensaje de la persona y arma `[system] + historial acotado`.
4. Bucle: el modelo contesta o pide herramientas; cada una pasa por
   `herramientas.ejecutar` (que rechaza las que no son del rol) y su resultado
   vuelve dentro de `<datos_tienda>`. Tope de `TOPE_VUELTAS` llamadas al modelo.
5. Registra el consumo de cada llamada con el rol (`ai_llamadas`), también
   cuando el proveedor falla a medio turno.

Cada mensaje del asistente guarda `nativo` (lo que el proveedor exige reenviar
intacto) y el último guarda `tablas` para la pantalla. Sin commit en el camino
feliz: lo hace el router.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import historial
from .contexto import Contexto
from .datos import envolver
from .herramientas import definiciones, ejecutar
from .models import AiConversation, AiMessage
from .prompt import armar_prompt
from .proveedores import Proveedor, ProveedorNoDisponible, RespuestaIncompleta
from .tareas import CONSULTA, proveedor_para
from .uso import Medidor, registrar_llamadas, verificar_cupo

logger = logging.getLogger(__name__)

TOPE_VUELTAS = 6            # llamadas al modelo por turno
TOPE_HISTORIAL = 24         # mensajes previos que viajan al modelo
MAX_TOKENS_RESPUESTA = 4000
TOPE_TABLAS = 3
TOPE_TITULO = 60

SIN_PASOS = "No pude terminar la consulta en los pasos permitidos. Intenta con una pregunta más concreta."
SIN_TEXTO = "No tengo una respuesta para eso. Intenta preguntarlo de otra forma."


@dataclass
class Turno:
    mensaje: AiMessage
    vueltas: int


def _registrar(db: Session, ctx: Contexto, medidor: Medidor) -> None:
    registrar_llamadas(db, ctx.org_id, medidor.llamadas, user_id=ctx.user.id,
                       rol=ctx.user.role, tarea=CONSULTA)


def responder(db: Session, ctx: Contexto, conversacion: AiConversation, mensaje: str, *,
              proveedor: Optional[Proveedor] = None) -> Turno:
    """Un turno completo. `proveedor` solo lo pasan las pruebas; en uso real
    sale de `proveedor_para(db, org, "consulta")`."""
    from app.modules.tenants.models import Organization

    verificar_cupo(db, ctx.org_id, ctx.user.id)
    medidor = Medidor(proveedor or proveedor_para(db, ctx.org_id, CONSULTA))

    ctx.conversacion = conversacion
    ctx.tablas = []
    # Todo lo que el turno escribe va en un SAVEPOINT: si el proveedor falla a
    # medias se deshace solo el turno, no el resto de la transacción.
    punto = db.begin_nested()
    previos = historial.historial_para_llm(db, conversacion, TOPE_HISTORIAL)
    historial.guardar_mensaje(db, conversacion, "user", mensaje)
    if not conversacion.titulo:
        conversacion.titulo = " ".join(mensaje.split())[:TOPE_TITULO]
    conversacion.updated_at = datetime.now(timezone.utc)

    org = db.get(Organization, ctx.org_id)
    mensajes = [{"role": "system", "content": armar_prompt(db, org, ctx.user)},
                *previos, {"role": "user", "content": mensaje}]
    herramientas = definiciones(ctx)

    final: Optional[AiMessage] = None
    vueltas = 0
    try:
        while vueltas < TOPE_VUELTAS and final is None:
            vueltas += 1
            r = medidor.conversar(mensajes=mensajes, herramientas=herramientas, max_tokens=MAX_TOKENS_RESPUESTA)
            mensajes.append(r.mensaje_asistente())
            guardado = historial.guardar_mensaje(
                db, conversacion, "assistant", r.texto,
                tool_calls=[t.como_tool_call() for t in r.tool_calls] or None,
                tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida, nativo=r.nativo,
            )
            if not r.tool_calls:
                if not (r.texto or "").strip():
                    guardado.contenido = SIN_TEXTO
                final = guardado
                break
            for llamada in r.tool_calls:
                if llamada.error_json:
                    resultado = {"error": f"Argumentos inválidos (no son JSON): {llamada.error_json}"}
                else:
                    resultado = ejecutar(llamada.nombre, llamada.argumentos, ctx)
                contenido = envolver(resultado)
                mensajes.append({"role": "tool", "tool_call_id": llamada.id, "content": contenido})
                historial.guardar_mensaje(db, conversacion, "tool", contenido, tool_call_id=llamada.id)
    except ProveedorNoDisponible as e:
        # Nada del turno se queda (la persona conserva su texto en pantalla),
        # pero lo que ya se gastó sí se cuenta.
        punto.rollback()
        _registrar(db, ctx, medidor)
        db.commit()
        logger.warning("IA: el proveedor falló en la conversación %s: %s", conversacion.id, e)
        if isinstance(e, RespuestaIncompleta):
            detalle = "La respuesta del agente quedó incompleta. Intenta con una pregunta más corta."
        else:
            detalle = "El agente no está disponible en este momento. Intenta de nuevo en un minuto."
        raise HTTPException(status_code=503, detail=detalle)

    if final is None:
        final = historial.guardar_mensaje(db, conversacion, "assistant", SIN_PASOS)
    if ctx.tablas:
        final.tablas = ctx.tablas[-TOPE_TABLAS:]
    db.flush()
    punto.commit()
    _registrar(db, ctx, medidor)
    return Turno(mensaje=final, vueltas=vueltas)
