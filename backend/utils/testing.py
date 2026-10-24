"""
Helpers the regression tests share (TASK-043). Each one first grew inside a
single task's tests; they live here so the next test can use them as is.

- run_together, meeting_point: race real requests on MySQL, each on its own
  thread and connection (TransactionTestCase only).
- locked_tables, share_lock_states: which tables a call locks FOR UPDATE,
  and which rows a second connection could still share-lock meanwhile.
- QueryCountMixin: a list page costs the same queries however many rows it
  shows, within a fixed budget, and counts related rows without loading them.
- admin_form_data, ChangeFormLockdownMixin: post a Django-admin form exactly
  as the browser would, with crafted values, and check what was kept.
- invoice_texts: the text each Paragraph of an order invoice draws.
- TransitionTableMixin: try every action from every status and compare the
  outcome with a table.
"""

import re
import threading
from html.parser import HTMLParser
from unittest import mock

from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext


# ---------------------------------------------------------------------------
# Concurrency (MySQL, TransactionTestCase)
# ---------------------------------------------------------------------------

def run_together(*calls, timeout=90):
    """Runs each call on its own thread and connection; returns what they raised."""
    errors = []

    def run(call):
        try:
            call()
        except Exception as exc:  # surfaced through the return value
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
    return errors


def meeting_point(target, attribute, parties=2, wait=3):
    """
    Patches target.attribute so each caller first waits up to `wait` seconds
    for the others: racing requests reach that write together, which is how
    an unguarded check-then-write fails. Code that locks before that point
    holds the others back, the wait runs out, and each goes on in turn.
    """
    barrier = threading.Barrier(parties)
    original = getattr(target, attribute)

    def waiting(*args, **kwargs):
        try:
            barrier.wait(wait)
        except threading.BrokenBarrierError:
            pass  # another request is held at a lock before this point
        return original(*args, **kwargs)

    return mock.patch.object(target, attribute, waiting)


def locked_tables(call):
    """The tables `call` reads FOR UPDATE, in the order it locks them."""
    with CaptureQueriesContext(connection) as queries:
        call()
    return [
        re.search(r"FROM `(\w+)`", query["sql"]).group(1)
        for query in queries
        if query["sql"].rstrip().endswith("FOR UPDATE")
    ]


def share_lock_states(targets, timeout=60):
    """
    {label: "free" | "locked"} for each (model, pk) in `targets`, seen from a
    second connection that tries a shared lock, NOWAIT. That is what another
    request needs to read a row and insert rows pointing at it, so only an
    exclusive lock held by the caller's transaction reads "locked". (An
    exclusive probe would also report the shared locks a foreign-key insert
    takes on its parent rows.)
    """
    seen = {}

    def probe():
        try:
            with connection.cursor() as cursor:
                for label, (model, pk) in targets.items():
                    table = connection.ops.quote_name(model._meta.db_table)
                    try:
                        with transaction.atomic():
                            cursor.execute(f"SELECT 1 FROM {table} WHERE id = %s FOR SHARE NOWAIT", [pk])
                        seen[label] = "free"
                    except DatabaseError:
                        seen[label] = "locked"
        finally:
            connection.close()

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join(timeout)
    return seen


# ---------------------------------------------------------------------------
# Query counts
# ---------------------------------------------------------------------------

def page_rows(response):
    """The rows of a paginated (`results`), cart-shaped (`items`) or plain list response."""
    data = response.data
    if isinstance(data, list):
        return data
    return data["results"] if "results" in data else data["items"]


class QueryCountMixin:
    """For APITestCase: list pages must not cost a query per row."""

    def assert_constant_queries(self, url, add_rows, user, budget=None):
        """
        Adding rows to the page adds no queries to it, and the page stays
        within `budget` queries when one is given. Returns the second response.
        """
        self.client.force_authenticate(user=user)
        self.client.get(url)  # warm per-process caches out of the count
        with CaptureQueriesContext(connection) as baseline:
            before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        if budget is not None:
            self.assertLessEqual(
                len(baseline), budget,
                f"{url} now takes {len(baseline)} queries, over its budget of {budget}:\n"
                + "\n".join(query["sql"] for query in baseline),
            )
        add_rows()
        with self.assertNumQueries(len(baseline)):
            after = self.client.get(url)
        self.assertEqual(after.status_code, 200)
        self.assertGreater(len(page_rows(after)), len(page_rows(before)))
        return after

    def assert_rows_not_loaded(self, url, table, user):
        """The page counts `table` inside its own query instead of fetching its rows."""
        self.client.force_authenticate(user=user)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)
        fetched = [query["sql"] for query in queries if re.search(rf"\bFROM `{table}`", query["sql"])]
        self.assertEqual(fetched, [])


# ---------------------------------------------------------------------------
# Django admin forms
# ---------------------------------------------------------------------------

