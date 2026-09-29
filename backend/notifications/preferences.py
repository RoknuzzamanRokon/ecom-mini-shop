"""
Which channels reach a person for a category (docs/NOTIFICATION_SYSTEM.md §3 D8).

A category's default channels are all on until the person switches one off
with a NotificationPreference row. A locked channel ignores that row.
"""
from collections import defaultdict

from .categories import CATEGORIES
from .events import EVENT_TYPES
from .models import Channel, NotificationPreference


def effective_channels(user, category_code, overrides=None):
    """
    The channels `user` receives `category_code` notifications on.
    `overrides` maps channel -> enabled; it's read from the database when
    omitted. Pass it when the rows are already loaded (see load_overrides).
    """
    category = CATEGORIES[category_code]
    if overrides is None:
        overrides = dict(
            NotificationPreference.objects.filter(user=user, category=category_code).values_list(
                "channel", "enabled"
            )
        )
    return frozenset(
        channel
        for channel in category.default_channels
        if channel in category.locked_channels or overrides.get(channel, True)
    )


def load_overrides(user_ids, category_codes):
    """{(user_id, category): {channel: enabled}} for many people in one query."""
    overrides = defaultdict(dict)
    rows = NotificationPreference.objects.filter(
        user_id__in=user_ids, category__in=category_codes
    ).values_list("user_id", "category", "channel", "enabled")
    for user_id, category, channel, enabled in rows:
        overrides[(user_id, category)][channel] = enabled
    return overrides


# --- The preferences API (§8) ----------------------------------------------
# Channels appear in the API as "in_app" and "email".

API_CHANNELS = {channel.lower(): channel for channel in Channel.values}


class PreferenceError(ValueError):
    """A preference change the API refuses (a 400)."""


def category_audiences():
    """{category: {audiences whose notifications file under it}}, from the event registry."""
    mapping = defaultdict(set)
    for event in EVENT_TYPES.values():
        for audience, category in event.audiences.items():
            mapping[category].add(audience)
    return mapping


def applicable_categories(audiences):
    """The categories, in registry order, that reach any of `audiences`."""
    reach = category_audiences()
    return [code for code in CATEGORIES if reach[code] & set(audiences)]


def describe_preferences(user, audiences):
    """The GET /preferences/ rows: every channel a category uses, with its state and lock."""
    codes = applicable_categories(audiences)
    overrides = load_overrides([user.pk], codes)
    rows = []
    for code in codes:
        category = CATEGORIES[code]
        enabled = effective_channels(user, code, overrides.get((user.pk, code), {}))
        rows.append({
            "category": code,
            "label": category.label,
            "channels": {
                channel.lower(): {
                    "enabled": channel in enabled,
                    "locked": channel in category.locked_channels,
                }
                for channel in Channel.values
                if channel in category.default_channels
            },
        })
    return rows


def parse_preference_changes(data, audiences):
    """
    Validates a PUT body ([{category, channels: {channel: {enabled}}}]) and
    returns {(category, channel): enabled}. Raises PreferenceError.
    """
    if not isinstance(data, list):
        raise PreferenceError("Send a list of categories.")
    allowed = set(applicable_categories(audiences))
    changes = {}
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("channels"), dict):
            raise PreferenceError("Each entry needs a category and its channels.")
        code = item.get("category")
        if code not in allowed:
            raise PreferenceError(f"'{code}' isn't a category you receive.")
        category = CATEGORIES[code]
        for key, toggle in item["channels"].items():
            channel = API_CHANNELS.get(key)
            if channel not in category.default_channels:
                raise PreferenceError(f"{category.label} has no '{key}' channel.")
            enabled = toggle.get("enabled") if isinstance(toggle, dict) else None
            if not isinstance(enabled, bool):
                raise PreferenceError(f"Say whether {category.label} {key} is enabled (true or false).")
            if channel in category.locked_channels and not enabled:
                raise PreferenceError(f"{category.label} {key} is required and can't be switched off.")
            changes[(code, channel)] = enabled
    return changes


def apply_preference_changes(user, changes):
    """
    Stores `changes` sparsely: a channel back at its default loses its row.
    Returns {(category, channel): (before, after)} for what actually changed.
    """
    stored = {
        (row.category, row.channel): row
        for row in NotificationPreference.objects.filter(
            user=user, category__in={code for code, _ in changes}
        )
    }
    changed = {}
    for (code, channel), enabled in changes.items():
        row = stored.get((code, channel))
        before = row.enabled if row else True
        if before == enabled:
            continue
        if enabled:  # back to the default, which is on
            row.delete()
        elif row:
            row.enabled = False
            row.save(update_fields=["enabled", "updated_at"])
        else:
            NotificationPreference.objects.create(user=user, category=code, channel=channel, enabled=False)
        changed[(code, channel)] = (before, enabled)
    return changed
