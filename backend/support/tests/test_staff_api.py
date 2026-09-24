from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from customers.models import CustomerProfile
from rbac.models import Role
from shop.models import Order
from support.models import SupportTicket, TicketAttachment
from support.services import SupportTicketService as Service

from .helpers import PrivateMediaMixin, make_user, pdf, png

LIST_URL = reverse("support:staff-ticket-list")
ASSIGNEES_URL = reverse("support:staff-assignees")
SUMMARY_URL = reverse("support:staff-summary")


def detail_url(ticket):
    return reverse("support:staff-ticket-detail", args=[ticket.ticket_number])


def messages_url(ticket):
    return reverse("support:staff-ticket-messages", args=[ticket.ticket_number])


def assign_url(ticket):
    return reverse("support:staff-ticket-assign", args=[ticket.ticket_number])


def attachment_url(attachment):
    return reverse("support:staff-attachment-download", args=[attachment.pk])


class StaffSupportApiTestCase(PrivateMediaMixin, TestCase):
    """
    customer / other_customer hold CUSTOMER; agent holds SUPPORT_TEAM (view,
    reply, manage); ops holds OPERATION_MANAGER (view, reply); finance holds
    no support code.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = make_user(
            "supstaff_customer", Role.ROLE_CUSTOMER, email="nadia@example.com",
            first_name="Nadia", last_name="Islam",
        )
        cls.other_customer = make_user("supstaff_other", Role.ROLE_CUSTOMER, email="karim@example.com")
        cls.agent = make_user("supstaff_agent", Role.ROLE_SUPPORT_TEAM, first_name="Rina", last_name="Akter")
        cls.ops = make_user("supstaff_ops", Role.ROLE_OPERATION_MANAGER, first_name="Omar")
        cls.finance = make_user("supstaff_finance", Role.ROLE_FINANCE)

    def setUp(self):
        self.client = self.as_user(self.agent)

    def as_user(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def open_ticket(self, customer=None, **overrides):
        data = {
            "category": SupportTicket.CATEGORY_ORDER,
            "subject": "Parcel is late",
            "description": "My parcel has not arrived yet.",
        }
        data.update(overrides)
        return Service.create_ticket(customer or self.customer, **data)

    @staticmethod
    def numbers(response):
        return [row["ticket_number"] for row in response.data["results"]]


class StaffPermissionApiTests(StaffSupportApiTestCase):
    def test_anonymous_is_401(self):
        self.assertEqual(self.as_user(None).get(LIST_URL).status_code, 401)

    def test_customers_and_other_staff_are_403_everywhere(self):
        ticket = self.open_ticket(files=[png()])
        attachment = TicketAttachment.objects.get(message__ticket=ticket)
        for user in (self.customer, self.finance):
            client = self.as_user(user)
            for method, url, body in (
                ("get", LIST_URL, None),
                ("get", detail_url(ticket), None),
                ("patch", detail_url(ticket), {"priority": "HIGH"}),
                ("post", messages_url(ticket), {"body": "Hi"}),
                ("post", assign_url(ticket), {"assignee_id": None}),
                ("get", ASSIGNEES_URL, None),
                ("get", SUMMARY_URL, None),
                ("get", attachment_url(attachment), None),
            ):
                with self.subTest(user=user.username, method=method, url=url):
                    response = getattr(client, method)(url, body, format="json") if body else getattr(client, method)(url)
                    self.assertEqual(response.status_code, 403)

    def test_operation_manager_can_read_and_reply_but_not_manage(self):
        ticket = self.open_ticket()
        client = self.as_user(self.ops)
        self.assertEqual(client.get(LIST_URL).status_code, 200)
        self.assertEqual(client.get(detail_url(ticket)).status_code, 200)
        self.assertEqual(client.post(messages_url(ticket), {"body": "On its way."}).status_code, 201)
        self.assertEqual(
            client.post(messages_url(ticket), {"body": "Done", "set_status": "RESOLVED"}).status_code, 403
        )
        self.assertEqual(client.patch(detail_url(ticket), {"priority": "HIGH"}, format="json").status_code, 403)
        self.assertEqual(client.post(assign_url(ticket), {"assignee_id": None}, format="json").status_code, 403)


class StaffListApiTests(StaffSupportApiTestCase):
    """
    t_open     customer, ORDER, linked order, untouched          → needs reply
    t_waiting  customer, PAYMENT, HIGH, agent's, waiting on them  → no reply needed
    t_urgent   other, PRODUCT, URGENT, ops', customer answered    → needs reply
    t_closed   other, ACCOUNT, closed by the customer
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Order.objects.create(user=cls.customer, order_number="ORDSTAFF-1")
        create = Service.create_ticket
        cls.t_open = create(
            cls.customer, category="ORDER", subject="Parcel is late",
            description="Two weeks and still nothing.", order_number="ORDSTAFF-1",
        )
        cls.t_waiting = create(
            cls.customer, category="PAYMENT", subject="Charged twice", description="Two bKash payments taken.",
        )
        Service.add_staff_message(cls.agent, cls.t_waiting.ticket_number, "Send the receipts?", set_status="WAITING_ON_CUSTOMER")
        Service.update_details(cls.agent, cls.t_waiting.ticket_number, priority="HIGH")
        Service.assign(cls.agent, cls.t_waiting.ticket_number, cls.agent)
        cls.t_urgent = create(
            cls.other_customer, category="PRODUCT", subject="Broken lamp", description="The lamp arrived in pieces.",
        )
        Service.add_staff_message(cls.agent, cls.t_urgent.ticket_number, "So sorry, checking.")
        Service.add_customer_reply(cls.other_customer, cls.t_urgent.ticket_number, "Any news?")
        Service.update_details(cls.agent, cls.t_urgent.ticket_number, priority="URGENT")
        Service.assign(cls.agent, cls.t_urgent.ticket_number, cls.ops)
        cls.t_closed = create(
            cls.other_customer, category="ACCOUNT", subject="Delete my account", description="Please remove my data.",
        )
        Service.close_by_customer(cls.other_customer, cls.t_closed.ticket_number)

    def test_lists_every_customers_tickets(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        row = next(r for r in response.data["results"] if r["ticket_number"] == self.t_urgent.ticket_number)
        self.assertEqual(row["priority"], "URGENT")
        self.assertEqual(row["priority_label"], "Urgent")
        self.assertEqual(row["status_label"], "In progress")
        self.assertEqual(row["customer"], {"id": self.other_customer.pk, "name": "supstaff_other", "email": "karim@example.com"})
        self.assertEqual(row["assigned_to"], {"id": self.ops.pk, "name": "Omar"})
        self.assertTrue(row["needs_reply"])

    def test_status_filter(self):
        self.assertEqual(self.client.get(LIST_URL, {"status": "active"}).data["count"], 3)
        self.assertEqual(self.numbers(self.client.get(LIST_URL, {"status": "CLOSED"})), [self.t_closed.ticket_number])
        self.assertEqual(
            self.numbers(self.client.get(LIST_URL, {"status": "WAITING_ON_CUSTOMER"})),
            [self.t_waiting.ticket_number],
        )
        self.assertEqual(self.client.get(LIST_URL, {"status": "all"}).data["count"], 4)
        self.assertEqual(self.client.get(LIST_URL, {"status": "bogus"}).status_code, 400)

    def test_priority_and_category_filters(self):
        self.assertEqual(self.numbers(self.client.get(LIST_URL, {"priority": "URGENT"})), [self.t_urgent.ticket_number])
        self.assertEqual(self.numbers(self.client.get(LIST_URL, {"category": "PAYMENT"})), [self.t_waiting.ticket_number])
        self.assertEqual(self.client.get(LIST_URL, {"priority": "PANIC"}).status_code, 400)
        self.assertEqual(self.client.get(LIST_URL, {"category": "FOOD"}).status_code, 400)

    def test_assigned_filter(self):
        self.assertEqual(self.numbers(self.client.get(LIST_URL, {"assigned": "me"})), [self.t_waiting.ticket_number])
        self.assertEqual(
            set(self.numbers(self.client.get(LIST_URL, {"assigned": "unassigned"}))),
            {self.t_open.ticket_number, self.t_closed.ticket_number},
        )
        self.assertEqual(
            self.numbers(self.client.get(LIST_URL, {"assigned": str(self.ops.pk)})), [self.t_urgent.ticket_number]
        )
        self.assertEqual(self.client.get(LIST_URL, {"assigned": "someone"}).status_code, 400)

    def test_needs_reply_filter(self):
        response = self.client.get(LIST_URL, {"needs_reply": "true"})
        self.assertEqual(set(self.numbers(response)), {self.t_open.ticket_number, self.t_urgent.ticket_number})
        self.assertTrue(all(row["needs_reply"] for row in response.data["results"]))

    def test_search(self):
        cases = {
            self.t_open.ticket_number[-6:].lower(): {self.t_open.ticket_number},
            "lamp": {self.t_urgent.ticket_number},
            "nadia@": {self.t_open.ticket_number, self.t_waiting.ticket_number},
            "Islam": {self.t_open.ticket_number, self.t_waiting.ticket_number},
            "ORDSTAFF-1": {self.t_open.ticket_number},
            "nothing matches this": set(),
        }
        for search, expected in cases.items():
            with self.subTest(search=search):
                self.assertEqual(set(self.numbers(self.client.get(LIST_URL, {"search": search}))), expected)

    def test_ordering(self):
        by_priority = self.numbers(self.client.get(LIST_URL, {"ordering": "-priority"}))
        self.assertEqual(by_priority[:2], [self.t_urgent.ticket_number, self.t_waiting.ticket_number])
        oldest_first = self.numbers(self.client.get(LIST_URL, {"ordering": "created_at"}))
        self.assertEqual(oldest_first[0], self.t_open.ticket_number)
        # Default: newest activity first (closing t_closed was the last thing to happen).
        self.assertEqual(self.numbers(self.client.get(LIST_URL))[0], self.t_closed.ticket_number)
        self.assertEqual(self.client.get(LIST_URL, {"ordering": "subject"}).status_code, 400)

    def test_page_size(self):
        response = self.client.get(LIST_URL, {"page_size": 2})
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])

    def test_summary(self):
        response = self.client.get(SUMMARY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "by_status": {"OPEN": 1, "IN_PROGRESS": 1, "WAITING_ON_CUSTOMER": 1, "RESOLVED": 0, "CLOSED": 1},
                "active": 3,
                "needs_reply": 2,
                "unassigned": 1,
                "assigned_to_me": 1,
            },
        )


