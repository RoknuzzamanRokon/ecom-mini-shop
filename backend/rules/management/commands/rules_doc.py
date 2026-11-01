"""
Writes docs/BUSINESS_RULES.md from rules/registry.py, so the written copy of
the rules cannot drift from the code. `--check` only compares, and fails when
the file is out of date (rules.tests runs it).
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rules.registry import CHECKS, GROUPS

DOC_PATH = Path(settings.BASE_DIR).parent / "docs" / "BUSINESS_RULES.md"


def _number(value: int) -> str:
    return f"{value:,}"


def render() -> str:
    lines = [
        "# Business rules",
        "",
        "Generated from `backend/rules/registry.py` by `python manage.py rules_doc`;",
        "do not edit by hand. The values below are the defaults. The current",
        "values, and who changed them last, are on the Console Rules page",
        "(`/admin/rules`), the only place they change. Every change there needs a",
        "reason and writes a `RULE_CHANGED` audit row.",
        "",
        "A change never rewrites what already happened: point lots keep their",
        "dates, running listing periods keep their end dates, and each onboarding",
        "keeps what its seller was given.",
    ]
    for group in GROUPS:
        lines += [
            "",
            f"## {group.title}",
            "",
            "| Key | Rule | Default | Range | Applies to | Takes effect |",
            "|---|---|---|---|---|---|",
        ]
        for rule in group.rules:
            lines.append(
                f"| `{rule.key}` | **{rule.label}.** {rule.help} | {_number(rule.default)} {rule.unit} "
                f"| {_number(rule.minimum)}–{_number(rule.maximum)} | {rule.applies_to} | {rule.takes_effect} |"
            )
        if group.fixed:
            lines += ["", "Fixed in code:", ""]
            lines += [f"- {text}" for text in group.fixed]
    lines += ["", "## Checks between rules", ""]
    lines += [f"- {check.description}" for check in CHECKS]
    return "\n".join(lines) + "\n"


class Command(BaseCommand):
    help = "Write docs/BUSINESS_RULES.md from rules/registry.py (--check only compares)."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Fail when the file is out of date; write nothing.")

    def handle(self, *args, **options):
        text = render()
        current = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else None
        if options["check"]:
            if current != text:
                raise CommandError(f"{DOC_PATH.name} is out of date: run `python manage.py rules_doc`.")
            self.stdout.write(f"{DOC_PATH.name} is up to date.")
            return
        if current == text:
            self.stdout.write(f"{DOC_PATH.name} is already up to date.")
            return
        DOC_PATH.write_text(text, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {DOC_PATH}."))
