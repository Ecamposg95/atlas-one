"""Detección del tipo de código de barras: EAN-13 o Code 128.

PORTADO TAL CUAL de `atlas_labels/barcode.py` del agente de impresión
(<https://github.com/Ecamposg95/Atlas-Print-Agent>). No se toca: los patrones y
los anchos de módulo son los que la Zebra GX420t ya imprimió y la tienda validó
en papel. Cualquier cambio aquí cambia lo que sale del rollo.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_CODE128_CHARS = 20
# 380 dots útiles menos 22 (un símbolo Code 128 a ^BY2) por si la impresora empaqueta distinto
MAX_BARCODE_DOTS = 358
EAN13_MODULES = 95

# Code 128: anchos de barras y espacios (alternados, empezando en barra) de cada valor 0..105.
CODE128_PATTERNS = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232",
)
CODE128_STOP = "2331112"
CODE_C = 99
CODE_B = 100
START_B = 104
START_C = 105

# EAN-13: patrones L, G y R por dígito, y paridad de los seis dígitos izquierdos según el primero.
_EAN_L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
_EAN_G = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
_EAN_R = ("1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100")
_EAN_PARITY = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


@dataclass(frozen=True)
class BarcodeSpec:
    kind: str  # "EAN13" | "CODE128"
    data: str
    module_width: int  # 1 o 2 dots por módulo
    warning: str = ""

    @property
    def bits(self) -> str:
        return encode_ean13(self.data) if self.kind == "EAN13" else encode_code128(self.data)

    @property
    def width_dots(self) -> int:
        return len(self.bits) * self.module_width


def ean13_checksum_ok(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


def encode_ean13(digits: str) -> str:
    """Módulos de un EAN-13 válido: 95 caracteres '1' (barra) o '0' (espacio)."""
    if not ean13_checksum_ok(digits):
        raise ValueError(f"EAN-13 inválido: {digits!r}")
    parity = _EAN_PARITY[int(digits[0])]
    left = "".join(
        (_EAN_L if parity[i] == "L" else _EAN_G)[int(d)] for i, d in enumerate(digits[1:7])
    )
    right = "".join(_EAN_R[int(d)] for d in digits[7:13])
    return "101" + left + "01010" + right + "101"


def _widths_to_bits(widths: str) -> str:
    out, bar = [], True
    for w in widths:
        out.append(("1" if bar else "0") * int(w))
        bar = not bar
    return "".join(out)


def _code128_values(data: str) -> list[int]:
    """Valores de símbolo con la regla del modo automático de Zebra: B por defecto,
    C para corridas de 4 o más dígitos (o toda la cadena si son solo dígitos y pares)."""
    values: list[int] = []
    current: str | None = None

    def switch(target: str) -> None:
        nonlocal current
        if current == target:
            return
        if not values:
            values.append(START_C if target == "C" else START_B)
        else:
            values.append(CODE_C if target == "C" else CODE_B)
        current = target

    i, n = 0, len(data)
    while i < n:
        run = 0
        while i + run < n and data[i + run].isdigit():
            run += 1
        use_c = run >= 4 or (i == 0 and run == n and n >= 2 and n % 2 == 0)
        if use_c:
            if run % 2 == 1:
                switch("B")
                values.append(ord(data[i]) - 32)
                i += 1
                run -= 1
            switch("C")
            for _ in range(run // 2):
                values.append(int(data[i : i + 2]))
                i += 2
        else:
            switch("B")
            values.append(ord(data[i]) - 32)
            i += 1
    return values


def encode_code128(data: str) -> str:
    """Módulos de un Code 128: START, datos, verificación y STOP, como '1'/'0'."""
    if not data or any(not 32 <= ord(ch) <= 126 for ch in data):
        raise ValueError(f"Code 128 solo admite ASCII imprimible: {data!r}")
    values = _code128_values(data)
    check = (values[0] + sum(i * v for i, v in enumerate(values[1:], 1))) % 103
    values.append(check)
    return "".join(_widths_to_bits(CODE128_PATTERNS[v]) for v in values) + _widths_to_bits(CODE128_STOP)


def code128_modules(data: str) -> int:
    """Ancho exacto en módulos del Code 128 que imprimirá la Zebra en modo automático."""
    return len(encode_code128(data))


def detect(text: str | None) -> BarcodeSpec | None:
    cleaned = "".join(ch for ch in (text or "") if ch not in "*" and not ch.isspace())
    if not cleaned:
        return None
    if ean13_checksum_ok(cleaned):
        return BarcodeSpec("EAN13", cleaned, 2)

    data = "".join(ch for ch in cleaned if 33 <= ord(ch) <= 126 and ch not in "^~>")
    if not data:
        return None

    warnings: list[str] = []
    if len(data) > MAX_CODE128_CHARS:
        data = data[:MAX_CODE128_CHARS]
        warnings.append(f"código recortado a {MAX_CODE128_CHARS} caracteres")

    module_width = 2 if code128_modules(data) * 2 <= MAX_BARCODE_DOTS else 1
    if module_width == 1:
        warnings.append("código largo, impreso angosto; puede costar trabajo escanear")
    return BarcodeSpec("CODE128", data, module_width, "; ".join(warnings))
