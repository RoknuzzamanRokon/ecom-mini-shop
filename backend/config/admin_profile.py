"""
The signed-in staff member's own profile page: /admin/profile/.

MiniShopAdminSite.get_urls() serves it through admin_view(), so only an active
staff account reaches it, and it only ever shows request.user -- there is no id
in the URL to swap for someone else's.

Everything on the page is read from tables that already exist. The one write is
the personal-details form, which goes through CustomerService.update_profile()
(the same service behind /api/profile/me/) so the change is audited as
PROFILE_UPDATED. Username, email, the access flags and roles are deliberately
read-only here: this page must never become a way to raise one's own access.

This module is imported lazily from admin_site.py, after apps are loaded.
"""
import re
from collections import Counter
from datetime import datetime, time, timedelta
from itertools import chain

from django import forms
from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.admin.utils import quote
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext_lazy as _

from audit.models import AuditLog
from customers.models import Address, CustomerProfile
from customers.services import CustomerService
from notifications.models import Audience, Notification
from notifications.permissions import can_read_audience
from rbac.models import UserPermission, UserRole
from rbac.services import get_user_permissions
from rbac.widgets import ACTIONS, DEFAULT_WEIGHT, SECTION_META, WILDCARD_CODE, build_minishop_permission_board
from sellers.models import SellerProfile
from shop.models import InventoryTransaction, Order, Product, Refund
from support.models import SupportTicket

User = get_user_model()

#: The activity heatmap covers this many whole weeks, ending with the current one.
ACTIVITY_WEEKS = 12
#: Newest entries shown in the activity timeline.
TIMELINE_LIMIT = 20
#: Open tickets listed under "Your work".
OPEN_TICKET_LIMIT = 5

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}

#: Digits plus the usual separators. Deliberately loose: numbers are written
#: many ways, and this only exists to stop obvious junk in the field.
PHONE_PATTERN = re.compile(r"[0-9+()\-\s]+")
PHONE_MIN_DIGITS = 6

#: SECTION_META (rbac/widgets.py) predates these two apps; they get real icons
#: here instead of falling back to a folder.
PANEL_SECTION_META = {
    **SECTION_META,
    "support": ("Support", "support_agent", 95),
    "notifications": ("Notifications", "notifications", 96),
}

ACCESS_LEVELS = {
    "super": (_("Superuser"), "shield_person"),
    "staff": (_("Staff"), "badge"),
}

# ---------------------------------------------------------------------------
# Personal details form
# ---------------------------------------------------------------------------


