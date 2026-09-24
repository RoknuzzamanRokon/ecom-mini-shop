from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditLog
from rbac.models import Role
from shop.models import Order
from support.models import SupportTicket, TicketAttachment
from support.services import SupportTicketService as Service

from .helpers import PrivateMediaMixin, image_bytes, make_user, pdf, png, upload

LIST_URL = reverse("support:ticket-list-create")
UNREAD_URL = reverse("support:ticket-unread-count")
STAFF_ONLY_KEYS = {"priority", "assigned_to", "first_response_at", "last_staff_reply_at"}


def detail_url(ticket):
    return reverse("support:ticket-detail", args=[ticket.ticket_number])


def messages_url(ticket):
    return reverse("support:ticket-messages", args=[ticket.ticket_number])


def close_url(ticket):
    return reverse("support:ticket-close", args=[ticket.ticket_number])


def attachment_url(attachment):
    return reverse("support:attachment-download", args=[attachment.pk])


class CustomerSupportApiTestCase(PrivateMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = make_user("supapi_customer", Role.ROLE_CUSTOMER)
        cls.other_customer = make_user("supapi_other", Role.ROLE_CUSTOMER)
        cls.agent = make_user("supapi_agent", Role.ROLE_SUPPORT_TEAM, first_name="Rina", last_name="Akter")
        cls.finance = make_user("supapi_finance", Role.ROLE_FINANCE)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def open_ticket(self, customer=None, **overrides):
        data = {
            "category": SupportTicket.CATEGORY_ORDER,
            "subject": "Parcel is late",
            "description": "My parcel has not arrived yet.",
        }
        data.update(overrides)
        return Service.create_ticket(customer or self.customer, **data)

    def as_user(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client


class CreateTicketApiTests(CustomerSupportApiTestCase):
    def test_create_with_attachments(self):
        response = self.client.post(
            LIST_URL,
            {
                "category": "PRODUCT",
                "subject": "Parcel arrived damaged",
                "description": "The box was crushed and the lamp is broken.",
                "attachments": [png("box.png"), pdf("label.jpg")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data

        self.assertRegex(data["ticket_number"], r"^TKT\d{8}[0-9A-F]{6}$")
        self.assertEqual(data["status"], "OPEN")
        self.assertEqual(data["status_label"], "Open")
        self.assertEqual(data["category_label"], "Wrong or damaged item")
        self.assertIsNone(data["order_number"])
        self.assertFalse(data["has_unread"])
        self.assertTrue(data["can_reply"])
        self.assertTrue(data["can_close"])
        self.assertFalse(STAFF_ONLY_KEYS & set(data))

        (message,) = data["messages"]
        self.assertEqual(message["author_type"], "CUSTOMER")
        self.assertEqual(message["author_name"], "You")
        self.assertEqual(message["body"], "The box was crushed and the lamp is broken.")
        self.assertEqual(
            [(a["name"], a["content_type"]) for a in message["attachments"]],
            [("box.png", "image/png"), ("label.pdf", "application/pdf")],
        )
        for item in message["attachments"]:
            self.assertEqual(item["url"], f"/api/support/attachments/{item['id']}/")

        ticket = SupportTicket.objects.get(ticket_number=data["ticket_number"])
        self.assertEqual(ticket.customer, self.customer)
        self.assertTrue(AuditLog.objects.filter(action="SUPPORT_TICKET_CREATED", target_id=str(ticket.pk)).exists())

    def test_create_linked_to_own_order(self):
        Order.objects.create(user=self.customer, order_number="ORDAPI-OWN")
        response = self.client.post(
            LIST_URL,
            {"category": "ORDER", "subject": "Where is it?", "description": "Order is two weeks late.",
             "order_number": "ORDAPI-OWN"},
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["order_number"], "ORDAPI-OWN")

    def test_field_errors(self):
        base = {"category": "ORDER", "subject": "Where is it?", "description": "Order is two weeks late."}
        cases = [
            ({"category": "NOPE"}, "category", "Choose a valid category."),
            ({"subject": "Hi"}, "subject", "Subject must be at least 5 characters."),
            ({"subject": "   "}, "subject", "Subject is required."),
            ({"description": "short"}, "description", "Description must be at least 10 characters."),
        ]
        for overrides, field, message in cases:
            with self.subTest(field=field, overrides=overrides):
                response = self.client.post(LIST_URL, {**base, **overrides})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data[field], [message])
        self.assertFalse(SupportTicket.objects.exists())

    def test_rule_errors_come_back_as_detail(self):
        Order.objects.create(user=self.other_customer, order_number="ORDAPI-OTHER")
        base = {"category": "ORDER", "subject": "Where is it?", "description": "Order is two weeks late."}

        response = self.client.post(LIST_URL, {**base, "order_number": "ORDAPI-OTHER"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Order not found."})

        response = self.client.post(
            LIST_URL, {**base, "attachments": [upload("evil.svg", b"<svg/>")]}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "“evil.svg” isn't a JPG, PNG, WebP or PDF file."})

        for _ in range(5):
            self.open_ticket()
        response = self.client.post(LIST_URL, base)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already have 5 open tickets", response.data["detail"])


class PermissionApiTests(CustomerSupportApiTestCase):
    def test_anonymous_is_rejected_everywhere(self):
        ticket = self.open_ticket()
        attachment_id = 1
        anonymous = self.as_user(None)
        for method, url in (
            ("get", LIST_URL),
            ("post", LIST_URL),
            ("get", UNREAD_URL),
            ("get", detail_url(ticket)),
            ("post", messages_url(ticket)),
            ("post", close_url(ticket)),
            ("get", reverse("support:attachment-download", args=[attachment_id])),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(anonymous, method)(url).status_code, 401)

    def test_users_without_the_codes_get_403(self):
        client = self.as_user(self.finance)
        self.assertEqual(client.get(LIST_URL).status_code, 403)
        self.assertEqual(client.get(UNREAD_URL).status_code, 403)
        response = client.post(
            LIST_URL, {"category": "ORDER", "subject": "Hello there", "description": "Let me in please."}
        )
        self.assertEqual(response.status_code, 403)


class ReadTicketApiTests(CustomerSupportApiTestCase):
    def test_list_is_scoped_filtered_and_paginated(self):
        first = self.open_ticket(subject="First ticket")
        second = self.open_ticket(subject="Second ticket")
        Service.close_by_customer(self.customer, first.ticket_number)
        self.open_ticket(customer=self.other_customer, subject="Not yours")

        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 2)
        # Newest activity first: closing "First" was the latest thing to happen.
        self.assertEqual(
            [t["ticket_number"] for t in response.data["results"]],
            [first.ticket_number, second.ticket_number],
        )
        self.assertFalse(STAFF_ONLY_KEYS & set(response.data["results"][0]))

        open_only = self.client.get(LIST_URL, {"status": "open"}).data
        self.assertEqual([t["ticket_number"] for t in open_only["results"]], [second.ticket_number])
        closed_only = self.client.get(LIST_URL, {"status": "closed"}).data
        self.assertEqual([t["ticket_number"] for t in closed_only["results"]], [first.ticket_number])
        self.assertEqual(self.client.get(LIST_URL, {"status": "bogus"}).status_code, 400)

    def test_detail_hides_internal_notes_and_staff_fields(self):
        ticket = self.open_ticket()
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "SECRET courier blames the warehouse.",
            is_internal=True, files=[pdf("courier-report.pdf")],
        )
        Service.add_staff_message(self.agent, ticket.ticket_number, "We're on it!")
        Service.update_details(self.agent, ticket.ticket_number, priority="URGENT")
        Service.assign(self.agent, ticket.ticket_number, self.agent)

        response = self.client.get(detail_url(ticket))
        self.assertEqual(response.status_code, 200)
        data = response.data

        self.assertNotIn(b"SECRET", response.content)
        self.assertNotIn(b"courier-report", response.content)
        self.assertNotIn(b"URGENT", response.content)
        self.assertNotIn(b"Assigned to", response.content)
        self.assertFalse(STAFF_ONLY_KEYS & set(data))
        self.assertEqual(data["status"], "IN_PROGRESS")
        self.assertEqual(data["status_label"], "In progress")
        self.assertEqual(
            [(m["author_type"], m["author_name"], m["body"]) for m in data["messages"]],
            [
                ("CUSTOMER", "You", "My parcel has not arrived yet."),
                ("STAFF", "Rina · MiniShop Support", "We're on it!"),
                ("SYSTEM", "MiniShop Support", "Status changed to In progress."),
            ],
        )

    def test_waiting_on_customer_reads_as_waiting_on_you(self):
        ticket = self.open_ticket()
        Service.add_staff_message(self.agent, ticket.ticket_number, "Photo please?", set_status="WAITING_ON_CUSTOMER")
        self.assertEqual(self.client.get(detail_url(ticket)).data["status_label"], "Waiting on you")

    def test_unread_marker_clears_when_the_ticket_is_opened(self):
        ticket = self.open_ticket()
        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 0})

        Service.add_staff_message(self.agent, ticket.ticket_number, "Any update from you?")
        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 1})
        self.assertTrue(self.client.get(LIST_URL).data["results"][0]["has_unread"])
        # An internal note isn't something the customer can read.
        other = self.open_ticket(subject="Second one")
        Service.add_staff_message(self.agent, other.ticket_number, "Internal only", is_internal=True)
        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 1})

        self.assertFalse(self.client.get(detail_url(ticket)).data["has_unread"])
        self.assertEqual(self.client.get(UNREAD_URL).data, {"unread": 0})
        self.assertFalse(self.client.get(LIST_URL).data["results"][0]["has_unread"])


