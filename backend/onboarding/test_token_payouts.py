"""docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §2: tokens handed in for real payment."""
from rest_framework import status

from audit.models import AuditLog
from notifications import events
from notifications.categories import STAFF_QUEUE, WALLET
from notifications.models import Notification, NotificationEvent
from notifications.routing import route_event
from rbac.models import Permission, UserPermission
from .models import OnboardingSettings, TokenPayoutRequest, TokenTransaction
from .services import TokenService
from .tests import OnboardingTestCase


class TokenPayoutTestCase(OnboardingTestCase):
    """`sales` holds 51 tokens from one onboarded seller."""

    def setUp(self):
        super().setUp()
        self.onboard()

    def ask(self, tokens=50, note="bKash 01712345678", user=None):
        return self.as_user(user or self.sales).post(
            "/api/onboarding/payouts/", {"tokens": tokens, "note": note}, format="json"
        )

    def accept(self, payout_id, user=None, note="Paid by bKash"):
        return self.as_user(user or self.admin).post(
            f"/api/onboarding/payouts/review/{payout_id}/accept/", {"note": note}, format="json"
        )

    def reject(self, payout_id, reason="Not this month", user=None):
        return self.as_user(user or self.admin).post(
            f"/api/onboarding/payouts/review/{payout_id}/reject/", {"reason": reason}, format="json"
        )


