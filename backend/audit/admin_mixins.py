"""
Shared Django-admin helpers.

Lives in `audit` because it is the project's only leaf app: `audit.models`
references other apps via string FKs ("shops.Shop", "sellers.SellerProfile")
and `audit.services` imports nothing from sibling apps. Every other app may
therefore import from here without creating a cycle.
"""
from django.contrib import messages
from django.contrib.admin import helpers
from django.core.exceptions import ValidationError
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

    def run_reason_action(self, request, queryset, *, action_name, title, verb,
                          reason_label, perform, audit_action,
                          catch=(ValidationError,), help_text=''):
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
                        perform(obj, request.user, reason)
                    except catch as exc:
                        self.message_user(
                            request, f'{verb} failed for {obj}: {exc}', messages.ERROR
                        )
                        continue
                    done += 1
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
