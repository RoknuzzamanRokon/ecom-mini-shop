"""
Private storage for support ticket attachments.

Attachments can hold payment screenshots, addresses and phone numbers, so they
are kept out of MEDIA_ROOT: that directory is served publicly whenever DEBUG is
on (config/urls.py) and the Next.js /media rewrite forwards it. Files here have
no public URL. The only way to read one is through the support download
endpoints, which check who is asking first.
"""
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils import timezone

# Extensions an attachment may be stored under. The attachment validator
# decides the real type from the file's content and names the upload to match;
# anything else that reaches the disk is stored as an inert ".bin".
STORED_EXTENSIONS = {"jpg", "png", "webp", "pdf"}


class PrivateMediaStorage(FileSystemStorage):
    """
    FileSystemStorage rooted at settings.PRIVATE_MEDIA_ROOT.

    The root is read on every access instead of being cached like MEDIA_ROOT,
    so tests can point it at a temporary directory with override_settings.
    """

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError(
            "Support attachments have no public URL; serve them through the "
            "support attachment download endpoint."
        )


def private_storage():
    """Storage callable for TicketAttachment.file (keeps migrations settings-free)."""
    return PrivateMediaStorage()


def support_attachment_path(instance, filename):
    """
    support/<yyyy>/<mm>/<uuid>.<ext>

    The client's file name never reaches the disk (it is kept in
    TicketAttachment.original_name for display only), so it can't collide,
    traverse directories, or reveal anything through the path.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if ext not in STORED_EXTENSIONS:
        ext = "bin"
    now = timezone.now()
    return f"support/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.{ext}"
