"""
Wave 3 producers and handlers (docs/NOTIFICATION_SYSTEM.md Task 10): product
moderation, low stock, reviews, points and support tickets.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from cart.services import CartService
from customers.models import Address
from customers.services import ReviewService, SelfReviewError, ShopReviewService
from notifications import categories as c
from notifications import events
from notifications.models import Audience, Notification, NotificationEvent
from notifications.routing import route_event
from points.models import PointTransaction
from points.services import InvalidTransactionError, PointService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.inventory_service import InventoryService
from shop.models import LOW_STOCK_THRESHOLD, Category, Product
from shop.services import OrderService, ProductModerationError, ProductService
from shops.models import Shop
from support.models import SupportTicket
from support.services import SupportTicketService

User = get_user_model()


def events_of(event_type):
    return NotificationEvent.objects.filter(event_type=event_type)


def route_all(event_type):
    for event in events_of(event_type):
        route_event(event.pk)
    return Notification.objects.filter(event_type=event_type)


class WaveThreeFixtures:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

        def user(name, role=None, **fields):
            account = User.objects.create_user(username=f"w3_{name}", email=f"{name}@example.com", password="pw", **fields)
            if role:
                assign_user_role(account, role)
            return account

        cls.admin = user("admin", Role.ROLE_ADMINISTRATOR, is_staff=True)
        cls.support_agent = user("agent", Role.ROLE_SUPPORT_TEAM, is_staff=True)
        cls.operations = user("operations", Role.ROLE_OPERATION_MANAGER, is_staff=True)
        cls.customer = user("customer", Role.ROLE_CUSTOMER)
        cls.seller_user = user("seller")
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Wave Co", status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=cls.seller, name="Wave Mart", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="Wave", slug="w3-wave", is_active=True)

    def make_product(self, stock=20, status=Product.STATUS_PUBLISHED):
        return Product.objects.create(
            name="Steel Kettle", category=self.category, shop=self.shop, description="Kettle",
            price=Decimal("1200.00"), stock=stock, status=status, is_active=True,
        )


class ProductModerationNotificationTests(WaveThreeFixtures, TestCase):
    def test_a_rejection_tells_the_owner_with_the_reason_and_an_email(self):
        product = self.make_product(status=Product.STATUS_DRAFT)
        ProductService.reject(product, self.admin, reason="Photos show a different item")
        event = events_of(events.PRODUCT_MODERATED).get()
        self.assertEqual(event.payload, {
            "product_id": product.pk, "product_name": "Steel Kettle", "action": "reject",
            "from_status": "DRAFT", "to_status": "REJECTED", "reason": "Photos show a different item",
        })
        row = route_all(events.PRODUCT_MODERATED).get()
        self.assertEqual((row.recipient, row.audience, row.category), (self.seller_user, Audience.SELLER, c.CATALOG))
        self.assertTrue(row.body.endswith("Reason: Photos show a different item"))
        self.assertEqual(row.deliveries.count(), 1)

    def test_other_outcomes_are_in_app_only(self):
        product = self.make_product(status=Product.STATUS_DRAFT)
        for action in ("approve", "publish", "unpublish"):
            getattr(ProductService, action)(product, self.admin)
        rows = route_all(events.PRODUCT_MODERATED)
        self.assertEqual(rows.count(), 3)
        self.assertFalse(any(row.deliveries.exists() for row in rows))

    def test_a_refused_publish_publishes_nothing(self):
        Shop.objects.filter(pk=self.shop.pk).update(status=Shop.STATUS_SUSPENDED)
        product = Product.objects.select_related("shop").get(pk=self.make_product(status=Product.STATUS_APPROVED).pk)
        with self.assertRaises(ProductModerationError):
            ProductService.publish(product, self.admin)
        self.assertFalse(events_of(events.PRODUCT_MODERATED).exists())


class LowStockNotificationTests(WaveThreeFixtures, TestCase):
    def test_crossing_the_threshold_tells_the_owner_once(self):
        product = self.make_product(stock=LOW_STOCK_THRESHOLD + 10)
        InventoryService.adjust_stock(product, -12, actor=self.seller_user, reason="Damaged")  # 20 -> 8
        event = events_of(events.INVENTORY_LOW_STOCK).get()
        self.assertEqual(event.payload, {
            "product_id": product.pk, "product_name": "Steel Kettle",
            "available_stock": LOW_STOCK_THRESHOLD - 2, "threshold": LOW_STOCK_THRESHOLD,
        })
        self.assertTrue(event.idempotency_key.startswith(f"low_stock:{product.pk}:"))
        row = route_all(events.INVENTORY_LOW_STOCK).get()
        self.assertEqual((row.recipient, row.category, row.title), (self.seller_user, c.INVENTORY, "Steel Kettle is running low"))
        self.assertFalse(row.deliveries.exists())

    def test_only_a_crossing_counts(self):
        product = self.make_product(stock=LOW_STOCK_THRESHOLD + 10)
        InventoryService.adjust_stock(product, -5, reason="Above to above")  # 20 -> 15
        self.assertFalse(events_of(events.INVENTORY_LOW_STOCK).exists())
        InventoryService.adjust_stock(product, -10, reason="Crossing")  # 15 -> 5
        InventoryService.adjust_stock(product, -2, reason="Already low")  # 5 -> 3
        self.assertEqual(events_of(events.INVENTORY_LOW_STOCK).count(), 1)

    def test_at_most_once_a_day_per_product(self):
        product = self.make_product(stock=LOW_STOCK_THRESHOLD + 10)
        InventoryService.adjust_stock(product, -15, reason="Down")  # 20 -> 5
        InventoryService.adjust_stock(product, 15, reason="Restocked")  # 5 -> 20
        InventoryService.adjust_stock(product, -20, reason="Down again")  # 20 -> 0
        self.assertEqual(events_of(events.INVENTORY_LOW_STOCK).count(), 1)

    def test_an_order_reserving_stock_can_cross_it(self):
        product = self.make_product(stock=LOW_STOCK_THRESHOLD + 1)
        Address.objects.create(user=self.customer, recipient_name="R", address_line_1="House 1", city="Dhaka",
                               country="Bangladesh", is_default=True)
        CartService.add_item(self.customer, product.pk, quantity=2)
        OrderService.create_order_from_cart(self.customer)
        self.assertEqual(events_of(events.INVENTORY_LOW_STOCK).get().payload["available_stock"], LOW_STOCK_THRESHOLD - 1)


class ReviewNotificationTests(WaveThreeFixtures, TestCase):
    def test_a_product_review_tells_the_shop_owner(self):
        product = self.make_product()
        review = ReviewService.create_review(self.customer, product.pk, rating=4, comment="Boils fast")
        event = events_of(events.REVIEW_CREATED).get()
        self.assertEqual(event.idempotency_key, f"review:product:{review.pk}")
        self.assertEqual(event.payload, {"kind": "product", "review_id": review.pk, "rating": 4, "subject_name": "Steel Kettle"})
        row = route_all(events.REVIEW_CREATED).get()
        self.assertEqual((row.recipient, row.category, row.action_url), (self.seller_user, c.REVIEWS, "/seller/products"))
        self.assertNotIn("Boils fast", row.body)
        self.assertFalse(row.deliveries.exists())

    def test_a_shop_review_tells_the_owner(self):
        review = ShopReviewService.create_review(self.customer, self.shop.pk, rating=5)
        self.assertEqual(events_of(events.REVIEW_CREATED).get().idempotency_key, f"review:shop:{review.pk}")
        row = route_all(events.REVIEW_CREATED).get()
        self.assertEqual((row.recipient, row.title), (self.seller_user, "New 5-star review for Wave Mart"))
        self.assertEqual(row.action_url, "/seller/shops")

    def test_a_refused_review_publishes_nothing(self):
        with self.assertRaises(SelfReviewError):
            ShopReviewService.create_review(self.seller_user, self.shop.pk, rating=5)
        self.assertFalse(events_of(events.REVIEW_CREATED).exists())


class PointsNotificationTests(WaveThreeFixtures, TestCase):
    def test_a_staff_adjustment_tells_the_seller(self):
        txn = PointService.adjust_points(self.seller, 20, "credit", "Launch bonus", actor=self.admin)
        event = events_of(events.POINTS_ADJUSTED).get()
        self.assertEqual(event.idempotency_key, f"points_txn:{txn.pk}")
        self.assertEqual(event.payload, {
            "transaction_id": txn.pk, "seller_id": self.seller.pk, "transaction_type": "ADMIN_CREDIT",
            "amount": 20, "balance_after": 20, "reason": "Launch bonus",
        })
        row = route_all(events.POINTS_ADJUSTED).get()
        self.assertEqual((row.recipient, row.category, row.title), (self.seller_user, c.WALLET, "20 points added to your wallet"))
        self.assertFalse(row.deliveries.exists())

    def test_platform_credits_and_refused_adjustments_publish_nothing(self):
        PointService.credit(self.seller, 5, PointTransaction.TYPE_BONUS, "Welcome")
        with self.assertRaises(InvalidTransactionError):
            PointService.adjust_points(self.seller, 5, "gift", "Nope", actor=self.admin)
        self.assertFalse(events_of(events.POINTS_ADJUSTED).exists())


class SupportNotificationTests(WaveThreeFixtures, TestCase):
    def open_ticket(self, **kwargs):
        return SupportTicketService.create_ticket(
            self.customer, category=SupportTicket.CATEGORY_ORDER, subject="Parcel is late",
            description="It has been two weeks.", **kwargs,
        )

    def test_a_new_ticket_tells_the_people_who_assign(self):
        ticket = self.open_ticket()
        event = events_of(events.SUPPORT_TICKET_CREATED).get()
        self.assertEqual(event.idempotency_key, f"support_ticket:{ticket.ticket_number}:created")
        rows = route_all(events.SUPPORT_TICKET_CREATED)
        # support.staff.manage: ADMINISTRATOR and SUPPORT_TEAM, not OPERATION_MANAGER.
        self.assertEqual(set(rows.values_list("recipient_id", flat=True)), {self.admin.pk, self.support_agent.pk})
        self.assertEqual(rows.first().action_url, f"/admin/support/{ticket.ticket_number}")

    def test_a_public_reply_tells_the_customer_and_an_internal_note_does_not(self):
        ticket = self.open_ticket()
        SupportTicketService.add_staff_message(self.support_agent, ticket.ticket_number, "Checking with the courier.",
                                               is_internal=True)
        self.assertFalse(events_of(events.SUPPORT_REPLY_RECEIVED).exists())

        message = SupportTicketService.add_staff_message(self.support_agent, ticket.ticket_number, "It ships today.")
        event = events_of(events.SUPPORT_REPLY_RECEIVED).get()
        self.assertEqual(event.idempotency_key, f"support_message:{message.pk}")
        row = route_all(events.SUPPORT_REPLY_RECEIVED).get()
        self.assertEqual((row.recipient, row.audience, row.category), (self.customer, Audience.CUSTOMER, c.SUPPORT))
        self.assertEqual(row.action_url, f"/profile/support/{ticket.ticket_number}")
        self.assertNotIn("ships today", row.body)
        self.assertEqual(row.deliveries.count(), 1)

    def test_a_seller_ticket_reply_goes_to_the_seller_center(self):
        ticket = SupportTicketService.create_ticket(
            self.seller_user, seller=self.seller, category=SupportTicket.CATEGORY_POINTS,
            subject="Points missing", description="My bonus never arrived.",
        )
        SupportTicketService.add_staff_message(self.support_agent, ticket.ticket_number, "Added now.")
        row = route_all(events.SUPPORT_REPLY_RECEIVED).get()
        self.assertEqual((row.recipient, row.audience), (self.seller_user, Audience.SELLER))
        self.assertEqual(row.action_url, f"/seller/support/{ticket.ticket_number}")

    def test_a_customer_reply_tells_the_assignee_only(self):
        ticket = self.open_ticket()
        SupportTicketService.add_customer_reply(self.customer, ticket.ticket_number, "Any news?")
        self.assertEqual(route_all(events.SUPPORT_CUSTOMER_REPLIED).count(), 0)  # unassigned: no one

        SupportTicketService.assign(self.admin, ticket.ticket_number, self.support_agent)
        NotificationEvent.objects.all().delete()
        SupportTicketService.add_customer_reply(self.customer, ticket.ticket_number, "Still waiting.")
        row = route_all(events.SUPPORT_CUSTOMER_REPLIED).get()
        self.assertEqual((row.recipient, row.audience, row.title),
                         (self.support_agent, Audience.STAFF, f"New reply on ticket {ticket.ticket_number}"))

    def test_assignment_tells_the_assignee_unless_they_took_it_themselves(self):
        ticket = self.open_ticket()
        SupportTicketService.assign(self.admin, ticket.ticket_number, self.support_agent)
        row = route_all(events.SUPPORT_TICKET_ASSIGNED).get()
        self.assertEqual((row.recipient, row.title), (self.support_agent, f"Ticket {ticket.ticket_number} is assigned to you"))
        self.assertEqual(row.deliveries.count(), 1)

        NotificationEvent.objects.all().delete()
        Notification.objects.all().delete()
        SupportTicketService.assign(self.support_agent, ticket.ticket_number, None)  # unassigning
        self.assertFalse(events_of(events.SUPPORT_TICKET_ASSIGNED).exists())
        SupportTicketService.assign(self.support_agent, ticket.ticket_number, self.support_agent)
        self.assertEqual(route_all(events.SUPPORT_TICKET_ASSIGNED).count(), 0)
