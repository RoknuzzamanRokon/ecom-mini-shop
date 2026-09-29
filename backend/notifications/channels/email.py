"""
The email channel (docs/NOTIFICATION_SYSTEM.md Task 7).

An email carries the notification the router already rendered for its
recipient (title, body and link), inside one shared layout: plain text plus
HTML with inline CSS. Per-recipient wording, such as a seller seeing only
their own items, is therefore identical in the inbox and in the email, and no
event needs its own email template.

The Message-ID is built from the delivery's UUID, so a retried send is
recognisably the same message (§4.5).
"""
import smtplib
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string

from ..categories import CATEGORIES
from ..conf import notification_setting
from ..models import Audience, Channel
from .base import PermanentSendError, SendResult, TransientSendError

TEXT_TEMPLATE = "notifications/email/layout.txt"
HTML_TEMPLATE = "notifications/email/layout.html"

# Where each audience reads its inbox (§9); the email footer links there.
INBOX_PATHS = {
    Audience.CUSTOMER: "/profile/notifications",
    Audience.SELLER: "/seller/notifications",
    Audience.STAFF: "/admin/notifications",
}


def email_destination(user, audience):
    """
    The address a notification is emailed to: for a SELLER notification the
    seller's business email if they set one, otherwise the account email.
    Empty means there's nowhere to send it.
    """
    if audience == Audience.SELLER:
        from sellers.models import SellerProfile  # lazy: channels import no domain app at load

        business = (
            SellerProfile.objects.filter(user=user).values_list("business_email", flat=True).first() or ""
        ).strip()
        if business:
            return business
    return (user.email or "").strip()


def absolute_url(path):
    return f"{settings.STOREFRONT_URL.rstrip('/')}{path}" if path else ""


def message_id(delivery):
    domain = parseaddr(notification_setting("FROM_EMAIL"))[1].rpartition("@")[2] or "minishop.local"
    return f"<{delivery.pk}@{domain}>"


def build_message(delivery):
    """The EmailMultiAlternatives for one delivery (text body plus an HTML alternative)."""
    notification = delivery.notification
    category = CATEGORIES.get(notification.category)
    context = {
        "title": notification.title,
        "body": notification.body,
        "action_link": absolute_url(notification.action_url),
        "inbox_link": absolute_url(INBOX_PATHS.get(notification.audience, "")),
        "storefront_link": absolute_url("/"),
        "category_label": category.label if category else notification.category,
        "can_opt_out": bool(category) and Channel.EMAIL not in category.locked_channels,
    }
    message = EmailMultiAlternatives(
        subject=" ".join(notification.title.split()),
        body=render_to_string(TEXT_TEMPLATE, context),
        from_email=notification_setting("FROM_EMAIL"),
        to=[delivery.destination],
        headers={
            "Message-ID": message_id(delivery),
            # RFC 3834: tells mail servers and autoresponders this is automated.
            "Auto-Submitted": "auto-generated",
        },
    )
    message.attach_alternative(render_to_string(HTML_TEMPLATE, context), "text/html")
    return message


class EmailAdapter:
    """
    Sends through Django's configured email backend.

    Outcomes, as the worker reads them (channels/base.py):
    - no address, an invalid one, or the server refusing the recipient
      permanently (5xx): SKIPPED;
    - the server refusing the message itself permanently (5xx): DEAD;
    - anything that may pass later: a 4xx reply, a timeout, a dropped or
      refused connection, and our own configuration being rejected
      (authentication, sender): retried.
    """

    channel = Channel.EMAIL

    def send(self, delivery):
        address = delivery.destination
        if not address:
            raise PermanentSendError("No email address.", skip=True)
        try:
            validate_email(address)
        except ValidationError:
            raise PermanentSendError(f"Invalid email address {address!r}.", skip=True) from None

        message = build_message(delivery)
        try:
            message.send(fail_silently=False)
        except smtplib.SMTPRecipientsRefused as exc:
            codes = [code for code, _ in exc.recipients.values()]
            if codes and all(code >= 500 for code in codes):
                raise PermanentSendError(f"Recipient refused: {exc.recipients}", skip=True) from exc
            raise TransientSendError(f"Recipient deferred: {exc.recipients}") from exc
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused) as exc:
            raise TransientSendError(f"The mail server rejected our configuration: {exc}") from exc
        except smtplib.SMTPResponseException as exc:
            if exc.smtp_code >= 500:
                raise PermanentSendError(f"Message refused ({exc.smtp_code}): {exc.smtp_error!r}") from exc
            raise TransientSendError(f"Temporary refusal ({exc.smtp_code}): {exc.smtp_error!r}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            # Includes timeouts, refused and dropped connections.
            raise TransientSendError(f"{type(exc).__name__}: {exc}") from exc
        return SendResult(provider_message_id=message.extra_headers["Message-ID"])
