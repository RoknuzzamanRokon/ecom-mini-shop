"""
Validators shared by the API serializers and the Django admin forms, so an
upload or a profile field is held to the same rules whichever way it arrives
(BUG-060). They raise Django's ValidationError, which DRF fields also accept.
"""
import re

from django.core.exceptions import ValidationError
from django.utils import timezone

#: Formats every browser renders. Pillow opens many more (GIF, TIFF, BMP...).
#: MPO is a JPEG with extra pictures embedded, as many phone cameras save.
IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
AVATAR_MAX_BYTES = 2 * 1024 * 1024
#: Product images and shop logos and covers.
CATALOG_IMAGE_MAX_BYTES = 5 * 1024 * 1024

#: Digits plus the usual separators. Deliberately loose: numbers are written
#: many ways, and this only exists to stop obvious junk in the field.
PHONE_PATTERN = re.compile(r"[0-9+()\-\s]+")
PHONE_MIN_DIGITS = 6
EARLIEST_BIRTH_YEAR = 1900


def _image_format(upload):
    # Django's and DRF's ImageField leave the Pillow image they verified on
    # the upload; anything else is opened here.
    image = getattr(upload, "image", None)
    if image is not None:
        return image.format
    from PIL import Image

    position = upload.tell()
    try:
        with Image.open(upload) as opened:
            return opened.format
    except Exception:
        return None
    finally:
        upload.seek(position)


def _validate_image(upload, max_bytes, noun):
    if not upload:
        return
    if upload.size > max_bytes:
        raise ValidationError(f"That {noun} is larger than {max_bytes // (1024 * 1024)} MB.")
    if _image_format(upload) not in IMAGE_FORMATS:
        raise ValidationError("Upload a JPEG, PNG or WebP image.")


def validate_avatar(upload):
    """A profile photo: JPEG, PNG or WebP, at most AVATAR_MAX_BYTES."""
    _validate_image(upload, AVATAR_MAX_BYTES, "photo")


def validate_catalog_image(upload):
    """A product image or shop logo/cover: JPEG, PNG or WebP, at most CATALOG_IMAGE_MAX_BYTES."""
    _validate_image(upload, CATALOG_IMAGE_MAX_BYTES, "image")


def validate_phone(value):
    """Digits, spaces, +, - and brackets, with at least PHONE_MIN_DIGITS digits. Blank passes."""
    if value and (
        not PHONE_PATTERN.fullmatch(value) or sum(char.isdigit() for char in value) < PHONE_MIN_DIGITS
    ):
        raise ValidationError("Enter a phone number using digits, spaces, +, - or brackets.")


def validate_date_of_birth(value):
    """Not in the future, and not before EARLIEST_BIRTH_YEAR. None passes."""
    if value is None:
        return
    if value > timezone.localdate():
        raise ValidationError("Date of birth can't be in the future.")
    if value.year < EARLIEST_BIRTH_YEAR:
        raise ValidationError(f"Enter a date after {EARLIEST_BIRTH_YEAR}.")
