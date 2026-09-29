import smtplib
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.template import Context, Template
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from notifications import categories as c
from notifications.channels import PermanentSendError, TransientSendError, get_adapter
from notifications.channels.email import (
    HTML_TEMPLATE,
    TEXT_TEMPLATE,
    EmailAdapter,
    build_message,
    email_destination,
)
from notifications.handlers import Recipient
from notifications.models import Audience, Channel, Notification, NotificationDelivery
from notifications.publisher import publish
from notifications.routing import route_event
from notifications.worker import NotificationWorker
from sellers.models import SellerProfile

from .helpers import TEST_EVENT, TestEventMixin, tell, with_test_templates

User = get_user_model()


class EmailFixtures:
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="em_customer", email="rahim@example.com", password="pw")

    def make_delivery(self, category=c.ORDERS, body="Your order ORD1 is on its way.\n\nIt left Dhaka today.",
                      action_url="/profile/orders/ORD1", destination="rahim@example.com"):
        notification = Notification.objects.create(
            recipient=self.customer, event=None, event_type=TEST_EVENT, category=category,
            audience=Audience.CUSTOMER, title="Order ORD1 shipped", body=body, action_url=action_url,
            occurred_at=timezone.now(),
        )
        return NotificationDelivery.objects.create(
            notification=notification, channel=Channel.EMAIL, destination=destination
        )


@override_settings(STOREFRONT_URL="https://shop.example.com/", NOTIFICATIONS={"FROM_EMAIL": "MiniShop <hello@minishop.test>"})
class EmailMessageTests(EmailFixtures, TestCase):
    def test_subject_bodies_and_headers(self):
        delivery = self.make_delivery()
        message = build_message(delivery)

        self.assertEqual(message.subject, "Order ORD1 shipped")
        self.assertEqual(message.from_email, "MiniShop <hello@minishop.test>")
        self.assertEqual(message.to, ["rahim@example.com"])
        self.assertEqual(message.extra_headers["Message-ID"], f"<{delivery.pk}@minishop.test>")
        self.assertEqual(message.extra_headers["Auto-Submitted"], "auto-generated")

        self.assertIn("Your order ORD1 is on its way.\n\nIt left Dhaka today.", message.body)
        self.assertIn("Open it in MiniShop: https://shop.example.com/profile/orders/ORD1", message.body)
        self.assertIn("All your notifications: https://shop.example.com/profile/notifications", message.body)
        self.assertIn("You can switch them off", message.body)

        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn('href="https://shop.example.com/profile/orders/ORD1"', html)
        self.assertIn("<p>Your order ORD1 is on its way.</p>", html)
        self.assertIn("Mini<span", html)

    def test_text_is_not_escaped_but_html_is(self):
        message = build_message(self.make_delivery(body="Tom & Jerry <b>"))
        self.assertIn("Tom & Jerry <b>", message.body)
        self.assertIn("Tom &amp; Jerry &lt;b&gt;", message.alternatives[0][0])

    def test_locked_categories_say_they_are_always_emailed(self):
        message = build_message(self.make_delivery(category=c.PAYMENTS))
        self.assertIn("which is always emailed", message.body)
        self.assertNotIn("switch them off", message.body)

    def test_no_link_means_no_button(self):
        message = build_message(self.make_delivery(action_url=""))
        self.assertNotIn("Open it in MiniShop", message.body)
        self.assertNotIn("Open in MiniShop", message.alternatives[0][0])

    def test_sending_uses_the_backend_and_returns_the_message_id(self):
        delivery = self.make_delivery()
        result = EmailAdapter().send(delivery)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0].message()
        self.assertEqual(sent["Message-ID"], f"<{delivery.pk}@minishop.test>")
        self.assertEqual(result.provider_message_id, sent["Message-ID"])


