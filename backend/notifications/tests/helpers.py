"""
A test-only event type, "test.happened", and the templates it renders with
(notifications/tests/templates, which only these tests can see). Real event
types and handlers arrive in Tasks 8–10.
"""
import copy
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import override_settings

from notifications import categories as c
from notifications.events import EVENT_TYPES, EventType
from notifications.handlers import HANDLERS
from notifications.models import Audience, Channel, Priority

TEST_EVENT = "test.happened"
TEST_EVENT_TYPE = EventType(
    TEST_EVENT,
    1,
    # PAYMENTS locks email; SELLER_ORDERS and STAFF_QUEUE don't.
    {Audience.CUSTOMER: c.PAYMENTS, Audience.SELLER: c.SELLER_ORDERS, Audience.STAFF: c.STAFF_QUEUE},
    frozenset({"thing"}),
    frozenset({Channel.IN_APP, Channel.EMAIL}),
    Priority.HIGH,
)

_templates = copy.deepcopy(settings.TEMPLATES)
_templates[0]["DIRS"] = [*_templates[0]["DIRS"], Path(__file__).resolve().parent / "templates"]
with_test_templates = override_settings(TEMPLATES=_templates)


class TestEventMixin:
    """Registers TEST_EVENT for one test; `self.handle(*funcs)` sets its handlers."""

    def setUp(self):
        super().setUp()
        for patcher in (
            mock.patch.dict(EVENT_TYPES, {TEST_EVENT: TEST_EVENT_TYPE}),
            mock.patch.dict(HANDLERS),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def handle(self, *funcs):
        HANDLERS[TEST_EVENT] = list(funcs)


def tell(*recipients):
    """A handler that returns these recipients."""
    return lambda event: list(recipients)
