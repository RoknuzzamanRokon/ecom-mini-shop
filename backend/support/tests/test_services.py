import re
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLog
from rbac.models import Permission, Role, UserPermission, UserRole
from shop.models import Order
from support.exceptions import AttachmentError, SupportTicketError
from support.models import SupportTicket, TicketAttachment, TicketMessage
from support.services import SupportTicketService as Service

from .helpers import PrivateMediaMixin, make_user, pdf, png, upload

User = get_user_model()

OPEN = SupportTicket.STATUS_OPEN
IN_PROGRESS = SupportTicket.STATUS_IN_PROGRESS
WAITING = SupportTicket.STATUS_WAITING_ON_CUSTOMER
RESOLVED = SupportTicket.STATUS_RESOLVED
CLOSED = SupportTicket.STATUS_CLOSED


class SupportServiceTestCase(PrivateMediaMixin, TestCase):
    """
    Customer and other_customer hold CUSTOMER; agent holds SUPPORT_TEAM (view,
    reply, manage); ops holds OPERATION_MANAGER (view, reply); finance holds
    FINANCE (no support codes at all).
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = make_user("sup_customer", Role.ROLE_CUSTOMER)
        cls.other_customer = make_user("sup_other", Role.ROLE_CUSTOMER)
        cls.agent = make_user("sup_agent", Role.ROLE_SUPPORT_TEAM, first_name="Rina", last_name="Akter")
        cls.ops = make_user("sup_ops", Role.ROLE_OPERATION_MANAGER)
        cls.finance = make_user("sup_finance", Role.ROLE_FINANCE)

    def open_ticket(self, customer=None, **overrides):
        data = {
            "category": SupportTicket.CATEGORY_ORDER,
            "subject": "Parcel is late",
            "description": "My parcel has not arrived yet.",
        }
        data.update(overrides)
        return Service.create_ticket(customer or self.customer, **data)

    def force_status(self, ticket, status, **extra):
        SupportTicket.objects.filter(pk=ticket.pk).update(status=status, **extra)
        ticket.refresh_from_db()

    def messages(self, ticket):
        return list(ticket.messages.order_by("created_at", "id"))

    def audits(self, action, ticket):
        return AuditLog.objects.filter(action=action, target_id=str(ticket.pk)).order_by("id")


class TicketCreationTests(SupportServiceTestCase):
    def test_creates_ticket_with_first_message(self):
        ticket = self.open_ticket(subject="  Parcel is late  ", description="  It is two weeks late.  ")

        self.assertRegex(ticket.ticket_number, r"^TKT\d{8}[0-9A-F]{6}$")
        self.assertEqual(ticket.status, OPEN)
        self.assertEqual(ticket.priority, SupportTicket.PRIORITY_NORMAL)
        self.assertEqual(ticket.subject, "Parcel is late")
        self.assertEqual(ticket.customer, self.customer)
        self.assertIsNone(ticket.order)
        self.assertEqual(ticket.last_activity_at, ticket.last_customer_message_at)
        self.assertIsNone(ticket.last_staff_reply_at)
        self.assertIsNone(ticket.first_response_at)

        (message,) = self.messages(ticket)
        self.assertEqual(message.author, self.customer)
        self.assertEqual(message.author_type, TicketMessage.AUTHOR_CUSTOMER)
        self.assertEqual(message.body, "It is two weeks late.")
        self.assertFalse(message.is_internal)

    def test_creation_is_audited(self):
        ticket = self.open_ticket(files=[png()])
        (entry,) = self.audits("SUPPORT_TICKET_CREATED", ticket)
        self.assertEqual(entry.actor, self.customer)
        self.assertEqual(entry.metadata["ticket_number"], ticket.ticket_number)
        self.assertEqual(entry.metadata["attachment_count"], 1)

    def test_links_the_customers_own_order(self):
        order = Order.objects.create(user=self.customer, order_number="ORDSUP-OWN")
        ticket = self.open_ticket(order_number=" ORDSUP-OWN ")
        self.assertEqual(ticket.order, order)

    def test_someone_elses_or_unknown_order_is_refused_the_same_way(self):
        Order.objects.create(user=self.other_customer, order_number="ORDSUP-OTHER")
        for order_number in ("ORDSUP-OTHER", "ORDSUP-NOPE"):
            with self.subTest(order_number=order_number):
                with self.assertRaisesMessage(SupportTicketError, "Order not found."):
                    self.open_ticket(order_number=order_number)
        self.assertFalse(SupportTicket.objects.filter(customer=self.customer).exists())

    def test_invalid_fields_are_refused(self):
        cases = {
            "category": {"category": "BOGUS"},
            "short subject": {"subject": "Hi  "},
            "long subject": {"subject": "x" * 151},
            "short description": {"description": "Too short"},
            "long description": {"description": "x" * 5001},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                with self.assertRaises(SupportTicketError):
                    self.open_ticket(**overrides)
        self.assertFalse(SupportTicket.objects.exists())

    def test_needs_support_create(self):
        with self.assertRaises(PermissionDenied):
            self.open_ticket(customer=self.finance)

    def test_sixth_unresolved_ticket_is_refused(self):
        tickets = [self.open_ticket() for _ in range(5)]
        with self.assertRaisesMessage(SupportTicketError, "already have 5 open tickets"):
            self.open_ticket()

        # Resolved and closed tickets don't count against the cap.
        self.force_status(tickets[0], RESOLVED)
        self.force_status(tickets[1], CLOSED)
        self.open_ticket()
        self.open_ticket()
        with self.assertRaises(SupportTicketError):
            self.open_ticket()

        # The cap is per customer.
        self.open_ticket(customer=self.other_customer)

    def test_attachments_are_stored_privately(self):
        ticket = self.open_ticket(files=[png("box.png"), pdf("label.jpg")])
        attachments = list(TicketAttachment.objects.filter(message__ticket=ticket).order_by("id"))

        self.assertEqual([a.original_name for a in attachments], ["box.png", "label.pdf"])
        self.assertEqual(
            [a.content_type for a in attachments], ["image/png", "application/pdf"]
        )
        stored = self.private_files()
        for attachment in attachments:
            self.assertRegex(attachment.file.name, r"^support/\d{4}/\d{2}/[0-9a-f]{32}\.(png|pdf)$")
            self.assertIn(attachment.file.name, stored)

    def test_a_refused_attachment_creates_nothing(self):
        before = self.private_files()
        with self.assertRaises(AttachmentError):
            self.open_ticket(files=[png(), upload("evil.svg", b"<svg/>")])
        self.assertFalse(SupportTicket.objects.exists())
        self.assertEqual(self.private_files(), before)

    def test_files_are_deleted_when_the_transaction_fails(self):
        before = self.private_files()
        with mock.patch("support.services.AuditService.log", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.open_ticket(files=[png(), pdf()])
        self.assertFalse(SupportTicket.objects.exists())
        self.assertFalse(TicketAttachment.objects.exists())
        self.assertEqual(self.private_files(), before)


class CustomerReplyAndCloseTests(SupportServiceTestCase):
    def test_reply_while_being_worked_on_keeps_the_status(self):
        for status in (OPEN, IN_PROGRESS):
            with self.subTest(status=status):
                ticket = self.open_ticket()
                self.force_status(ticket, status)
                before = ticket.last_customer_message_at

                message = Service.add_customer_reply(self.customer, ticket.ticket_number, "Any news?")
                ticket.refresh_from_db()

                self.assertEqual(ticket.status, status)
                self.assertEqual(message.author_type, TicketMessage.AUTHOR_CUSTOMER)
                self.assertGreater(ticket.last_customer_message_at, before)
                self.assertEqual(ticket.last_activity_at, ticket.last_customer_message_at)
                self.assertFalse(ticket.messages.filter(author_type=TicketMessage.AUTHOR_SYSTEM).exists())

    def test_reply_reopens_a_waiting_or_resolved_ticket(self):
        for status in (WAITING, RESOLVED):
            with self.subTest(status=status):
                ticket = self.open_ticket()
                self.force_status(ticket, status, resolved_at=timezone.now())

                Service.add_customer_reply(self.customer, ticket.ticket_number, "Still broken.")
                ticket.refresh_from_db()

                self.assertEqual(ticket.status, OPEN)
                self.assertIsNone(ticket.resolved_at)
                system = self.messages(ticket)[-1]
                self.assertEqual(system.author_type, TicketMessage.AUTHOR_SYSTEM)
                self.assertFalse(system.is_internal)
                self.assertEqual(system.body, "Reopened by the customer's reply.")
                (entry,) = self.audits("SUPPORT_TICKET_STATUS_CHANGED", ticket)
                self.assertEqual(entry.actor, self.customer)
                self.assertEqual(entry.metadata["previous_state"], {"status": status})
                self.assertEqual(entry.metadata["new_state"], {"status": OPEN})
                self.assertEqual(entry.metadata["changed_by"], "customer")

    def test_closed_ticket_cannot_be_replied_to(self):
        ticket = self.open_ticket()
        self.force_status(ticket, CLOSED)
        with self.assertRaisesMessage(SupportTicketError, "This ticket is closed"):
            Service.add_customer_reply(self.customer, ticket.ticket_number, "Hello?")
        self.assertEqual(ticket.messages.count(), 1)

    def test_another_customers_ticket_does_not_exist(self):
        ticket = self.open_ticket()
        with self.assertRaises(SupportTicket.DoesNotExist):
            Service.add_customer_reply(self.other_customer, ticket.ticket_number, "Mine now")
        with self.assertRaises(SupportTicket.DoesNotExist):
            Service.close_by_customer(self.other_customer, ticket.ticket_number)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, OPEN)
        self.assertEqual(ticket.messages.count(), 1)

    def test_a_reply_needs_text_or_a_file(self):
        ticket = self.open_ticket()
        with self.assertRaisesMessage(SupportTicketError, "Write a message or attach a file."):
            Service.add_customer_reply(self.customer, ticket.ticket_number, "   ")
        with self.assertRaises(SupportTicketError):
            Service.add_customer_reply(self.customer, ticket.ticket_number, "x" * 5001)

        message = Service.add_customer_reply(self.customer, ticket.ticket_number, "", files=[png()])
        self.assertEqual(message.body, "")
        self.assertEqual(message.attachments.count(), 1)

    def test_customer_can_close_their_ticket(self):
        ticket = self.open_ticket()
        self.force_status(ticket, WAITING)

        Service.close_by_customer(self.customer, ticket.ticket_number)
        ticket.refresh_from_db()

        self.assertEqual(ticket.status, CLOSED)
        self.assertIsNotNone(ticket.closed_at)
        self.assertEqual(self.messages(ticket)[-1].body, "Closed by the customer.")
        self.assertEqual(self.audits("SUPPORT_TICKET_STATUS_CHANGED", ticket).count(), 1)
        with self.assertRaisesMessage(SupportTicketError, "already closed"):
            Service.close_by_customer(self.customer, ticket.ticket_number)

    def test_mark_read(self):
        ticket = self.open_ticket()
        SupportTicket.objects.filter(pk=ticket.pk).update(customer_last_read_at=None)
        Service.mark_read_by_customer(ticket)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.customer_last_read_at)


class StaffMessageTests(SupportServiceTestCase):
    def test_first_public_reply_moves_open_to_in_progress(self):
        ticket = self.open_ticket()

        Service.add_staff_message(self.agent, ticket.ticket_number, "Looking into it.")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, IN_PROGRESS)
        self.assertIsNotNone(ticket.first_response_at)
        self.assertEqual(ticket.last_staff_reply_at, ticket.first_response_at)
        self.assertEqual(ticket.last_activity_at, ticket.last_staff_reply_at)
        first_response = ticket.first_response_at

        Service.add_staff_message(self.agent, ticket.ticket_number, "Found your parcel.")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, IN_PROGRESS)
        self.assertEqual(ticket.first_response_at, first_response)
        self.assertGreater(ticket.last_staff_reply_at, first_response)
        self.assertEqual(
            [m.author_type for m in self.messages(ticket)],
            ["CUSTOMER", "STAFF", "SYSTEM", "STAFF"],
        )

    def test_a_reply_can_set_the_status(self):
        ticket = self.open_ticket()
        Service.add_staff_message(
            self.agent, ticket.ticket_number, "Can you send a photo?", set_status=WAITING
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WAITING)
        staff, system = self.messages(ticket)[1:]
        self.assertEqual(staff.body, "Can you send a photo?")
        self.assertEqual(system.body, "Status changed to Waiting on customer.")

    def test_a_reply_with_a_forbidden_status_changes_nothing(self):
        ticket = self.open_ticket()
        self.force_status(ticket, RESOLVED)
        with self.assertRaisesMessage(SupportTicketError, "can't move from Resolved to Waiting"):
            Service.add_staff_message(self.agent, ticket.ticket_number, "Hi", set_status=WAITING)
        self.assertEqual(ticket.messages.count(), 1)

    def test_setting_a_status_needs_manage(self):
        ticket = self.open_ticket()
        with self.assertRaises(PermissionDenied):
            Service.add_staff_message(self.ops, ticket.ticket_number, "Hi", set_status=RESOLVED)

        # A plain reply only needs support.staff.reply, and still picks the ticket up.
        Service.add_staff_message(self.ops, ticket.ticket_number, "On its way.")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, IN_PROGRESS)

    def test_internal_note_changes_nothing_the_customer_sees(self):
        ticket = self.open_ticket()
        before = SupportTicket.objects.get(pk=ticket.pk)

        note = Service.add_staff_message(
            self.agent, ticket.ticket_number, "Courier says it was lost.", is_internal=True, files=[pdf()]
        )
        ticket.refresh_from_db()

        self.assertTrue(note.is_internal)
        self.assertEqual(note.attachments.count(), 1)
        self.assertEqual(ticket.status, OPEN)
        self.assertEqual(ticket.last_activity_at, before.last_activity_at)
        self.assertIsNone(ticket.last_staff_reply_at)
        self.assertIsNone(ticket.first_response_at)

    def test_internal_note_cannot_set_a_status(self):
        ticket = self.open_ticket()
        with self.assertRaisesMessage(SupportTicketError, "internal note can't change the status"):
            Service.add_staff_message(
                self.agent, ticket.ticket_number, "Note", is_internal=True, set_status=RESOLVED
            )

    def test_closed_ticket_takes_notes_but_not_replies(self):
        ticket = self.open_ticket()
        self.force_status(ticket, CLOSED)
        with self.assertRaisesMessage(SupportTicketError, "This ticket is closed"):
            Service.add_staff_message(self.agent, ticket.ticket_number, "Hello?")
        Service.add_staff_message(self.agent, ticket.ticket_number, "For the record.", is_internal=True)
        self.assertEqual(ticket.messages.count(), 2)

    def test_customers_cannot_use_staff_methods(self):
        ticket = self.open_ticket()
        with self.assertRaises(PermissionDenied):
            Service.add_staff_message(self.customer, ticket.ticket_number, "I'm staff now")
        with self.assertRaises(PermissionDenied):
            Service.add_staff_message(self.finance, ticket.ticket_number, "Me too")


class StaffManagementTests(SupportServiceTestCase):
    def test_change_status_records_everything(self):
        ticket = self.open_ticket()
        Service.change_status(self.agent, ticket.ticket_number, RESOLVED, reason="Refund issued.")
        ticket.refresh_from_db()

        self.assertEqual(ticket.status, RESOLVED)
        self.assertIsNotNone(ticket.resolved_at)
        public, reason_note = self.messages(ticket)[1:]
        self.assertEqual(public.body, "Status changed to Resolved.")
        self.assertFalse(public.is_internal)
        self.assertEqual(reason_note.body, "Status change reason: Refund issued.")
        self.assertTrue(reason_note.is_internal)
        (entry,) = self.audits("SUPPORT_TICKET_STATUS_CHANGED", ticket)
        self.assertEqual(entry.actor, self.agent)
        self.assertEqual(entry.metadata["reason"], "Refund issued.")
        self.assertEqual(entry.metadata["previous_state"], {"status": OPEN})
        self.assertEqual(entry.metadata["new_state"], {"status": RESOLVED})

    def test_leaving_resolved_clears_resolved_at_and_closing_sets_closed_at(self):
        ticket = self.open_ticket()
        Service.change_status(self.agent, ticket.ticket_number, RESOLVED)
        Service.change_status(self.agent, ticket.ticket_number, IN_PROGRESS)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.resolved_at)

        Service.change_status(self.agent, ticket.ticket_number, CLOSED)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    def test_invalid_status_changes_are_refused(self):
        ticket = self.open_ticket()
        with self.assertRaisesMessage(SupportTicketError, "already open"):
            Service.change_status(self.agent, ticket.ticket_number, OPEN)
        with self.assertRaisesMessage(SupportTicketError, "valid status"):
            Service.change_status(self.agent, ticket.ticket_number, "BOGUS")
        with self.assertRaises(SupportTicketError):
            Service.change_status(self.agent, ticket.ticket_number, CLOSED, reason="x" * 501)

        self.force_status(ticket, CLOSED)
        with self.assertRaisesMessage(SupportTicketError, "can't move from Closed to Open"):
            Service.change_status(self.agent, ticket.ticket_number, OPEN)

    def test_managing_needs_manage(self):
        ticket = self.open_ticket()
        for call in (
            lambda: Service.change_status(self.ops, ticket.ticket_number, RESOLVED),
            lambda: Service.update_details(self.ops, ticket.ticket_number, priority="HIGH"),
            lambda: Service.assign(self.ops, ticket.ticket_number, self.ops),
        ):
            with self.assertRaises(PermissionDenied):
                call()

    def test_update_details(self):
        ticket = self.open_ticket()
        Service.update_details(
            self.agent, ticket.ticket_number,
            priority=SupportTicket.PRIORITY_HIGH,
            category=SupportTicket.CATEGORY_PAYMENT,
            reason="Charged twice.",
        )
        ticket.refresh_from_db()

        self.assertEqual(ticket.priority, SupportTicket.PRIORITY_HIGH)
        self.assertEqual(ticket.category, SupportTicket.CATEGORY_PAYMENT)
        note = self.messages(ticket)[-1]
        self.assertTrue(note.is_internal)
        self.assertEqual(
            note.body,
            "Priority changed from Normal to High. Category changed from Order & delivery "
            "to Payment & refund. Reason: Charged twice.",
        )
        (entry,) = self.audits("SUPPORT_TICKET_UPDATED", ticket)
        self.assertEqual(entry.metadata["previous_state"], {"priority": "NORMAL", "category": "ORDER"})
        self.assertEqual(entry.metadata["new_state"], {"priority": "HIGH", "category": "PAYMENT"})

        with self.assertRaisesMessage(SupportTicketError, "Nothing to change."):
            Service.update_details(self.agent, ticket.ticket_number, priority=SupportTicket.PRIORITY_HIGH)
        with self.assertRaisesMessage(SupportTicketError, "valid priority"):
            Service.update_details(self.agent, ticket.ticket_number, priority="PANIC")

    def test_assign_and_unassign(self):
        ticket = self.open_ticket()

        Service.assign(self.agent, ticket.ticket_number, self.agent)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_to, self.agent)
        self.assertEqual(self.messages(ticket)[-1].body, "Assigned to Rina Akter.")
        self.assertTrue(self.messages(ticket)[-1].is_internal)
        with self.assertRaisesMessage(SupportTicketError, "already assigned"):
            Service.assign(self.agent, ticket.ticket_number, self.agent)

        Service.assign(self.agent, ticket.ticket_number, None)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assigned_to)
        self.assertEqual(self.messages(ticket)[-1].body, "Unassigned.")
        entries = list(self.audits("SUPPORT_TICKET_ASSIGNED", ticket))
        self.assertEqual(entries[0].metadata["new_state"], {"assigned_to": self.agent.pk})
        self.assertEqual(entries[1].metadata["new_state"], {"assigned_to": None})

    def test_assignee_must_be_able_to_reply(self):
        ticket = self.open_ticket()
        inactive = make_user("sup_gone", Role.ROLE_SUPPORT_TEAM, is_active=False)
        for user in (self.customer, self.finance, inactive):
            with self.subTest(user=user.username):
                with self.assertRaisesMessage(SupportTicketError, "can't be assigned"):
                    Service.assign(self.agent, ticket.ticket_number, user)

        # OPERATION_MANAGER can reply, so it can be assigned (but not assign).
        Service.assign(self.agent, ticket.ticket_number, self.ops)

    def test_assignable_staff(self):
        direct = make_user("sup_direct")
        UserPermission.objects.create(
            user=direct, permission=Permission.objects.get(code="support.staff.reply")
        )
        superuser = User.objects.create_superuser("sup_root", "root@example.com", "pw")
        super_admin = make_user("sup_super_admin", Role.ROLE_SUPER_ADMINISTRATOR)
        inactive = make_user("sup_inactive", Role.ROLE_SUPPORT_TEAM, is_active=False)
        revoked = make_user("sup_revoked", Role.ROLE_SUPPORT_TEAM)
        UserRole.objects.filter(user=revoked).update(is_active=False)

        assignable = set(Service.get_assignable_staff())

        for user in (self.agent, self.ops, direct, superuser, super_admin):
            self.assertIn(user, assignable, user.username)
        for user in (self.customer, self.finance, inactive, revoked):
            self.assertNotIn(user, assignable, user.username)
        self.assertEqual(Service.get_assignable_staff().filter(pk=self.agent.pk).count(), 1)
