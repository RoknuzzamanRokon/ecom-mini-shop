"""
Formatting for notification templates. Money is always Taka:

    {% load notification_format %}
    {{ total_amount|taka }}   ->  ৳1,500.00
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def taka(value):
    """A decimal amount (payloads carry money as strings) as ৳1,234.50."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return f"৳{value}"
    if not amount.is_finite():
        return f"৳{value}"
    return f"৳{amount.quantize(Decimal('0.01')):,.2f}"