class EmailErrorClassificationTests(EmailFixtures, TestCase):
    def send_raising(self, error, **delivery_fields):
        delivery = self.make_delivery(**delivery_fields)
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=error):
            EmailAdapter().send(delivery)

    def test_missing_or_invalid_addresses_are_skipped(self):
        for destination in ("", "not-an-address"):
            with self.subTest(destination=destination):
                with self.assertRaises(PermanentSendError) as caught:
                    EmailAdapter().send(self.make_delivery(destination=destination))
                self.assertTrue(caught.exception.skip)
        self.assertEqual(mail.outbox, [])

    def test_permanent_refusals(self):
        cases = [
            (smtplib.SMTPRecipientsRefused({"rahim@example.com": (550, b"no such user")}), True),
            (smtplib.SMTPDataError(554, b"rejected as spam"), False),
        ]
        for error, skip in cases:
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(PermanentSendError) as caught:
                    self.send_raising(error)
                self.assertEqual(caught.exception.skip, skip)

    def test_transient_failures(self):
        for error in (
            smtplib.SMTPRecipientsRefused({"rahim@example.com": (450, b"mailbox busy")}),
            smtplib.SMTPDataError(451, b"try again later"),
            smtplib.SMTPAuthenticationError(535, b"bad credentials"),
            smtplib.SMTPSenderRefused(553, b"sender not allowed", "hello@minishop.test"),
            smtplib.SMTPServerDisconnected("connection dropped"),
            TimeoutError("timed out"),
            ConnectionRefusedError("refused"),
        ):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(TransientSendError):
                    self.send_raising(error)


class EmailDestinationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="em_seller", email=" owner@example.com ", password="pw")

    def seller(self, business_email):
        return SellerProfile.objects.create(
            user=self.user, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Destination Co", business_email=business_email, status=SellerProfile.STATUS_ACTIVE,
        )

    def test_customers_and_staff_use_the_account_email(self):
        self.seller("shop@example.com")
        for audience in (Audience.CUSTOMER, Audience.STAFF):
            with self.subTest(audience=audience):
                self.assertEqual(email_destination(self.user, audience), "owner@example.com")

    def test_sellers_use_their_business_email_first(self):
        self.seller(" shop@example.com ")
        self.assertEqual(email_destination(self.user, Audience.SELLER), "shop@example.com")

    def test_sellers_fall_back_to_the_account_email(self):
        self.assertEqual(email_destination(self.user, Audience.SELLER), "owner@example.com")
        self.seller("")
        self.assertEqual(email_destination(self.user, Audience.SELLER), "owner@example.com")

    def test_no_address_at_all(self):
        User.objects.filter(pk=self.user.pk).update(email="")
        self.user.refresh_from_db()
        self.assertEqual(email_destination(self.user, Audience.SELLER), "")


@with_test_templates
class EmailEndToEndTests(TestEventMixin, TestCase):
    """Publish -> route -> worker -> one email in the outbox."""

    @classmethod
    def setUpTestData(cls):
        cls.seller_user = User.objects.create_user(username="em_e2e", email="owner@example.com", password="pw")
        SellerProfile.objects.create(
            user=cls.seller_user, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="E2E Co", business_email="shop@example.com", status=SellerProfile.STATUS_ACTIVE,
        )

    def test_the_email_goes_to_the_business_address_and_is_marked_sent(self):
        self.handle(tell(Recipient(self.seller_user, Audience.SELLER)))
        with transaction.atomic():
            event = publish(TEST_EVENT, payload={"thing": "E2E"}, aggregate=self.seller_user)
        route_event(event.pk)
        delivery = NotificationDelivery.objects.get(notification__event=event)
        self.assertEqual(delivery.destination, "shop@example.com")

        NotificationWorker(worker_id="w1").run_once("deliveries")

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["shop@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Thing E2E happened")
        self.assertEqual(delivery.provider_message_id, mail.outbox[0].extra_headers["Message-ID"])


class EmailSetupTests(SimpleTestCase):
    def test_the_email_adapter_is_registered(self):
        self.assertIsInstance(get_adapter(Channel.EMAIL), EmailAdapter)

    def test_the_shared_layouts_exist(self):
        for name in (TEXT_TEMPLATE, HTML_TEMPLATE):
            with self.subTest(template=name):
                get_template(name)

    def test_taka_formats_money(self):
        render = lambda value: Template("{% load notification_format %}{{ v|taka }}").render(Context({"v": value}))  # noqa: E731
        self.assertEqual(render("1500"), "৳1,500.00")
        self.assertEqual(render("1234567.5"), "৳1,234,567.50")
        self.assertEqual(render(0), "৳0.00")
        self.assertEqual(render("n/a"), "৳n/a")
