"""Atlas BOS core/security/cookies — cuándo una cookie de sesión lleva `Secure`."""
import os

from fastapi import Request

_SI = ("true", "1", "yes", "si", "sí", "on")
_NO = ("false", "0", "no", "off")


def cookie_segura(request: Request) -> bool:
    """`Secure` de las cookies de sesión, según `COOKIE_SECURE`:

    - `auto` (por omisión): `Secure` solo si la petición llegó por https. Detrás
      del proxy lo dice `X-Forwarded-Proto` (uvicorn corre con `--proxy-headers`
      en producción, así que `request.url.scheme` ya es `https`); en desarrollo
      local por http la cookie sale sin `Secure` y el navegador la guarda.
    - `true`: siempre `Secure`. `false`: nunca.

    Se lee en cada llamada, no al importar, para poder cambiarla sin tocar código.
    """
    modo = os.getenv("COOKIE_SECURE", "auto").strip().lower()
    if modo in _SI:
        return True
    if modo in _NO:
        return False
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return (proto or request.url.scheme) == "https"
