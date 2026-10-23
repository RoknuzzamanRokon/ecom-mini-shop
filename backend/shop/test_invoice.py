"""
The order invoice PDF (TASK-010): database text is printed literally
(BUG-019), and the balance due is right for cancelled and refunded orders
(BUG-020).

The PDF is built in memory. Its text is read from the Paragraphs the builder
creates, after ReportLab has parsed their markup: that is exactly what gets
drawn, and it needs no PDF text extractor.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from reportlab.platypus import Paragraph

from shop import invoice
from shop.models import Order, OrderItem
from shop.payment_service import PaymentService

User = get_user_model()

MARKUP_NAME = "<b>Rahim & Sons"
LINK_PRODUCT = '<a href="https://evil.example/pay">Click to pay</a>'
IMAGE_REASON = '<img src="/etc/passwd"/> refund'


class InvoiceTestCase(TestCase):
    def make_order(self, **fields):
        customer = User.objects.create_user(username=f"inv_customer_{Order.objects.count()}", password="Invoice-Test-1")
        values = dict(
            user=customer,
            order_number=f"ORD-INVOICE-{Order.objects.count()}",
            status=Order.STATUS_PENDING,
            customer_name="Plain Name",
            shipping_recipient_name="Plain Name",
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
        )
        values.update(fields)
        order = Order.objects.create(**values)
        OrderItem.objects.create(
            order=order, product_name="Desk Lamp", unit_price=Decimal("1000.00"),
            quantity=1, line_total=Decimal("1000.00"),
        )
        return order

    def pay(self, order):
        payment = PaymentService.create_or_get_payment(order=order, payment_method="CARD")
        return PaymentService.process_payment_success(payment, transaction_id=f"TXN-{order.pk}")

    def build(self, order):
        """The PDF bytes, and the text each Paragraph renders."""
        texts = []

        def recording_paragraph(*args, **kwargs):
            paragraph = Paragraph(*args, **kwargs)
            # Read before layout, which reshapes the fragments.
            texts.append("".join(getattr(frag, "text", "") for frag in paragraph.frags))
            return paragraph

        with mock.patch("shop.invoice.Paragraph", side_effect=recording_paragraph):
            pdf = invoice.build_order_invoice_pdf(order)
        return pdf, texts

    def balance_text(self, texts):
        return texts[texts.index("Balance due") + 1]


class InvoiceEscapingTests(InvoiceTestCase):
    def test_markup_in_database_text_is_printed_literally(self):
        order = self.make_order(
            customer_name=MARKUP_NAME,
            shipping_recipient_name=MARKUP_NAME,
            shipping_address_line_1="House <12> & Road 4",
            shipping_phone="<u>01700</u>",
        )
        order.items.update(product_name=LINK_PRODUCT, shop_name="Shop <i>", seller_name="Seller & Co")
        payment = self.pay(order)
        PaymentService.process_refund(payment=payment, amount=Decimal("100.00"), reason=IMAGE_REASON)

        pdf, texts = self.build(order)  # an unclosed <b> used to raise here

        self.assertTrue(pdf.startswith(b"%PDF"))
        for literal in (MARKUP_NAME, "House <12> & Road 4", "<u>01700</u>",
                        LINK_PRODUCT, IMAGE_REASON):
            with self.subTest(literal=literal):
                self.assertIn(literal, texts)
        self.assertIn("Shop <i> · Seller & Co", texts)
        # No clickable link annotation was injected into the document.
        self.assertNotIn(b"/URI", pdf)


class InvoiceBalanceTests(InvoiceTestCase):
    def test_unpaid_open_order_owes_the_total(self):
        order = self.make_order()
        self.assertEqual(invoice.balance_due(order), Decimal("1000.00"))
        _, texts = self.build(order)
        self.assertIn("1,000.00", self.balance_text(texts))

    def test_paid_order_owes_nothing(self):
        order = self.make_order()
        self.pay(order)
        self.assertEqual(invoice.balance_due(order), Decimal("0.00"))

    def test_a_partial_refund_is_not_billed_again(self):
        order = self.make_order(status=Order.STATUS_DELIVERED)
        payment = self.pay(order)
        PaymentService.process_refund(payment=payment, amount=Decimal("200.00"), reason="Damaged box")
        self.assertEqual(invoice.balance_due(order), Decimal("0.00"))

    def test_cancelled_and_refunded_order_owes_nothing(self):
        order = self.make_order()
        payment = self.pay(order)
        PaymentService.process_refund(payment=payment, amount=Decimal("1000.00"), reason="Cancelled")
        Order.objects.filter(pk=order.pk).update(status=Order.STATUS_CANCELLED)
        order.refresh_from_db()

        self.assertEqual(invoice.balance_due(order), Decimal("0.00"))
        _, texts = self.build(order)
        self.assertIn("0.00", self.balance_text(texts))
        self.assertNotIn("1,000.00", self.balance_text(texts))

    def test_cancelled_unpaid_order_owes_nothing(self):
        order = self.make_order(status=Order.STATUS_CANCELLED)
        self.assertEqual(invoice.balance_due(order), Decimal("0.00"))
