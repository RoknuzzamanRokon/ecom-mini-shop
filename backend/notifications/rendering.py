"""
Rendering (docs/NOTIFICATION_SYSTEM.md §3 D7): one Django template per event
type, schema version and channel, versioned in git with the event contract.

    notifications/templates/notifications/<event_type>/v<version>/<channel>.txt

The in-app template has three blocks:

    {% block title %}Order {{ order_number }} is on its way{% endblock %}
    {% block body %}...{% endblock %}
    {% block action_url %}/profile/orders/{{ order_number }}{% endblock %}

The output is plain text, so it isn't HTML-escaped: the apps escape it when
they display it. HTML email templates (Task 7) autoescape as usual.
"""
from dataclasses import dataclass

from django.template import Context
from django.template.loader import get_template
from django.template.loader_tags import BlockNode

from .models import Channel, Notification

TITLE_MAX_LENGTH = Notification._meta.get_field("title").max_length
ACTION_URL_MAX_LENGTH = Notification._meta.get_field("action_url").max_length


class RenderError(Exception):
    """Raised when a template renders something a notification can't hold."""


@dataclass(frozen=True)
class RenderedMessage:
    title: str
    body: str
    action_url: str


def template_name(event_type, version, channel):
    return f"notifications/{event_type}/v{version}/{channel.lower()}.txt"


def render_blocks(name, context):
    """Every {% block %} of the template `name`, rendered and stripped."""
    compiled = get_template(name).template
    blocks = compiled.nodelist.get_nodes_by_type(BlockNode)
    ctx = Context(context, autoescape=False)
    with ctx.render_context.push_state(compiled), ctx.bind_template(compiled):
        return {block.name: block.render(ctx).strip() for block in blocks}


def render_in_app(event_type, version, context):
    """The inbox title, body and link. A missing template raises TemplateDoesNotExist."""
    name = template_name(event_type, version, Channel.IN_APP)
    blocks = render_blocks(name, context)
    missing = {"title", "body", "action_url"} - blocks.keys()
    if missing:
        raise RenderError(f"{name} has no {', '.join(sorted(missing))} block.")

    title, body, action_url = blocks["title"], blocks["body"], blocks["action_url"]
    if not title:
        raise RenderError(f"{name} rendered an empty title.")
    if len(title) > TITLE_MAX_LENGTH:
        title = title[: TITLE_MAX_LENGTH - 1] + "…"
    # An app path, never an address on someone else's site (§4.7).
    if action_url and (not action_url.startswith("/") or action_url[1:2] in ("/", "\\")):
        raise RenderError(f"{name} rendered the link '{action_url}'; it must be an app path.")
    if len(action_url) > ACTION_URL_MAX_LENGTH:
        raise RenderError(f"{name} rendered a link longer than {ACTION_URL_MAX_LENGTH} characters.")
    return RenderedMessage(title=title, body=body, action_url=action_url)