class PayoutRequestTests(TokenPayoutTestCase):
    def test_asking_holds_the_tokens_and_values_them_in_taka(self):
        response = self.ask()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            (response.data["status"], response.data["tokens"], response.data["taka_per_token"], response.data["amount_taka"]),
            ("PENDING", 50, 1, 50),
        )
        self.assertEqual(TokenService.get_balance(self.sales), 1)
        held = TokenTransaction.objects.get(transaction_type=TokenTransaction.TYPE_PAYOUT_HELD)
        self.assertEqual((held.amount, held.payout_request_id), (50, response.data["id"]))
        self.assertTrue(AuditLog.objects.filter(action="TOKEN_PAYOUT_REQUESTED", actor=self.sales).exists())

        summary = self.as_user(self.sales).get("/api/onboarding/me/").data
        self.assertEqual((summary["tokens"], summary["taka_per_token"], summary["pending_payout_tokens"]), (1, 1, 50))

    def test_admins_hear_about_it(self):
        self.ask()
        route_event(NotificationEvent.objects.get(event_type=events.TOKEN_PAYOUT_REQUESTED).pk)
        inbox = Notification.objects.get(event_type=events.TOKEN_PAYOUT_REQUESTED)
        self.assertEqual((inbox.recipient, inbox.category), (self.admin, STAFF_QUEUE))
        self.assertIn("৳50", inbox.body)

    def test_the_token_value_comes_from_the_rules_and_stays(self):
        OnboardingSettings.objects.create(taka_per_token=2)
        payout = TokenPayoutRequest.objects.get(pk=self.ask(tokens=20).data["id"])
        self.assertEqual(payout.amount_taka, 40)
        OnboardingSettings.objects.filter(pk=1).update(taka_per_token=5)
        payout.refresh_from_db()
        self.assertEqual(payout.amount_taka, 40)

    def test_one_pending_request_at_a_time(self):
        self.ask(tokens=10)
        response = self.ask(tokens=10)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already have a payout request waiting", response.data["detail"])

    def test_no_more_than_the_wallet_holds(self):
        response = self.ask(tokens=52)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("51 at most", response.data["detail"])
        self.assertEqual(self.ask(tokens=0).status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelling_gives_the_tokens_back(self):
        payout_id = self.ask().data["id"]
        self.assertEqual(
            self.as_user(self.other_sales).post(f"/api/onboarding/payouts/{payout_id}/cancel/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        response = self.as_user(self.sales).post(f"/api/onboarding/payouts/{payout_id}/cancel/")
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(TokenService.get_balance(self.sales), 51)
        self.assertFalse(NotificationEvent.objects.filter(event_type=events.TOKEN_PAYOUT_DECIDED).exists())
        self.assertEqual(self.ask(tokens=51).status_code, status.HTTP_201_CREATED)

    def test_the_list_shows_only_ones_own_requests(self):
        self.ask()
        self.assertEqual(len(self.as_user(self.sales).get("/api/onboarding/payouts/").data["results"]), 1)
        self.assertEqual(self.as_user(self.other_sales).get("/api/onboarding/payouts/").data["results"], [])


class PayoutDecisionTests(TokenPayoutTestCase):
    def test_accepting_moves_the_tokens_to_the_admin(self):
        payout_id = self.ask().data["id"]
        response = self.accept(payout_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["status"], response.data["decided_by"]), ("ACCEPTED", "admin"))
        self.assertEqual(response.data["decision_note"], "Paid by bKash")
        self.assertEqual((TokenService.get_balance(self.sales), TokenService.get_balance(self.admin)), (1, 50))
        received = TokenTransaction.objects.get(transaction_type=TokenTransaction.TYPE_PAYOUT_RECEIVED)
        self.assertEqual((received.wallet.user, received.amount), (self.admin, 50))
        self.assertTrue(AuditLog.objects.filter(action="TOKEN_PAYOUT_ACCEPTED", actor=self.admin).exists())

        route_event(NotificationEvent.objects.get(event_type=events.TOKEN_PAYOUT_DECIDED).pk)
        inbox = Notification.objects.get(event_type=events.TOKEN_PAYOUT_DECIDED)
        self.assertEqual((inbox.recipient, inbox.category), (self.sales, WALLET))
        self.assertEqual(inbox.title, "Your payout of ৳50 was accepted")

        listed = self.as_user(self.admin).get("/api/onboarding/payouts/review/").data
        self.assertEqual(listed["your_tokens"], 50)

    def test_rejecting_gives_the_tokens_back_with_a_reason(self):
        payout_id = self.ask().data["id"]
        self.assertEqual(self.reject(payout_id, reason=" ").status_code, status.HTTP_400_BAD_REQUEST)
        response = self.reject(payout_id)
        self.assertEqual((response.data["status"], response.data["decision_note"]), ("REJECTED", "Not this month"))
        self.assertEqual((TokenService.get_balance(self.sales), TokenService.get_balance(self.admin)), (51, 0))
        released = TokenTransaction.objects.get(transaction_type=TokenTransaction.TYPE_PAYOUT_RELEASED)
        self.assertEqual(released.wallet.user, self.sales)

    def test_a_decided_request_stays_decided(self):
        payout_id = self.ask().data["id"]
        self.accept(payout_id)
        for response in (self.accept(payout_id), self.reject(payout_id)):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("already accepted", response.data["detail"])
        self.assertEqual(TokenService.get_balance(self.admin), 50)

    def test_nobody_settles_their_own_request(self):
        UserPermission.objects.create(user=self.sales, permission=Permission.objects.get(code="onboarding.payouts.manage"))
        payout_id = self.ask().data["id"]
        response = self.accept(payout_id, user=self.sales)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Someone else", response.data["detail"])

        route_event(NotificationEvent.objects.get(event_type=events.TOKEN_PAYOUT_REQUESTED).pk)
        recipients = set(Notification.objects.filter(event_type=events.TOKEN_PAYOUT_REQUESTED).values_list("recipient", flat=True))
        self.assertNotIn(self.sales.pk, recipients)

    def test_settling_needs_the_permission(self):
        payout_id = self.ask().data["id"]
        for user in (self.sales, self.sales_manager):
            self.assertEqual(self.as_user(user).get("/api/onboarding/payouts/review/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.accept(payout_id, user=user).status_code, status.HTTP_403_FORBIDDEN)

    def test_the_queue_filters_pending_oldest_first(self):
        first = self.ask(tokens=10).data["id"]
        self.reject(first)
        second = self.ask(tokens=20).data["id"]
        pending = self.as_user(self.admin).get("/api/onboarding/payouts/review/?status=pending").data["results"]
        self.assertEqual([row["id"] for row in pending], [second])
        everything = self.as_user(self.admin).get("/api/onboarding/payouts/review/").data["results"]
        self.assertEqual([row["id"] for row in everything], [second, first])

    def test_a_rejected_seller_takes_back_only_what_is_left(self):
        seller_pk = self.as_user(self.sales).get("/api/onboarding/sellers/").data["results"][0]["id"]
        payout_id = self.ask(tokens=50).data["id"]
        self.accept(payout_id)
        self.as_user(self.admin).post(f"/api/onboarding/review/{seller_pk}/reject/", {"reason": "Closed down"})
        self.assertEqual(TokenService.get_balance(self.sales), 0)
        self.assertEqual(
            TokenTransaction.objects.get(transaction_type=TokenTransaction.TYPE_TAKEN_BACK).amount, 1
        )
