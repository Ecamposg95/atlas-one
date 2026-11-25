"""Lista ordenada de proveedores: si uno falla por red, 5xx o cuota, cae al siguiente."""
from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence

from .base import (
    MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, Proveedor, ProveedorNoDisponible, Respuesta, RespuestaJSON,
)

logger = logging.getLogger(__name__)


class ProveedorConRespaldo:
    """Cumple `Proveedor` sobre varias opciones. Solo un `ProveedorNoDisponible`
    con `recuperable=True` pasa a la siguiente; un rechazo, una respuesta
    cortada o una petición inválida se propagan tal cual. La respuesta dice en
    `proveedor`/`modelo` quién contestó."""

    def __init__(self, opciones: Sequence[Proveedor]):
        if not opciones:
            raise ValueError("ProveedorConRespaldo necesita al menos una opción")
        self.opciones = list(opciones)

    @property
    def nombre(self) -> str:
        return self.opciones[0].nombre

    @property
    def modelo(self) -> str:
        return self.opciones[0].modelo

    def _intentar(self, llamar: Callable[[Proveedor], object]):
        ultima = len(self.opciones) - 1
        for i, opcion in enumerate(self.opciones):
            try:
                return llamar(opcion)
            except ProveedorNoDisponible as e:
                if not e.recuperable or i == ultima:
                    raise
                logger.warning("IA: %s:%s no disponible (%s); se prueba %s:%s", opcion.nombre, opcion.modelo,
                               e, self.opciones[i + 1].nombre, self.opciones[i + 1].modelo)
        raise AssertionError("inalcanzable")  # pragma: no cover

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        return self._intentar(lambda p: p.conversar(
            mensajes=mensajes, herramientas=herramientas, max_tokens=max_tokens))

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        return self._intentar(lambda p: p.generar_json(
            sistema=sistema, contenido=contenido, esquema=esquema, max_tokens=max_tokens, latido=latido))
