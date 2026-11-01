"""
Who hears about the Sales Team's token payouts (docs/NOTIFICATION_SYSTEM.md §5).

- tokens.payout_requested: the staff who can settle payouts, i.e. holders of
  'onboarding.payouts.manage' at routing time (D5), in-app and email.
- tokens.payout_decided: the onboarder who asked (WALLET), in-app only.
"""
from ..events import TOKEN_PAYOUT_DECIDED, TOKEN_PAYOUT_REQUESTED
from ..models import Audience
from .base import Recipient, handles


@handles(TOKEN_PAYOUT_REQUESTED)
def tell_payout_settlers(event):
    from rbac.services import users_with_permission

    # Someone else settles a request, so its author is not asked.
    settlers = users_with_permission("onboarding.payouts.manage").exclude(username=event.payload["requested_by"])
    for settler in settlers.order_by("pk"):
        yield Recipient(settler, Audience.STAFF)


@handles(TOKEN_PAYOUT_DECIDED)
def tell_payout_requester(event):
    from django.contrib.auth import get_user_model

    requester = get_user_model().objects.filter(pk=event.payload["requested_by_id"]).first()
    if requester:
        yield Recipient(requester, Audience.STAFF)
