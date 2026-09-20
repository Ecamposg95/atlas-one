# app/pos_printer.py
from __future__ import annotations
import os
import logging
import platform
import unicodedata
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")

# Encabezado semilla de TODAS las organizaciones: no es un encabezado que
# alguien haya pedido, asi que el ticket no lo imprime (ver
# PosPrinter._ticket_header_lines).
LEGACY_TICKET_HEADER = "ATLAS POS - Nota de Venta"

# Linea del proveedor tecnologico, al pie del pie.
VENDOR_LINES = ("Sistema: Atlas One | Atlas Tech", "atlasone.com.mx")
from typing import List, Optional
from decimal import Decimal

# Importamos tus modelos reales
from app.models import SalesDocument, Payment, SalesLineItem


def _es_publico_general(nombre) -> bool:
    """True si `nombre` es el valor por defecto "Público General" del historial,
    no un cliente real. Ignora mayúsculas/minúsculas y acentos ("PUBLICO GENERAL",
    "público general", "Público General" cuentan igual) — lo reutiliza también el
    ticket HTML (`app/templates/print/ticket.html`) vía el router que lo renderiza."""
    limpio = unicodedata.normalize("NFKD", (nombre or "")).encode("ascii", "ignore").decode()
    return limpio.casefold().strip() == "publico general"


def _describe_variant(variant) -> str:
    """"Playera (Rojo / M)" o solo el nombre del producto para la variante estandar."""
    nombre = variant.product.name if variant is not None and variant.product else "Producto"
    etiqueta = (variant.variant_name or "").strip() if variant is not None else ""
    if etiqueta and etiqueta != "Estándar":
        return f"{nombre} ({etiqueta})"
    return nombre


def _card_surcharge_amount(sale) -> float:
    """Comision de tarjeta congelada en la venta, como float. 0.0 si no aplico.

    `getattr` defensivo y `try` alrededor del `float`: varias rutas arman el
    documento con SimpleNamespace (`tests/test_ticket_layout.py`) o MagicMock
    (`tests/test_pos_printer.py`), y una venta anterior a la funcion no tiene
    la columna poblada. Un atributo que no es un numero vale 0.0, nunca una
    excepcion en medio de una impresion.
    """
    valor = getattr(sale, "card_surcharge_amount", None)
    if valor is None:
        return 0.0
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return monto if monto > 0 else 0.0


def _fmt_pct(pct) -> "Optional[str]":
    """'3.5', '2.75', '3'. Sin ceros de relleno.

    La etiqueta del ticket tiene 20 columnas contadas en papel de 58 mm
    (`_total_line`), y `COM. TARJETA ` ya gasta 13: el porcentaje no puede
    pasar de 6 caracteres. Por eso `card_surcharge_pct` es NUMERIC(5,2) y aqui
    se formatea a dos decimales como maximo. `None` si el valor no es un
    numero, y entonces la etiqueta se imprime sin porcentaje.
    """
    try:
        texto = f"{Decimal(str(pct)):.2f}"
    except Exception:  # noqa: BLE001 — nunca reventar una impresion
        return None
    # "3.50" -> "3.5"; "3.00" -> "3"; "19.99" -> "19.99". El punto detiene el
    # rstrip, asi que "20.00" nunca se convierte en "2".
    return texto.rstrip("0").rstrip(".") or "0"


