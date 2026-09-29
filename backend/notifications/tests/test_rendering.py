from django.template import TemplateDoesNotExist
from django.test import SimpleTestCase

from notifications.models import Channel
from notifications.rendering import RenderError, render_in_app, template_name

from .helpers import with_test_templates


def echo(title="A title", body="A body", link="/orders/1"):
    return render_in_app("test.echo", 1, {"title": title, "body": body, "link": link})


@with_test_templates
class InAppRenderingTests(SimpleTestCase):
    def test_template_name(self):
        self.assertEqual(
            template_name("order.placed", 2, Channel.IN_APP), "notifications/order.placed/v2/in_app.txt"
        )

    def test_renders_the_three_blocks_stripped(self):
        class Person:
            username = "rahim"

        message = render_in_app("test.happened", 1, {"thing": "T1", "note": "twice", "recipient": Person()})
        self.assertEqual(message.title, "Thing T1 happened")
        self.assertEqual(message.body, "Hello rahim, T1 happened (twice).")
        self.assertEqual(message.action_url, "/things/T1")

    def test_output_is_plain_text_not_html_escaped(self):
        self.assertEqual(echo(body="Tom & Jerry <3").body, "Tom & Jerry <3")

    def test_missing_template_fails_loudly(self):
        with self.assertRaises(TemplateDoesNotExist):
            render_in_app("test.happened", 2, {"thing": "T1"})

    def test_missing_block_is_refused(self):
        with self.assertRaisesMessage(RenderError, "no body block"):
            render_in_app("test.no_body", 1, {})

    def test_empty_title_is_refused(self):
        with self.assertRaisesMessage(RenderError, "empty title"):
            echo(title="   ")

    def test_long_title_is_shortened_to_fit(self):
        title = echo(title="x" * 250).title
        self.assertEqual(len(title), 200)
        self.assertTrue(title.endswith("…"))

    def test_links_must_be_app_paths(self):
        for link in ("/orders/1", "/profile/notifications?unread=1", ""):
            with self.subTest(link=link):
                self.assertEqual(echo(link=link).action_url, link)
        for link in ("https://evil.example/", "//evil.example", "/\\evil.example", "orders/1", "javascript:alert(1)"):
            with self.subTest(link=link):
                with self.assertRaisesMessage(RenderError, "must be an app path"):
                    echo(link=link)

    def test_overlong_link_is_refused(self):
        with self.assertRaisesMessage(RenderError, "longer than 500"):
            echo(link="/" + "a" * 500)
