"""Composición de la etiqueta ZPL 51 x 25 mm (Zebra GX420t, 203 dpi).

Portado del agente de impresión (`atlas_labels/`) sin tocar la geometría: el
backend arma los bytes y el navegador se los pasa al agente, igual que el
ticket de venta (`app/pos_printer.py`).
"""
from .barcode import (  # noqa: F401
    BarcodeSpec,
    detect,
    ean13_checksum_ok,
    encode_code128,
    encode_ean13,
)
from .zpl import (  # noqa: F401
    BARCODE_HEIGHT,
    LABEL_HEIGHT,
    LABEL_WIDTH,
    MARGIN,
    Bars,
    DatosEtiqueta,
    Text,
    build_batch,
    build_label,
    build_test_label,
    fit_text,
    layout,
    parse_price,
    zpl_safe,
)

__all__ = [
    "BarcodeSpec", "detect", "ean13_checksum_ok", "encode_code128", "encode_ean13",
    "BARCODE_HEIGHT", "LABEL_HEIGHT", "LABEL_WIDTH", "MARGIN",
    "Bars", "DatosEtiqueta", "Text",
    "build_batch", "build_label", "build_test_label", "fit_text", "layout",
    "parse_price", "zpl_safe",
]
