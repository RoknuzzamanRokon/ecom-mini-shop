"""
TASK-043: every ShopService lifecycle action tried from every shop status,
compared with a table written out here. An allowed action moves the shop to
its result status; a refused one raises InvalidShopTransitionError and
leaves the shop as it was.
"""

from itertools import count

from django.contrib.auth import get_user_model
from django.test import TestCase

from sellers.models import SellerProfile
from shops.models import Shop
from shops.services import InvalidShopTransitionError, ShopService
from utils.testing import TransitionTableMixin

User = get_user_model()

SERIAL = count(1)

S = Shop
STATUSES = (S.STATUS_DRAFT, S.STATUS_PENDING, S.STATUS_APPROVED, S.STATUS_ACTIVE,
            S.STATUS_SUSPENDED, S.STATUS_REJECTED)
#: action -> the statuses it may start from
ALLOWED = {
    "submit_for_review": {S.STATUS_DRAFT, S.STATUS_REJECTED},
    "approve": {S.STATUS_PENDING, S.STATUS_DRAFT, S.STATUS_REJECTED},
    "reject": {S.STATUS_PENDING},
    "suspend": {S.STATUS_ACTIVE, S.STATUS_APPROVED},
    "reactivate": {S.STATUS_SUSPENDED},
}
RESULT = {
    "submit_for_review": S.STATUS_PENDING,
    "approve": S.STATUS_ACTIVE,
    "reject": S.STATUS_REJECTED,
    "suspend": S.STATUS_SUSPENDED,
    "reactivate": S.STATUS_ACTIVE,
}


class ShopStateMachineTests(TransitionTableMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(username="sm_shop_staff", email="sms@example.com", password="Shop-State-1")
        cls.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="sm_shop_seller", password="Shop-State-1"),
            business_name="State Machine Seller", status=SellerProfile.STATUS_ACTIVE,
        )

    def make_shop(self, status):
        n = next(SERIAL)
        return Shop.objects.create(
            owner=self.seller, name=f"State Shop {n}", slug=f"state-shop-{n}", status=status,
            rejection_reason="Blurry photos." if status == S.STATUS_REJECTED else "",
            suspension_reason="Unpaid fees." if status == S.STATUS_SUSPENDED else "",
        )

    def run_action(self, shop, action):
        if action == "submit_for_review":
            return ShopService.submit_for_review(shop, self.seller)
        if action in ("reject", "suspend"):
            return getattr(ShopService, f"{action}_shop")(shop, self.staff, "Checked by staff.")
        return getattr(ShopService, f"{action}_shop")(shop, self.staff)

    def test_the_table_names_every_status(self):
        self.assertEqual(set(STATUSES), {value for value, _ in Shop.STATUS_CHOICES})

    def test_every_action_from_every_status(self):
        def attempt(start, action):
            shop = self.make_shop(start)
            try:
                self.run_action(shop, action)
            except InvalidShopTransitionError:
                shop.refresh_from_db()
                self.assertEqual(shop.status, start)
                return False
            shop.refresh_from_db()
            self.assertEqual(shop.status, RESULT[action])
            return True

        self.assert_transition_table(STATUSES, ALLOWED, attempt)
