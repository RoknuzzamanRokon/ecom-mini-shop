import io
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from rbac.services import assign_user_role

User = get_user_model()


def image_bytes(image_format, size=(4, 4)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=image_format)
    return buffer.getvalue()


def upload(name, data, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def png(name="photo.png"):
    return upload(name, image_bytes("PNG"), "image/png")


def jpeg(name="photo.jpg"):
    return upload(name, image_bytes("JPEG"), "image/jpeg")


def webp(name="photo.webp"):
    return upload(name, image_bytes("WEBP"), "image/webp")


def pdf(name="receipt.pdf", padding=b""):
    return upload(name, b"%PDF-1.4\n" + padding + b"\n%%EOF\n", "application/pdf")


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username=username, password="pw", **extra)
    if role:
        assign_user_role(user, role)
    return user


class PrivateMediaMixin:
    """Points PRIVATE_MEDIA_ROOT at a temporary directory for the whole test class."""

    @classmethod
    def setUpClass(cls):
        cls.private_root = tempfile.mkdtemp(prefix="support_private_")
        cls._private_override = override_settings(PRIVATE_MEDIA_ROOT=cls.private_root)
        cls._private_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_override.disable()
        shutil.rmtree(cls.private_root, ignore_errors=True)

    def private_files(self) -> set:
        root = Path(self.private_root)
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
