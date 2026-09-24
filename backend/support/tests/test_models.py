from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from support.models import SupportTicket, TicketMessage

User = get_user_model()

OPEN = SupportTicket.STATUS_OPEN
IN_PROGRESS = SupportTicket.STATUS_IN_PROGRESS
WAITING = SupportTicket.STATUS_WAITING_ON_CUSTOMER
RESOLVED = SupportTicket.STATUS_RESOLVED
CLOSED = SupportTicket.STATUS_CLOSED
ALL_STATUSES = [OPEN, IN_PROGRESS, WAITING, RESOLVED, CLOSED]


class TicketTransitionTests(SimpleTestCase):
    """The staff transition table from docs/SUPPORT_SYSTEM.md §3, pair by pair."""

    ALLOWED = {
        OPEN: {IN_PROGRESS, WAITING, RESOLVED, CLOSED},
        IN_PROGRESS: {WAITING, RESOLVED, CLOSED},
        WAITING: {IN_PROGRESS, RESOLVED, CLOSED},
        RESOLVED: {IN_PROGRESS, CLOSED},
        CLOSED: set(),
    }

    def test_every_pair_matches_the_table(self):
        for current in ALL_STATUSES:
            for target in ALL_STATUSES:
                with self.subTest(current=current, target=target):
                    ticket = SupportTicket(status=current)
                    self.assertEqual(
                        ticket.can_transition_to(target),
                        target in self.ALLOWED[current],
                    )

    def test_table_covers_every_status_choice(self):
        choices = {value for value, _ in SupportTicket.STATUS_CHOICES}
        self.assertEqual(set(SupportTicket.VALID_TRANSITIONS), choices)

    def test_closed_is_terminal(self):
        self.assertEqual(SupportTicket.VALID_TRANSITIONS[CLOSED], [])
        self.assertTrue(SupportTicket(status=CLOSED).is_closed)
        self.assertFalse(SupportTicket(status=RESOLVED).is_closed)

    def test_customer_can_close_from_every_open_status(self):
        # The customer "Close ticket" action relies on this.
        for current in ALL_STATUSES:
            if current == CLOSED:
                continue
            with self.subTest(current=current):
                self.assertTrue(SupportTicket(status=current).can_transition_to(CLOSED))

    def test_unknown_status_goes_nowhere(self):
        self.assertFalse(SupportTicket(status="BOGUS").can_transition_to(OPEN))
        self.assertFalse(SupportTicket(status=OPEN).can_transition_to("BOGUS"))

    def test_status_groups(self):
        self.assertEqual(set(SupportTicket.CUSTOMER_REOPEN_STATUSES), {WAITING, RESOLVED})
        self.assertEqual(set(SupportTicket.UNRESOLVED_STATUSES), {OPEN, IN_PROGRESS, WAITING})


class TicketModelDatabaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="support_model_customer", password="pw")
        cls.ticket = SupportTicket.objects.create(
            ticket_number="TKT20260924ABC123",
            customer=cls.customer,
            category=SupportTicket.CATEGORY_ORDER,
            subject="Parcel arrived damaged",
        )

    def test_defaults(self):
        self.assertEqual(self.ticket.status, OPEN)
        self.assertEqual(self.ticket.priority, SupportTicket.PRIORITY_NORMAL)
        self.assertIsNone(self.ticket.assigned_to)
        self.assertIsNone(self.ticket.order)
        self.assertIsNotNone(self.ticket.last_activity_at)
        self.assertEqual(str(self.ticket), "TKT20260924ABC123 (OPEN)")

    def test_ticket_number_is_unique(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SupportTicket.objects.create(
                ticket_number="TKT20260924ABC123",
                customer=self.customer,
                category=SupportTicket.CATEGORY_OTHER,
                subject="Duplicate",
            )

    def test_customer_message_cannot_be_internal(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TicketMessage.objects.create(
                ticket=self.ticket,
                author=self.customer,
                author_type=TicketMessage.AUTHOR_CUSTOMER,
                body="Hidden from myself?",
                is_internal=True,
            )

    def test_staff_and_system_messages_may_be_internal(self):
        for author_type in (TicketMessage.AUTHOR_STAFF, TicketMessage.AUTHOR_SYSTEM):
            with self.subTest(author_type=author_type):
                message = TicketMessage.objects.create(
                    ticket=self.ticket,
                    author_type=author_type,
                    body="Staff only",
                    is_internal=True,
                )
                self.assertTrue(message.is_internal)

    def test_ticket_survives_customer_deletion(self):
        customer = User.objects.create_user(username="support_model_leaver", password="pw")
        ticket = SupportTicket.objects.create(
            ticket_number="TKT20260924DEF456",
            customer=customer,
            category=SupportTicket.CATEGORY_ACCOUNT,
            subject="Close my account",
        )
        customer.delete()
        ticket.refresh_from_db()
        self.assertIsNone(ticket.customer)
