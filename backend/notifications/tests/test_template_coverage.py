from django.template.loader import get_template
from django.test import SimpleTestCase

from notifications.events import EVENT_TYPES, get_event_type
from notifications.handlers import HANDLERS
from notifications.models import Channel
from notifications.rendering import template_name


class TemplateCoverageTests(SimpleTestCase):
    """Every event type that has a handler can be rendered (§13, Templates)."""

    def test_handlers_only_handle_registry_events(self):
        self.assertLessEqual(set(HANDLERS), set(EVENT_TYPES))

    def test_every_handled_event_has_an_in_app_template(self):
        for event_type, handlers in HANDLERS.items():
            if not handlers:
                continue
            definition = get_event_type(event_type)
            name = template_name(event_type, definition.version, Channel.IN_APP)
            with self.subTest(event=event_type):
                get_template(name)