class StaffDetailAndWriteApiTests(StaffSupportApiTestCase):
    def test_detail_shows_internal_notes_and_contact_details(self):
        CustomerProfile.objects.create(user=self.customer, display_name="Nadia I.", phone="01700000000")
        order = Order.objects.create(user=self.customer, order_number="ORDSTAFF-2")
        ticket = self.open_ticket(order_number="ORDSTAFF-2")
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "Courier blames the warehouse.", is_internal=True,
            files=[pdf("courier.pdf")],
        )
        Service.add_staff_message(self.agent, ticket.ticket_number, "We're on it!")

        response = self.client.get(detail_url(ticket))
        self.assertEqual(response.status_code, 200)
        data = response.data

        self.assertEqual(
            data["customer"],
            {
                "id": self.customer.pk, "name": "Nadia I.", "username": "supstaff_customer",
                "email": "nadia@example.com", "phone": "01700000000",
                "customer_profile_id": self.customer.customer_profile.pk,
            },
        )
        self.assertEqual(data["order"]["id"], order.pk)
        self.assertEqual(data["order"]["order_number"], "ORDSTAFF-2")
        self.assertEqual(data["priority"], "NORMAL")
        self.assertEqual(data["status"], "IN_PROGRESS")
        self.assertEqual(data["allowed_transitions"], ["WAITING_ON_CUSTOMER", "RESOLVED", "CLOSED"])
        self.assertIsNotNone(data["first_response_at"])
        self.assertFalse(data["needs_reply"])
        self.assertEqual(
            [(m["author_type"], m["author_name"], m["is_internal"], m["body"]) for m in data["messages"]],
            [
                ("CUSTOMER", "Nadia I.", False, "My parcel has not arrived yet."),
                ("STAFF", "Rina Akter", True, "Courier blames the warehouse."),
                ("STAFF", "Rina Akter", False, "We're on it!"),
                ("SYSTEM", "System", False, "Status changed to In progress."),
            ],
        )
        (internal_file,) = data["messages"][1]["attachments"]
        self.assertEqual(internal_file["name"], "courier.pdf")
        self.assertEqual(internal_file["url"], f"/api/support/staff/attachments/{internal_file['id']}/")
        self.assertEqual(self.client.get(internal_file["url"]).status_code, 200)

    def test_unknown_ticket_is_404(self):
        url = reverse("support:staff-ticket-detail", args=["TKT00000000NOPE00"])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"priority": "HIGH"}, format="json").status_code, 404)
        self.assertEqual(
            self.client.post(reverse("support:staff-ticket-messages", args=["TKT00000000NOPE00"]), {"body": "Hi"}).status_code,
            404,
        )

    def test_reply_and_internal_note(self):
        ticket = self.open_ticket()
        response = self.client.post(messages_url(ticket), {"body": "Looking into it."})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "IN_PROGRESS")

        response = self.client.post(
            messages_url(ticket),
            {"body": "Courier ref 12345", "is_internal": "true", "attachments": [png("label.png")]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        note = [m for m in response.data["messages"] if m["body"] == "Courier ref 12345"][0]
        self.assertTrue(note["is_internal"])
        self.assertEqual(note["attachments"][0]["name"], "label.png")

    def test_reply_can_set_status(self):
        ticket = self.open_ticket()
        response = self.client.post(messages_url(ticket), {"body": "Photo please?", "set_status": "WAITING_ON_CUSTOMER"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "WAITING_ON_CUSTOMER")
        self.assertFalse(response.data["needs_reply"])

    def test_reply_errors(self):
        ticket = self.open_ticket()
        response = self.client.post(messages_url(ticket), {"body": "Hi", "set_status": "LATER"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["set_status"], ["Choose a valid status."])

        Service.close_by_customer(self.customer, ticket.ticket_number)
        response = self.client.post(messages_url(ticket), {"body": "Hello?"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("This ticket is closed", response.data["detail"])

    def test_patch_status_priority_and_category(self):
        ticket = self.open_ticket()
        response = self.client.patch(
            detail_url(ticket), {"status": "RESOLVED", "reason": "Refund sent."}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "RESOLVED")
        self.assertIsNotNone(response.data["resolved_at"])
        self.assertEqual(response.data["allowed_transitions"], ["IN_PROGRESS", "CLOSED"])
        self.assertEqual(response.data["messages"][-1]["body"], "Status change reason: Refund sent.")

        response = self.client.patch(
            detail_url(ticket), {"priority": "HIGH", "category": "PAYMENT", "status": "CLOSED"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            (response.data["priority"], response.data["category"], response.data["status"]),
            ("HIGH", "PAYMENT", "CLOSED"),
        )

    def test_patch_is_all_or_nothing(self):
        ticket = self.open_ticket()
        Service.close_by_customer(self.customer, ticket.ticket_number)
        response = self.client.patch(detail_url(ticket), {"priority": "HIGH", "status": "OPEN"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "A ticket can't move from Closed to Open."})
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, "NORMAL")
        self.assertFalse(ticket.messages.filter(body__startswith="Priority changed").exists())

    def test_patch_validation(self):
        ticket = self.open_ticket()
        response = self.client.patch(detail_url(ticket), {"reason": "Just because"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Nothing to change."})
        response = self.client.patch(detail_url(ticket), {"priority": "PANIC"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["priority"], ["Choose a valid priority."])

    def test_assign(self):
        ticket = self.open_ticket()
        response = self.client.post(assign_url(ticket), {"assignee_id": self.ops.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["assigned_to"], {"id": self.ops.pk, "name": "Omar"})

        for bad in (self.customer.pk, self.finance.pk, 999999):
            with self.subTest(assignee_id=bad):
                response = self.client.post(assign_url(ticket), {"assignee_id": bad}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": "That user can't be assigned support tickets."})

        response = self.client.post(assign_url(ticket), {"assignee_id": None}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["assigned_to"])
        self.assertEqual(self.client.post(assign_url(ticket), {}, format="json").status_code, 400)

    def test_assignees(self):
        response = self.client.get(ASSIGNEES_URL)
        self.assertEqual(response.status_code, 200)
        by_id = {row["id"]: row for row in response.data}
        self.assertEqual(by_id[self.agent.pk]["name"], "Rina Akter")
        self.assertIn(self.ops.pk, by_id)
        self.assertNotIn(self.customer.pk, by_id)
        self.assertNotIn(self.finance.pk, by_id)
