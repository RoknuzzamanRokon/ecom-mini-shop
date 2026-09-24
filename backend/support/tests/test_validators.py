from django.test import SimpleTestCase

from support.exceptions import AttachmentError
from support.validators import (
    MAX_ATTACHMENT_BYTES,
    MAX_NAME_LENGTH,
    clean_display_name,
    validate_attachments,
)

from .helpers import image_bytes, jpeg, pdf, png, upload, webp

NOT_ALLOWED = "isn't a JPG, PNG, WebP or PDF file"


class AttachmentValidatorTests(SimpleTestCase):
    def test_each_allowed_type_is_detected_from_content(self):
        cases = [
            (png(), "image/png", "png"),
            (jpeg(), "image/jpeg", "jpg"),
            (webp(), "image/webp", "webp"),
            (pdf(), "application/pdf", "pdf"),
        ]
        for f, content_type, extension in cases:
            with self.subTest(name=f.name):
                checked = validate_attachments([f])[0]
                self.assertEqual(checked.content_type, content_type)
                self.assertEqual(checked.extension, extension)
                self.assertEqual(checked.size, f.size)
                self.assertIs(checked.file, f)

    def test_file_is_rewound_after_checking(self):
        f = png()
        validate_attachments([f])
        self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_no_files_is_fine(self):
        self.assertEqual(validate_attachments(None), [])
        self.assertEqual(validate_attachments([]), [])

    def test_five_files_accepted_six_refused(self):
        self.assertEqual(len(validate_attachments([png() for _ in range(5)])), 5)
        with self.assertRaisesMessage(AttachmentError, "up to 5 files"):
            validate_attachments([png() for _ in range(6)])

    def test_empty_file_refused(self):
        with self.assertRaisesMessage(AttachmentError, "“blank.pdf” is empty."):
            validate_attachments([upload("blank.pdf", b"")])

    def test_size_limit_is_5_mb(self):
        overhead = len(pdf().read())
        exact = pdf(padding=b"0" * (MAX_ATTACHMENT_BYTES - overhead))
        self.assertEqual(exact.size, MAX_ATTACHMENT_BYTES)
        self.assertEqual(len(validate_attachments([exact])), 1)

        too_big = pdf(name="big.pdf", padding=b"0" * (MAX_ATTACHMENT_BYTES - overhead + 1))
        with self.assertRaisesMessage(AttachmentError, "“big.pdf” is larger than 5 MB."):
            validate_attachments([too_big])

    def test_disallowed_content_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        cases = [
            upload("notes.png", b"just some text, not an image"),
            upload("drawing.svg", svg, "image/svg+xml"),
            upload("drawing.png", svg, "image/png"),
            upload("page.html", b"<html><script>alert(1)</script></html>", "text/html"),
            upload("anim.gif", image_bytes("GIF"), "image/gif"),
            upload("bitmap.bmp", image_bytes("BMP"), "image/bmp"),
            upload("archive.pdf", b"PK\x03\x04 not a pdf", "application/pdf"),
        ]
        for f in cases:
            with self.subTest(name=f.name):
                with self.assertRaisesMessage(AttachmentError, f"“{f.name}” {NOT_ALLOWED}"):
                    validate_attachments([f])

    def test_truncated_image_is_refused(self):
        with self.assertRaisesMessage(AttachmentError, NOT_ALLOWED):
            validate_attachments([upload("cut.png", image_bytes("PNG")[:40], "image/png")])

    def test_one_bad_file_refuses_the_whole_batch(self):
        with self.assertRaises(AttachmentError):
            validate_attachments([png(), upload("evil.svg", b"<svg/>")])

    def test_type_comes_from_content_not_name(self):
        renamed_pdf = validate_attachments([pdf(name="scan.jpg")])[0]
        self.assertEqual(renamed_pdf.content_type, "application/pdf")
        self.assertEqual(renamed_pdf.original_name, "scan.pdf")

        renamed_png = validate_attachments([png(name="photo.jpg")])[0]
        self.assertEqual(renamed_png.content_type, "image/png")
        self.assertEqual(renamed_png.original_name, "photo.png")

    def test_matching_names_are_kept_as_typed(self):
        self.assertEqual(validate_attachments([jpeg("Photo.JPEG")])[0].original_name, "Photo.JPEG")
        self.assertEqual(validate_attachments([jpeg("box.jpg")])[0].original_name, "box.jpg")


class DisplayNameTests(SimpleTestCase):
    def test_directories_are_dropped(self):
        self.assertEqual(clean_display_name("..\\..\\secret\\evil.png", "png"), "evil.png")
        self.assertEqual(clean_display_name("/etc/../photo.png", "png"), "photo.png")

    def test_control_characters_are_dropped(self):
        self.assertEqual(clean_display_name("re\x00ce\x1fipt‮.pdf", "pdf"), "receipt.pdf")

    def test_missing_name_or_extension(self):
        self.assertEqual(clean_display_name("", "pdf"), "attachment.pdf")
        self.assertEqual(clean_display_name("scan", "jpg"), "scan.jpg")
        self.assertEqual(clean_display_name(".pdf", "pdf"), "pdf.pdf")

    def test_long_names_are_cut_keeping_the_extension(self):
        name = clean_display_name("a" * 400 + ".webp", "webp")
        self.assertEqual(len(name), MAX_NAME_LENGTH)
        self.assertTrue(name.endswith(".webp"))