class PosPrinter:
    # Compact OXXO-style layout (2026-04-29 v2):
    # Use the FULL printable width on each paper size so no horizontal whitespace
    # is wasted. The compactness comes from collapsing vertical lines (3-line
    # header, 1-line products, 1-line payment), not from narrow columns.
    # 80mm + Font B → 56 cols (validated for Epson/Star 80mm thermals).
    # 58mm + Font A → 32 cols.
    DEFAULT_COLS_80MM = 56
    DEFAULT_COLS_58MM = 32

    # Paper printable width in dots (ESC/POS GS v 0 raster). Used to
    # manually center the logo by padding the bitmap — many cheap thermals
    # ignore `ESC a` for raster images and print from the left edge.
    PAPER_DOTS_80MM = 576
    PAPER_DOTS_58MM = 384

    def __init__(
        self,
        printer_name: str = None,
        paper_width_mm: int = 80,
        use_small_font: bool = False, # Ignored, forcing standard
    ):
        self.printer_name = printer_name or "POS-80"
        self.paper_width_mm = paper_width_mm

        # DYNAMIC COLUMNS + default font per width.
        # 80mm + Font B (compact) → 56 cols aprovecha el papel.
        # 58mm + Font A (regular) → 32 cols standard.
        if self.paper_width_mm < 70:
            self.cols = self.DEFAULT_COLS_58MM
        else:
            self.cols = self.DEFAULT_COLS_80MM

        # Comandos ESC/POS extendidos
        self.CMD = {
            "RESET": b"\x1B\x40", # EXTENDED: Initialize
            "INIT": b"\x1B\x40",
            "LF": b"\x0A",
            "CUT": b"\x1D\x56\x42\x00",
            "CENTER": b"\x1B\x61\x01",
            "LEFT": b"\x1B\x61\x00",
            "RIGHT": b"\x1B\x61\x02",
            "BOLD_ON": b"\x1B\x45\x01",
            "BOLD_OFF": b"\x1B\x45\x00",
            "SIZE_NORMAL": b"\x1D\x21\x00",
            "SIZE_LARGE": b"\x1D\x21\x11", 
            # Force Font A (ESC M 0)
            "FONT_A": b"\x1B\x4D\x00",
            "FONT_B": b"\x1B\x4D\x01",
            # Underline
            "UNDERLINE_ON":  b"\x1B\x2D\x01",
            "UNDERLINE_OFF": b"\x1B\x2D\x00",
            # Cash drawer kick — ESC p m t1 t2 (pin 2, 25ms on, 250ms off).
            # Estándar Epson; compatible con 99% de cajones RJ-11.
            "DRAWER": b"\x1B\x70\x00\x19\xFA",
        }

        # Font por defecto según ancho de papel:
        # 80mm → Font B (compact) para caber los 56 cols validados.
        # 58mm → Font A (regular).
        # Dentro del ticket, `FONT_A` se usa como "emphasize" para títulos.
        self._default_font = self.CMD["FONT_B"] if self.paper_width_mm >= 70 else self.CMD["FONT_A"]

    @staticmethod
    def get_available_printers() -> List[str]:
        import platform as _p
        import subprocess
        if _p.system() == "Windows":
            try:
                import win32print
                return [p[2] for p in win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )]
            except ImportError:
                return ["Error: win32print not found"]
            except Exception:
                return []
        else:
            # Linux/macOS: usar lpstat -a para listar impresoras CUPS
            try:
                result = subprocess.run(
                    ["lpstat", "-a"],
                    capture_output=True, text=True, timeout=5
                )
                names = [line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()]
                return names if names else ["(sin impresoras CUPS configuradas)"]
            except FileNotFoundError:
                return ["CUPS no instalado (sudo apt install cups)"]
            except Exception as e:
                return [f"Error: {e}"]

    def send_raw_bytes(self, raw_data: bytes):
        if platform.system() == "Windows":
            try:
                import win32print
                p = win32print.OpenPrinter(self.printer_name)
                try:
                    job = win32print.StartDocPrinter(p, 1, ("AtlasPOS Ticket", None, "RAW"))
                    win32print.StartPagePrinter(p)
                    win32print.WritePrinter(p, raw_data)
                    win32print.EndPagePrinter(p)
                    win32print.EndDocPrinter(p)
                finally:
                    win32print.ClosePrinter(p)
            except Exception as e:
                raise RuntimeError(f"Error Windows Print: {e}")
        else:
            # Linux: pipe raw bytes a lp (CUPS)
            import subprocess
            try:
                proc = subprocess.run(
                    ["lp", "-d", self.printer_name, "-o", "raw", "-"],
                    input=raw_data,
                    capture_output=True,
                    timeout=10
                )
                if proc.returncode != 0:
                    err = proc.stderr.decode(errors="replace")
                    raise RuntimeError(f"lp error: {err}")
            except FileNotFoundError:
                raise RuntimeError("lp no encontrado — instala CUPS: sudo apt install cups")
            except subprocess.TimeoutExpired:
                raise RuntimeError("Timeout enviando a impresora CUPS")

    def build_ticket_bytes(self, sale: SalesDocument, paid: Decimal, change: Decimal, method: str, cashier: str, is_reprint: bool, organization = None, branch = None, returns: list = None, payments_detail: list = None, open_drawer: bool = False) -> bytes:
        """Compact OXXO-style ticket: 3-line header, 1-line products, 1-line payment.

        Layout for 80mm (42 cols):
            qty(4) + name(20) + unit(8) + total(10)
        Header keeps only org name, branch+phone, and date|folio|cashier.
        Logo (when configured) renders at 1/3 paper width (~27mm)."""
        raw = b""
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")

        # --- Init + default font ---
        raw += self.CMD["RESET"] + self._default_font + self.CMD["SIZE_NORMAL"]

        # --- 1. HEADER (logo + 3 lines) ---
        raw += self._build_compact_header(sale, cashier, organization, branch)

        # --- 2. PRODUCTS ---
        raw += self.CMD["LEFT"] + sep
        for line in sale.lines:
            qty_val = float(line.quantity)
            unit_price = float(line.unit_price) if line.unit_price is not None else 0.0
            total_val = float(line.total_line)
            raw += self._product_line(qty_val, line.description or "Articulo", unit_price, total_val)

        # Inline returns: "- DEVUELTO Nx ITEM      -monto"
        total_returned = 0.0
        if returns:
            for ret in returns:
                for item in ret.items:
                    r_qty = float(item.quantity)
                    r_amt = float(item.refund_amount)
                    total_returned += r_amt
                    p_name = _describe_variant(item.variant) if item.variant else "Producto"
                    raw += self._return_line(r_qty, p_name, r_amt)

        raw += sep

        # --- 3. TOTALS ---
        net_total = float(sale.total_amount) - total_returned
        net_subtotal = float(sale.subtotal) * (net_total / float(sale.total_amount)) if float(sale.total_amount) > 0 else float(sale.subtotal)
        net_tax = float(sale.tax_amount) * (net_total / float(sale.total_amount)) if float(sale.total_amount) > 0 else float(sale.tax_amount)

        raw += self._total_line("SUBTOTAL", net_subtotal)
        raw += self._total_line("IVA", net_tax)
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", net_total)
        raw += self.CMD["BOLD_OFF"]

        # Comision por pago con tarjeta. Vacio si la venta no la trae, asi que
        # una organizacion sin comision imprime el ticket de siempre.
        raw += self._card_surcharge_lines(sale, net_total)

        # Equivalente en dolares. Solo si la venta trae el tipo congelado
        # (`sales_documents.usd_rate`); una organizacion sin tipo de cambio ve
        # el ticket de siempre. Va DESPUES de la comision y sobre el total a
        # pagar: el equivalente es lo que el cliente entrega, no la mercancia.
        raw += self._usd_line(getattr(sale, "usd_rate", None),
                              net_total + _card_surcharge_amount(sale))

        # --- 4. PAYMENT (1 line single, N lines mixed) ---
        raw += self._payment_block(method, float(paid), float(change), payments_detail)

        # --- 5. REPRINT marker + footer ---
        if is_reprint:
            raw += self.CMD["CENTER"] + b"*** REIMPRESION ***\n" + self.CMD["LEFT"]

        footer_msg = self._resolve_footer(organization, branch)
        if footer_msg:
            raw += self.CMD["CENTER"]
            # Sin sufijo de marca del proveedor: el pie es del negocio.
            raw += (self._truncate(footer_msg, self.cols) + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

        # --- 6. BLOQUE BOUTIQUE (redes / terminos / proveedor) ---
        raw += self._build_boutique_footer(organization, branch)

        raw += self.CMD["LF"] * 3
        if open_drawer:
            raw += self.CMD["DRAWER"]
        raw += self.CMD["CUT"]
        return raw

    # ─── Compact-layout helpers ────────────────────────────────────────────

    def _build_compact_header(self, sale, cashier: str, organization, branch) -> bytes:
        """Logo (1/3 width) + 3 centered lines: org / branch+phone / date|folio|cashier."""
        raw = self.CMD["CENTER"]

        # Logo (branch overrides org)
        effective_logo = (getattr(branch, 'logo_url', None) if branch else None) \
                         or (organization.logo_url if organization else None)
        if effective_logo:
            raw += self._generate_image_bytes(effective_logo)

        # Line 1: org name (bold). If a distinct legal_name exists and both fit,
        # prepend as "LEGAL | NAME" (e.g. "ELEVEN FASHION SA DE CV | ELEVEN FASHION").
        org_name = (organization.name if organization else None) or "ATLAS POS"
        legal_name = (organization.legal_name if organization else None)
        if legal_name and legal_name != org_name:
            combined = f"{legal_name} | {org_name}"
            line1 = combined if len(combined) <= self.cols else org_name
        else:
            line1 = org_name
        raw += self.CMD["BOLD_ON"]
        raw += (self._truncate(line1, self.cols) + "\n").encode("latin-1", "replace")
        raw += self.CMD["BOLD_OFF"]

        # Line 1.5 (opcional): encabezado propio del negocio. La sucursal gana
        # sobre la organizacion. NUNCA se imprime el seed heredado
        # ("ATLAS POS - Nota de Venta"): lo traen todas las organizaciones sin
        # haberlo pedido, y nadie quiere una linea nueva en su ticket de hoy.
        raw += self._ticket_header_lines(organization, branch)

        # Line 2: city/branch | phone
        zone = None
        phone = None
        if branch:
            zone = getattr(branch, 'city', None) or branch.name
            phone = branch.phone
        if not phone and organization:
            phone = organization.phone
        if zone and phone:
            line2 = f"{zone} | {phone}"
        elif zone:
            line2 = zone
        elif phone:
            line2 = phone
        else:
            line2 = None
        if line2:
            raw += (self._truncate(line2, self.cols) + "\n").encode("latin-1", "replace")

        # Line 3: date | folio | cashier
        dt = sale.created_at if sale.created_at else datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(MX_TZ)
        fecha = local_dt.strftime("%d/%m/%y %H:%M")
        folio = f"{sale.series or ''}-{sale.folio}".strip("-")
        cashier_short = (cashier or "").split()[0].split('.')[0].title() if cashier else ""
        line3_parts = [fecha, folio, cashier_short]
        line3 = " | ".join(p for p in line3_parts if p)
        raw += (self._truncate(line3, self.cols) + "\n").encode("latin-1", "replace")

        # Line 4 (opcional): cliente. "Público General" es el valor por defecto
        # del historial, no un cliente: no se imprime (ni con o sin acento).
        cliente = (getattr(sale, "customer_name", None) or "").strip()
        if cliente and not _es_publico_general(cliente):
            raw += (self._truncate(f"Cliente: {cliente}", self.cols) + "\n").encode("latin-1", "replace")
        return raw

    def _truncate(self, text: str, width: int) -> str:
        text = (text or "").strip()
        return text[:width]

    def _product_line(self, qty: float, name: str, unit_price: float, total: float) -> bytes:
        """qty(4) + name(name_w) + unit(8) + total(total_w) = self.cols.
        80mm/56cols: 4+32+8+12. 58mm/32cols: 4+12+8+8."""
        qty_w = 4
        if self.cols >= 56:
            unit_w, total_w = 8, 12
        elif self.cols >= 42:
            unit_w, total_w = 8, 10
        else:
            unit_w, total_w = 8, 8
        name_w = self.cols - qty_w - unit_w - total_w
        qty_str = f"{int(qty) if qty == int(qty) else qty:g}x"
        if len(qty_str) > qty_w - 1:
            qty_str = qty_str[: qty_w - 1]
        line = (
            f"{qty_str:<{qty_w}}"
            f"{name.upper()[:name_w]:<{name_w}}"
            f"{('@' + f'{unit_price:.2f}'):>{unit_w}}"
            f"{total:>{total_w}.2f}\n"
        )
        return line.encode("latin-1", "replace")

    def _return_line(self, qty: float, name: str, refund: float) -> bytes:
        """One-line refund marker: '- DEVUELTO Nx ITEM      -monto'."""
        prefix = f"- DEVUELTO {int(qty) if qty == int(qty) else qty:g}x "
        total_w = 12 if self.cols >= 56 else (10 if self.cols >= 42 else 8)
        name_w = self.cols - len(prefix) - total_w
        if name_w < 4:
            name_w = 4
        line = (
            f"{prefix}{name.upper()[:name_w]:<{name_w}}"
            f"{-refund:>{total_w}.2f}\n"
        )
        return line.encode("latin-1", "replace")

    def _total_line(self, label: str, value: float) -> bytes:
        """Label-padded-left + value-padded-right.
        56 cols → 40+16. 42 cols → 28+14. 32 cols → 20+12."""
        if self.cols >= 56:
            label_w = 40
        elif self.cols >= 42:
            label_w = 28
        else:
            label_w = self.cols - 12
        val_w = self.cols - label_w
        label_text = f"{label}:"
        line = f"{label_text:<{label_w}}{value:>{val_w}.2f}\n"
        return line.encode("latin-1", "replace")

    def _usd_line(self, usd_rate: Optional[Decimal], total_mxn: float) -> bytes:
        """'USD (T.C. 18.5000):            12.34'. Vacio si la venta no trae tipo.

        El tipo de cambio viaja EN LA ETIQUETA, no en una linea aparte con el
        simbolo '≈': el ticket se codifica en latin-1 (`_total_line`) y '≈'
        saldria impreso como '?'. La etiqueta mide 19 caracteres, asi que cabe
        en el `label_w` de 20 del papel de 58 mm.

        La conversion la hace `app/services/exchange_rate.py::to_usd`, unica
        fuente del redondeo (el mismo que usa la pantalla del POS).
        """
        from app.services.exchange_rate import _dec, to_usd

        tasa = _dec(usd_rate)
        if tasa is None or tasa <= 0:
            return b""
        equivalente = to_usd(Decimal(str(total_mxn)), tasa)
        return self._total_line(f"USD (T.C. {tasa:.4f})", float(equivalente))

    def _card_surcharge_lines(self, sale, net_total: float) -> bytes:
        """'COM. TARJETA 3.5%' + 'TOTAL A PAGAR'. Vacio si la venta no trae comision.

        `net_total` es el total de MERCANCIA (ya neto de devoluciones); el
        renglon "TOTAL A PAGAR" le suma la comision, que es lo que el cliente
        entrego de verdad.

        La comision NO se devuelve en una devolucion (diseño §7): se imprime el
        importe congelado en la venta aunque `net_total` haya bajado. En una
        devolucion total eso imprime TOTAL $0.00 y la comision entera. Es feo, y
        es verdad: ese dinero se lo quedo el banco.
        """
        monto = _card_surcharge_amount(sale)
        if monto <= 0:
            return b""

        pct = _fmt_pct(getattr(sale, "card_surcharge_pct", None))
        etiqueta = f"COM. TARJETA {pct}%" if pct else "COM. TARJETA"
        raw = self._total_line(etiqueta, monto)
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL A PAGAR", net_total + monto)
        raw += self.CMD["BOLD_OFF"]
        return raw

    def _payment_block(self, method, paid: float, change: float, payments_detail) -> bytes:
        """Single payment → 1 line with REC + CAM. Mixed → N lines, last one carries CAM."""
        method_map = {
            "CASH":         "EFECTIVO",
            "CARD":         "TARJETA",
            "TRANSFER":     "TRANSFER",
            "STORE_CREDIT": "CREDITO",
            "CHECK":        "CHEQUE",
            "OTHER":        "OTRO",
            "PENDING":      "PENDIENTE",
            "MIXTO":        "MIXTO",
        }
        def _key(m) -> str:
            return (m.value if hasattr(m, 'value') else str(m)).upper()

        raw = b""
        if payments_detail and len(payments_detail) > 1:
            for idx, pd in enumerate(payments_detail):
                k = _key(pd["method"])
                label = method_map.get(k, k)
                amt = float(pd["amount"])
                if idx == len(payments_detail) - 1:
                    line = f"{label:<9} REC:{amt:.2f}  CAM:{change:.2f}\n"
                else:
                    line = f"{label:<9} REC:{amt:.2f}\n"
                raw += line.encode("latin-1", "replace")
        else:
            k = _key(method)
            label = method_map.get(k, k)
            line = f"{label:<9} REC:{paid:.2f}  CAM:{change:.2f}\n"
            raw += line.encode("latin-1", "replace")
        return raw

    # ─── Secciones boutique (2026-09-19) ───────────────────────────────────
    #
    # Encabezado propio, redes sociales, terminos y condiciones y la linea del
    # proveedor tecnologico. Cada seccion se imprime SOLO si esta capturada:
    # una organizacion que no configuro nada recibe el ticket de siempre, byte
    # por byte (tests/test_ticket_boutique.py).

    @staticmethod
    def _texto_config(obj, attr: str) -> str:
        """Valor de configuracion como texto limpio.

        Devuelve "" para cualquier cosa que no sea una cadena con contenido.
        El filtro por tipo importa: los mocks de las pruebas (y cualquier
        objeto a medio construir) devuelven atributos truthy que NO son texto,
        y un `repr` de mock impreso en el ticket no cabe en el papel.
        """
        val = getattr(obj, attr, None) if obj is not None else None
        return val.strip() if isinstance(val, str) else ""

    def _ticket_header_lines(self, organization, branch) -> bytes:
        """Encabezado propio bajo el nombre del negocio (sucursal > organizacion).

        Se ignora el seed heredado "ATLAS POS - Nota de Venta": lo traen todas
        las organizaciones sin haberlo pedido. El campo admite varias lineas
        (el panel de Empresa ofrece hasta 4), cada una truncada al ancho.
        """
        texto = self._texto_config(branch, "ticket_header") or \
                self._texto_config(organization, "ticket_header")
        if not texto or texto == LEGACY_TICKET_HEADER:
            return b""
        raw = b""
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea or linea == LEGACY_TICKET_HEADER:
                continue
            raw += (self._truncate(linea, self.cols) + "\n").encode("latin-1", "replace")
        return raw

    def _build_boutique_footer(self, organization, branch = None) -> bytes:
        """Redes + terminos + proveedor, despues del pie del negocio.

        Vacio (b"") cuando no hay nada configurado y cuando no hay
        organizacion: el ticket termina como siempre en LF*3 + corte.
        """
        if organization is None:
            return b""

        raw = b""
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")

        # --- Redes sociales ---
        etiquetas = (
            ("Instagram", "ticket_instagram"),
            ("Facebook", "ticket_facebook"),
            ("TikTok", "ticket_tiktok"),
            ("WhatsApp", "ticket_whatsapp"),
            ("Web", "website"),
        )
        redes = []
        for etiqueta, attr in etiquetas:
            valor = self._texto_config(organization, attr)
            if valor:
                redes.append(f"{etiqueta}: {valor}")
        if redes:
            raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
            raw += b"SIGUENOS\n"
            raw += self.CMD["BOLD_OFF"]
            for red in redes:
                raw += (self._truncate(red, self.cols) + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

        # --- Terminos y condiciones ---
        terminos = self._texto_config(organization, "ticket_terms")
        if terminos:
            raw += self.CMD["LEFT"] + sep
            raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
            raw += b"TERMINOS Y CONDICIONES\n"
            raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
            # En 80 mm el cuerpo va en Font B (compact): son parrafos largos y
            # el papel se agradece. En 58 mm se queda la fuente por defecto.
            if self.paper_width_mm >= 70:
                raw += self.CMD["FONT_B"]
            for parrafo in terminos.splitlines():
                parrafo = parrafo.strip()
                if not parrafo:
                    raw += self.CMD["LF"]
                    continue
                for linea in self._wrap_text(parrafo, self.cols):
                    raw += (linea + "\n").encode("latin-1", "replace")
            if self.paper_width_mm >= 70:
                raw += self._default_font

        # --- Proveedor tecnologico ---
        if self._mostrar_proveedor(organization):
            raw += self.CMD["LEFT"] + sep + self.CMD["CENTER"]
            for linea in VENDOR_LINES:
                raw += (self._truncate(linea, self.cols) + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

        return raw

    @staticmethod
    def _mostrar_proveedor(organization) -> bool:
        """TRUE por defecto: el ticket HTML ya imprimia "Software: Atlas One"
        para todos, asi que apagarlo es una decision explicita del dueño."""
        if organization is None:
            return False
        val = getattr(organization, "ticket_show_vendor", True)
        if val is None:
            return True
        return bool(val)

    def _resolve_footer(self, organization, branch) -> str:
        if branch and getattr(branch, 'ticket_footer', None):
            return branch.ticket_footer
        if organization and getattr(organization, 'ticket_footer', None):
            return organization.ticket_footer
        return "Gracias por su compra"

    # ──────────────────────────────────────────────────────────────────────


    def build_reissued_ticket_bytes(self, sale: SalesDocument, cashier: str, organization = None, branch = None, returns: list = None) -> bytes:
        """Reissued (post-return) ticket using compact layout.
        Shows only items with remaining qty after returns; recomputes totals."""
        raw = b""
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")

        raw += self.CMD["RESET"] + self._default_font + self.CMD["SIZE_NORMAL"]
        raw += self._build_compact_header(sale, cashier, organization, branch)

        # REEMITIDO marker (centered, bold)
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"*** TICKET REEMITIDO ***\n"
        raw += self.CMD["BOLD_OFF"]

        # --- Compute remaining qty per variant ---
        returned_totals = {}
        if returns:
            for ret in returns:
                for item in ret.items:
                    returned_totals[item.variant_id] = returned_totals.get(item.variant_id, 0) + float(item.quantity)

        # --- Products (only remaining) ---
        raw += self.CMD["LEFT"] + sep
        new_subtotal = 0.0
        for line in sale.lines:
            qty_orig = float(line.quantity)
            qty_ret = returned_totals.get(line.variant_id, 0.0)
            qty_rem = qty_orig - qty_ret
            if qty_rem <= 0:
                continue
            unit_price = float(line.unit_price)
            line_total = qty_rem * unit_price
            new_subtotal += line_total
            raw += self._product_line(qty_rem, line.description or "Articulo", unit_price, line_total)
        raw += sep

        # --- Recomputed totals ---
        # IVA: fuente única (app/services/tax.py). `new_subtotal` viene de sumar
        # `qty * unit_price`, que es neto o bruto según el modo de precio de la
        # organización; sumarle el IVA encima en modo "precio con IVA incluido"
        # inflaba el ticket reemitido ~16% (auditoría Rmazh §3).
        from app.services.tax import compute_line_tax, effective_tax_rate, resolve_org_tax_mode

        tasa_pct = effective_tax_rate(sale.subtotal, sale.tax_amount) * Decimal("100")
        totales = compute_line_tax(
            line_gross=new_subtotal,
            tax_rate=tasa_pct,
            has_iva=True,
            price_includes_tax=resolve_org_tax_mode(organization),
            requires_invoice=True,
        )
        new_subtotal = float(totales.subtotal)
        new_tax = float(totales.tax)
        new_final = float(totales.total)

        raw += self._total_line("SUBTOTAL", new_subtotal)
        raw += self._total_line("IVA", new_tax)
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", new_final)
        raw += self.CMD["BOLD_OFF"]

        # Misma comision que el ticket original: viene congelada en la venta y
        # NO se devuelve (diseño §7).
        raw += self._card_surcharge_lines(sale, new_final)

        # Mismo tipo de cambio que el ticket original: viene congelado en la
        # venta, no se vuelve a resolver.
        raw += self._usd_line(getattr(sale, "usd_rate", None),
                              new_final + _card_surcharge_amount(sale))

        # Footer
        footer_msg = self._resolve_footer(organization, branch)
        if footer_msg:
            raw += self.CMD["CENTER"]
            # Sin sufijo de marca del proveedor: el pie es del negocio.
            raw += (self._truncate(footer_msg, self.cols) + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

        raw += self._build_boutique_footer(organization, branch)

        raw += self.CMD["LF"] * 3 + self.CMD["CUT"]
        return raw

    def build_cash_cut_bytes(self, audit_data: dict, open_drawer: bool = False) -> bytes:
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")
        raw = b""
        
        session = audit_data['session']
        payments = audit_data['payments']
        movements = audit_data['movements']
        kpis = audit_data['kpis']
        recon = audit_data['reconciliation']
        expected = audit_data['expected']

        # --- 1. HEADER ---
        raw += self.CMD["RESET"] + self._default_font
        raw += self.CMD["SIZE_NORMAL"] + self.CMD["CENTER"]
        
        # Org Name (Bold)
        org_name = session.get('organization_name', 'ATLAS ERP')
        raw += self.CMD["BOLD_ON"]
        raw += self._wrap_line(org_name, 0).replace(b"\n", b"\n" + self.CMD["CENTER"]) 
        raw += self.CMD["BOLD_OFF"]

        raw += self.CMD["SIZE_LARGE"]
        raw += self.CMD["BOLD_ON"] + b"CORTE DE CAJA\n" + self.CMD["BOLD_OFF"]
        raw += self.CMD["SIZE_NORMAL"] + self.CMD["LF"]
        
        raw += f"ID SESION: {session['id']}\n".encode("latin-1")
        raw += f"SUCURSAL:  {session['branch_name'].upper()}\n".encode("latin-1")
        raw += f"CAJERO:    {session['user_name'].upper()}\n".encode("latin-1")
        
        opened_str = session['opened_at'].strftime("%d/%m/%y %H:%M")
        raw += f"APERTURA: {opened_str}\n".encode("latin-1")
        
        if session['closed_at']:
            closed_str = session['closed_at'].strftime("%d/%m/%y %H:%M")
            raw += f"CIERRE:   {closed_str}\n".encode("latin-1")
        else:
            raw += b"ESTADO:   EN OPERACION\n"
        
        raw += self.CMD["LF"] + self.CMD["LEFT"] + sep

        # --- 2. COBRADO POR METODO ---
        # Corte con historia: esta seccion ABRE el corte -- es el BRUTO que
        # entro por caja, el primer capitulo de la historia que cuenta el
        # ticket (cuanto entro -> que se devolvio -> cuanto quedo neto ->
        # como se concilia contra el cajon).
        #
        # Antes vivia DESPUES del resumen de ventas, mezclando dos
        # convenciones sin decirlo: "Ventas Totales" ya viene neteada por
        # `approve_return` (reescribe `sale.total_amount`), pero este bloque
        # de pagos es bruto (los `Payment` no se tocan). Una cajera que hacia
        # "Ventas Totales - Tarjeta - Devoluciones" restaba la devolucion DOS
        # VECES. "Total cobrado" deja el bruto explicito para que esa resta
        # ya no haga falta.
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== COBRADO POR METODO ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]

        _method_labels = [
            ('cash',         'Efectivo'),
            ('card',         'Tarjeta'),
            ('transfer',     'Transferencia'),
            ('store_credit', 'Credito Tienda'),
            ('check',        'Cheque'),
            ('others',       'Otros'),
        ]
        # `_total_cobrado` se acumula en la MISMA pasada que imprime los
        # renglones, sobre las mismas claves: no hay forma de que sume un
        # metodo que no se imprimio ni de que cuente uno dos veces. Es el
        # numero contra el que se resta "Devoluciones" para llegar a "Ventas
        # Totales", asi que tiene que cuadrar exacto con esa resta.
        # Comision de tarjeta cobrada al cliente en el turno. Informativa: YA
        # esta dentro de `payments['card']['total']` (el Payment de CARD se
        # guarda con ella incluida). `.get` con default para que un corte
        # reimpreso de antes de la funcion siga funcionando.
        _comision_tarjeta = audit_data.get('card_surcharges', 0) or 0

        _total_cobrado = 0.0
        for m_key, m_label in _method_labels:
            data = payments.get(m_key, {"total": 0, "count": 0})
            _total_cobrado += data.get('total') or 0
            if data['count'] > 0 or data['total'] > 0:
                line = f"{m_label} ({data['count']})"
                raw += self._rline(line, data['total'])
                # NO se suma a `_total_cobrado`: ya esta contada dentro de
                # `card`. Sumarla romperia la invariante del bloque -- el
                # desglose tiene que dar EXACTAMENTE el total, ni un peso mas.
                if m_key == 'card' and _comision_tarjeta > 0:
                    raw += self._rline("  incl. comision", _comision_tarjeta)
        raw += self._rline("Total cobrado", _total_cobrado)

        raw += self.CMD["LF"] + sep

        # --- 3. DEVOLUCIONES (si existen) ---
        returns_data = audit_data.get('returns', {})
        if returns_data.get('count', 0) > 0:
            raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
            raw += b"== DEVOLUCIONES ==\n"
            raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]

            # El DETALLE va primero, los TOTALES despues: el lector ve QUE se
            # devolvio antes que CUANTO en total. El conteo y el total no
            # dicen que se devolvio; el folio de la venta original es lo que
            # permite rastrearla y la marca "EFEC." separa las que afectan el
            # arqueo de las que no.
            for r in (returns_data.get('list') or []):
                raw += self._return_detail_line(r)

            raw += self._rline(f"Devoluciones ({returns_data['count']})", -returns_data['total'])
            # Subtotales por metodo de reembolso. "en efectivo" sale de
            # `cash_refunds` -- la cifra CANONICA del arqueo (los
            # `CashMovement` OUT que `compute_expected_cash` resta), no de
            # `by_method['cash']`, para que este renglon y el "Reembolsos (-)"
            # del arqueo no puedan discrepar. El resto sale de
            # `by_method` (suma de `total_refunded` agrupada por
            # `refund_method`). Un metodo sin devoluciones no imprime linea.
            _cash_refunds = returns_data.get('cash_refunds', 0) or 0
            _by_method = returns_data.get('by_method') or {}
            _subtotales = _cash_refunds
            if _cash_refunds > 0:
                raw += self._rline("  en efectivo", -_cash_refunds)
            for _rm_key, _rm_label in [('card', 'tarjeta'),
                                       ('transfer', 'transferencia'),
                                       ('other', 'otros')]:
                _rm_val = _by_method.get(_rm_key) or 0
                _subtotales += _rm_val
                if _rm_val > 0:
                    raw += self._rline(f"  en {_rm_label}", -_rm_val)
            # Residuo. "en efectivo" sale de `cash_refunds` (los CashMovement
            # OUT que resta el arqueo) y el resto de `by_method` (los
            # SaleReturn); en datos previos a la reasignacion de sesion que
            # hace `approve_return` los dos pueden vivir en cortes distintos y
            # entonces los subtotales NO suman el total. Imprimir el residuo
            # deja la columna cuadrada siempre y hace visible la anomalia en
            # vez de esconderla en una resta que no cierra.
            _residuo = round(returns_data['total'] - _subtotales, 2)
            if abs(_residuo) >= 0.01:
                raw += self._rline("  sin clasificar", -_residuo)

            # "Neto cobrado" = Total cobrado - Devoluciones. Cierta por
            # construccion (ambos sumandos salen de este mismo ticket), a
            # diferencia de "Ventas Totales", que es otra cifra y otra fuente
            # -- ver el comentario de VENTAS NETAS mas abajo.
            raw += self._rline("Neto cobrado", _total_cobrado - returns_data['total'])

            raw += self.CMD["LF"] + sep

        # --- 4. VENTAS NETAS ---
        # Aqui NO se imprime ninguna resta: "Ventas Totales" es
        # `SUM(sales_documents.total_amount)` ya neteado por `approve_return`,
        # y NO es igual a "Total cobrado - Devoluciones" en dos casos
        # deterministas:
        #   a) Con IVA. `SaleReturn.total_refunded` es PRE-IVA
        #      (app/crud/returns.py), mientras `approve_return` baja
        #      `sale.total_amount` por el pre-IVA MAS el IVA prorrateado. Al
        #      16%, una devolucion de $500 baja las ventas $580.
        #   b) Devolucion post-cierre o de otro dia: se ata a esta sesion
        #      (`cash_session_id`) pero netea el `total_amount` de una venta
        #      que pertenece al corte de otro dia.
        #   c) Con comision de tarjeta. La comision es dinero que entro por la
        #      terminal, asi que suma en "Total cobrado", pero NO es mercancia
        #      vendida: `total_amount` la excluye a proposito
        #      (app/services/card_surcharge.py), asi que NO suma en "Ventas
        #      Totales". Al 3.5%, un dia de $10,000 en tarjeta cobra $10,350 y
        #      vende $10,000.
        # La resta que SI es cierta por construccion ("Neto cobrado") cierra
        # el bloque de DEVOLUCIONES, justo arriba.
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== VENTAS NETAS ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]

        raw += self._rline("Ventas Totales", kpis['total_sales'])
        raw += f"Tickets: {kpis['total_tickets']}".rjust(self.cols).encode("latin-1") + b"\n"
        raw += self._rline("Ticket Promedio", kpis['avg_ticket'])
        raw += self._rline("Impuestos (IVA)", kpis['total_taxes'])

        raw += self.CMD["LF"] + sep

        # --- 5. FLUJO DE CAJA (ARQUEO) ---
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== ARQUEO DE CAJA ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
        
        # Etiquetas cortas a proposito: a 58mm (32 columnas) un importe de 8
        # cifras deja 18 caracteres para la etiqueta, y la guarda de ancho de
        # `_rline` recortaria en silencio ("Reembolsos Efec. (-:"). Estas
        # caben enteras en los dos anchos de papel, con cualquier importe que
        # un cajon real pueda tener.
        #
        # "Efec. cobrado (+)", no "Ventas Efectivo (+)": este importe es el
        # BRUTO cobrado en efectivo (ya neto de cambio entregado, ver
        # `breakdown.net_cash` en `get_session_audit_data`) -- el mismo numero
        # que abre el corte en COBRADO POR METODO. "Ventas" sugeria el neto
        # post-devolucion de VENTAS NETAS, y aqui la cuenta es la contraria:
        # los reembolsos se restan aparte, dos renglones mas abajo.
        raw += self._rline("Fondo Inicial (+)", session['opening_balance'])
        raw += self._rline("Efec. cobrado (+)", payments['cash']['total'])
        raw += self._rline("Entradas man. (+)", movements['inflows'])
        raw += self._rline("Salidas/Gastos (-)", movements['outflows'])
        if audit_data.get('returns', {}).get('cash_refunds', 0) > 0:
            raw += self._rline("Reembolsos (-)", -audit_data['returns']['cash_refunds'])
        
        dot_line = ("." * self.cols + "\n").encode("latin-1", "replace")
        raw += self.CMD["LF"] + dot_line
        raw += self.CMD["BOLD_ON"]
        raw += self._rline("ESPERADO CAJA", expected['cash_physical'])
        raw += self.CMD["BOLD_OFF"]
        raw += dot_line
        
        raw += self.CMD["LF"]
        raw += self._rline("REPORTADO", recon['reported'])
        
        diff = recon['difference']
        label = "DIFERENCIA"
        if diff < -0.01: label = "FALTANTE (-)"
        if diff > 0.01: label = "SOBRANTE (+)"
        
        raw += self.CMD["BOLD_ON"]
        raw += self._rline(label, diff)
        raw += self.CMD["BOLD_OFF"]
        
        raw += self.CMD["LF"] + sep

        # --- 6. MOVIMIENTOS DETALLE (Opcional, últimos 5) ---
        if movements['list']:
            raw += self.CMD["CENTER"] + b"ULTIMOS MOVIMIENTOS\n"
            raw += self.CMD["LEFT"]
            for m in movements['list'][-5:]:
                type_label = "ENTRADA" if m['type'] == "IN" else "SALIDA"
                line = f"{m['time']} {type_label} {self._format_currency(m['amount'])}".ljust(18) + f" {m['reason'][:28]}"
                raw += (line + "\n").encode("latin-1", "replace")
            raw += sep

        # --- 7. FIRMAS ---
        raw += self.CMD["LF"] * 2
        raw += self.CMD["CENTER"]
        raw += b"______________________\n"
        raw += b"Firma Cajero\n"
        raw += self.CMD["LF"]
        raw += b"______________________\n"
        raw += b"Firma Supervisor\n"

        raw += self.CMD["LF"] * 3
        if open_drawer:
            raw += self.CMD["DRAWER"]
        raw += self.CMD["CUT"]

        return raw

    def _format_currency(self, val: float) -> str:
        return f"${val:.2f}"

    # --- Helpers de formato ---
    def _rline(self, label: str, value: float) -> bytes:
        """Renglon etiqueta + importe, anclado al borde derecho del papel.

        El importe NUNCA se sacrifica: si la etiqueta no cabe se recorta
        desde la derecha. Una etiqueta corta sigue siendo legible; un importe
        que desborda el ancho se parte en dos renglones, descuadra la columna
        y deja un corte de caja ilegible justo donde hay que leer dinero.
        """
        amount = f"${value:.2f}"
        max_label = self.cols - len(amount) - 2  # 2 = ": "
        if max_label <= 0:
            # Papel absurdamente angosto o importe gigantesco: el importe
            # solo, sin etiqueta, sigue siendo mas util que ambos partidos.
            return (amount.rjust(self.cols) + "\n").encode("latin-1", "replace")
        if len(label) > max_label:
            label = label[:max_label].rstrip()
        txt = f"{label}: {amount}"
        return (txt.rjust(self.cols) + "\n").encode("latin-1", "replace")

    def _return_detail_line(self, r: dict) -> bytes:
        """Un renglon del detalle de devoluciones: hora, folio, marca de
        efectivo y el importe anclado a la derecha.

        Orden de sacrificio cuando no cabe todo: marca > folio > sangria
        cosmetica. El folio es todo-o-nada, nunca un prefijo: "A-21444"
        recortado a "A-21" es un folio DISTINTO pero igual de verosimil, y
        el supervisor que lo busque abriria otra venta real. La marca de
        efectivo es lo ultimo que se suelta porque un renglon de efectivo
        SIN marca miente (dice implicitamente "no toco el cajon").

        El importe se formatea igual que en `_rline` (`$-220.00`, sin
        separador de miles) para que las dos columnas del bloque de
        devoluciones — detalle y totales — se lean como la misma unidad.
        """
        amount = f"${-float(r.get('amount') or 0):.2f}"
        time = r.get('time') or ''
        # Devolucion aprobada en OTRA fecha (ruta `[POST-CLOSE]` de
        # `approve_return`: se aprueba hoy una devolucion cuya caja cerro
        # ayer). Una hora suelta se leeria como de esta jornada, asi que el
        # renglon lleva la fecha: "05/08 18:02" si cabe, y si no al menos un
        # "+" pegado a la hora ("18:02+") que diga "no es de hoy". El folio ya
        # se sacrifica solo para hacer sitio (ver mas abajo).
        if r.get('cross_day'):
            fecha = r.get('date')
            largo = f"{fecha} {time}" if fecha else f"{time}+"
            if self.cols - (len(largo) + 1 + len(amount)) >= 0:
                time = largo
            else:
                time = f"{time}+"
        # Margen calculado con el importe REAL de este renglon, nunca con una
        # cantidad de cifras asumida.
        remaining = max(self.cols - (len(time) + 1 + len(amount)), 0)

        tag = ""
        if r.get('is_cash'):
            if remaining >= 6:
                tag = " EFEC."      # 1 separador + 5 letras
            elif remaining >= 2:
                # "$" ya lo usa el importe del mismo renglon; "*" no colisiona
                # con nada mas que aparezca aqui (folio: letras/digitos/guion).
                tag = " *"
            elif remaining >= 1:
                tag = "*"           # sin separador -- el ultimo peldano
            remaining -= len(tag)

        folio_full = r.get('folio') or '-'
        if len(folio_full) + 1 <= remaining:
            folio = f" {folio_full}"
            remaining -= len(folio)
        else:
            folio = ""

        indent = "  " if remaining >= 2 else ""
        left = indent + time + folio + tag
        gap = max(self.cols - len(left) - len(amount), 0)
        return (left + " " * gap + amount + "\n").encode("latin-1", "replace")

    def _wrap_text(self, text: str, width: int) -> List[str]:
        if not text: return []
        if width <= 0: return [text]
        words = text.split()
        lines, cur = [], ""
        for w in words:
            # Split words that are longer than width
            while len(w) > width:
                chunk = w[:width]
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(chunk)
                w = w[width:]
            if len(cur) + len(w) + (1 if cur else 0) <= width:
                cur += (" " if cur else "") + w
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines

    def _wrap_line(self, text: str, indent: int) -> bytes:
        if len(text) <= self.cols: return (text + "\n").encode("latin-1", "replace")
        lines = self._wrap_text(text[indent:], self.cols - indent)
        res = (text[:indent] + lines[0] + "\n")
        for l in lines[1:]: res += (" " * indent) + l + "\n"
        return res.encode("latin-1", "replace")

    def build_test_ticket_bytes(self, organization, branch=None) -> bytes:
        """Ticket de prueba, brandeado ATLAS TECH.

        No es un ticket de venta: es la tarjeta de presentación del sistema en
        el momento en que la impresora queda lista. Lleva la marca del
        proveedor arriba y, como muestra, el negocio y la sucursal tal como
        saldrán en los tickets reales (mismo logo a 1/3 del ancho).
        """
        raw = b""
        sep = ("=" * self.cols + "\n").encode("latin-1", "replace")
        dash = ("-" * self.cols + "\n").encode("latin-1", "replace")

        def line(text: str) -> bytes:
            return (self._truncate(text, self.cols) + "\n").encode("latin-1", "replace")

        raw += self.CMD["INIT"] + self._default_font + self.CMD["SIZE_NORMAL"]
        raw += self.CMD["CENTER"]

        # Marca del proveedor
        raw += self.CMD["BOLD_ON"] + line("ATLAS TECH") + self.CMD["BOLD_OFF"]
        raw += line("Atlas One - Punto de venta")
        raw += line("atlasone.com.mx")
        raw += sep
        raw += self.CMD["BOLD_ON"] + line("IMPRESION DE PRUEBA") + self.CMD["BOLD_OFF"]
        raw += line(datetime.now(timezone.utc).astimezone(MX_TZ).strftime("%d/%m/%Y %H:%M"))
        raw += sep

        # Muestra: asi se vera el encabezado del negocio en los tickets reales
        effective_logo = (getattr(branch, 'logo_url', None) if branch else None) \
                         or (organization.logo_url if organization else None)
        if effective_logo:
            raw += self._generate_image_bytes(effective_logo)
        org_name = (organization.name if organization else None) or "Tu negocio"
        raw += self.CMD["BOLD_ON"] + line(org_name) + self.CMD["BOLD_OFF"]
        zone = (getattr(branch, 'city', None) or branch.name) if branch else None
        phone = (branch.phone if branch and branch.phone else (organization.phone if organization else None))
        if zone and phone:
            raw += line(f"{zone} | {phone}")
        elif zone:
            raw += line(zone)

        raw += self.CMD["LEFT"] + dash
        raw += line("Si puedes leer esto, la impresora")
        raw += line("esta configurada correctamente.")
        raw += line(f"Ancho de papel: {self.cols} columnas")
        raw += ("|" + "-" * (self.cols - 2) + "|\n").encode("latin-1", "replace")
        raw += dash

        raw += self.CMD["CENTER"]
        footer_text = None
        if branch and getattr(branch, 'ticket_footer', None):
            footer_text = branch.ticket_footer
        elif organization and organization.ticket_footer:
            footer_text = organization.ticket_footer
        if footer_text:
            raw += line(footer_text)
        raw += line("Impresora lista. Atlas Tech")
        raw += self.CMD["LEFT"]

        raw += self.CMD["LF"] * 3 + self.CMD["CUT"]
        return raw

    # Operational hardening (audit 2026-04-30 image-url):
    # H-3: cap remote logo download size — protects worker memory.
    # L-2: shorter timeout — slow logos must not block prints.
    _LOGO_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
    _LOGO_FETCH_TIMEOUT = 5            # seconds

    def _generate_image_bytes(self, image_path: str) -> bytes:
        """
        Generates ESC/POS GS v 0 raster bit image commands from an image file.
        Requires Pillow (PIL).
        """
        try:
            from PIL import Image, ImageOps
        except ImportError:
            logger.warning("logo skipped: Pillow not installed")
            return b""

        # H-2: defuse Pillow decompression bombs. A PNG declaring 100k × 100k
        # pixels (~40 GB at RGBA) would OOM the worker on Image.open(). Capping
        # at 25 MP covers any real logo with margin and makes Pillow raise
        # DecompressionBombError for malicious inputs.
        Image.MAX_IMAGE_PIXELS = 25_000_000

        # Strip cache-busting query string (?v=timestamp) before filesystem lookup.
        # If the URL stored in DB has a query string the path will never exist on disk.
        clean_path = image_path.split('?')[0]

        # Resolver: HTTP(S) → fetch a memoria; ruta local → leer del disco.
        # Cloudinary y CDNs externos devuelven URLs absolutas — Pillow no las abre
        # directamente, hay que descargarlas vía requests primero.
        im = None
        try:
            if clean_path.startswith(("http://", "https://")):
                import io
                import requests
                # Streamed fetch with size cap and content-type check (H-3 + M-1):
                # never read more than _LOGO_MAX_BYTES into memory, and reject
                # non-image responses before passing bytes to Pillow.
                # NOTE: redirects intentionally allowed because Cloudinary CDN
                # edges return 30x routinely. Proper SSRF defense (per-hop IP
                # allowlist) is Day 3 of the 2026-04-30 image-url-audit
                # roadmap — until then the size+ctype cap below is still the
                # last line of defense against malicious payloads at any hop.
                with requests.get(
                    image_path,
                    stream=True,
                    timeout=self._LOGO_FETCH_TIMEOUT,
                ) as resp:
                    resp.raise_for_status()
                    ctype = resp.headers.get("Content-Type", "")
                    if not ctype.lower().startswith("image/"):
                        logger.warning(
                            "logo rejected: non-image Content-Type %r for %s",
                            ctype, image_path,
                        )
                        return b""
                    declared_len = resp.headers.get("Content-Length")
                    if declared_len and int(declared_len) > self._LOGO_MAX_BYTES:
                        logger.warning(
                            "logo rejected: declared %s bytes > cap %s for %s",
                            declared_len, self._LOGO_MAX_BYTES, image_path,
                        )
                        return b""
                    buf = io.BytesIO()
                    total = 0
                    for chunk in resp.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > self._LOGO_MAX_BYTES:
                            logger.warning(
                                "logo rejected: stream exceeded cap %s for %s",
                                self._LOGO_MAX_BYTES, image_path,
                            )
                            return b""
                        buf.write(chunk)
                im = Image.open(buf)
                logger.info("logo resolved (CDN, %d bytes): %s", total, image_path)
            else:
                final_path = None
                if os.path.exists(clean_path):
                    final_path = clean_path
                else:
                    base_url = clean_path.lstrip("/")
                    for p in (base_url, f"app/{base_url}", os.path.join(os.getcwd(), "app", base_url)):
                        if os.path.exists(p):
                            final_path = p
                            break
                if not final_path:
                    logger.warning("logo not found on disk: %s (clean: %s)", image_path, clean_path)
                    return b""
                logger.info("logo resolved (disk): %s", final_path)
                im = Image.open(final_path)
        except Exception as e:
            logger.warning("logo fetch/open failed for %s: %s", image_path, e)
            return b""

        try:

            # 0. Flatten transparency onto a white background. PNG/WEBP with an
            # alpha channel often store transparent pixels with RGB=(255,255,255)
            # OR (0,0,0); a direct .convert('L') drops alpha and uses whatever
            # RGB happened to be there. With RGB=255 the background became white
            # → invert turned it BLACK → the printer rendered the whole rectangle
            # as ink. Compositing onto white guarantees transparent = no ink.
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])  # alpha as mask
                im = bg

            # 1. Resize logo to ~1/3 of the printable width (OXXO-style compact).
            #    Always scale (up OR down) so all branches' logos look uniform.
            paper_dots = self.PAPER_DOTS_80MM if self.paper_width_mm >= 80 else self.PAPER_DOTS_58MM
            target_width = (paper_dots // 3 // 8) * 8  # multiple of 8 for byte alignment
            if im.width != target_width:
                ratio = target_width / im.width
                new_height = max(1, int(im.height * ratio))
                im = im.resize((target_width, new_height), Image.Resampling.LANCZOS)

            # 2. Convert to Monochrome (ESC/POS bit-set = ink).
            im = im.convert('L')
            im = ImageOps.invert(im)
            im = im.convert('1')

            # 3. Center manually: pad the bitmap to the full paper width.
            #    Many cheap thermals ignore `ESC a 1` for raster images and
            #    always print from the left edge. Paddeing forces center.
            pad_left = ((paper_dots - target_width) // 2 // 8) * 8  # byte-aligned
            canvas = Image.new('1', (paper_dots, im.height), 0)  # 0 = no ink
            canvas.paste(im, (pad_left, 0))
            im = canvas

            # 4. Build GS v 0 Command
            width_bytes = (im.width + 7) // 8
            data = im.tobytes()

            header = b"\x1D\x76\x30\x00"
            xL = width_bytes % 256
            xH = width_bytes // 256
            yL = im.height % 256
            yH = im.height // 256

            cmd = self.CMD["CENTER"] + header + bytes([xL, xH, yL, yH]) + data + b"\x1B\x4A\x10"
            return cmd

        except Exception as e:
            logger.exception("logo rasterize failed for %s: %s", final_path, e)
            return b""