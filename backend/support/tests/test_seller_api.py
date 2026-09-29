"""
Seller Center support: /api/support/seller/… on the SELLER channel.

The rules that matter most: a seller needs only a SellerProfile (no RBAC
code), sees only the tickets they opened as a seller, and never a customer
ticket, including the ones they opened themselves as a customer; and customer
endpoints never show seller tickets.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditLog
from rbac.models import Role
from sellers.models import SellerProfile
from shop.models import Order, OrderItem
from support.models import SupportTicket, TicketMessage
from support.services import SupportTicketService as Service

from .helpers import PrivateMediaMixin, make_user, png

LIST_URL = reverse("support:seller-ticket-list-create")
UNREAD_URL = reverse("support:seller-ticket-unread-count")
CUSTOMER_LIST_URL = reverse("support:ticket-list-create")
STAFF_LIST_URL = reverse("support:staff-ticket-list")


def detail_url(ticket):
    return reverse("support:seller-ticket-detail", args=[ticket.ticket_number])


def messages_url(ticket):
    return reverse("support:seller-ticket-messages", args=[ticket.ticket_number])


def close_url(ticket):
    return reverse("support:seller-ticket-close", args=[ticket.ticket_number])


def staff_detail_url(ticket):
    return reverse("support:staff-ticket-detail", args=[ticket.ticket_number])


def make_seller(username, role=None, **profile):
    user = make_user(username, role)
    seller = SellerProfile.objects.create(
        user=user,
        seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
        business_name=profile.pop("business_name", f"{username} Traders"),
        status=profile.pop("status", SellerProfile.STATUS_ACTIVE),
        **profile,
    )
    return user, seller


class SellerSupportApiTestCase(PrivateMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        # A seller who is also a customer, to prove the two channels stay apart.
        cls.seller_user, cls.seller = make_seller("sellsup_seller", Role.ROLE_CUSTOMER)
        cls.other_user, cls.other_seller = make_seller("sellsup_other")
        cls.customer = make_user("sellsup_customer", Role.ROLE_CUSTOMER)
        cls.agent = make_user("sellsup_agent", Role.ROLE_SUPPORT_TEAM, first_name="Rina")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.seller_user)

    def as_user(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def open_seller_ticket(self, user=None, seller=None, **overrides):
        data = {
            "category": SupportTicket.CATEGORY_POINTS,
            "subject": "Please add points",
            "description": "I need 500 points to list my new products.",
        }
        data.update(overrides)
        return Service.create_ticket(user or self.seller_user, seller=seller or self.seller, **data)


class SellerCreateTicketTests(SellerSupportApiTestCase):
    def test_seller_without_any_role_can_open_a_ticket(self):
        response = self.as_user(self.other_user).post(
            LIST_URL,
            {
                "category": "POINTS",
                "subject": "Point top-up request",
                "description": "Please credit 1000 points to my wallet.",
                "attachments": [png("receipt.png")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        ticket = SupportTicket.objects.get(ticket_number=response.data["ticket_number"])
        self.assertEqual(ticket.channel, SupportTicket.CHANNEL_SELLER)
        self.assertEqual(ticket.seller, self.other_seller)
        self.assertEqual(ticket.customer, self.other_user)
        self.assertEqual(response.data["category_label"], "Points & wallet")
        attachment_url = response.data["messages"][0]["attachments"][0]["url"]
        self.assertTrue(attachment_url.startswith("/api/support/seller/attachments/"))

        entry = AuditLog.objects.get(action="SUPPORT_TICKET_CREATED", target_id=str(ticket.pk))
        self.assertEqual(entry.metadata["channel"], "SELLER")
        self.assertEqual(entry.metadata["seller_id"], self.other_seller.pk)

    def test_suspended_seller_can_still_ask_for_help(self):
        user, _ = make_seller("sellsup_suspended", status=SellerProfile.STATUS_SUSPENDED,
                              suspension_reason="Policy review")
        response = self.as_user(user).post(
            LIST_URL,
            {"category": "ACCOUNT", "subject": "Why am I suspended?",
             "description": "Please explain the suspension."},
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_customer_only_categories_are_rejected(self):
        response = self.client.post(
            LIST_URL,
            {"category": "RETURN", "subject": "Return request", "description": "A customer return."},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Choose a valid category."})

    def test_seller_categories_are_rejected_on_the_customer_channel(self):
        response = self.as_user(self.customer).post(
            CUSTOMER_LIST_URL,
            {"category": "POINTS", "subject": "Points please", "description": "Add points to me."},
        )
        self.assertEqual(response.status_code, 400)

    def test_order_must_contain_the_sellers_items(self):
        own = Order.objects.create(user=self.customer, order_number="SELLSUP-OWN")
        OrderItem.objects.create(order=own, product_name="Lamp", seller=self.seller)
        foreign = Order.objects.create(user=self.customer, order_number="SELLSUP-FOREIGN")
        OrderItem.objects.create(order=foreign, product_name="Chair", seller=self.other_seller)
        base = {"category": "FULFILLMENT", "subject": "Courier issue",
                "description": "The courier did not pick up the parcel."}

        response = self.client.post(LIST_URL, {**base, "order_number": "SELLSUP-OWN"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["order_number"], "SELLSUP-OWN")

        response = self.client.post(LIST_URL, {**base, "order_number": "SELLSUP-FOREIGN"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Order not found."})

    def test_unresolved_cap_is_per_channel(self):
        for i in range(5):
            self.open_seller_ticket(subject=f"Seller question {i}")
        response = self.client.post(
            LIST_URL,
            {"category": "OTHER", "subject": "Sixth one", "description": "One more question."},
        )
        self.assertEqual(response.status_code, 400)
        # The same person's customer channel still has room.
        response = self.client.post(
            CUSTOMER_LIST_URL,
            {"category": "ORDER", "subject": "My own order", "description": "My parcel is late."},
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_non_sellers_are_refused(self):
        for user, expected in ((self.customer, 403), (self.agent, 403), (None, 401)):
            client = self.as_user(user)
            self.assertEqual(client.get(LIST_URL).status_code, expected)
            response = client.post(
                LIST_URL,
                {"category": "OTHER", "subject": "Let me in", "description": "Not a seller."},
            )
            self.assertEqual(response.status_code, expected)
        self.assertFalse(SupportTicket.objects.filter(channel="SELLER").exists())


class SellerChannelIsolationTests(SellerSupportApiTestCase):
    def test_seller_sees_only_their_own_seller_tickets(self):
        mine = self.open_seller_ticket()
        self.open_seller_ticket(user=self.other_user, seller=self.other_seller)
        Service.create_ticket(
            self.seller_user, category="ORDER", subject="My personal order",
            description="Bought something as a customer.",
        )

        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([t["ticket_number"] for t in response.data["results"]], [mine.ticket_number])

    def test_customer_endpoints_never_show_seller_tickets(self):
        seller_ticket = self.open_seller_ticket()
        customer_ticket = Service.create_ticket(
            self.seller_user, category="ORDER", subject="My personal order",
            description="Bought something as a customer.",
        )
        response = self.client.get(CUSTOMER_LIST_URL)
        self.assertEqual(
            [t["ticket_number"] for t in response.data["results"]], [customer_ticket.ticket_number]
        )
        customer_detail = reverse("support:ticket-detail", args=[seller_ticket.ticket_number])
        self.assertEqual(self.client.get(customer_detail).status_code, 404)
        # And the seller endpoint can't open the customer ticket either.
        self.assertEqual(self.client.get(detail_url(customer_ticket)).status_code, 404)

    def test_seller_never_sees_customer_complaints_about_their_shop(self):
        complaint = Service.create_ticket(
            self.customer, category="SHOP", subject="Rude seller",
            description="The seller was rude to me.",
        )
        self.assertEqual(self.client.get(detail_url(complaint)).status_code, 404)
        self.assertEqual(self.client.get(LIST_URL).data["count"], 0)

    def test_another_sellers_ticket_is_a_404(self):
        theirs = self.open_seller_ticket(user=self.other_user, seller=self.other_seller)
        self.assertEqual(self.client.get(detail_url(theirs)).status_code, 404)
        response = self.client.post(messages_url(theirs), {"body": "Hello?"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(close_url(theirs)).status_code, 404)

    def test_attachments_are_scoped_to_the_channel(self):
        ticket = Service.create_ticket(
            self.seller_user, seller=self.seller, category="POINTS", subject="Proof attached",
            description="Here is the payment proof.", files=[png("proof.png")],
        )
        attachment = ticket.messages.get().attachments.get()
        seller_url = reverse("support:seller-attachment-download", args=[attachment.pk])
        customer_url = reverse("support:attachment-download", args=[attachment.pk])
        self.assertEqual(self.client.get(seller_url).status_code, 200)
        # The same user, through the customer route: not a customer ticket.
        self.assertEqual(self.client.get(customer_url).status_code, 404)
        self.assertEqual(self.as_user(self.other_user).get(seller_url).status_code, 404)


class SellerConversationTests(SellerSupportApiTestCase):
    def test_reply_unread_and_close(self):
        ticket = self.open_seller_ticket()
        Service.add_staff_message(self.agent, ticket.ticket_number, "How many points do you need?")
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "Internal: check the payment first.", is_internal=True
        )

        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 1})
        # The customer channel's unread count is unaffected.
        self.assertEqual(self.client.get(reverse("support:ticket-unread-count")).data, {"unread": 0})

        response = self.client.get(detail_url(ticket))
        self.assertEqual(response.status_code, 200)
        bodies = [m["body"] for m in response.data["messages"]]
        self.assertNotIn("Internal: check the payment first.", bodies)
        self.assertEqual(response.data["messages"][1]["author_name"], "Rina · MiniShop Support")
        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 0})

        response = self.client.post(messages_url(ticket), {"body": "500 points, please."})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["messages"][-1]["author_name"], "You")

        response = self.client.post(close_url(ticket))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], SupportTicket.STATUS_CLOSED)
        note = TicketMessage.objects.filter(ticket=ticket, author_type="SYSTEM").last()
        self.assertEqual(note.body, "Closed by the seller.")

    def test_seller_reply_reopens_a_ticket_waiting_on_them(self):
        ticket = self.open_seller_ticket()
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "Send the receipt, please.",
            set_status=SupportTicket.STATUS_WAITING_ON_CUSTOMER,
        )
        response = self.client.post(messages_url(ticket), {"body": "Receipt attached now."})
        self.assertEqual(response.data["status"], SupportTicket.STATUS_OPEN)
        note = TicketMessage.objects.filter(ticket=ticket, author_type="SYSTEM").last()
        self.assertEqual(note.body, "Reopened by the seller's reply.")


class StaffSeesSellerTicketsTests(SellerSupportApiTestCase):
    def test_staff_list_shows_channel_and_seller_and_filters_by_channel(self):
        seller_ticket = self.open_seller_ticket()
        customer_ticket = Service.create_ticket(
            self.customer, category="ORDER", subject="Late parcel", description="Where is my parcel?",
        )
        staff = self.as_user(self.agent)

        response = staff.get(STAFF_LIST_URL, {"channel": "SELLER"})
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        self.assertEqual([r["ticket_number"] for r in rows], [seller_ticket.ticket_number])
        self.assertEqual(rows[0]["channel_label"], "Seller")
        self.assertEqual(rows[0]["seller"]["business_name"], self.seller.business_name)

        response = staff.get(STAFF_LIST_URL, {"channel": "CUSTOMER"})
        self.assertEqual([r["ticket_number"] for r in response.data["results"]],
                         [customer_ticket.ticket_number])
        self.assertIsNone(response.data["results"][0]["seller"])

        response = staff.get(STAFF_LIST_URL, {"search": self.seller.business_name})
        self.assertEqual([r["ticket_number"] for r in response.data["results"]],
                         [seller_ticket.ticket_number])

        self.assertEqual(staff.get(STAFF_LIST_URL, {"channel": "ALIENS"}).status_code, 400)

    def test_staff_detail_limits_categories_to_the_channel(self):
        ticket = self.open_seller_ticket()
        lead = make_user("sellsup_manager", Role.ROLE_SUPPORT_TEAM)
        staff = self.as_user(lead)

        response = staff.get(staff_detail_url(ticket))
        self.assertIn("POINTS", response.data["allowed_categories"])
        self.assertNotIn("RETURN", response.data["allowed_categories"])

        response = staff.patch(staff_detail_url(ticket), {"category": "RETURN"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = staff.patch(staff_detail_url(ticket), {"category": "LISTING"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["category"], "LISTING")
