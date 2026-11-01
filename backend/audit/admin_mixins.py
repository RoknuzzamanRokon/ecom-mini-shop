"""
Shared Django-admin helpers.

Lives in `audit` because it is the project's only leaf app: `audit.models`
references other apps via string FKs ("shops.Shop", "sellers.SellerProfile")
and `audit.services` imports nothing from sibling apps. Every other app may
therefore import from here without creating a cycle.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction
from django.template.response import TemplateResponse
from django.utils.html import format_html

from .services import AuditService
from .utils import get_client_ip

# Semantic colour buckets: (text, background).
_GREEN = ('#10B981', '#ECFDF5')
_BLUE = ('#3B82F6', '#EFF6FF')
_AMBER = ('#F59E0B', '#FFFBEB')
_RED = ('#EF4444', '#FEF2F2')
_GREY = ('#6B7280', '#F3F4F6')

# Union of every lifecycle state across Product, Order, SellerProfile,
# Shop, Payment and Refund. Keep in sync when a model gains a status.
STATUS_COLORS = {
    # Settled / healthy
    'ACTIVE': _GREEN,
    'APPROVED': _GREEN,
    'PUBLISHED': _GREEN,
    'PAID': _GREEN,
    'COMPLETED': _GREEN,
    'DELIVERED': _GREEN,
    # In flight
    'PENDING': _BLUE,
    'PROCESSING': _BLUE,
    'UNDER_REVIEW': _BLUE,
    'CONFIRMED': _BLUE,
    'SHIPPED': _BLUE,
    # Needs attention
    'DRAFT': _AMBER,
    'SUBMITTED': _AMBER,
    'PARTIALLY_REFUNDED': _AMBER,
    'REFUNDED': _AMBER,
    # Terminal / adverse
    'SUSPENDED': _RED,
    'REJECTED': _RED,
    'FAILED': _RED,
    'CANCELLED': _RED,
    'UNPUBLISHED': _RED,
}


class StatusBadgeMixin:
    """Renders `obj.status` as a coloured pill in list_display."""

    def status_badge(self, obj):
        raw = getattr(obj, 'status', None) or ''
        status = raw.upper()
        color, bg = STATUS_COLORS.get(status, _GREY)
        label = obj.get_status_display() if hasattr(obj, 'get_status_display') else status
        return format_html(
            '<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
            'font-size:11px;font-weight:700;color:{};background:{};">{}</span>',
            color, bg, label
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'


CONFIRM_FLAG = 'apply_reason'
REASON_FIELD = 'reason'


def _audit_value(value):
    """A form value as something the AuditLog JSON column can store."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, File):  # an upload, or the stored file
        return value.name
    if hasattr(value, 'pk'):  # a model instance
        return value.pk
    if isinstance(value, (list, tuple, set)) or hasattr(value, 'values_list'):
        return [_audit_value(item) for item in value]
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


class ChangeFormAuditMixin:
    """
    One AuditLog row per save made through the admin add or change form, or
    through the changelist's editable columns, which reach the same
    save_model() (TASK-006). An edit records only the fields that changed,
    as previous_state and new_state.

    Set `audit_action_prefix` (e.g. 'ADMIN_ORDER'); the actions are
    '<prefix>_CREATED' and '<prefix>_EDITED'. Lifecycle changes do not come
    through here: those fields are read-only and go through the services,
    which write their own rows.
    """

    audit_action_prefix = None
    #: False when a service already records the creation (ProductAdmin).
    audit_creations = True

    def audit_context(self, obj):
        """Hook for per-model AuditService kwargs (shop=..., seller=...)."""
        return {}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if (change and not form.changed_data) or (not change and not self.audit_creations):
            return
        fields = form.changed_data if change else list(form.cleaned_data)
        new_state = {name: _audit_value(form.cleaned_data.get(name)) for name in fields}
        previous_state = (
            {name: _audit_value(form.initial.get(name)) for name in fields} if change else None
        )
        AuditService.log(
            action=f"{self.audit_action_prefix}_{'EDITED' if change else 'CREATED'}",
            target=obj,
            actor=request.user,
            previous_state=previous_state,
            new_state=new_state,
            ip_address=get_client_ip(request),
            **self.audit_context(obj),
        )


def _error_text(exc) -> str:
    """A ValidationError's messages as plain text, not a list repr."""
    return '; '.join(getattr(exc, 'messages', None) or [str(exc)])


