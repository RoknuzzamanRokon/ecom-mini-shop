"""
Every change to a support ticket goes through SupportTicketService.

Customer methods take the customer and a ticket number, and look the ticket up
*scoped to that customer* under a row lock: another customer's ticket simply
doesn't exist for them (SupportTicket.DoesNotExist, a 404 in the views). Staff
methods check the staff member's permission code themselves, so a caller can't
forget to (unlike OrderService.transition_order_status, which authorizes
nothing and relies on every caller).

Every write runs in transaction.atomic() with select_for_update() on the
ticket, so two agents acting at once can't lose each other's change. Files are
written to storage inside that transaction; if it fails, the files written so
far are deleted again.
"""
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from audit.services import AuditService
from rbac.models import Role, UserPermission, UserRole
from rbac.services import has_user_permission
from shop.models import Order

from .exceptions import SupportTicketError
from .models import SupportTicket, TicketAttachment, TicketMessage
from .validators import validate_attachments

User = get_user_model()

PERM_CREATE = "support.create"
PERM_STAFF_REPLY = "support.staff.reply"
PERM_STAFF_MANAGE = "support.staff.manage"

SUBJECT_MIN_LENGTH = 5
SUBJECT_MAX_LENGTH = 150
DESCRIPTION_MIN_LENGTH = 10
MESSAGE_MAX_LENGTH = 5000
REASON_MAX_LENGTH = 500
MAX_UNRESOLVED_TICKETS = 5
# D17: close_resolved_tickets closes a resolved ticket left quiet this long.
AUTO_CLOSE_AFTER_DAYS = 7

STATUS_LABELS = dict(SupportTicket.STATUS_CHOICES)
CATEGORY_LABELS = dict(SupportTicket.CATEGORY_CHOICES)
PRIORITY_LABELS = dict(SupportTicket.PRIORITY_CHOICES)

_OPEN = SupportTicket.STATUS_OPEN
_IN_PROGRESS = SupportTicket.STATUS_IN_PROGRESS
_RESOLVED = SupportTicket.STATUS_RESOLVED
_CLOSED = SupportTicket.STATUS_CLOSED


def person_name(user) -> str:
    """Full name, else username; for staff-facing system notes."""
    if user is None:
        return "nobody"
    return user.get_full_name().strip() or user.username


