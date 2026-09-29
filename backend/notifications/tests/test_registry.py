from django.test import SimpleTestCase

from notifications import categories as c
from notifications.categories import CATEGORIES
from notifications.events import EVENT_TYPES, UnknownEventTypeError, get_event_type
from notifications.models import Audience, Channel, Priority

# The v1 catalog, docs/NOTIFICATION_SYSTEM.md §5.
CATALOG = {
    "order.placed", "order.status_changed", "payment.succeeded", "payment.failed",
    "refund.processed", "support.reply_received",
    "seller.status_changed", "shop.status_changed", "product.moderated",
    "inventory.low_stock", "review.created", "points.adjusted",
    "shop.submitted", "support.ticket_created", "support.ticket_assigned",
    "support.customer_replied",
}
# §5's email column: ● or ○.
SENDS_EMAIL = {
    "order.placed", "order.status_changed", "payment.succeeded", "payment.failed",
    "refund.processed", "support.reply_received", "seller.status_changed",
    "shop.status_changed", "product.moderated", "support.ticket_assigned",
}


class EventRegistryTests(SimpleTestCase):
    def test_registry_is_exactly_the_v1_catalog(self):
        self.assertEqual(set(EVENT_TYPES), CATALOG)
        for name, event in EVENT_TYPES.items():
            self.assertEqual(event.name, name)

    def test_every_event_category_exists(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertTrue(event.audiences)
                self.assertLessEqual(event.categories, set(CATEGORIES))

    def test_audiences_are_known(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertLessEqual(set(event.audiences), set(Audience.values))

    def test_versions_are_at_least_one(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertIsInstance(event.version, int)
                self.assertGreaterEqual(event.version, 1)

    def test_required_keys_are_non_empty_strings(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertIsInstance(event.required_keys, frozenset)
                self.assertTrue(event.required_keys)
                self.assertTrue(all(isinstance(key, str) and key for key in event.required_keys))

    def test_names_and_lengths_fit_the_model(self):
        for name in EVENT_TYPES:
            with self.subTest(event=name):
                self.assertLessEqual(len(name), 64)
                self.assertRegex(name, r"^[a-z_]+\.[a-z_]+$")

    def test_priority_is_a_model_value(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertIn(event.priority, Priority.values)

    def test_every_event_uses_in_app_and_email_matches_the_catalog(self):
        for event in EVENT_TYPES.values():
            with self.subTest(event=event.name):
                self.assertIn(Channel.IN_APP, event.channels)
                self.assertLessEqual(event.channels, set(Channel.values))
                self.assertEqual(Channel.EMAIL in event.channels, event.name in SENDS_EMAIL)

    def test_email_events_only_file_under_categories_that_allow_email(self):
        for event in EVENT_TYPES.values():
            if Channel.EMAIL not in event.channels:
                continue
            for category in event.categories:
                with self.subTest(event=event.name, category=category):
                    self.assertIn(Channel.EMAIL, CATEGORIES[category].default_channels)

    def test_get_event_type(self):
        self.assertEqual(get_event_type("order.placed").version, 1)
        with self.assertRaises(UnknownEventTypeError):
            get_event_type("order.teleported")


class CategoryRegistryTests(SimpleTestCase):
    def test_codes_match_and_fit_the_model(self):
        for code, category in CATEGORIES.items():
            with self.subTest(category=code):
                self.assertEqual(category.code, code)
                self.assertLessEqual(len(code), 32)
                self.assertTrue(category.label)

    def test_in_app_is_on_and_locked_everywhere(self):
        for category in CATEGORIES.values():
            with self.subTest(category=category.code):
                self.assertIn(Channel.IN_APP, category.default_channels)
                self.assertIn(Channel.IN_APP, category.locked_channels)

    def test_locked_channels_are_a_subset_of_the_defaults(self):
        for category in CATEGORIES.values():
            with self.subTest(category=category.code):
                self.assertLessEqual(category.locked_channels, category.default_channels)

    def test_email_is_locked_for_account_and_payments_only(self):
        locked = {code for code, cat in CATEGORIES.items() if Channel.EMAIL in cat.locked_channels}
        self.assertEqual(locked, {c.ACCOUNT, c.PAYMENTS})

    def test_every_category_is_used_and_every_email_toggle_has_an_email_event(self):
        for code, category in CATEGORIES.items():
            events = [e for e in EVENT_TYPES.values() if code in e.categories]
            with self.subTest(category=code):
                self.assertTrue(events)
                if Channel.EMAIL in category.default_channels:
                    self.assertTrue(any(Channel.EMAIL in e.channels for e in events))