class ReasonRequiredActionMixin:
    """
    Django's intermediate-confirmation-page pattern for admin actions that
    need a mandatory, human-written reason (suspend / reject).

    Returning a TemplateResponse from an action makes ModelAdmin.response_action
    render it; returning None falls through to the usual changelist redirect.
    Re-entry works because Django re-resolves the action and rebuilds the
    queryset from the ACTION_CHECKBOX_NAME values the form re-posts.
    """

    reason_action_template = 'admin/admin_actions.html'
    reason_min_length = 10

    def audit_context(self, obj):
        """Hook for per-model AuditService kwargs (shop=..., seller=...)."""
        return {}

    def _require_change_permission(self, request):
        """
        Defense in depth for every action routed through this mixin.

        Each action also declares `allowed_permissions = ("change",)`, which is
        what Django itself filters on; this second check means a future action
        wired to these helpers cannot silently mutate records without it.
        """
        if not self.has_change_permission(request):
            raise PermissionDenied

    def run_simple_action(self, request, queryset, *, verb, perform,
                          audit_action, catch=(ValidationError,)):
        """Lifecycle action that needs no reason (approve / reactivate)."""
        self._require_change_permission(request)
        done = 0
        for obj in queryset:
            previous_state = {'status': obj.status}
            try:
                # The change and its audit row commit together or not at all
                # (BUG-015): a service that commits on its own must not leave
                # a status change behind if the audit write then fails.
                with transaction.atomic():
                    perform(obj, request.user)
                    AuditService.log(
                        action=audit_action,
                        target=obj,
                        actor=request.user,
                        previous_state=previous_state,
                        new_state={'status': obj.status},
                        ip_address=get_client_ip(request),
                        **self.audit_context(obj),
                    )
            except catch as exc:
                self.message_user(
                    request, f'{verb} failed for {obj}: {_error_text(exc)}', messages.ERROR
                )
                continue
            done += 1
        if done:
            self.message_user(request, f'{verb} {done} record(s).', messages.SUCCESS)

    def run_reason_action(self, request, queryset, *, action_name, title, verb,
                          reason_label, perform, audit_action,
                          catch=(ValidationError,), help_text=''):
        self._require_change_permission(request)
        reason = (request.POST.get(REASON_FIELD) or '').strip()
        errors = []

        if request.POST.get(CONFIRM_FLAG):
            if len(reason) < self.reason_min_length:
                errors.append(
                    f'A reason of at least {self.reason_min_length} characters is required.'
                )
            else:
                done = 0
                for obj in queryset:
                    previous_state = {'status': obj.status}
                    try:
                        # Change and audit row commit together (see run_simple_action).
                        with transaction.atomic():
                            perform(obj, request.user, reason)
                            AuditService.log(
                                action=audit_action,
                                target=obj,
                                actor=request.user,
                                reason=reason,
                                previous_state=previous_state,
                                new_state={'status': obj.status},
                                ip_address=get_client_ip(request),
                                **self.audit_context(obj),
                            )
                    except catch as exc:
                        self.message_user(
                            request, f'{verb} failed for {obj}: {_error_text(exc)}', messages.ERROR
                        )
                        continue
                    done += 1
                if done:
                    self.message_user(
                        request, f'{verb} {done} record(s).', messages.SUCCESS
                    )
                return None

        context = {
            **self.admin_site.each_context(request),
            'title': title,
            'verb': verb,
            'help_text': help_text,
            'opts': self.model._meta,
            'queryset': queryset,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'action_name': action_name,
            'confirm_flag': CONFIRM_FLAG,
            'reason_field': REASON_FIELD,
            'reason_label': reason_label,
            'reason': reason,
            'reason_min_length': self.reason_min_length,
            'select_across': request.POST.get('select_across', '0'),
            'errors': errors,
            'media': self.media,
        }
        return TemplateResponse(request, self.reason_action_template, context)


class ConsoleManagedRuleMixin:
    """
    A business-rule singleton (rules/registry.py). Its values change only on
    the Console Rules page, which checks each change against the other rules
    and audits it, so the Django admin shows them read-only.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _point_to_console(self, request):
        messages.info(request, format_html(
            'These values change on the <a href="{}">Console Rules page</a>, where every change is checked '
            'and audited. Until the first change there, the defaults apply.',
            f"{settings.STOREFRONT_URL.rstrip('/')}/admin/rules",
        ))

    def changelist_view(self, request, extra_context=None):
        self._point_to_console(request)
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self._point_to_console(request)
        return super().change_view(request, object_id, form_url, extra_context)
