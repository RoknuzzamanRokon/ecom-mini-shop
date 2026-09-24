"""
close_resolved_tickets (D17): which resolved tickets it closes, what a close
records, and that --dry-run changes nothing.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLog
from rbac.models import Role
from support.models import SupportTicket, TicketMessage
from support.services import SupportTicketService as Service

from .helpers import make_user

OPEN = SupportTicket.STATUS_OPEN
IN_PROGRESS = SupportTicket.STATUS_IN_PROGRESS
WAITING = SupportTicket.STATUS_WAITING_ON_CUSTOMER
RESOLVED = SupportTicket.STATUS_RESOLVED
CLOSED = SupportTicket.STATUS_CLOSED

STATUS_CHANGED = "SUPPORT_TICKET_STATUS_CHANGED"


class AutoCloseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = make_user("auto_customer", Role.ROLE_CUSTOMER)

    def ticket(self, status=RESOLVED, *, resolved=None, activity=None, customer=None, **extra):
        """
        A real ticket, then forced into `status` with its timestamps set so many
        days in the past (None leaves resolved_at / last_customer_message_at
        empty; `activity` defaults to `resolved`).
        """
        ticket = Service.create_ticket(
            self.customer,
            category=SupportTicket.CATEGORY_OTHER,
            subject="Old problem",
            description="Something went wrong with my order.",
        )
        now = timezone.now()

        def ago(days):
            return None if days is None else now - timedelta(days=days)

        SupportTicket.objects.filter(pk=ticket.pk).update(
            status=status,
            resolved_at=ago(resolved),
            last_activity_at=ago(activity if activity is not None else resolved) or now,
            last_customer_message_at=ago(customer),
            **extra,
        )
        ticket.refresh_from_db()
        return ticket

    def run_command(self, *args):
        out = StringIO()
        call_command("close_resolved_tickets", *args, stdout=out)
        return out.getvalue()

    def assertStatus(self, ticket, status):
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, status)


class WhichTicketsCloseTests(AutoCloseTestCase):
    def test_closes_a_ticket_resolved_more_than_seven_days_ago(self):
        ticket = self.ticket(resolved=8, customer=9)

        out = self.run_command()

        self.assertStatus(ticket, CLOSED)
        self.assertIsNotNone(ticket.closed_at)
        self.assertIn(f"closed {ticket.ticket_number}", out)
        self.assertIn("Closed 1 resolved ticket(s) quiet for 7+ day(s).", out)

    def test_leaves_a_recently_resolved_ticket(self):
        ticket = self.ticket(resolved=3, customer=4)

        out = self.run_command()

        self.assertStatus(ticket, RESOLVED)
        self.assertIn("Closed 0 resolved ticket(s)", out)

    def test_leaves_a_ticket_the_customer_wrote_in_after_it_was_resolved(self):
        # A customer reply normally reopens the ticket; this guards the case
        # where one didn't, however old the message is.
        recent = self.ticket(resolved=10, activity=2, customer=2)
        old = self.ticket(resolved=10, activity=9, customer=9)

        self.run_command()

        self.assertStatus(recent, RESOLVED)
        self.assertStatus(old, RESOLVED)

    def test_a_staff_follow_up_after_resolving_restarts_the_clock(self):
        ticket = self.ticket(resolved=10, activity=2, customer=11)

        self.run_command()

        self.assertStatus(ticket, RESOLVED)

    def test_only_resolved_tickets_are_closed(self):
        tickets = {status: self.ticket(status, activity=30, customer=30) for status in (OPEN, IN_PROGRESS, WAITING)}

        self.run_command()

        for status, ticket in tickets.items():
            self.assertStatus(ticket, status)

    def test_days_option_changes_the_cut_off(self):
        ticket = self.ticket(resolved=4, customer=5)

        self.run_command()
        self.assertStatus(ticket, RESOLVED)

        out = self.run_command("--days", "3")
        self.assertStatus(ticket, CLOSED)
        self.assertIn("quiet for 3+ day(s)", out)
        line = ticket.messages.order_by("-id").first()
        self.assertEqual(line.body, "Closed automatically after 3 days without a reply.")

    def test_days_must_be_at_least_one(self):
        for value in ("0", "-2"):
            with self.subTest(days=value), self.assertRaisesMessage(CommandError, "--days must be at least 1."):
                self.run_command("--days", value)


class WhatAClosingRecordsTests(AutoCloseTestCase):
    def test_public_system_line_and_audit_entry_with_no_actor(self):
        ticket = self.ticket(resolved=8, customer=9)

        self.run_command()

        ticket.refresh_from_db()
        line = ticket.messages.order_by("-id").first()
        self.assertEqual(line.author_type, TicketMessage.AUTHOR_SYSTEM)
        self.assertIsNone(line.author)
        self.assertFalse(line.is_internal)
        self.assertEqual(line.body, "Closed automatically after 7 days without a reply.")
        self.assertEqual(ticket.last_activity_at, ticket.closed_at)

        audit = AuditLog.objects.get(action=STATUS_CHANGED, target_id=str(ticket.pk))
        self.assertIsNone(audit.actor)
        self.assertEqual(audit.metadata["previous_state"], {"status": RESOLVED})
        self.assertEqual(audit.metadata["new_state"], {"status": CLOSED})
        self.assertEqual(audit.metadata["changed_by"], "system")
        self.assertEqual(audit.metadata["ticket_number"], ticket.ticket_number)
        self.assertEqual(audit.reason, "Resolved, with no customer reply for 7 days.")

    def test_the_customer_gets_no_unread_marker(self):
        # The closing line is a system line, not a staff reply.
        ticket = self.ticket(
            resolved=8, customer=9,
            last_staff_reply_at=timezone.now() - timedelta(days=8, hours=1),
            customer_last_read_at=timezone.now() - timedelta(days=8),
        )

        self.run_command()

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CLOSED)
        self.assertFalse(ticket.has_unread_for_customer)

    def test_running_twice_closes_once(self):
        ticket = self.ticket(resolved=8, customer=9)

        self.run_command()
        out = self.run_command()

        self.assertIn("Closed 0 resolved ticket(s)", out)
        self.assertEqual(AuditLog.objects.filter(action=STATUS_CHANGED, target_id=str(ticket.pk)).count(), 1)


class DryRunTests(AutoCloseTestCase):
    def test_dry_run_lists_the_tickets_and_changes_nothing(self):
        ticket = self.ticket(resolved=8, customer=9)
        recent = self.ticket(resolved=2, customer=3)
        messages_before = TicketMessage.objects.count()
        audits_before = AuditLog.objects.count()

        out = self.run_command("--dry-run")

        self.assertStatus(ticket, RESOLVED)
        self.assertIsNone(ticket.closed_at)
        self.assertStatus(recent, RESOLVED)
        self.assertEqual(TicketMessage.objects.count(), messages_before)
        self.assertEqual(AuditLog.objects.count(), audits_before)
        self.assertIn(f"would close {ticket.ticket_number} (resolved ", out)
        self.assertNotIn(recent.ticket_number, out)
        self.assertIn("Dry run: 1 resolved ticket(s) quiet for 7+ day(s) would be closed.", out)


class ChangedWhileRunningTests(AutoCloseTestCase):
    def test_a_ticket_reopened_after_it_was_listed_is_left_alone(self):
        ticket = self.ticket(resolved=8, customer=9)
        listed = list(Service.stale_resolved_tickets().values_list("ticket_number", flat=True))
        self.assertEqual(listed, [ticket.ticket_number])

        # The customer answers before the command gets to the ticket.
        Service.add_customer_reply(self.customer, ticket.ticket_number, "Actually it broke again.")

        self.assertFalse(Service.auto_close_resolved(ticket.ticket_number))
        self.assertStatus(ticket, OPEN)

    def test_the_summary_counts_tickets_left_alone(self):
        self.ticket(resolved=8, customer=9)

        with mock.patch.object(Service, "auto_close_resolved", return_value=False):
            out = self.run_command()

        self.assertIn("Closed 0 resolved ticket(s) quiet for 7+ day(s). 1 changed while running", out)
