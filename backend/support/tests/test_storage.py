import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings

from support.models import SupportTicket, TicketAttachment, TicketMessage
from support.storage import support_attachment_path

User = get_user_model()

STORED_PATH = re.compile(r"^support/\d{4}/\d{2}/[0-9a-f]{32}\.(jpg|png|webp|pdf|bin)$")


class AttachmentPathTests(SimpleTestCase):
    def test_path_is_a_uuid_under_support(self):
        path = support_attachment_path(None, "My Receipt.PDF")
        self.assertRegex(path, STORED_PATH)
        self.assertTrue(path.endswith(".pdf"))

    def test_client_file_name_never_reaches_the_path(self):
        path = support_attachment_path(None, "../../etc/passwd my-secret-name.png")
        self.assertRegex(path, STORED_PATH)
        self.assertNotIn("secret", path)
        self.assertNotIn("..", path)

    def test_jpeg_is_stored_as_jpg(self):
        self.assertTrue(support_attachment_path(None, "photo.jpeg").endswith(".jpg"))

    def test_unexpected_extensions_are_stored_as_bin(self):
        for name in ("drawing.svg", "page.html", "script.js", "no_extension"):
            with self.subTest(name=name):
                self.assertTrue(support_attachment_path(None, name).endswith(".bin"))

    def test_two_uploads_never_share_a_path(self):
        self.assertNotEqual(
            support_attachment_path(None, "a.png"),
            support_attachment_path(None, "a.png"),
        )


class PrivateStorageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = User.objects.create_user(username="support_storage_customer", password="pw")
        ticket = SupportTicket.objects.create(
            ticket_number="TKT20260924STORE1",
            customer=customer,
            category=SupportTicket.CATEGORY_PAYMENT,
            subject="Charged twice",
        )
        cls.message = TicketMessage.objects.create(
            ticket=ticket,
            author=customer,
            author_type=TicketMessage.AUTHOR_CUSTOMER,
            body="Receipt attached.",
        )

    def setUp(self):
        self.private_root = tempfile.mkdtemp(prefix="support_private_")
        self.addCleanup(shutil.rmtree, self.private_root, ignore_errors=True)

    def test_private_root_is_outside_media_root(self):
        private = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()
        self.assertNotEqual(private, media)
        self.assertNotIn(media, private.parents)

    def test_attachment_is_written_under_the_private_root(self):
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            attachment = TicketAttachment.objects.create(
                message=self.message,
                file=ContentFile(b"%PDF-1.4 test", name="receipt.pdf"),
                original_name="receipt.pdf",
                content_type="application/pdf",
                size=13,
            )
            self.assertRegex(attachment.file.name, STORED_PATH)
            stored = Path(self.private_root) / attachment.file.name
            self.assertTrue(stored.is_file())
            self.assertEqual(stored.read_bytes(), b"%PDF-1.4 test")
            self.assertFalse((Path(settings.MEDIA_ROOT) / attachment.file.name).exists())

            attachment.refresh_from_db()
            with attachment.file.open("rb") as fh:
                self.assertEqual(fh.read(), b"%PDF-1.4 test")

    def test_storage_follows_the_setting(self):
        storage = TicketAttachment._meta.get_field("file").storage
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            self.assertEqual(Path(storage.location), Path(self.private_root).resolve())

    def test_attachments_have_no_public_url(self):
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            attachment = TicketAttachment.objects.create(
                message=self.message,
                file=ContentFile(b"%PDF-1.4", name="receipt.pdf"),
                original_name="receipt.pdf",
                content_type="application/pdf",
                size=8,
            )
            with self.assertRaises(ValueError):
                attachment.file.url
