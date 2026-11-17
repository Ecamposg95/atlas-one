"""Registro del listener de disponibilidad web (canal «Tienda en línea»).

Módulo ligero, sin imports de la app: `app/models/__init__.py` lo llama al
final para que el listener quede activo en todo proceso que cargue los modelos
—la API, pero también scripts que abren `SessionLocal()` y llaman servicios
(ajustes de existencias, altas de variantes)—. El cuerpo real vive en
`app.services.canal_disponibilidad._procesar_flush` y se importa al primer
flush (importarlo aquí cerraría un ciclo con los modelos).
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session


def _antes_del_flush(session: Session, flush_context, instances) -> None:
    from app.services.canal_disponibilidad import _procesar_flush

    _procesar_flush(session, flush_context, instances)


def registrar_listener() -> None:
    """Registra el listener global en la clase Session (idempotente)."""
    if not event.contains(Session, "before_flush", _antes_del_flush):
        event.listen(Session, "before_flush", _antes_del_flush)


def quitar_listener() -> None:
    """Solo para pruebas: medir el costo del listener."""
    if event.contains(Session, "before_flush", _antes_del_flush):
        event.remove(Session, "before_flush", _antes_del_flush)
