"""
Checks for files attached to support ticket messages.

The type of a file is decided from its content, never from its name or the
Content-Type the browser sent: a PDF starts with "%PDF-", and an image must be
one Pillow can open and verify as JPEG, PNG or WebP. Everything else (SVG,
HTML, GIF, scripts, renamed text files) is refused, so nothing that a browser
could run ever reaches storage.
"""
import os
import unicodedata
from dataclasses import dataclass

from PIL import Image

from .exceptions import AttachmentError

MAX_ATTACHMENTS_PER_MESSAGE = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_NAME_LENGTH = 255

ALLOWED_TYPES_LABEL = "JPG, PNG, WebP or PDF"

_IMAGE_TYPES = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_PDF_TYPE = ("application/pdf", "pdf")

# File-name extensions that already match a detected type, so the customer's
# own name is kept as typed ("photo.JPEG" stays "photo.JPEG").
_MATCHING_EXTENSIONS = {
    "jpg": {"jpg", "jpeg"},
    "png": {"png"},
    "webp": {"webp"},
    "pdf": {"pdf"},
}


@dataclass(frozen=True)
class CheckedAttachment:
    """An accepted upload, with the facts the attachment row stores."""

    file: object
    original_name: str
    content_type: str
    extension: str
    size: int


def validate_attachments(files) -> list:
    """Checks every file; returns CheckedAttachments or raises AttachmentError."""
    files = list(files or [])
    if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise AttachmentError(
            f"You can attach up to {MAX_ATTACHMENTS_PER_MESSAGE} files to one message."
        )
    return [_check_file(f) for f in files]


def clean_display_name(raw_name, extension: str) -> str:
    """
    The client's file name, made safe to show: no directories, no control
    characters, at most MAX_NAME_LENGTH characters, and an extension that
    matches the detected type ("receipt.jpg" holding a PDF becomes
    "receipt.pdf").
    """
    name = _base_name(raw_name)
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if ext.lower() not in _MATCHING_EXTENSIONS[extension]:
        name = f"{stem or 'attachment'}.{extension}"
    if len(name) > MAX_NAME_LENGTH:
        suffix = name[name.rfind("."):]
        name = name[: MAX_NAME_LENGTH - len(suffix)] + suffix
    return name


def _base_name(raw_name) -> str:
    name = str(raw_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C"))
    return name.strip().strip(".").strip()


def _file_size(f) -> int:
    size = getattr(f, "size", None)
    if size is None:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
    return size


def _check_file(f) -> CheckedAttachment:
    raw_name = getattr(f, "name", "") or ""
    shown = _base_name(raw_name)[:80] or "The file"
    size = _file_size(f)
    if size == 0:
        raise AttachmentError(f"“{shown}” is empty.")
    if size > MAX_ATTACHMENT_BYTES:
        raise AttachmentError(
            f"“{shown}” is larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB."
        )
    detected = _detect_type(f)
    if detected is None:
        raise AttachmentError(f"“{shown}” isn't a {ALLOWED_TYPES_LABEL} file.")
    content_type, extension = detected
    return CheckedAttachment(
        file=f,
        original_name=clean_display_name(raw_name, extension),
        content_type=content_type,
        extension=extension,
        size=size,
    )


def _detect_type(f):
    """(content_type, extension) from the file's bytes, or None if not allowed."""
    f.seek(0)
    head = f.read(5)
    f.seek(0)
    if head == b"%PDF-":
        return _PDF_TYPE
    try:
        with Image.open(f) as image:
            image_format = image.format
            image.verify()
    except Exception:
        # Pillow signals "not an image I can read" (and truncated or corrupt
        # data, and decompression bombs) through several exception types.
        return None
    finally:
        f.seek(0)
    return _IMAGE_TYPES.get(image_format)
