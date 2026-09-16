"""
Order invoice / voucher PDF generation.

Built on reportlab's platypus layer rather than an HTML-to-PDF converter: the
document is a fixed, tabular commercial form, so laying it out directly is both
smaller in dependencies (no native GTK/Pango stack) and exact about column
widths, page breaks and the "Page X of Y" stamp.

Currency is the Bangladeshi Taka throughout, per the project rule. The Taka sign
(U+09F3) is absent from reportlab's built-in Type1 fonts, so `resolve_fonts()`
looks for a TrueType face that actually carries the glyph and only then uses it;
without one the amounts read "Tk" rather than rendering a row of black boxes.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Palette lifted from static/css/japanese_admin.css so the document and the
# admin panel read as one system.
INK = colors.HexColor("#19232D")
INK_BODY = colors.HexColor("#4A5568")
INK_MUTED = colors.HexColor("#8291A0")
KACHI = colors.HexColor("#21486B")
KACHI_DEEP = colors.HexColor("#132B40")
GOLD = colors.HexColor("#BA8630")
RULE = colors.HexColor("#DCD7CC")
RULE_SOFT = colors.HexColor("#EDEAE3")
BAND = colors.HexColor("#F4F2EC")

PAGE_SIZE = A4
MARGIN_X = 16 * mm
MARGIN_TOP = 14 * mm
MARGIN_BOTTOM = 18 * mm

TAKA_SIGN = "\u09f3"

# Candidate faces, in preference order. A project-bundled font wins over
# whatever the host happens to ship, so a deployment can pin the look by
# dropping a file into static/fonts/.
_FONT_CANDIDATES = (
    # (regular path, bold path, subfont index)
    ("static/fonts/NotoSansBengali-Regular.ttf", "static/fonts/NotoSansBengali-Bold.ttf", 0),
    ("static/fonts/Nirmala.ttf", "static/fonts/NirmalaB.ttf", 0),
    (r"C:\Windows\Fonts\Nirmala.ttc", r"C:\Windows\Fonts\Nirmala.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
     "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
     "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf", 0),
    ("/Library/Fonts/Bangla Sangam MN.ttc", "/Library/Fonts/Bangla Sangam MN.ttc", 0),
)


@dataclass(frozen=True)
class FontSet:
    """The faces the document draws with, and whether they carry the Taka sign."""

    regular: str
    bold: str
    has_taka: bool

    @property
    def currency_prefix(self) -> str:
        return TAKA_SIGN if self.has_taka else "Tk"


def _absolute(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(str(settings.BASE_DIR), path)


def _covers_taka(font: TTFont) -> bool:
    try:
        return ord(TAKA_SIGN) in font.face.charToGlyph
    except Exception:
        return False


@lru_cache(maxsize=1)
def resolve_fonts() -> FontSet:
    """
    Register and return the best available font pair.

    Cached for the process: probing a .ttc parses the whole font table, and the
    answer cannot change while the process lives.
    """
    for regular_path, bold_path, index in _FONT_CANDIDATES:
        regular_abs = _absolute(regular_path)
        if not os.path.exists(regular_abs):
            continue
        try:
            regular = TTFont("MiniShopBody", regular_abs, subfontIndex=index)
            if not _covers_taka(regular):
                continue
            pdfmetrics.registerFont(regular)

            bold_abs = _absolute(bold_path)
            bold_name = "MiniShopBody"
            if os.path.exists(bold_abs):
                try:
                    bold = TTFont("MiniShopBodyBold", bold_abs, subfontIndex=index)
                    pdfmetrics.registerFont(bold)
                    bold_name = "MiniShopBodyBold"
                except Exception:
                    bold_name = "MiniShopBody"
            # A single-face fallback still needs a bold slot for the styles
            # below; reportlab maps the family so <b> resolves predictably.
            pdfmetrics.registerFontFamily(
                "MiniShopBody",
                normal="MiniShopBody",
                bold=bold_name,
                italic="MiniShopBody",
                boldItalic=bold_name,
            )
            return FontSet(regular="MiniShopBody", bold=bold_name, has_taka=True)
        except Exception:
            # A candidate that fails to parse is simply not a candidate.
            continue

    return FontSet(regular="Helvetica", bold="Helvetica-Bold", has_taka=False)


def money(amount, fonts: FontSet, *, with_symbol: bool = True) -> str:
    """Formats a Decimal as a grouped two-decimal amount, Taka-prefixed."""
    value = Decimal(amount or 0).quantize(Decimal("0.01"))
    text = f"{value:,.2f}"
    if not with_symbol:
        return text
    return f"{fonts.currency_prefix} {text}"


def _styles(fonts: FontSet) -> dict[str, ParagraphStyle]:
    base = dict(fontName=fonts.regular, textColor=INK_BODY, leading=11.5, fontSize=8.5)
    return {
        "wordmark": ParagraphStyle(
            "wordmark", fontName=fonts.bold, fontSize=19, leading=21,
            textColor=colors.white,
        ),
        "wordmark_sub": ParagraphStyle(
            "wordmark_sub", fontName=fonts.regular, fontSize=7.5, leading=10,
            textColor=colors.HexColor("#A9C4DC"),
        ),
        "doctype": ParagraphStyle(
            "doctype", fontName=fonts.bold, fontSize=15, leading=17,
            textColor=colors.white, alignment=TA_RIGHT,
        ),
        "doctype_sub": ParagraphStyle(
            "doctype_sub", fontName=fonts.regular, fontSize=8, leading=11,
            textColor=colors.HexColor("#A9C4DC"), alignment=TA_RIGHT,
        ),
        "label": ParagraphStyle(
            "label", fontName=fonts.bold, fontSize=6.8, leading=9,
            textColor=INK_MUTED,
        ),
        "value": ParagraphStyle("value", **base),
        "value_strong": ParagraphStyle(
            "value_strong", fontName=fonts.bold, fontSize=8.5, leading=11.5,
            textColor=INK,
        ),
        "section": ParagraphStyle(
            "section", fontName=fonts.bold, fontSize=8, leading=11,
            textColor=KACHI,
        ),
        "cell": ParagraphStyle("cell", **base),
        "cell_strong": ParagraphStyle(
            "cell_strong", fontName=fonts.bold, fontSize=8.5, leading=11.5,
            textColor=INK,
        ),
        "cell_muted": ParagraphStyle(
            "cell_muted", fontName=fonts.regular, fontSize=7.2, leading=9.5,
            textColor=INK_MUTED,
        ),
        "num": ParagraphStyle("num", alignment=TA_RIGHT, **base),
        "num_strong": ParagraphStyle(
            "num_strong", fontName=fonts.bold, fontSize=8.5, leading=11.5,
            textColor=INK, alignment=TA_RIGHT,
        ),
        "th": ParagraphStyle(
            "th", fontName=fonts.bold, fontSize=7, leading=9.5,
            textColor=colors.white,
        ),
        "th_num": ParagraphStyle(
            "th_num", fontName=fonts.bold, fontSize=7, leading=9.5,
            textColor=colors.white, alignment=TA_RIGHT,
        ),
        "note": ParagraphStyle(
            "note", fontName=fonts.regular, fontSize=7, leading=9.5,
            textColor=INK_MUTED,
        ),
        "empty": ParagraphStyle(
            "empty", fontName=fonts.regular, fontSize=8, leading=11,
            textColor=INK_MUTED, alignment=TA_CENTER,
        ),
    }


def _fmt_dt(value) -> str:
    if not value:
        return "\u2014"
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p")


def _fmt_date(value) -> str:
    if not value:
        return "\u2014"
    return timezone.localtime(value).strftime("%d %b %Y")


def _shipping_lines(order) -> list[str]:
    """Address snapshot first, legacy flat fields as the fallback."""
    street = [order.shipping_address_line_1, order.shipping_address_line_2]
    locality = [order.shipping_area, order.shipping_city]
    region = [order.shipping_state, order.shipping_postal_code]

    lines = [part.strip() for part in street if part and part.strip()]
    for group in (locality, region):
        joined = ", ".join(part.strip() for part in group if part and part.strip())
        if joined:
            lines.append(joined)
    if order.shipping_country:
        lines.append(order.shipping_country)

    if not lines and order.address:
        lines = [chunk.strip() for chunk in order.address.splitlines() if chunk.strip()]
        if order.city:
            lines.append(order.city)
    return lines


class _InvoiceCanvas(pdfcanvas.Canvas):
    """
    Buffers pages so the footer can print the true total page count.

    reportlab draws each page as it is laid out, so "Page 1 of 3" is unknowable
    at draw time. Holding the page states and emitting them in `save()` is the
    standard way around it.
    """

    def __init__(self, *args, footer_text: str = "", fonts: FontSet | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []
        self._footer_text = footer_text
        self._fonts = fonts or FontSet("Helvetica", "Helvetica-Bold", False)

    def showPage(self):  # noqa: N802 - reportlab API
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        self._saved_states = []
        super().save()

    def _draw_footer(self, total_pages: int):
        width, _ = PAGE_SIZE
        y = MARGIN_BOTTOM - 6 * mm

        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, y + 5 * mm, width - MARGIN_X, y + 5 * mm)

        self.setFont(self._fonts.regular, 6.8)
        self.setFillColor(INK_MUTED)
        self.drawString(MARGIN_X, y, self._footer_text)
        self.drawRightString(
            width - MARGIN_X, y, f"Page {self._pageNumber} of {total_pages}"
        )


def _status_watermark(order):
    """Diagonal stamp for orders that are no longer commercially live."""
    status = (order.status or "").upper()
    if status != "CANCELLED":
        return None
    return "CANCELLED"


def _make_page_decorator(order, fonts: FontSet):
    watermark = _status_watermark(order)

    def decorate(canvas_obj, _doc):
        if not watermark:
            return
        width, height = PAGE_SIZE
        canvas_obj.saveState()
        canvas_obj.translate(width / 2, height / 2)
        canvas_obj.rotate(38)
        canvas_obj.setFont(fonts.bold, 68)
        canvas_obj.setFillColor(colors.HexColor("#E11D48"))
        canvas_obj.setFillAlpha(0.08)
        canvas_obj.drawCentredString(0, 0, watermark)
        canvas_obj.restoreState()

    return decorate


def _masthead(order, fonts: FontSet, st: dict, content_width: float) -> Table:
    left = [
        Paragraph("MINISHOP", st["wordmark"]),
        Paragraph("Online Marketplace &middot; Bangladesh", st["wordmark_sub"]),
    ]
    right = [
        Paragraph("ORDER INVOICE", st["doctype"]),
        Paragraph(order.order_number or f"Order #{order.pk}", st["doctype_sub"]),
    ]
    table = Table(
        [[left, right]],
        colWidths=[content_width * 0.55, content_width * 0.45],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), KACHI_DEEP),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    return table


def _meta_strip(order, fonts: FontSet, st: dict, content_width: float) -> Table:
    payment = order.current_payment
    paid_state = "Paid" if order.is_paid else "Unpaid"
    if order.total_refunded_amount > 0:
        paid_state = "Refunded" if order.refundable_amount <= 0 else "Partially refunded"

    cells = [
        ("Order number", order.order_number or f"#{order.pk}"),
        ("Order date", _fmt_date(order.created_at)),
        ("Order status", order.get_status_display()),
        ("Payment", paid_state),
        ("Method", payment.get_payment_method_display() if payment else "\u2014"),
    ]
    header = [Paragraph(label.upper(), st["label"]) for label, _ in cells]
    values = [Paragraph(str(value), st["value_strong"]) for _, value in cells]

    # Proportional, not equal: the order number is the longest value on the
    # strip and wrapped onto a second line at 1/5 of the width.
    ratios = (0.26, 0.16, 0.17, 0.20, 0.21)
    table = Table(
        [header, values],
        colWidths=[content_width * ratio for ratio in ratios],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, RULE),
    ]))
    return table


def _party_block(order, fonts: FontSet, st: dict, content_width: float) -> Table:
    account = order.user
    billed = [Paragraph("BILLED TO", st["label"]), Spacer(1, 3)]
    billed.append(Paragraph(
        order.customer_name or order.shipping_recipient_name or "\u2014",
        st["value_strong"],
    ))
    for line in (order.phone or order.shipping_phone, getattr(account, "email", "")):
        if line:
            billed.append(Paragraph(str(line), st["value"]))
    if account:
        billed.append(Paragraph(f"Account: {account.get_username()}", st["cell_muted"]))

    shipped = [Paragraph("SHIP TO", st["label"]), Spacer(1, 3)]
    shipped.append(Paragraph(
        order.shipping_recipient_name or order.customer_name or "\u2014",
        st["value_strong"],
    ))
    if order.shipping_phone:
        shipped.append(Paragraph(order.shipping_phone, st["value"]))
    for line in _shipping_lines(order):
        shipped.append(Paragraph(line, st["value"]))

    half = content_width / 2
    table = Table([[billed, shipped]], colWidths=[half, half])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, RULE_SOFT),
    ]))
    return table


def _items_table(order, fonts: FontSet, st: dict, content_width: float) -> Table:
    widths = [
        content_width * 0.06,
        content_width * 0.46,
        content_width * 0.16,
        content_width * 0.10,
        content_width * 0.22,
    ]
    rows = [[
        Paragraph("#", st["th"]),
        Paragraph("ITEM", st["th"]),
        Paragraph("UNIT PRICE", st["th_num"]),
        Paragraph("QTY", st["th_num"]),
        Paragraph("LINE TOTAL", st["th_num"]),
    ]]

    items = list(order.items.all())
    for index, item in enumerate(items, start=1):
        origin = " \u00b7 ".join(
            part for part in (item.shop_name, item.seller_name) if part
        )
        cell = [Paragraph(item.product_name or "\u2014", st["cell_strong"])]
        if origin:
            cell.append(Paragraph(origin, st["cell_muted"]))
        rows.append([
            Paragraph(str(index), st["cell"]),
            cell,
            Paragraph(money(item.unit_price or item.price, fonts), st["num"]),
            Paragraph(str(item.quantity), st["num"]),
            Paragraph(money(item.line_total or item.subtotal, fonts), st["num_strong"]),
        ])

    if not items:
        rows.append([Paragraph("This order has no line items.", st["empty"]), "", "", "", ""])

    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), KACHI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, RULE_SOFT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, RULE),
    ]
    if not items:
        style.append(("SPAN", (0, 1), (-1, 1)))
    else:
        for row in range(2, len(rows), 2):
            style.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#FBFAF7")))
    table.setStyle(TableStyle(style))
    return table


def _totals_table(order, fonts: FontSet, st: dict, content_width: float) -> Table:
    paid = order.total_paid_amount
    refunded = order.total_refunded_amount
    balance = (order.total_amount or Decimal("0.00")) - paid + refunded

    discount = order.discount_total or Decimal("0.00")
    lines = [
        ("Subtotal", money(order.subtotal, fonts), False),
        # A deduction reads as "- Tk 400.00"; money() would render the signed
        # Decimal as "Tk -400.00", with the sign stranded after the symbol.
        ("Discount",
         f"− {money(discount, fonts)}" if discount > 0 else money(discount, fonts),
         False),
        ("Shipping fee", money(order.shipping_fee, fonts), False),
        ("Grand total", money(order.total_amount, fonts), True),
        ("Amount paid", money(paid, fonts), False),
    ]
    if refunded > 0:
        lines.append(("Refunded", money(refunded, fonts), False))
    lines.append(("Balance due", money(balance, fonts), True))

    rows = []
    for label, value, strong in lines:
        rows.append([
            Paragraph(label, st["cell_strong"] if strong else st["cell"]),
            Paragraph(value, st["num_strong"] if strong else st["num"]),
        ])

    table = Table(rows, colWidths=[content_width * 0.58, content_width * 0.42])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, RULE_SOFT),
    ]
    # Grand total and balance due are the two rows a reader looks for.
    for offset, (label, _formatted, strong) in enumerate(lines):
        if not strong:
            continue
        band = BAND if label == "Grand total" else colors.HexColor("#FDF6E8")
        style.append(("BACKGROUND", (0, offset), (-1, offset), band))
    style.append(("LINEABOVE", (0, len(lines) - 1), (-1, len(lines) - 1), 0.7, GOLD))
    table.setStyle(TableStyle(style))
    return table


def _ledger_table(title, header, rows, st, content_width, widths) -> list:
    if not rows:
        return []
    head = [Paragraph(text, st["th_num"] if align == "r" else st["th"])
            for text, align in header]
    table = Table([head] + rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5A6B7C")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, RULE_SOFT),
    ]))
    return [
        Spacer(1, 9 * mm),
        Paragraph(title, st["section"]),
        Spacer(1, 3 * mm),
        table,
    ]


def _payments_section(order, fonts: FontSet, st: dict, content_width: float) -> list:
    rows = []
    for payment in order.payments.all().order_by("created_at"):
        rows.append([
            Paragraph(payment.payment_number, st["cell_strong"]),
            Paragraph(payment.get_payment_method_display(), st["cell"]),
            Paragraph(payment.transaction_id or "\u2014", st["cell"]),
            Paragraph(payment.get_status_display(), st["cell"]),
            Paragraph(_fmt_dt(payment.paid_at or payment.created_at), st["cell"]),
            Paragraph(money(payment.amount, fonts), st["num_strong"]),
        ])
    header = [("PAYMENT NO.", "l"), ("METHOD", "l"), ("REFERENCE", "l"),
              ("STATUS", "l"), ("DATE", "l"), ("AMOUNT", "r")]
    widths = [content_width * w for w in (0.19, 0.17, 0.17, 0.13, 0.19, 0.15)]
    return _ledger_table("PAYMENT RECORDS", header, rows, st, content_width, widths)


def _refunds_section(order, fonts: FontSet, st: dict, content_width: float) -> list:
    rows = []
    for refund in order.refunds.all().order_by("created_at"):
        rows.append([
            Paragraph(refund.refund_number, st["cell_strong"]),
            Paragraph(refund.payment.payment_number if refund.payment_id else "\u2014", st["cell"]),
            Paragraph(refund.reason or "\u2014", st["cell"]),
            Paragraph(refund.get_status_display(), st["cell"]),
            Paragraph(_fmt_dt(refund.created_at), st["cell"]),
            Paragraph(money(refund.amount, fonts), st["num_strong"]),
        ])
    header = [("REFUND NO.", "l"), ("AGAINST", "l"), ("REASON", "l"),
              ("STATUS", "l"), ("DATE", "l"), ("AMOUNT", "r")]
    widths = [content_width * w for w in (0.18, 0.18, 0.23, 0.11, 0.15, 0.15)]
    return _ledger_table("REFUND RECORDS", header, rows, st, content_width, widths)


def invoice_filename(order) -> str:
    """`invoice-<order number>.pdf`, with the pk as the fallback identifier."""
    raw = (order.order_number or "").strip() or f"order-{order.pk}"
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in raw)
    return f"invoice-{safe.strip('-') or order.pk}.pdf"


def build_order_invoice_pdf(order, *, generated_by=None) -> bytes:
    """Renders the order as a single-file invoice PDF and returns its bytes."""
    fonts = resolve_fonts()
    st = _styles(fonts)

    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    content_width = width - (2 * MARGIN_X)

    issuer = ""
    if generated_by is not None:
        issuer = f"  \u00b7  Issued by {generated_by.get_username()}"
    footer_text = (
        f"{order.order_number or order.pk}  \u00b7  "
        f"Generated {_fmt_dt(timezone.now())}{issuer}  \u00b7  "
        "Computer-generated document"
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"Invoice {order.order_number or order.pk}",
        author="MiniShop",
        subject=f"Order invoice for {order.order_number or order.pk}",
    )
    frame = Frame(
        MARGIN_X, MARGIN_BOTTOM, content_width,
        height - MARGIN_TOP - MARGIN_BOTTOM,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="body",
    )
    doc.addPageTemplates([
        PageTemplate(id="invoice", frames=[frame],
                     onPage=_make_page_decorator(order, fonts)),
    ])

    story = [
        _masthead(order, fonts, st, content_width),
        Spacer(1, 4 * mm),
        _meta_strip(order, fonts, st, content_width),
        Spacer(1, 9 * mm),
        _party_block(order, fonts, st, content_width),
        Spacer(1, 9 * mm),
        Paragraph("ORDER ITEMS", st["section"]),
        Spacer(1, 3 * mm),
        _items_table(order, fonts, st, content_width),
        Spacer(1, 6 * mm),
    ]

    totals = _totals_table(order, fonts, st, content_width * 0.46)
    totals_row = Table(
        [[
            Paragraph(
                "All amounts are in Bangladeshi Taka (BDT). "
                "Line totals are the server-authoritative values recorded at "
                "the time the order was placed.",
                st["note"],
            ),
            totals,
        ]],
        colWidths=[content_width * 0.52, content_width * 0.48],
    )
    totals_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
        ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 16),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether(totals_row))

    story.extend(_payments_section(order, fonts, st, content_width))
    story.extend(_refunds_section(order, fonts, st, content_width))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _InvoiceCanvas(
            *a, footer_text=footer_text, fonts=fonts, **kw
        ),
    )
    return buffer.getvalue()
