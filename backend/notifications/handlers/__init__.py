"""
Event handlers, one module per area (Tasks 8–10). NotificationsConfig.ready()
imports this package, and each module imported here registers its handlers.
"""
from .base import HANDLERS, Recipient, handlers_for, handles  # noqa: F401
