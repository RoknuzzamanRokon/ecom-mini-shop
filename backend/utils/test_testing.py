"""Checks for the shared test helpers themselves (TASK-043)."""

from django.test import SimpleTestCase

from utils.testing import TransitionTableMixin, admin_form_data

PAGE = """
<form id="changelist-search"><input name="q" value="ignored"></form>
<form id="product_form" method="post">
  <input type="hidden" name="csrfmiddlewaretoken" value="token">
  <input name="name" value="Desk &amp; Lamp">
  <input type="number" name="price" value="100.00">
  <input type="checkbox" name="is_active" checked>
  <input type="checkbox" name="featured">
  <input type="checkbox" name="tags" value="a" checked><input type="checkbox" name="tags" value="b" checked>
  <input type="radio" name="size" value="S"><input type="radio" name="size" value="M" checked>
  <input type="file" name="image">
  <input name="locked" value="x" disabled>
  <select name="category"><option value="">---</option><option value="3" selected>Lamps</option></select>
  <select name="shop"><option value="7">First</option><option value="8">Second</option></select>
  <select name="colours" multiple><option value="red" selected>Red</option><option value="blue">Blue</option>
    <option value="green" selected>Green</option></select>
  <textarea name="description">
Bright &lt;and&gt; sturdy.</textarea>
  <input type="submit" name="_save" value="Save">
</form>
"""


class AdminFormDataTests(SimpleTestCase):
    def test_reads_what_a_browser_would_post(self):
        self.assertEqual(admin_form_data(PAGE), {
            "csrfmiddlewaretoken": "token",
            "name": "Desk & Lamp",
            "price": "100.00",
            "is_active": "on",
            "tags": ["a", "b"],
            "size": "M",
            "category": "3",
            "shop": "7",
            "colours": ["red", "green"],
            "description": "Bright <and> sturdy.",
        })

    def test_reads_a_named_form(self):
        self.assertEqual(admin_form_data(PAGE, form_id="changelist-search"), {"q": "ignored"})


class TransitionTableTests(TransitionTableMixin, SimpleTestCase):
    def test_tries_every_action_from_every_start(self):
        tried = []

        def attempt(start, action):
            tried.append((start, action))
            return start == "A"

        self.assert_transition_table(["A", "B"], {"go": {"A"}, "stop": {"A"}}, attempt)
        self.assertEqual(tried, [("A", "go"), ("B", "go"), ("A", "stop"), ("B", "stop")])
