"""Doble de pruebas de `Proveedor`: devuelve un guion fijo y anota cada llamada."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .base import MAX_TOKENS_CONVERSAR, MAX_TOKENS_JSON, Respuesta, RespuestaJSON


@dataclass
class ProveedorFalso:
    """Cada paso del guion es una excepción (se lanza), una `Respuesta` /
    `RespuestaJSON` ya armada, o un `dict` (los datos de `generar_json`)."""
    guion: list = field(default_factory=list)
    llamadas: list = field(default_factory=list)
    nombre: str = "falso"
    modelo: str = "modelo-falso"

    def _paso(self):
        if not self.guion:
            raise AssertionError("ProveedorFalso: guion agotado (la prueba no esperaba otra llamada al modelo)")
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        self.llamadas.append({"mensajes": [dict(m) for m in mensajes],
                              "herramientas": list(herramientas or []), "max_tokens": max_tokens})
        paso = self._paso()
        if not isinstance(paso, Respuesta):
            raise AssertionError("ProveedorFalso.conversar espera una Respuesta en el guion")
        paso.proveedor = paso.proveedor or self.nombre
        paso.modelo = paso.modelo or self.modelo
        return paso

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        self.llamadas.append({"sistema": sistema, "contenido": contenido,
                              "esquema": esquema, "max_tokens": max_tokens, "latido": latido})
        paso = self._paso()
        if isinstance(paso, RespuestaJSON):
            paso.proveedor = paso.proveedor or self.nombre
            paso.modelo = paso.modelo or self.modelo
            return paso
        return RespuestaJSON(datos=paso, tokens_entrada=0, tokens_salida=0,
                             proveedor=self.nombre, modelo=self.modelo)
