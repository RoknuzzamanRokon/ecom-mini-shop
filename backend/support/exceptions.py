class SupportTicketError(Exception):
    """A support rule was broken. The message is plain text, safe to return as a 400."""


class AttachmentError(SupportTicketError):
    """An uploaded file was refused because of its count, size or type."""