class WriteTicketApiTests(CustomerSupportApiTestCase):
    def test_reply_returns_the_updated_ticket(self):
        ticket = self.open_ticket()
        Service.add_staff_message(self.agent, ticket.ticket_number, "Photo please?", set_status="WAITING_ON_CUSTOMER")

        response = self.client.post(
            messages_url(ticket), {"body": "Here it is.", "attachments": [png("label.png")]}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "OPEN")
        last_two = response.data["messages"][-2:]
        self.assertEqual(last_two[0]["body"], "Here it is.")
        self.assertEqual(last_two[0]["attachments"][0]["name"], "label.png")
        self.assertEqual(last_two[1]["body"], "Reopened by the customer's reply.")

    def test_reply_errors(self):
        ticket = self.open_ticket()
        response = self.client.post(messages_url(ticket), {"body": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Write a message or attach a file."})

        Service.close_by_customer(self.customer, ticket.ticket_number)
        response = self.client.post(messages_url(ticket), {"body": "Hello?"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("This ticket is closed", response.data["detail"])

    def test_close(self):
        ticket = self.open_ticket()
        response = self.client.post(close_url(ticket))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CLOSED")
        self.assertFalse(response.data["can_reply"])
        self.assertFalse(response.data["can_close"])
        self.assertIsNotNone(response.data["closed_at"])

        response = self.client.post(close_url(ticket))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "This ticket is already closed."})

    def test_other_customers_tickets_are_404(self):
        ticket = self.open_ticket(files=[png()])
        attachment = TicketAttachment.objects.get(message__ticket=ticket)
        intruder = self.as_user(self.other_customer)

        self.assertEqual(intruder.get(detail_url(ticket)).status_code, 404)
        self.assertEqual(intruder.post(messages_url(ticket), {"body": "Hi"}).status_code, 404)
        self.assertEqual(intruder.post(close_url(ticket)).status_code, 404)
        self.assertEqual(intruder.get(attachment_url(attachment)).status_code, 404)
        self.assertEqual(self.client.get(reverse("support:ticket-detail", args=["TKT00000000NOPE00"])).status_code, 404)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "OPEN")
        self.assertEqual(ticket.messages.count(), 1)


class AttachmentDownloadApiTests(CustomerSupportApiTestCase):
    def test_owner_downloads_with_safe_headers(self):
        ticket = self.open_ticket(files=[png("box.png")])
        attachment = TicketAttachment.objects.get(message__ticket=ticket)

        response = self.client.get(attachment_url(attachment))
        self.assertEqual(response.status_code, 200)
        # Reading streaming_content to the end closes the response. Don't call
        # response.close() again: that fires request_finished a second time, and
        # Django then closes the database connection mid-transaction.
        self.assertEqual(b"".join(response.streaming_content), image_bytes("PNG"))
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Disposition"], 'inline; filename="box.png"')
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_internal_note_attachments_are_404_even_for_the_owner(self):
        ticket = self.open_ticket()
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "Courier report", is_internal=True, files=[pdf()]
        )
        attachment = TicketAttachment.objects.get(message__ticket=ticket)
        self.assertEqual(self.client.get(attachment_url(attachment)).status_code, 404)

    def test_missing_file_is_404(self):
        ticket = self.open_ticket(files=[png()])
        attachment = TicketAttachment.objects.get(message__ticket=ticket)
        (Path(self.private_root) / attachment.file.name).unlink()

        response = self.client.get(attachment_url(attachment))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"detail": "This file is no longer available."})
