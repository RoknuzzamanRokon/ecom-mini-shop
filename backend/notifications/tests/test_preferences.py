from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications import categories as c
from notifications.models import Channel, NotificationPreference
from notifications.preferences import effective_channels, load_overrides

User = get_user_model()

BOTH = {Channel.IN_APP, Channel.EMAIL}


class EffectiveChannelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pref_user", password="pw")
        cls.other = User.objects.create_user(username="pref_other", password="pw")

    def opt(self, user, category, channel, enabled):
        NotificationPreference.objects.create(user=user, category=category, channel=channel, enabled=enabled)

    def test_defaults_without_any_preference(self):
        self.assertEqual(effective_channels(self.user, c.ORDERS), BOTH)
        self.assertEqual(effective_channels(self.user, c.INVENTORY), {Channel.IN_APP})

    def test_switching_email_off(self):
        self.opt(self.user, c.ORDERS, Channel.EMAIL, False)
        self.assertEqual(effective_channels(self.user, c.ORDERS), {Channel.IN_APP})
        self.assertEqual(effective_channels(self.user, c.SUPPORT), BOTH)
        self.assertEqual(effective_channels(self.other, c.ORDERS), BOTH)

    def test_locked_channels_ignore_the_opt_out(self):
        self.opt(self.user, c.PAYMENTS, Channel.EMAIL, False)
        self.opt(self.user, c.ORDERS, Channel.IN_APP, False)
        self.assertEqual(effective_channels(self.user, c.PAYMENTS), BOTH)
        self.assertEqual(effective_channels(self.user, c.ORDERS), BOTH)

    def test_a_preference_never_adds_a_channel_the_category_lacks(self):
        self.opt(self.user, c.INVENTORY, Channel.EMAIL, True)
        self.assertEqual(effective_channels(self.user, c.INVENTORY), {Channel.IN_APP})

    def test_load_overrides_matches_single_lookups(self):
        self.opt(self.user, c.ORDERS, Channel.EMAIL, False)
        self.opt(self.other, c.SUPPORT, Channel.EMAIL, False)
        overrides = load_overrides([self.user.pk, self.other.pk], {c.ORDERS, c.SUPPORT})
        for user in (self.user, self.other):
            for category in (c.ORDERS, c.SUPPORT):
                with self.subTest(user=user.username, category=category):
                    self.assertEqual(
                        effective_channels(user, category, overrides.get((user.pk, category), {})),
                        effective_channels(user, category),
                    )
