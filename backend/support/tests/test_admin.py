from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from support.models import SupportTicket, TicketMessage

User = get_user_model()


class SupportTicketAdminTests(TestCase):
    """
    Django admin may only inspect tickets. A change form would let anyone with
    Django's own change permission rewrite status or assignee without the
    service's row lock or audit entry (the Known Issue #22 bypass).
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="support_admin_root", email="root@example.com", password="pw"
        )
        customer = User.objects.create_user(username="support_admin_customer", password="pw")
        cls.ticket = SupportTicket.objects.create(
            ticket_number="TKT20260924ADMIN1",
            customer=customer,
            category=SupportTicket.CATEGORY_ORDER,
            subject="Where is my parcel?",
        )
        TicketMessage.objects.create(
            ticket=cls.ticket,
            author=customer,
            author_type=TicketMessage.AUTHOR_CUSTOMER,
            body="It has been two weeks.",
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.change_url = reverse("admin:support_supportticket_change", args=[self.ticket.pk])

    def test_changelist_lists_the_ticket(self):
        response = self.client.get(reverse("admin:support_supportticket_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TKT20260924ADMIN1")

    def test_change_page_is_view_only(self):
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "It has been two weeks.")
        self.assertNotContains(response, 'name="_save"')
        self.assertNotContains(response, 'name="status"')

    def test_post_to_change_page_does_not_change_the_ticket(self):
        response = self.client.post(self.change_url, {"status": SupportTicket.STATUS_CLOSED})
        self.assertEqual(response.status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, SupportTicket.STATUS_OPEN)

    def test_add_is_forbidden(self):
        response = self.client.get(reverse("admin:support_supportticket_add"))
        self.assertEqual(response.status_code, 403)

    def test_delete_is_forbidden(self):
        url = reverse("admin:support_supportticket_delete", args=[self.ticket.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(SupportTicket.objects.filter(pk=self.ticket.pk).exists())
