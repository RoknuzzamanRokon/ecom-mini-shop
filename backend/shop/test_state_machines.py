"""
TASK-043: the order and payment state machines, every status against every
other, compared with tables written out here rather than read from the
models. Changing a model's VALID_TRANSITIONS without updating its table
fails here, so the change is made on purpose.

Orders go through OrderService.transition_order_status, the one path staff
and customers use: an allowed move changes the status and writes one audit
row; a refused one raises and changes nothing.
"""

from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from audit.models import AuditLog
from shop.models import Order, Payment
from shop.services import OrderService
from utils.testing import TransitionTableMixin

User = get_user_model()

SERIAL = count(1)

O = Order
ORDER_STATUSES = (O.STATUS_PENDING, O.STATUS_CONFIRMED, O.STATUS_PROCESSING,
                  O.STATUS_SHIPPED, O.STATUS_DELIVERED, O.STATUS_CANCELLED)
#: target status -> the statuses an order may move to it from
ORDER_ALLOWED = {
    O.STATUS_PENDING: set(),
    O.STATUS_CONFIRMED: {O.STATUS_PENDING},
    O.STATUS_PROCESSING: {O.STATUS_CONFIRMED},
    O.STATUS_SHIPPED: {O.STATUS_PROCESSING},
    O.STATUS_DELIVERED: {O.STATUS_SHIPPED},
    O.STATUS_CANCELLED: {O.STATUS_PENDING, O.STATUS_CONFIRMED, O.STATUS_PROCESSING},
}

P = Payment
PAYMENT_STATUSES = (P.STATUS_PENDING, P.STATUS_PROCESSING, P.STATUS_PAID, P.STATUS_FAILED,
                    P.STATUS_CANCELLED, P.STATUS_REFUNDED, P.STATUS_PARTIALLY_REFUNDED)
PAYMENT_ALLOWED = {
    P.STATUS_PENDING: {P.STATUS_FAILED},
    P.STATUS_PROCESSING: {P.STATUS_PENDING, P.STATUS_FAILED},
    P.STATUS_PAID: {P.STATUS_PENDING, P.STATUS_PROCESSING},
    P.STATUS_FAILED: {P.STATUS_PENDING, P.STATUS_PROCESSING},
    P.STATUS_CANCELLED: {P.STATUS_PENDING, P.STATUS_PROCESSING},
    # A partial refund that still leaves a balance stays partial (BUG-057).
    P.STATUS_PARTIALLY_REFUNDED: {P.STATUS_PAID, P.STATUS_PARTIALLY_REFUNDED},
    P.STATUS_REFUNDED: {P.STATUS_PAID, P.STATUS_PARTIALLY_REFUNDED},
}


class StateMachineTestCase(TransitionTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="sm_customer", password="State-Machine-1")
        cls.staff = User.objects.create_superuser(username="sm_staff", email="sm@example.com", password="State-Machine-1")

    def make_order(self, status):
        return Order.objects.create(
            user=self.customer, order_number=f"ORD-SM-{next(SERIAL):04d}", status=status,
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        )


class OrderStateMachineTests(StateMachineTestCase):
    def test_the_table_names_every_status(self):
        current = {value for value, _ in Order.STATUS_CHOICES if value.isupper()}
        self.assertEqual(set(ORDER_STATUSES), current)
        self.assertEqual(set(ORDER_ALLOWED), current)

    def test_every_move_through_the_order_service(self):
        def attempt(start, target):
            order = self.make_order(start)
            audited = AuditLog.objects.filter(action="ORDER_STATUS_UPDATED", target_id=str(order.pk))
            try:
                OrderService.transition_order_status(order, target, actor=self.staff)
            except ValidationError:
                order.refresh_from_db()
                self.assertEqual(order.status, start)
                self.assertFalse(audited.exists())
                return False
            order.refresh_from_db()
            self.assertEqual(order.status, target)
            self.assertEqual(audited.count(), 1)
            return True

        self.assert_transition_table(ORDER_STATUSES, ORDER_ALLOWED, attempt)

    def test_the_model_agrees_with_the_table(self):
        def attempt(start, target):
            return Order(status=start).can_transition_to(target)

        self.assert_transition_table(ORDER_STATUSES, ORDER_ALLOWED, attempt)


class PaymentStateMachineTests(StateMachineTestCase):
    def test_the_table_names_every_status(self):
        current = {value for value, _ in Payment.STATUS_CHOICES}
        self.assertEqual(set(PAYMENT_STATUSES), current)
        self.assertEqual(set(PAYMENT_ALLOWED), current)

    def test_every_move(self):
        def attempt(start, target):
            payment = Payment.objects.create(
                order=self.make_order(Order.STATUS_PENDING), user=self.customer,
                payment_number=f"PAY-SM-{next(SERIAL):04d}", payment_method=Payment.METHOD_CASH_ON_DELIVERY,
                status=start, amount=Decimal("100.00"),
            )
            try:
                payment.transition_to(target)
            except ValidationError:
                payment.refresh_from_db()
                self.assertEqual(payment.status, start)
                return False
            payment.refresh_from_db()
            self.assertEqual(payment.status, target)
            if target == Payment.STATUS_PAID:
                self.assertIsNotNone(payment.paid_at)
            return True

        self.assert_transition_table(PAYMENT_STATUSES, PAYMENT_ALLOWED, attempt)
