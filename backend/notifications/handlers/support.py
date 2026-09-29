"""
Who hears about support tickets (docs/NOTIFICATION_SYSTEM.md §5). The
existing unread markers stay as they are (D10); these add the bell, email
and staff alerts.

- support.ticket_created: holders of 'support.staff.manage', who assign
  tickets, as STAFF.
- support.reply_received: a public staff reply, to whoever opened the ticket,
  in the audience of the ticket's channel (a customer, or a seller).
- support.customer_replied: the requester's reply, to the assigned agent, if any.
- support.ticket_assigned: the new assignee, unless they assigned it to themselves.
"""
from ..events import (
    SUPPORT_CUSTOMER_REPLIED,
    SUPPORT_REPLY_RECEIVED,
    SUPPORT_TICKET_ASSIGNED,
    SUPPORT_TICKET_CREATED,
)
from ..models import Audience
from .base import Recipient, handles


def _ticket(ticket_id):
    from support.models import SupportTicket

    return SupportTicket.objects.select_related("customer", "assigned_to").filter(pk=ticket_id).first()


@handles(SUPPORT_TICKET_CREATED)
def tell_ticket_managers(event):
    from rbac.services import users_with_permission

    for manager in users_with_permission("support.staff.manage").order_by("pk"):
        yield Recipient(manager, Audience.STAFF)


@handles(SUPPORT_REPLY_RECEIVED)
def tell_requester_staff_replied(event):
    ticket = _ticket(event.payload["ticket_id"])
    if ticket and ticket.customer:
        audience = Audience.SELLER if ticket.is_seller_ticket else Audience.CUSTOMER
        yield Recipient(ticket.customer, audience)


@handles(SUPPORT_CUSTOMER_REPLIED)
def tell_assignee_requester_replied(event):
    ticket = _ticket(event.payload["ticket_id"])
    if ticket and ticket.assigned_to:
        yield Recipient(ticket.assigned_to, Audience.STAFF)


@handles(SUPPORT_TICKET_ASSIGNED)
def tell_new_assignee(event):
    from django.contrib.auth import get_user_model

    assignee_id = event.payload["assignee_id"]
    if assignee_id == event.actor_id:
        return
    assignee = get_user_model().objects.filter(pk=assignee_id).first()
    if assignee:
        yield Recipient(assignee, Audience.STAFF)
