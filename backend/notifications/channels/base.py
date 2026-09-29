"""
Channel adapters (docs/NOTIFICATION_SYSTEM.md §4.2): each one sends a
delivery through one provider and knows nothing about event types.

The worker calls `adapter.send(delivery)` outside any transaction and reads
the outcome from what it returns or raises:

- a SendResult: SENT;
- TransientSendError, or any unexpected exception: retried with backoff,
  then DEAD;
- PermanentSendError: DEAD at once, or SKIPPED when `skip=True` (e.g. no
  usable address).

Deliveries for a channel with no registered adapter are left PENDING.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str = ""


class SendError(Exception):
    pass


class TransientSendError(SendError):
    """Worth retrying: a timeout, a refused connection, a 4xx reply."""


class PermanentSendError(SendError):
    """Won't work on a retry: a 5xx reply, an invalid address."""

    def __init__(self, message, *, skip=False):
        super().__init__(message)
        self.skip = skip


class ChannelAdapter(Protocol):
    channel: str

    def send(self, delivery) -> SendResult: ...


ADAPTERS = {}


def register_adapter(adapter):
    ADAPTERS[adapter.channel] = adapter
    return adapter


def get_adapter(channel):
    return ADAPTERS.get(channel)