class _FormParser(HTMLParser):
    """Collects what a browser would submit for one <form>."""

    def __init__(self, form_id):
        super().__init__(convert_charrefs=True)
        self.form_id = form_id
        self.in_form = False
        self.fields = []  # (name, value) in document order
        self.select = None  # [name, multiple, chosen values, first option value]
        self.option = None  # [value or None, selected, text]
        self.textarea = None  # [name, text]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            form_id = attrs.get("id") or ""
            self.in_form = form_id == self.form_id if self.form_id else form_id.endswith("_form")
            return
        if not self.in_form or "disabled" in attrs:
            return
        name = attrs.get("name")
        if tag == "input" and name:
            kind = (attrs.get("type") or "text").lower()
            if kind in ("submit", "button", "image", "reset", "file"):
                return
            if kind in ("checkbox", "radio"):
                if "checked" in attrs:
                    self.fields.append((name, attrs.get("value", "on")))
                return
            self.fields.append((name, attrs.get("value") or ""))
        elif tag == "select" and name:
            self.select = [name, "multiple" in attrs, [], None]
        elif tag == "option" and self.select is not None:
            self.option = [attrs.get("value"), "selected" in attrs, ""]
        elif tag == "textarea" and name:
            self.textarea = [name, ""]

    def handle_data(self, data):
        if self.option is not None:
            self.option[2] += data
        if self.textarea is not None:
            self.textarea[1] += data

    def _close_option(self):
        if self.option is None:
            return
        value = self.option[0] if self.option[0] is not None else self.option[2].strip()
        if self.select[3] is None:
            self.select[3] = value
        if self.option[1]:
            self.select[2].append(value)
        self.option = None

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False
        elif tag == "option":
            self._close_option()
        elif tag == "select" and self.select is not None:
            self._close_option()
            name, multiple, chosen, first = self.select
            if multiple:
                self.fields.extend((name, value) for value in chosen)
            elif chosen or first is not None:
                self.fields.append((name, chosen[-1] if chosen else first))
            self.select = None
        elif tag == "textarea" and self.textarea is not None:
            name, text = self.textarea
            # A newline right after <textarea> is not part of the value.
            self.fields.append((name, text[1:] if text.startswith("\n") else text))
            self.textarea = None


def admin_form_data(html, form_id=None):
    """
    The data a browser would post from the page's form: the admin's change
    or add form (id ending in "_form") unless `form_id` names another. Text,
    hidden and other inputs, checked boxes and radios, selected options and
    textareas, inline formset management fields included; disabled controls
    and buttons left out. A field with several values maps to a list.
    """
    parser = _FormParser(form_id)
    parser.feed(html)
    data = {}
    for name, value in parser.fields:
        if name in data:
            data[name] = (data[name] if isinstance(data[name], list) else [data[name]]) + [value]
        else:
            data[name] = value
    return data


class ChangeFormLockdownMixin:
    """
    For admin change-form lockdown tests (TASK-006, Known #22): post the
    form exactly as rendered, with crafted values for the fields it must not
    change, and check what was stored.
    """

    def change_form_data(self, url, **overrides):
        """The form at `url` as the browser would post it ("Save"), with `overrides` applied."""
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = admin_form_data(response.content.decode())
        data["_save"] = "Save"
        data.update(overrides)
        return data

    @staticmethod
    def _attname(obj, key):
        # A split widget posts "<field>_0" and "<field>_1".
        name = re.sub(r"_\d+$", "", key) if not hasattr(obj, key) else key
        return obj._meta.get_field(name).attname

    def assert_change_form_keeps(self, obj, url, crafted, harmless):
        """
        Posts the change form of `obj` with `crafted` values (post key ->
        value) for fields it must leave alone and `harmless` ones it may
        change. The harmless edit must be saved, which proves the form was
        accepted rather than rejected, and every crafted field must keep its
        stored value. Returns the POST response.
        """
        attnames = {self._attname(obj, key) for key in crafted}
        before = {attname: getattr(obj, attname) for attname in attnames}
        response = self.client.post(url, self.change_form_data(url, **crafted, **harmless))
        errors = getattr(response, "context", None) and response.context.get("errors")
        self.assertEqual(response.status_code, 302, f"the form was rejected: {errors}")

        obj.refresh_from_db()
        for key, value in harmless.items():
            self.assertEqual(str(getattr(obj, self._attname(obj, key))), value, key)
        for attname, value in before.items():
            self.assertEqual(getattr(obj, attname), value, f"{attname} was changed through the form")
        return response


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

def invoice_texts(order):
    """
    (pdf bytes, [text of each Paragraph]) for the order's invoice. The text
    is read after ReportLab has parsed the Paragraph markup, which is exactly
    what gets drawn, so no PDF text extractor is needed.
    """
    from reportlab.platypus import Paragraph

    from shop import invoice

    texts = []

    def recording_paragraph(*args, **kwargs):
        paragraph = Paragraph(*args, **kwargs)
        # Read before layout, which reshapes the fragments.
        texts.append("".join(getattr(frag, "text", "") for frag in paragraph.frags))
        return paragraph

    with mock.patch("shop.invoice.Paragraph", side_effect=recording_paragraph):
        pdf = invoice.build_order_invoice_pdf(order)
    return pdf, texts


# ---------------------------------------------------------------------------
# State machines
# ---------------------------------------------------------------------------

class TransitionTableMixin:
    """Table-driven state-machine tests."""

    def assert_transition_table(self, starts, allowed, attempt):
        """
        `allowed` maps each action (or target status) to the statuses it may
        start from. `attempt(start, action)` tries it on a fresh object in
        status `start` and returns True when it went through, False when it
        was refused; it may assert more about either outcome. Every action is
        tried from every start, each pair in its own subTest.
        """
        for action, sources in allowed.items():
            for start in starts:
                with self.subTest(action=action, start=start):
                    self.assertEqual(
                        attempt(start, action), start in sources,
                        f"{action} from {start} should be {'allowed' if start in sources else 'refused'}",
                    )
