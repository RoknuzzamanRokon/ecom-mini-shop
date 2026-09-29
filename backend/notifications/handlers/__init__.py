"""
Event handlers, one module per area. NotificationsConfig.ready() imports this
package, and each module imported here registers its handlers.
"""
from .base import HANDLERS, Recipient, handlers_for, handles  # noqa: F401

from . import orders, payments  # noqa: E402,F401
