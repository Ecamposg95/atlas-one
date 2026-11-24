"""Interfaz única de proveedor de IA.

Todo lo que habla con un modelo (Cargar mercancía hoy, el chat mañana) usa
`Proveedor`; nadie importa un cliente concreto. Dos implementaciones:
`ProveedorAnthropic` (SDK nativo) y `ProveedorOpenAI` (cualquier API compatible
con OpenAI: Gemini, Groq, Mistral…), más `ProveedorFalso` para la suite y
`ProveedorConRespaldo`, que recorre una lista ordenada.

Formato canónico (el que guarda `ai_messages`):

- **mensajes**: lista estilo OpenAI. `{"role": "system"|"user", "content": str}`,
  `{"role": "assistant", "content": str|None, "tool_calls": [...]}` y
  `{"role": "tool", "tool_call_id": str, "content": str}`. Un mensaje de
  asistente puede traer además `"nativo"` (lo que devolvió `Respuesta.nativo`):
  el proveedor que lo produjo lo reenvía tal cual; los demás lo ignoran.
- **herramientas**: `{"type": "function", "function": {"name", "description",
  "parameters"}}` (lo que arma `Herramienta.definicion`).
- **contenido** de `generar_json`: bloques `{"type": "text", "text": ...}` y
  `{"type": "document", "source": {"type": "base64", "media_type", "data"}}`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable

MAX_TOKENS_CONVERSAR = 16000
MAX_TOKENS_JSON = 64000


class ProveedorNoDisponible(RuntimeError):
    """El proveedor no respondió o respondió algo inutilizable (→ HTTP 503).

    `recuperable=True` (red, 5xx, cuota del proveedor): vale la pena probar el
    siguiente modelo de la lista. `False` (rechazo, formato, petición inválida):
    otro modelo no lo arregla o no debe intentarse a ciegas."""

    def __init__(self, mensaje: str = "", *, recuperable: bool = False):
        super().__init__(mensaje)
        self.recuperable = recuperable


class RespuestaIncompleta(ProveedorNoDisponible):
    """El modelo llegó a `max_tokens` (incluye su razonamiento) y la salida quedó cortada."""


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict[str, Any]
    argumentos_crudos: str = "{}"
    # Texto del error cuando los argumentos no son un objeto JSON válido: la
    # herramienta no se ejecuta y el modelo recibe el error para corregirse.
    error_json: Optional[str] = None

    @classmethod
    def desde_crudo(cls, id: str, nombre: str, crudo: Any) -> "LlamadaHerramienta":
        if isinstance(crudo, dict):
            return cls(id=id, nombre=nombre, argumentos=crudo,
                       argumentos_crudos=json.dumps(crudo, ensure_ascii=False))
        texto = crudo if isinstance(crudo, str) else ""
        if not texto.strip():
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos="{}")
        try:
            valor = json.loads(texto)
        except json.JSONDecodeError as e:
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto, error_json=str(e))
        if not isinstance(valor, dict):
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto,
                       error_json="los argumentos no son un objeto JSON")
        return cls(id=id, nombre=nombre, argumentos=valor, argumentos_crudos=texto)

    def como_tool_call(self) -> dict:
        return {"id": self.id, "type": "function",
                "function": {"name": self.nombre, "arguments": self.argumentos_crudos}}


@dataclass
class Respuesta:
    """Resultado de `conversar`: texto, llamadas a herramientas y tokens."""
    texto: Optional[str] = None
    tool_calls: list[LlamadaHerramienta] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    # Quién contestó de verdad (con respaldo puede no ser el primero de la lista).
    proveedor: str = ""
    modelo: str = ""
    # Contenido tal cual lo devolvió el proveedor, para reenviarlo en el
    # siguiente turno (`mensaje_asistente`). Anthropic lo exige para sus
    # bloques de razonamiento; en OpenAI es None.
    nativo: Optional[dict] = None

    def mensaje_asistente(self) -> dict:
        """El mensaje canónico que se agrega al historial tras esta respuesta."""
        m: dict[str, Any] = {"role": "assistant", "content": self.texto}
        if self.tool_calls:
            m["tool_calls"] = [t.como_tool_call() for t in self.tool_calls]
        if self.nativo is not None:
            m["nativo"] = self.nativo
        return m


@dataclass
class RespuestaJSON:
    """Resultado de `generar_json`: un objeto que cumple el esquema pedido."""
    datos: dict
    tokens_entrada: int = 0
    tokens_salida: int = 0
    proveedor: str = ""
    modelo: str = ""


@runtime_checkable
class Proveedor(Protocol):
    nombre: str   # "anthropic", "compatible", …
    modelo: str

    def conversar(self, *, mensajes: list[dict], herramientas: Optional[list[dict]] = None,
                  max_tokens: int = MAX_TOKENS_CONVERSAR) -> Respuesta:
        """Un turno del modelo sobre el historial. No ejecuta herramientas."""
        ...

    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = MAX_TOKENS_JSON,
                     latido: Optional[Callable[[], None]] = None) -> RespuestaJSON:
        """Salida estructurada: un objeto JSON que cumple `esquema`. `latido`, si
        viene, se llama de vez en cuando mientras la respuesta sigue llegando."""
        ...
