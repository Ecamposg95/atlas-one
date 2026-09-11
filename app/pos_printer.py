# app/pos_printer.py
from __future__ import annotations
import os
import logging
import platform
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")
from typing import List, Optional
from decimal import Decimal

# Importamos tus modelos reales
from app.models import SalesDocument, Payment, SalesLineItem

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
                    p_name = "Producto"
                    if item.variant and item.variant.product:
                        p_name = item.variant.product.name
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

        # --- 4. PAYMENT (1 line single, N lines mixed) ---
        raw += self._payment_block(method, float(paid), float(change), payments_detail)

        # --- 5. REPRINT marker + footer ---
        if is_reprint:
            raw += self.CMD["CENTER"] + b"*** REIMPRESION ***\n" + self.CMD["LEFT"]

        footer_msg = self._resolve_footer(organization, branch)
        if footer_msg:
            raw += self.CMD["CENTER"]
            footer_full = f"{footer_msg} | rmazh.mx"
            if len(footer_full) > self.cols:
                footer_full = footer_msg[: self.cols - 12].rstrip() + " | rmazh.mx"
            raw += (footer_full + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

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
        # prepend as "LEGAL | NAME" (e.g. "RMAZH | EL MUNDO DE LA TAZA").
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

        # Footer
        footer_msg = self._resolve_footer(organization, branch)
        if footer_msg:
            raw += self.CMD["CENTER"]
            footer_full = f"{footer_msg} | rmazh.mx"
            if len(footer_full) > self.cols:
                footer_full = footer_msg[: self.cols - 12].rstrip() + " | rmazh.mx"
            raw += (footer_full + "\n").encode("latin-1", "replace")
            raw += self.CMD["LEFT"]

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

        # --- 2. RESUMEN DE VENTAS ---
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== RESUMEN DE VENTAS ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
        
        raw += self._rline("Ventas Totales", kpis['total_sales'])
        raw += f"Tickets: {kpis['total_tickets']}".rjust(self.cols).encode("latin-1") + b"\n"
        raw += self._rline("Ticket Promedio", kpis['avg_ticket'])
        raw += self._rline("Impuestos (IVA)", kpis['total_taxes'])
        
        raw += self.CMD["LF"] + sep

        # --- 2.5 DEVOLUCIONES (si existen) ---
        returns_data = audit_data.get('returns', {})
        if returns_data.get('count', 0) > 0:
            raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
            raw += b"== DEVOLUCIONES ==\n"
            raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
            raw += self._rline(f"Devoluciones ({returns_data['count']})", -returns_data['total'])
            if returns_data.get('cash_refunds', 0) > 0:
                raw += self._rline("  Efectivo devuelto", -returns_data['cash_refunds'])
            raw += self.CMD["LF"] + sep

        # --- 3. POR METODO DE PAGO ---
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== POR METODO DE PAGO ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
        
        _method_labels = [
            ('cash',         'Efectivo'),
            ('card',         'Tarjeta'),
            ('transfer',     'Transferencia'),
            ('store_credit', 'Credito Tienda'),
            ('check',        'Cheque'),
            ('others',       'Otros'),
        ]
        for m_key, m_label in _method_labels:
            data = payments.get(m_key, {"total": 0, "count": 0})
            if data['count'] > 0 or data['total'] > 0:
                line = f"{m_label} ({data['count']})"
                raw += self._rline(line, data['total'])
            
        raw += self.CMD["LF"] + sep

        # --- 4. FLUJO DE CAJA (ARQUEO) ---
        raw += self.CMD["CENTER"] + self.CMD["BOLD_ON"]
        raw += b"== ARQUEO DE CAJA ==\n"
        raw += self.CMD["BOLD_OFF"] + self.CMD["LEFT"]
        
        raw += self._rline("Fondo Inicial (+)", session['opening_balance'])
        raw += self._rline("Ventas Efectivo (+)", payments['cash']['total'])
        raw += self._rline("Entradas manual (+)", movements['inflows'])
        raw += self._rline("Salidas/Gastos (-)", movements['outflows'])
        if audit_data.get('returns', {}).get('cash_refunds', 0) > 0:
            raw += self._rline("Reembolsos Efec. (-)", -audit_data['returns']['cash_refunds'])
        
        dot_line = ("." * self.cols + "\n").encode("latin-1", "replace")
        raw += self.CMD["LF"] + dot_line
        raw += self.CMD["BOLD_ON"]
        raw += self._rline("ESPERADO CAJA", expected['cash_physical'])
        raw += self.CMD["BOLD_OFF"]
        raw += dot_line
        
        raw += self.CMD["LF"]
        raw += self._rline("REPORTADO (CONTADO)", recon['reported'])
        
        diff = recon['difference']
        label = "DIFERENCIA"
        if diff < -0.01: label = "FALTANTE (-)"
        if diff > 0.01: label = "SOBRANTE (+)"
        
        raw += self.CMD["BOLD_ON"]
        raw += self._rline(label, diff)
        raw += self.CMD["BOLD_OFF"]
        
        raw += self.CMD["LF"] + sep

        # --- 5. MOVIMIENTOS DETALLE (Opcional, últimos 5) ---
        if movements['list']:
            raw += self.CMD["CENTER"] + b"ULTIMOS MOVIMIENTOS\n"
            raw += self.CMD["LEFT"]
            for m in movements['list'][-5:]:
                type_label = "ENTRADA" if m['type'] == "IN" else "SALIDA"
                line = f"{m['time']} {type_label} {self._format_currency(m['amount'])}".ljust(18) + f" {m['reason'][:28]}"
                raw += (line + "\n").encode("latin-1", "replace")
            raw += sep

        # --- 6. FIRMAS ---
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
        txt = f"{label}: ${value:.2f}"
        return (txt.rjust(self.cols) + "\n").encode("latin-1", "replace")

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
        """Test ticket — uses the same compact header so the cashier sees
        exactly what real tickets will look like (including 1/3-width logo)."""
        raw = b""
        sep = ("-" * self.cols + "\n").encode("latin-1", "replace")

        raw += self.CMD["INIT"] + self._default_font + self.CMD["SIZE_NORMAL"]
        raw += self.CMD["CENTER"]

        # Logo (branch overrides org)
        effective_logo = (getattr(branch, 'logo_url', None) if branch else None) \
                         or (organization.logo_url if organization else None)
        if effective_logo:
            raw += self._generate_image_bytes(effective_logo)

        org_name = (organization.name if organization else None) or "ATLAS POS"
        raw += self.CMD["BOLD_ON"]
        raw += (self._truncate(org_name, self.cols) + "\n").encode("latin-1", "replace")
        raw += self.CMD["BOLD_OFF"]

        zone = (getattr(branch, 'city', None) or branch.name) if branch else None
        phone = (branch.phone if branch and branch.phone else (organization.phone if organization else None))
        if zone and phone:
            raw += (self._truncate(f"{zone} | {phone}", self.cols) + "\n").encode("latin-1", "replace")
        elif zone:
            raw += (self._truncate(zone, self.cols) + "\n").encode("latin-1", "replace")

        raw += b"IMPRESION DE PRUEBA\n"
        raw += self.CMD["LEFT"] + sep
        raw += b"Si puedes leer esto, la impresora\n"
        raw += b"esta configurada correctamente.\n"
        raw += sep

        # Footer (org/branch override)
        footer_text = None
        if branch and getattr(branch, 'ticket_footer', None):
            footer_text = branch.ticket_footer
        elif organization and organization.ticket_footer:
            footer_text = organization.ticket_footer
        if footer_text:
            raw += self.CMD["CENTER"]
            raw += (self._truncate(f"{footer_text} | rmazh.mx", self.cols) + "\n").encode("latin-1", "replace")

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