class AdminProfileForm(forms.Form):
    """
    The fields a staff member may change about themselves.

    first_name/last_name live on auth.User; the rest on CustomerProfile, which
    the model's own docstring opens to "any user (customer, seller, or staff)".
    Nothing that affects access -- username, email, is_staff, is_superuser,
    roles -- is a field here, so posting them does nothing.
    """

    DETAIL_FIELDS = ("first_name", "last_name", "display_name", "phone", "date_of_birth", "gender")

    first_name = forms.CharField(label=_("First name"), max_length=150, required=False)
    last_name = forms.CharField(label=_("Last name"), max_length=150, required=False)
    display_name = forms.CharField(
        label=_("Display name"),
        max_length=150,
        required=False,
        help_text=_("Shown instead of your full name where space is tight."),
    )
    phone = forms.CharField(
        label=_("Phone"),
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
        help_text=_("Digits, spaces, +, - and brackets."),
    )
    date_of_birth = forms.DateField(
        label=_("Date of birth"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    gender = forms.ChoiceField(
        label=_("Gender"),
        required=False,
        choices=[("", _("Not set"))] + list(CustomerProfile.GENDER_CHOICES),
    )
    avatar = forms.ImageField(
        label=_("Photo"),
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        help_text=_("JPEG, PNG or WebP, up to 2 MB. A square photo looks best."),
    )
    remove_avatar = forms.BooleanField(label=_("Remove current photo"), required=False)

    def __init__(self, *args, user, profile=None, **kwargs):
        self.user = user
        self.profile = profile
        initial = {"first_name": user.first_name, "last_name": user.last_name}
        if profile is not None:
            initial.update(
                display_name=profile.display_name,
                phone=profile.phone,
                date_of_birth=profile.date_of_birth,
                gender=profile.gender,
            )
        kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        for name, field in self.fields.items():
            if field.help_text:
                field.widget.attrs["aria-describedby"] = f"id_{name}_help"

    @property
    def detail_fields(self):
        return [self[name] for name in self.DETAIL_FIELDS]

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"

    def clean_phone(self):
        phone = " ".join(self.cleaned_data["phone"].split())
        if phone and (
            not PHONE_PATTERN.fullmatch(phone) or sum(char.isdigit() for char in phone) < PHONE_MIN_DIGITS
        ):
            raise forms.ValidationError(_("Enter a phone number using digits, spaces, +, - or brackets."))
        return phone

    def clean_date_of_birth(self):
        value = self.cleaned_data["date_of_birth"]
        if value is not None:
            if value > timezone.localdate():
                raise forms.ValidationError(_("Date of birth can't be in the future."))
            if value.year < 1900:
                raise forms.ValidationError(_("Enter a date after 1900."))
        return value

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return None
        if avatar.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError(_("That photo is larger than 2 MB."))
        # forms.ImageField has already opened the file with Pillow.
        image_format = getattr(getattr(avatar, "image", None), "format", None)
        if image_format not in AVATAR_FORMATS:
            raise forms.ValidationError(_("Upload a JPEG, PNG or WebP image."))
        return avatar

    def profile_data(self):
        """The payload for CustomerService.update_profile(), which diffs and audits it."""
        data = {name: self.cleaned_data[name] for name in self.DETAIL_FIELDS}
        for name in ("first_name", "last_name", "display_name"):
            data[name] = data[name].strip()
        if self.cleaned_data.get("avatar"):
            data["avatar"] = self.cleaned_data["avatar"]
        elif self.cleaned_data.get("remove_avatar") and self.profile is not None and self.profile.avatar:
            data["avatar"] = None
        return data


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def profile_view(site, request):
    user = request.user
    profile = CustomerProfile.objects.filter(user=user).first()

    if request.method == "POST":
        form = AdminProfileForm(request.POST, request.FILES, user=user, profile=profile)
        if form.is_valid():
            if form.has_changed():
                with transaction.atomic():
                    CustomerService.update_profile(
                        user=user,
                        data=form.profile_data(),
                        actor=user,
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                messages.success(request, _("Your profile was updated."))
            else:
                messages.info(request, _("Nothing to save: your profile is unchanged."))
            return redirect(f"{reverse('admin:profile')}#personal")
        editing = True
    else:
        form = AdminProfileForm(user=user, profile=profile)
        editing = request.GET.get("edit") == "1"

    context = site.each_context(request)
    context.update(
        build_profile_context(site, request, context, profile),
        title=_("My profile"),
        form=form,
        editing=editing,
    )
    request.current_app = site.name
    return TemplateResponse(request, "admin/profile.html", context)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def build_profile_context(site, request, site_context, profile):
    """`site_context` is each_context(): its available_apps and storefront_url are reused."""
    user = request.user
    now = timezone.now()
    available_apps = site_context["available_apps"]
    viewable = _viewable_models(available_apps)
    storefront = site_context["storefront_url"].rstrip("/")

    rbac = _rbac_access(user)
    activity = _activity(user, viewable, now)
    work = _work(user, viewable)
    notifications = _notifications(user, storefront)

    audit_url = _changelist_url(viewable, AuditLog, f"actor__id__exact={user.pk}")
    user_record_url = _change_url(viewable, User, user.pk)

    return {
        "identity": _identity(user, profile),
        "access": _access_level(user),
        "completeness": _completeness(user, profile),
        "profile": profile,
        "roles": _roles(user),
        "direct_grants": _direct_grants(user),
        "rbac": rbac,
        "panel": _panel_access(site, available_apps),
        "activity": activity,
        "work": work,
        "security": _security(user, now),
        "notifications": notifications,
        "linked": _linked(user, profile, viewable, work["counts"]),
        "kpis": _kpis(work, activity, notifications, rbac, audit_url),
        "audit_trail_url": audit_url,
        "user_record_url": user_record_url,
        "console_profile_url": f"{storefront}/admin/profile",
    }


def _viewable_models(available_apps):
    """Model class -> True for every model the user may open in this admin."""
    viewable = {}
    for app in available_apps:
        for entry in app["models"]:
            perms = entry.get("perms", {})
            if perms.get("view") or perms.get("change"):
                viewable[entry["model"]] = True
    return viewable


def _change_url(viewable, model, pk):
    if model not in viewable:
        return ""
    opts = model._meta
    try:
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[quote(pk)])
    except NoReverseMatch:
        return ""


def _changelist_url(viewable, model, query=""):
    if model not in viewable:
        return ""
    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
    return f"{url}?{query}" if query else url


def _relative(value, now):
    """"3 days ago" -- one unit is plenty for a glance."""
    if value is None:
        return ""
    if now - value < timedelta(minutes=1):
        return _("just now")
    return _("%(time)s ago") % {"time": timesince(value, now, depth=1)}


def _identity(user, profile):
    full_name = user.get_full_name().strip()
    display_name = (profile.display_name.strip() if profile else "") or ""
    name = full_name or display_name or user.get_username()

    if user.first_name and user.last_name:
        initials = user.first_name[0] + user.last_name[0]
    else:
        words = name.split()
        initials = (words[0][0] + words[1][0]) if len(words) > 1 else name[:1]

    return {
        "name": name,
        "initials": initials.upper() or "?",
        "display_name": display_name,
        "avatar_url": profile.avatar.url if profile and profile.avatar else "",
        "phone": profile.phone if profile else "",
        "date_of_birth": profile.date_of_birth if profile else None,
        "gender": profile.get_gender_display() if profile and profile.gender else "",
    }


def _access_level(user):
    key = "super" if user.is_superuser else "staff"
    label, icon = ACCESS_LEVELS[key]
    return {"key": key, "label": label, "icon": icon}


def _completeness(user, profile):
    """Only fields this page can fill in, so every nudge is actionable here."""
    items = (
        (_("photo"), "id_avatar", bool(profile and profile.avatar)),
        (_("first name"), "id_first_name", bool(user.first_name)),
        (_("last name"), "id_last_name", bool(user.last_name)),
        (_("phone number"), "id_phone", bool(profile and profile.phone)),
    )
    done = sum(1 for _label, _anchor, filled in items if filled)
    missing = [{"label": label, "anchor": anchor} for label, anchor, filled in items if not filled]
    return {
        "done": done,
        "total": len(items),
        "percent": round(done * 100 / len(items)),
        "missing": missing,
    }


def _roles(user):
    rows = []
    assignments = (
        UserRole.objects.filter(user=user)
        .select_related("role", "assigned_by")
        .order_by("-is_active", "role__name")
    )
    for assignment in assignments:
        role = assignment.role
        rows.append(
            {
                "name": role.name,
                "code": role.code,
                "description": role.description,
                "active": assignment.is_active and role.is_active,
                "assigned_by": _person(assignment.assigned_by),
                "assigned_at": assignment.assigned_at,
            }
        )
    return rows


def _direct_grants(user):
    rows = []
    grants = (
        UserPermission.objects.filter(user=user)
        .select_related("permission", "granted_by")
        .order_by("-is_active", "permission__code")
    )
    for grant in grants:
        rows.append(
            {
                "name": grant.permission.name,
                "code": grant.permission.code,
                "note": grant.note,
                "active": grant.is_active,
                "granted_by": _person(grant.granted_by),
                "granted_at": grant.granted_at,
            }
        )
    return rows


def _person(user):
    if user is None:
        return ""
    return user.get_full_name().strip() or user.get_username()


def _rbac_access(user):
    """
    Effective MiniShop (Console & API) permissions, grouped like the board on the
    user change form. `granted` comes from get_user_permissions() -- the one
    resolver every API permission class uses -- so a superuser shows every code
    as held, not the zero that the role tables alone would suggest.
    """
    effective = get_user_permissions(user)
    full_access = WILDCARD_CODE in effective
    board = build_minishop_permission_board(user)["board"] or {"sections": [], "roles": []}
    role_names = {role["code"]: role["name"] for role in board["roles"]}

    sections = []
    for section in board["sections"]:
        held = []
        for permission in section["permissions"]:
            if permission["code"] not in effective:
                continue
            if permission["direct"]:
                source = _("Direct grant")
            elif permission["roles"]:
                source = ", ".join(role_names.get(code, code) for code in permission["roles"])
            else:
                source = _("Full access")
            held.append({"name": permission["name"], "code": permission["code"], "source": source})
        sections.append(
            {
                "key": section["key"],
                "label": section["label"],
                "icon": section["icon"],
                "permissions": held,
                "granted": len(held),
                "total": section["total"],
                "percent": round(len(held) * 100 / section["total"]) if section["total"] else 0,
            }
        )

    granted = sum(section["granted"] for section in sections)
    total = sum(section["total"] for section in sections)
    return {"sections": sections, "full_access": full_access, "granted": granted, "total": total}


def _panel_access(site, available_apps):
    """
    What this person can do inside the Django admin, straight from
    get_app_list() -- the same per-model permissions the sidebar and dashboard
    are built from, including any ModelAdmin that overrides has_*_permission.
    """
    sections = []
    for app in available_apps:
        label, icon, weight = PANEL_SECTION_META.get(
            app["app_label"], (app["name"], "folder", DEFAULT_WEIGHT)
        )
        models = []
        for entry in app["models"]:
            perms = entry.get("perms", {})
            models.append(
                {
                    "name": entry["name"],
                    "url": entry.get("admin_url") or "",
                    "actions": [
                        {"key": key, "label": action_label, "icon": action_icon, "allowed": bool(perms.get(key))}
                        for key, action_label, action_icon in ACTIONS
                    ],
                }
            )
        sections.append({"key": app["app_label"], "label": label, "icon": icon, "weight": weight, "models": models})
    sections.sort(key=lambda section: (section["weight"], str(section["label"])))

    reachable = sum(len(section["models"]) for section in sections)
    return {"sections": sections, "reachable": reachable, "total": len(site._registry)}


# --- Activity ---------------------------------------------------------------

#: Prefixes that say who acted, not what happened ("ADMIN_SELLER_APPROVE").
_ACTION_PREFIXES = {"ADMIN", "SUPERUSER"}
#: Imperative verbs some codes use, read back in the past tense.
_PAST_TENSE = {
    "APPROVE": "approved",
    "REJECT": "rejected",
    "SUSPEND": "suspended",
    "REACTIVATE": "reactivated",
    "MINT": "minted",
    "TRANSFER": "transferred",
    "CREDIT": "credited",
}
#: First match wins, so the more severe outcomes are listed first.
_ACTION_STYLES = (
    ({"DELETED", "DELETE", "REMOVED"}, "delete", "rose"),
    ({"REJECT", "REJECTED", "FAILED", "CANCELLED"}, "block", "rose"),
    ({"SUSPEND", "SUSPENDED", "HIDDEN"}, "pause_circle", "amber"),
    ({"APPROVE", "APPROVED", "REACTIVATE", "SUCCESS", "UNHIDDEN"}, "check_circle", "green"),
    ({"CREATED", "CREATE", "MINT", "CREDIT"}, "add_circle", "green"),
    ({"ASSIGNED"}, "person_add", "blue"),
    ({"PROCESSED", "TRANSFER", "RESERVED", "RELEASED", "DELIVERED", "ADJUSTED", "REQUEUED"}, "sync_alt", "indigo"),
    ({"UPDATED", "UPDATE", "CHANGED", "SET", "PROMOTED"}, "edit", "blue"),
)
_LOG_ENTRY_STYLES = {
    ADDITION: (_("Added"), "add_circle", "green"),
    CHANGE: (_("Changed"), "edit", "blue"),
    DELETION: (_("Deleted"), "delete", "rose"),
}


def humanize_action(code):
    """ "ADMIN_SELLER_APPROVE" -> "Seller approved"; "PRODUCT_UPDATED" -> "Product updated"."""
    words = [word for word in (code or "").upper().split("_") if word]
    while len(words) > 1 and words[0] in _ACTION_PREFIXES:
        words = words[1:]
    text = " ".join(_PAST_TENSE.get(word, word.lower()) for word in words)
    return text[:1].upper() + text[1:]


def action_style(code):
    words = set((code or "").upper().split("_"))
    for keywords, icon, tone in _ACTION_STYLES:
        if words & keywords:
            return icon, tone
    return "bolt", "indigo"


def _activity(user, viewable, now):
    today = timezone.localdate(now)
    start = today - timedelta(days=today.weekday(), weeks=ACTIVITY_WEEKS - 1)
    start_at = timezone.make_aware(datetime.combine(start, time.min))
    month_ago = now - timedelta(days=30)

    # Bucketed in Python rather than with TruncDate so the day boundary is the
    # site's local day without relying on MySQL's timezone tables.
    stamps = list(
        chain(
            AuditLog.objects.filter(actor=user, created_at__gte=start_at).values_list("created_at", flat=True),
            LogEntry.objects.filter(user=user, action_time__gte=start_at).values_list("action_time", flat=True),
        )
    )
    per_day = Counter(timezone.localdate(stamp) for stamp in stamps)

    weeks, previous_month = [], None
    for week in range(ACTIVITY_WEEKS):
        monday = start + timedelta(weeks=week)
        days = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            count = per_day.get(day, 0)
            days.append({"date": day, "count": count, "level": _heat_level(count), "future": day > today})
        month = monday.strftime("%b") if monday.month != previous_month else ""
        previous_month = monday.month
        weeks.append({"days": days, "month": month})

    busiest = max(per_day.items(), key=lambda item: (item[1], item[0]), default=None)
    total = len(stamps)
    return {
        "weeks": weeks,
        "weeks_count": ACTIVITY_WEEKS,
        "total": total,
        "active_days": len(per_day),
        "busiest": {"date": busiest[0], "count": busiest[1]} if busiest else None,
        "last_30_days": sum(1 for stamp in stamps if stamp >= month_ago),
        "timeline": _timeline(user, viewable, now, today),
    }


def _heat_level(count):
    if count == 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


def _timeline(user, viewable, now, today):
    models_by_name = {model.__name__: model for model in viewable}
    items = []

    for entry in AuditLog.objects.filter(actor=user).order_by("-created_at")[:TIMELINE_LIMIT]:
        icon, tone = action_style(entry.action)
        reason = entry.metadata.get("reason", "") if isinstance(entry.metadata, dict) else ""
        model = models_by_name.get(entry.target_type)
        items.append(
            {
                "when": entry.created_at,
                "title": humanize_action(entry.action),
                "target": entry.target_repr or f"{entry.target_type} #{entry.target_id}",
                "url": _change_url(viewable, model, entry.target_id) if model else "",
                "detail": reason,
                "icon": icon,
                "tone": tone,
                "source": _("Audit log"),
            }
        )

    for entry in LogEntry.objects.filter(user=user).select_related("content_type").order_by("-action_time")[
        :TIMELINE_LIMIT
    ]:
        verb, icon, tone = _LOG_ENTRY_STYLES.get(entry.action_flag, (_("Changed"), "edit", "blue"))
        kind = entry.content_type.name if entry.content_type else ""
        items.append(
            {
                "when": entry.action_time,
                "title": f"{verb} {kind}".strip(),
                "target": entry.object_repr,
                "url": "" if entry.action_flag == DELETION else (entry.get_admin_url() or ""),
                "detail": entry.get_change_message() if entry.action_flag == CHANGE else "",
                "icon": icon,
                "tone": tone,
                "source": _("Admin"),
            }
        )

    items.sort(key=lambda item: item["when"], reverse=True)
    groups = []
    for item in items[:TIMELINE_LIMIT]:
        day = timezone.localdate(item["when"])
        if not groups or groups[-1]["date"] != day:
            if day == today:
                label = _("Today")
            elif day == today - timedelta(days=1):
                label = _("Yesterday")
            else:
                label = ""
            groups.append({"date": day, "label": label, "items": []})
        groups[-1]["items"].append(item)
    return groups


# --- Work -------------------------------------------------------------------

_TICKET_STATUS_TONES = {
    SupportTicket.STATUS_OPEN: "blue",
    SupportTicket.STATUS_IN_PROGRESS: "indigo",
    SupportTicket.STATUS_WAITING_ON_CUSTOMER: "amber",
    SupportTicket.STATUS_RESOLVED: "green",
    SupportTicket.STATUS_CLOSED: "muted",
}
_TICKET_PRIORITY_TONES = {
    SupportTicket.PRIORITY_URGENT: "rose",
    SupportTicket.PRIORITY_HIGH: "amber",
    SupportTicket.PRIORITY_NORMAL: "muted",
    SupportTicket.PRIORITY_LOW: "muted",
}


def _count_of(model, field):
    """A correlated COUNT(*) of `model` rows pointing at the outer user."""
    rows = (
        model.objects.filter(**{field: OuterRef("pk")})
        .order_by()
        .values(field)
        .annotate(n=Count("pk"))
        .values("n")[:1]
    )
    return Coalesce(Subquery(rows, output_field=IntegerField()), 0)


def _work(user, viewable):
    counts = (
        User.objects.filter(pk=user.pk)
        .annotate(
            sellers_reviewed=_count_of(SellerProfile, "reviewed_by"),
            products_reviewed=_count_of(Product, "reviewed_by"),
            refunds_processed=_count_of(Refund, "processed_by"),
            stock_movements=_count_of(InventoryTransaction, "actor"),
            roles_assigned=_count_of(UserRole, "assigned_by"),
            grants_given=_count_of(UserPermission, "granted_by"),
            orders_placed=_count_of(Order, "user"),
            addresses_saved=_count_of(Address, "user"),
        )
        .values(
            "sellers_reviewed", "products_reviewed", "refunds_processed", "stock_movements",
            "roles_assigned", "grants_given", "orders_placed", "addresses_saved",
        )
        .get()
    )

    tickets = SupportTicket.objects.filter(assigned_to=user)
    by_status = dict(tickets.order_by().values_list("status").annotate(n=Count("pk")))
    statuses = [
        {"key": key, "label": label, "count": by_status.get(key, 0), "tone": _TICKET_STATUS_TONES[key]}
        for key, label in SupportTicket.STATUS_CHOICES
    ]
    unresolved = sum(by_status.get(key, 0) for key in SupportTicket.UNRESOLVED_STATUSES)

    open_tickets = []
    for ticket in tickets.filter(status__in=SupportTicket.UNRESOLVED_STATUSES).order_by("-last_activity_at")[
        :OPEN_TICKET_LIMIT
    ]:
        open_tickets.append(
            {
                "number": ticket.ticket_number,
                "subject": ticket.subject,
                "status": ticket.get_status_display(),
                "status_tone": _TICKET_STATUS_TONES.get(ticket.status, "muted"),
                "priority": ticket.get_priority_display(),
                "priority_tone": _TICKET_PRIORITY_TONES.get(ticket.priority, "muted"),
                "last_activity_at": ticket.last_activity_at,
                "url": _change_url(viewable, SupportTicket, ticket.pk),
            }
        )

    contributions = [
        {"label": _("Sellers reviewed"), "icon": "badge", "count": counts["sellers_reviewed"]},
        {"label": _("Products reviewed"), "icon": "inventory_2", "count": counts["products_reviewed"]},
        {"label": _("Refunds processed"), "icon": "currency_exchange", "count": counts["refunds_processed"]},
        {"label": _("Stock movements"), "icon": "swap_vert", "count": counts["stock_movements"]},
        {"label": _("Roles assigned"), "icon": "workspace_premium", "count": counts["roles_assigned"]},
        {"label": _("Direct grants given"), "icon": "key", "count": counts["grants_given"]},
    ]
    return {
        "counts": counts,
        "statuses": statuses,
        "unresolved": unresolved,
        "open_tickets": open_tickets,
        "tickets_url": _changelist_url(viewable, SupportTicket, f"assigned_to__id__exact={user.pk}"),
        "contributions": contributions,
    }


# --- Rail -------------------------------------------------------------------


def _security(user, now):
    last_ip = (
        AuditLog.objects.filter(actor=user, ip_address__isnull=False)
        .order_by("-created_at")
        .values_list("ip_address", "created_at")
        .first()
    )
    return {
        "last_login": user.last_login,
        "last_login_ago": _relative(user.last_login, now),
        "joined": user.date_joined,
        "joined_ago": _relative(user.date_joined, now),
        "has_password": user.has_usable_password(),
        "last_ip": last_ip[0] if last_ip else "",
        "last_ip_at": last_ip[1] if last_ip else None,
    }


def _notifications(user, storefront):
    if not can_read_audience(user, Audience.STAFF):
        return {"show": False}
    unread = Notification.objects.filter(recipient=user, audience=Audience.STAFF, read_at__isnull=True).count()
    return {
        "show": True,
        "unread": unread,
        "inbox_url": f"{storefront}/admin/notifications",
        "settings_url": f"{storefront}/admin/notifications/settings",
    }


def _linked(user, profile, viewable, counts):
    seller = SellerProfile.objects.filter(user=user).first()
    return {
        "customer": {
            "exists": profile is not None,
            "url": _change_url(viewable, CustomerProfile, profile.pk) if profile else "",
            "orders": counts["orders_placed"],
            "addresses": counts["addresses_saved"],
        },
        "seller": {
            "exists": seller is not None,
            "name": seller.business_name if seller else "",
            "status": seller.get_status_display() if seller else "",
            "url": _change_url(viewable, SellerProfile, seller.pk) if seller else "",
        },
    }


def _kpis(work, activity, notifications, rbac, audit_url):
    access_value = _("Full") if rbac["full_access"] else rbac["granted"]
    access_label = _("platform access") if rbac["full_access"] else _("of %(total)s permissions") % {
        "total": rbac["total"]
    }
    return [
        {
            "value": work["unresolved"],
            "label": _("open tickets assigned"),
            "icon": "support_agent",
            "tone": "blue",
            "url": work["tickets_url"],
        },
        {
            "value": activity["last_30_days"],
            "label": _("actions in 30 days"),
            "icon": "bolt",
            "tone": "gold",
            "url": audit_url,
        },
        {
            "value": notifications["unread"] if notifications["show"] else "—",
            "label": _("unread notifications"),
            "icon": "notifications",
            "tone": "indigo",
            "url": notifications.get("inbox_url", ""),
            "external": True,
        },
        {
            "value": access_value,
            "label": access_label,
            "icon": "verified_user",
            "tone": "green",
            "url": "#access",
        },
    ]