class SupportTicketService:

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def generate_ticket_number() -> str:
        """
        Unique, server-controlled reference: TKT<YYYYMMDD><6-HEX>
        (e.g. TKT20260924A1B2C3), the same shape as order numbers.
        """
        prefix = f"TKT{timezone.now():%Y%m%d}"
        for _ in range(10):
            candidate = f"{prefix}{uuid.uuid4().hex[:6].upper()}"
            if not SupportTicket.objects.filter(ticket_number=candidate).exists():
                return candidate
        return f"{prefix}{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _require(user, code: str):
        if not has_user_permission(user, code):
            raise PermissionDenied(f"You do not have permission to do this ('{code}' required).")

    @staticmethod
    def _clean_text(value, label: str, min_length: int, max_length: int) -> str:
        text = str(value or "").strip()
        if len(text) < min_length:
            raise SupportTicketError(f"{label} must be at least {min_length} characters.")
        if len(text) > max_length:
            raise SupportTicketError(f"{label} can be at most {max_length} characters.")
        return text

    @staticmethod
    def _clean_body(value, has_files: bool) -> str:
        text = str(value or "").strip()
        if not text and not has_files:
            raise SupportTicketError("Write a message or attach a file.")
        if len(text) > MESSAGE_MAX_LENGTH:
            raise SupportTicketError(f"A message can be at most {MESSAGE_MAX_LENGTH} characters.")
        return text

    @staticmethod
    def _clean_reason(value) -> str:
        text = str(value or "").strip()
        if len(text) > REASON_MAX_LENGTH:
            raise SupportTicketError(f"A reason can be at most {REASON_MAX_LENGTH} characters.")
        return text

    @staticmethod
    def _lock(ticket_number, **scope) -> SupportTicket:
        """Row-locks the ticket for the rest of the transaction; DoesNotExist propagates."""
        return SupportTicket.objects.select_for_update().get(ticket_number=ticket_number, **scope)

    @staticmethod
    @contextmanager
    def _discard_files_on_error():
        """Yields a list; every storage name appended to it is deleted if the block fails."""
        written = []
        try:
            yield written
        except BaseException:
            storage = TicketAttachment._meta.get_field("file").storage
            for name in written:
                try:
                    storage.delete(name)
                except OSError:
                    pass
            raise

    @staticmethod
    def _save_attachments(message, checked, written):
        for item in checked:
            attachment = TicketAttachment(
                message=message,
                original_name=item.original_name,
                content_type=item.content_type,
                size=item.size,
            )
            # Named from the detected type; support_attachment_path swaps in a UUID.
            attachment.file.save(f"attachment.{item.extension}", item.file, save=False)
            written.append(attachment.file.name)
            attachment.save()

    @staticmethod
    def _system_note(ticket, actor, body: str, internal: bool):
        return TicketMessage.objects.create(
            ticket=ticket,
            author=actor,
            author_type=TicketMessage.AUTHOR_SYSTEM,
            body=body,
            is_internal=internal,
        )

    @classmethod
    def _set_status(cls, ticket, new_status, actor, now, *, note, changed_by, reason="", ip_address=None):
        """
        Moves the ticket to new_status and records it: a public system line in
        the thread, and an audit entry. The caller saves the ticket.
        """
        previous = ticket.status
        ticket.status = new_status
        ticket.last_activity_at = now
        if new_status == _RESOLVED:
            ticket.resolved_at = now
        elif new_status == _CLOSED:
            ticket.closed_at = now
        else:
            ticket.resolved_at = None
        cls._system_note(ticket, actor, note, internal=False)
        AuditService.log(
            action="SUPPORT_TICKET_STATUS_CHANGED",
            target=ticket,
            actor=actor,
            reason=reason or None,
            previous_state={"status": previous},
            new_state={"status": new_status},
            metadata={"ticket_number": ticket.ticket_number, "changed_by": changed_by},
            ip_address=ip_address,
        )

    # ---------------------------------------------------------------- customer

    @classmethod
    def create_ticket(
        cls,
        customer,
        *,
        category,
        subject,
        description,
        order_number=None,
        files=(),
        ip_address=None,
    ) -> SupportTicket:
        """Opens a ticket; the description becomes its first message."""
        cls._require(customer, PERM_CREATE)
        if category not in CATEGORY_LABELS:
            raise SupportTicketError("Choose a valid category.")
        subject = cls._clean_text(subject, "Subject", SUBJECT_MIN_LENGTH, SUBJECT_MAX_LENGTH)
        description = cls._clean_text(
            description, "Description", DESCRIPTION_MIN_LENGTH, MESSAGE_MAX_LENGTH
        )
        checked = validate_attachments(files)

        order = None
        order_number = str(order_number or "").strip()
        if order_number:
            # Same message whether the order is someone else's or doesn't exist.
            order = Order.objects.filter(user=customer, order_number=order_number).first()
            if order is None:
                raise SupportTicketError("Order not found.")

        with cls._discard_files_on_error() as written, transaction.atomic():
            # Serialises one customer's ticket creation, so two simultaneous
            # requests can't both slip under the cap.
            User.objects.select_for_update().get(pk=customer.pk)
            unresolved = SupportTicket.objects.filter(
                customer=customer, status__in=SupportTicket.UNRESOLVED_STATUSES
            ).count()
            if unresolved >= MAX_UNRESOLVED_TICKETS:
                raise SupportTicketError(
                    f"You already have {MAX_UNRESOLVED_TICKETS} open tickets. Please add to one "
                    "of them, or wait until one is resolved."
                )

            now = timezone.now()
            ticket = SupportTicket.objects.create(
                ticket_number=cls.generate_ticket_number(),
                customer=customer,
                order=order,
                category=category,
                subject=subject,
                last_activity_at=now,
                last_customer_message_at=now,
                customer_last_read_at=now,
            )
            message = TicketMessage.objects.create(
                ticket=ticket,
                author=customer,
                author_type=TicketMessage.AUTHOR_CUSTOMER,
                body=description,
            )
            cls._save_attachments(message, checked, written)
            AuditService.log(
                action="SUPPORT_TICKET_CREATED",
                target=ticket,
                actor=customer,
                metadata={
                    "ticket_number": ticket.ticket_number,
                    "category": category,
                    "order_number": order.order_number if order else None,
                    "attachment_count": len(checked),
                },
                ip_address=ip_address,
            )
        return ticket

    @classmethod
    def add_customer_reply(cls, customer, ticket_number, body, files=(), ip_address=None) -> TicketMessage:
        """
        Adds the customer's reply. A ticket waiting on the customer, or resolved,
        goes back to OPEN; a closed ticket can't be replied to.
        """
        cls._require(customer, PERM_CREATE)
        checked = validate_attachments(files)
        body = cls._clean_body(body, has_files=bool(checked))

        with cls._discard_files_on_error() as written, transaction.atomic():
            ticket = cls._lock(ticket_number, customer=customer)
            if ticket.is_closed:
                raise SupportTicketError(
                    "This ticket is closed. Please open a new ticket if you still need help."
                )
            now = timezone.now()
            message = TicketMessage.objects.create(
                ticket=ticket,
                author=customer,
                author_type=TicketMessage.AUTHOR_CUSTOMER,
                body=body,
            )
            cls._save_attachments(message, checked, written)
            if ticket.status in SupportTicket.CUSTOMER_REOPEN_STATUSES:
                cls._set_status(
                    ticket, _OPEN, customer, now,
                    note="Reopened by the customer's reply.",
                    changed_by="customer",
                    ip_address=ip_address,
                )
            ticket.last_customer_message_at = now
            ticket.last_activity_at = now
            ticket.customer_last_read_at = now
            ticket.save()
        return message

    @classmethod
    def close_by_customer(cls, customer, ticket_number, ip_address=None) -> SupportTicket:
        """The customer's "my problem is solved": any open status → CLOSED."""
        cls._require(customer, PERM_CREATE)
        with transaction.atomic():
            ticket = cls._lock(ticket_number, customer=customer)
            if ticket.is_closed:
                raise SupportTicketError("This ticket is already closed.")
            cls._set_status(
                ticket, _CLOSED, customer, timezone.now(),
                note="Closed by the customer.",
                changed_by="customer",
                ip_address=ip_address,
            )
            ticket.save()
        return ticket

    @staticmethod
    def mark_read_by_customer(ticket) -> None:
        """Records that the customer has seen every reply so far."""
        now = timezone.now()
        SupportTicket.objects.filter(pk=ticket.pk).update(customer_last_read_at=now)
        ticket.customer_last_read_at = now

    # ------------------------------------------------------------------- staff

    @classmethod
    def add_staff_message(
        cls,
        staff,
        ticket_number,
        body,
        files=(),
        is_internal=False,
        set_status=None,
        ip_address=None,
    ) -> TicketMessage:
        """
        A public reply to the customer, or an internal note only staff see.

        A public reply on an OPEN ticket moves it to IN_PROGRESS unless
        set_status (which needs support.staff.manage) says otherwise. An
        internal note never changes the status or the customer-visible
        timestamps, and may be added to a closed ticket.
        """
        cls._require(staff, PERM_STAFF_REPLY)
        if set_status:
            if is_internal:
                raise SupportTicketError(
                    "An internal note can't change the status. Send a reply, or change the "
                    "status on its own."
                )
            if set_status not in STATUS_LABELS:
                raise SupportTicketError("Choose a valid status.")
            cls._require(staff, PERM_STAFF_MANAGE)
        checked = validate_attachments(files)
        body = cls._clean_body(body, has_files=bool(checked))

        with cls._discard_files_on_error() as written, transaction.atomic():
            ticket = cls._lock(ticket_number)
            target = None
            if not is_internal:
                if ticket.is_closed:
                    raise SupportTicketError(
                        "This ticket is closed, so the customer can't be replied to. You can "
                        "still add an internal note."
                    )
                target = set_status or (_IN_PROGRESS if ticket.status == _OPEN else None)
                if target == ticket.status:
                    target = None
                elif target and not ticket.can_transition_to(target):
                    raise SupportTicketError(
                        f"A ticket can't move from {STATUS_LABELS[ticket.status]} to "
                        f"{STATUS_LABELS[target]}."
                    )

            now = timezone.now()
            message = TicketMessage.objects.create(
                ticket=ticket,
                author=staff,
                author_type=TicketMessage.AUTHOR_STAFF,
                body=body,
                is_internal=is_internal,
            )
            cls._save_attachments(message, checked, written)
            if not is_internal:
                ticket.last_staff_reply_at = now
                ticket.first_response_at = ticket.first_response_at or now
                ticket.last_activity_at = now
                if target:
                    cls._set_status(
                        ticket, target, staff, now,
                        note=f"Status changed to {STATUS_LABELS[target]}.",
                        changed_by="staff",
                        ip_address=ip_address,
                    )
                ticket.save()
        return message

    @classmethod
    def change_status(cls, staff, ticket_number, new_status, reason="", ip_address=None) -> SupportTicket:
        """Moves the ticket along VALID_TRANSITIONS. A reason is optional and stays staff-only."""
        cls._require(staff, PERM_STAFF_MANAGE)
        if new_status not in STATUS_LABELS:
            raise SupportTicketError("Choose a valid status.")
        reason = cls._clean_reason(reason)

        with transaction.atomic():
            ticket = cls._lock(ticket_number)
            if ticket.status == new_status:
                raise SupportTicketError(
                    f"The ticket is already {STATUS_LABELS[new_status].lower()}."
                )
            if not ticket.can_transition_to(new_status):
                raise SupportTicketError(
                    f"A ticket can't move from {STATUS_LABELS[ticket.status]} to "
                    f"{STATUS_LABELS[new_status]}."
                )
            cls._set_status(
                ticket, new_status, staff, timezone.now(),
                note=f"Status changed to {STATUS_LABELS[new_status]}.",
                changed_by="staff",
                reason=reason,
                ip_address=ip_address,
            )
            if reason:
                cls._system_note(ticket, staff, f"Status change reason: {reason}", internal=True)
            ticket.save()
        return ticket

    @classmethod
    def update_details(
        cls, staff, ticket_number, *, priority=None, category=None, reason="", ip_address=None
    ) -> SupportTicket:
        """Changes priority and/or category. Staff-only, so the thread note is internal."""
        cls._require(staff, PERM_STAFF_MANAGE)
        if priority is not None and priority not in PRIORITY_LABELS:
            raise SupportTicketError("Choose a valid priority.")
        if category is not None and category not in CATEGORY_LABELS:
            raise SupportTicketError("Choose a valid category.")
        reason = cls._clean_reason(reason)

        with transaction.atomic():
            ticket = cls._lock(ticket_number)
            changes = {}
            if priority is not None and priority != ticket.priority:
                changes["priority"] = (ticket.priority, priority, PRIORITY_LABELS)
            if category is not None and category != ticket.category:
                changes["category"] = (ticket.category, category, CATEGORY_LABELS)
            if not changes:
                raise SupportTicketError("Nothing to change.")

            notes = []
            for field, (old, new, labels) in changes.items():
                setattr(ticket, field, new)
                notes.append(f"{field.capitalize()} changed from {labels[old]} to {labels[new]}.")
            if reason:
                notes.append(f"Reason: {reason}")
            ticket.save()
            cls._system_note(ticket, staff, " ".join(notes), internal=True)
            AuditService.log(
                action="SUPPORT_TICKET_UPDATED",
                target=ticket,
                actor=staff,
                reason=reason or None,
                previous_state={field: old for field, (old, _, _) in changes.items()},
                new_state={field: new for field, (_, new, _) in changes.items()},
                metadata={"ticket_number": ticket.ticket_number},
                ip_address=ip_address,
            )
        return ticket

    @classmethod
    def assign(cls, staff, ticket_number, assignee, ip_address=None) -> SupportTicket:
        """Assigns the ticket to a support.staff.reply holder, or unassigns it (None)."""
        cls._require(staff, PERM_STAFF_MANAGE)
        if assignee is not None and not (
            assignee.is_active and has_user_permission(assignee, PERM_STAFF_REPLY)
        ):
            raise SupportTicketError("That user can't be assigned support tickets.")

        with transaction.atomic():
            ticket = cls._lock(ticket_number)
            new_id = assignee.pk if assignee else None
            if ticket.assigned_to_id == new_id:
                raise SupportTicketError(
                    "The ticket is already assigned to them." if assignee
                    else "The ticket is already unassigned."
                )
            previous_id = ticket.assigned_to_id
            ticket.assigned_to = assignee
            ticket.save()
            cls._system_note(
                ticket, staff,
                f"Assigned to {person_name(assignee)}." if assignee else "Unassigned.",
                internal=True,
            )
            AuditService.log(
                action="SUPPORT_TICKET_ASSIGNED",
                target=ticket,
                actor=staff,
                previous_state={"assigned_to": previous_id},
                new_state={"assigned_to": new_id},
                metadata={"ticket_number": ticket.ticket_number},
                ip_address=ip_address,
            )
        return ticket

    @staticmethod
    def get_assignable_staff():
        """
        Active users who may be assigned tickets: they hold support.staff.reply
        through an active role or an active direct grant, or they are a
        superuser or SUPER_ADMINISTRATOR (who hold every code). Mirrors
        rbac.services.has_user_permission, as a single query.
        """
        role_holders = UserRole.objects.filter(
            is_active=True, role__is_active=True
        ).filter(
            Q(role__code=Role.ROLE_SUPER_ADMINISTRATOR)
            | Q(role__role_permissions__permission__code=PERM_STAFF_REPLY)
        ).values("user_id")
        direct_holders = UserPermission.objects.filter(
            is_active=True, permission__code=PERM_STAFF_REPLY
        ).values("user_id")
        return User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(pk__in=role_holders) | Q(pk__in=direct_holders)
        ).order_by("first_name", "last_name", "username")

    # -------------------------------------------------------------- automation

    @staticmethod
    def stale_resolved_tickets(days=AUTO_CLOSE_AFTER_DAYS):
        """
        RESOLVED tickets that have sat untouched for `days`: resolved at least
        that long ago, no public activity since (a staff follow-up restarts the
        clock), and no customer message after the resolution.
        """
        cutoff = timezone.now() - timedelta(days=days)
        return SupportTicket.objects.filter(
            status=_RESOLVED,
            resolved_at__lte=cutoff,
            last_activity_at__lte=cutoff,
        ).filter(
            Q(last_customer_message_at__isnull=True)
            | Q(last_customer_message_at__lte=F("resolved_at"))
        )

    @classmethod
    def auto_close_resolved(cls, ticket_number, days=AUTO_CLOSE_AFTER_DAYS) -> bool:
        """
        Closes one stale resolved ticket on the system's behalf (no actor): the
        usual public status line and audit entry. The conditions are checked
        again under the row lock, so a ticket the customer answered or staff
        reopened since it was listed is left alone. Returns whether it closed.
        """
        with transaction.atomic():
            ticket = (
                cls.stale_resolved_tickets(days)
                .select_for_update()
                .filter(ticket_number=ticket_number)
                .first()
            )
            if ticket is None:
                return False
            cls._set_status(
                ticket, _CLOSED, None, timezone.now(),
                note=f"Closed automatically after {days} days without a reply.",
                changed_by="system",
                reason=f"Resolved, with no customer reply for {days} days.",
            )
            ticket.save()
        return True
