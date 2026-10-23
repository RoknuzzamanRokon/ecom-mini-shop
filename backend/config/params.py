"""
Query-parameter parsing shared by the API views. A malformed value is a 400
naming the parameter, never a 500 from inside a queryset (BUG-066).
"""
import re
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from rest_framework.exceptions import ValidationError

_WHOLE_NUMBER = re.compile(r"[0-9]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def is_whole_number(value) -> bool:
    """ASCII digits only. str.isdigit() also accepts "²", which int() rejects."""
    return isinstance(value, str) and bool(_WHOLE_NUMBER.fullmatch(value))


def id_param(params, *names) -> Optional[int]:
    """The first of `names` given in `params`, as a positive id; None when none is."""
    for name in names:
        raw = (params.get(name) or "").strip()
        if raw:
            if not is_whole_number(raw) or int(raw) < 1:
                raise ValidationError({name: "Must be a positive whole number."})
            return int(raw)
    return None


def date_param(params, *names) -> Optional[date]:
    """The first of `names` given in `params`, as a YYYY-MM-DD date; None when none is."""
    for name in names:
        raw = (params.get(name) or "").strip()
        if raw:
            try:
                if not _ISO_DATE.fullmatch(raw):
                    raise ValueError
                return date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({name: "Enter a valid date as YYYY-MM-DD."})
    return None


def business_day_start(day: date) -> datetime:
    """Midnight starting `day` in settings.BUSINESS_TIME_ZONE, as an aware datetime."""
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(settings.BUSINESS_TIME_ZONE))
