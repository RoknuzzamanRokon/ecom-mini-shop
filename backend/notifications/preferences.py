"""
Which channels reach a person for a category (docs/NOTIFICATION_SYSTEM.md §3 D8).

A category's default channels are all on until the person switches one off
with a NotificationPreference row. A locked channel ignores that row.
"""
from collections import defaultdict

from .categories import CATEGORIES
from .models import NotificationPreference


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
