"""
Wave 1 producers and handlers (docs/NOTIFICATION_SYSTEM.md Task 8): orders
and payments publish inside their own transactions, and routing tells the
right people.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from cart.services import CartService
from customers.models import Address
from notifications import categories as c
from notifications import events
from notifications.models import (
    Audience,
    Channel,
    Notification,
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)
from notifications.routing import route_event
from sellers.models import SellerProfile
from shop.models import Category, Order, Product
from shop.payment_service import PaymentService
from shop.services import OrderService
from shops.models import Shop

User = get_user_model()


def events_of(event_type):
    return NotificationEvent.objects.filter(event_type=event_type)


class OrderPaymentFixtures:
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Kitchen", slug="np-kitchen", is_active=True)

        def seller(name, business_email=""):
            user = User.objects.create_user(username=f"np_{name}", email=f"{name}@example.com", password="pw")
            profile = SellerProfile.objects.create(
                user=user, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER, business_name=f"{name} Co",
                business_email=business_email, status=SellerProfile.STATUS_ACTIVE,
            )
            shop = Shop.objects.create(owner=profile, name=f"{name} Shop", status=Shop.STATUS_ACTIVE)
            return profile, shop

        cls.seller_a, shop_a = seller("alpha", business_email="orders@alpha.example.com")
        cls.seller_b, shop_b = seller("beta")
        cls.kettle = Product.objects.create(
            name="Steel Kettle", slug="np-kettle", category=category, shop=shop_a,
            price=Decimal("1200.00"), stock=20, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        cls.mug = Product.objects.create(
            name="Clay Mug", slug="np-mug", category=category, shop=shop_b,
            price=Decimal("150.00"), stock=20, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        cls.customer = User.objects.create_user(username="np_customer", email="rahim@example.com", password="pw")
        cls.address = Address.objects.create(
            user=cls.customer, recipient_name="Rahim", phone="01700000000",
            address_line_1="House 1", city="Dhaka", country="Bangladesh", is_default=True,
        )
        cls.staff = User.objects.create_user(username="np_staff", password="pw", is_staff=True)

    def place_order(self, *products):
        for product in products or (self.kettle, self.mug):
            CartService.add_item(self.customer, product.pk, quantity=2 if product == self.kettle else 1)
        return OrderService.create_order_from_cart(self.customer, address_id=self.address.pk)

    def inbox(self, event_type):
        return Notification.objects.filter(event_type=event_type)


class OrderPlacedTests(OrderPaymentFixtures, TestCase):
    def test_publishes_one_event_with_every_line(self):
        order = self.place_order()
        event = events_of(events.ORDER_PLACED).get()
        self.assertEqual(event.idempotency_key, f"order:{order.order_number}:placed")
        self.assertEqual(event.aggregate_id, str(order.pk))
        self.assertEqual(event.actor, self.customer)
        payload = event.payload
        self.assertEqual(
            (payload["order_id"], payload["order_number"], payload["total_amount"]),
            (order.pk, order.order_number, "2550.00"),
        )
        self.assertCountEqual(
            payload["items"],
            [
                {"product_name": "Steel Kettle", "quantity": 2, "line_total": "2400.00", "seller_id": self.seller_a.pk},
                {"product_name": "Clay Mug", "quantity": 1, "line_total": "150.00", "seller_id": self.seller_b.pk},
            ],
        )

    def test_a_refused_order_publishes_nothing(self):
        with self.assertRaises(ValidationError):
            OrderService.create_order_from_cart(self.customer, address_id=self.address.pk)
        self.assertFalse(events_of(events.ORDER_PLACED).exists())

    def test_customer_and_each_seller_are_told(self):
        order = self.place_order()
        route_event(events_of(events.ORDER_PLACED).get().pk)

        customer_row = self.inbox(events.ORDER_PLACED).get(recipient=self.customer)
        self.assertEqual((customer_row.audience, customer_row.category), (Audience.CUSTOMER, c.ORDERS))
        self.assertEqual(customer_row.title, f"Order {order.order_number} placed")
        self.assertIn("৳2,550.00", customer_row.body)
        self.assertEqual(customer_row.action_url, f"/profile/orders/{order.order_number}")

        rows = {row.recipient_id: row for row in self.inbox(events.ORDER_PLACED).filter(audience=Audience.SELLER)}
        self.assertEqual(set(rows), {self.seller_a.user_id, self.seller_b.user_id})
        alpha, beta = rows[self.seller_a.user_id], rows[self.seller_b.user_id]
        self.assertEqual(alpha.category, c.SELLER_ORDERS)
        self.assertEqual(alpha.action_url, "/seller/orders")
        # Each seller sees only their own items and their own total (§4.7).
        self.assertIn("2 × Steel Kettle: ৳2,400.00", alpha.body)
        self.assertIn("Your items come to ৳2,400.00", alpha.body)
        self.assertNotIn("Clay Mug", alpha.body)
        self.assertIn("1 × Clay Mug: ৳150.00", beta.body)
        self.assertNotIn("Kettle", beta.body)
        self.assertNotIn("2,550", beta.body)

    def test_emails_go_to_the_customer_and_the_sellers_business_addresses(self):
        self.place_order()
        route_event(events_of(events.ORDER_PLACED).get().pk)
        destinations = set(
            NotificationDelivery.objects.filter(channel=Channel.EMAIL).values_list("destination", flat=True)
        )
        self.assertEqual(destinations, {"rahim@example.com", "orders@alpha.example.com", "beta@example.com"})


class OrderStatusTests(OrderPaymentFixtures, TestCase):
    def setUp(self):
        self.order = self.place_order()
        NotificationEvent.objects.all().delete()

    def status_event(self):
        return events_of(events.ORDER_STATUS_CHANGED).get()

    def route(self):
        route_event(self.status_event().pk)

    def test_staff_transition_publishes_one_event(self):
        OrderService.transition_order_status(self.order, Order.STATUS_CONFIRMED, actor=self.staff)
        event = self.status_event()
        self.assertEqual(event.payload, {
            "order_id": self.order.pk,
            "order_number": self.order.order_number,
            "from_status": "PENDING",
            "to_status": "CONFIRMED",
            "changed_by": "STAFF",
        })
        self.assertEqual(event.actor, self.staff)

    def test_a_refused_transition_publishes_nothing(self):
        with self.assertRaises(Exception):
            OrderService.transition_order_status(self.order, Order.STATUS_DELIVERED, actor=self.staff)
        self.assertFalse(events_of(events.ORDER_STATUS_CHANGED).exists())

    def test_confirmed_tells_the_customer_in_app_only(self):
        OrderService.transition_order_status(self.order, Order.STATUS_CONFIRMED, actor=self.staff)
        self.route()
        row = self.inbox(events.ORDER_STATUS_CHANGED).get()
        self.assertEqual((row.recipient, row.title), (self.customer, f"Order {self.order.order_number} confirmed"))
        self.assertFalse(NotificationDelivery.objects.exists())

    def test_processing_tells_no_one(self):
        OrderService.transition_order_status(self.order, Order.STATUS_CONFIRMED, actor=self.staff)
        NotificationEvent.objects.all().delete()
        OrderService.transition_order_status(self.order, Order.STATUS_PROCESSING, actor=self.staff)
        self.route()
        self.assertFalse(self.inbox(events.ORDER_STATUS_CHANGED).exists())

    def test_shipped_and_delivered_email_the_customer(self):
        for status in (Order.STATUS_CONFIRMED, Order.STATUS_PROCESSING):
            OrderService.transition_order_status(self.order, status, actor=self.staff)
        for status, title in ((Order.STATUS_SHIPPED, "is on its way"), (Order.STATUS_DELIVERED, "delivered")):
            with self.subTest(status=status):
                NotificationEvent.objects.all().delete()
                OrderService.transition_order_status(self.order, status, actor=self.staff)
                self.route()
                row = self.inbox(events.ORDER_STATUS_CHANGED).get(title__endswith=title)
                self.assertEqual(row.recipient, self.customer)
                self.assertEqual(row.deliveries.get().destination, "rahim@example.com")

    def test_customer_cancellation_tells_the_customer_and_every_seller(self):
        OrderService.cancel_customer_order(self.order, self.customer, reason="Changed my mind")
        event = self.status_event()
        self.assertEqual(event.payload["changed_by"], "CUSTOMER")
        self.route()
        rows = self.inbox(events.ORDER_STATUS_CHANGED)
        self.assertEqual(rows.get(audience=Audience.CUSTOMER).body.split(".")[0], "You cancelled this order")
        sellers = rows.filter(audience=Audience.SELLER)
        self.assertEqual(
            set(sellers.values_list("recipient_id", flat=True)), {self.seller_a.user_id, self.seller_b.user_id}
        )
        self.assertTrue(all(row.title.endswith("cancelled by the customer") for row in sellers))
        self.assertNotIn("Changed my mind", "".join(rows.values_list("body", flat=True)))

    def test_staff_cancellation_does_not_tell_the_sellers(self):
        OrderService.transition_order_status(self.order, Order.STATUS_CANCELLED, actor=self.staff)
        self.assertEqual(self.status_event().payload["changed_by"], "STAFF")
        self.route()
        self.assertEqual(
            list(self.inbox(events.ORDER_STATUS_CHANGED).values_list("audience", flat=True)), [Audience.CUSTOMER]
        )

    def test_seller_transition_is_marked_as_the_sellers(self):
        CartService.clear_cart(self.customer)
        order = self.place_order(self.kettle)
        NotificationEvent.objects.all().delete()
        OrderService.transition_seller_order_status(
            order, Order.STATUS_CONFIRMED, seller=self.seller_a, actor=self.seller_a.user
        )
        self.assertEqual(self.status_event().payload["changed_by"], "SELLER")


class PaymentTests(OrderPaymentFixtures, TestCase):
    def setUp(self):
        self.order = self.place_order()
        self.payment = PaymentService.create_or_get_payment(self.order)
        NotificationEvent.objects.all().delete()

    def test_success_publishes_once_and_always_emails(self):
        NotificationPreference.objects.create(
            user=self.customer, category=c.PAYMENTS, channel=Channel.EMAIL, enabled=False
        )
        PaymentService.process_payment_success(self.payment, transaction_id="TX1")
        PaymentService.process_payment_success(self.payment, transaction_id="TX1")  # idempotent repeat

        event = events_of(events.PAYMENT_SUCCEEDED).get()
        self.assertEqual(event.idempotency_key, f"payment:{self.payment.payment_number}:succeeded")
        self.assertEqual(event.payload, {
            "payment_id": self.payment.pk,
            "payment_number": self.payment.payment_number,
            "order_number": self.order.order_number,
            "amount": "2550.00",
        })
        route_event(event.pk)
        row = self.inbox(events.PAYMENT_SUCCEEDED).get()
        self.assertEqual((row.recipient, row.category), (self.customer, c.PAYMENTS))
        # PAYMENTS locks email, so the opt-out above is ignored.
        self.assertEqual(row.deliveries.count(), 1)

    def test_each_failure_is_its_own_event(self):
        PaymentService.process_payment_failure(self.payment, reason="Card declined")
        PaymentService.process_payment_failure(self.payment, reason="Card declined")  # already FAILED: no-op
        self.assertEqual(events_of(events.PAYMENT_FAILED).count(), 1)
        route_event(events_of(events.PAYMENT_FAILED).get().pk)
        row = self.inbox(events.PAYMENT_FAILED).get()
        self.assertEqual(row.recipient, self.customer)
        self.assertNotIn("Card declined", row.body)

    def test_refund_publishes_once_per_refund(self):
        PaymentService.process_payment_success(self.payment)
        refund = PaymentService.process_refund(self.payment, amount="500.00", reason="Damaged mug", actor=self.staff)
        event = events_of(events.REFUND_PROCESSED).get()
        self.assertEqual(event.idempotency_key, f"refund:{refund.refund_number}")
        self.assertEqual(event.payload["amount"], "500.00")
        route_event(event.pk)
        row = self.inbox(events.REFUND_PROCESSED).get()
        self.assertEqual((row.recipient, row.title), (self.customer, f"Refund of ৳500.00 for order {self.order.order_number}"))

    def test_a_refused_refund_publishes_nothing(self):
        with self.assertRaises(ValidationError):
            PaymentService.process_refund(self.payment, amount="10.00")  # not paid yet
        self.assertFalse(events_of(events.REFUND_PROCESSED).exists())

    def test_cancelling_a_paid_order_announces_both_the_cancellation_and_the_refund(self):
        PaymentService.process_payment_success(self.payment)
        OrderService.transition_order_status(self.order, Order.STATUS_CANCELLED, actor=self.staff)
        self.assertEqual(events_of(events.ORDER_STATUS_CHANGED).count(), 1)
        self.assertEqual(events_of(events.REFUND_PROCESSED).get().payload["amount"], "2550.00")
