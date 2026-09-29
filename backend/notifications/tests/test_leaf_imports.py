"""
The dependency rule (docs/NOTIFICATION_SYSTEM.md §4.3): domain apps import the
publisher and the event-name constants, so those modules must not import a
project app back. The publisher joins LEAF_MODULES when it exists (Task 4).
"""
import ast
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

APP_DIR = Path(__file__).resolve().parent.parent
LEAF_MODULES = ("models.py", "categories.py", "events.py")


def imported_top_level_modules(path):
    """Top-level names of every absolute import in the file."""
    tree = ast.parse(path.read_text(), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


class LeafImportTests(SimpleTestCase):
    def project_packages(self):
        # The virtualenv lives inside backend/, so installed packages are
        # excluded explicitly.
        base = Path(settings.BASE_DIR).resolve()
        venv = Path(sys.prefix).resolve()
        return {
            config.name.split(".")[0]
            for config in apps.get_app_configs()
            if Path(config.path).resolve().is_relative_to(base)
            and not Path(config.path).resolve().is_relative_to(venv)
        } | {"config"}

    def test_project_apps_are_detected(self):
        packages = self.project_packages()
        self.assertTrue({"shop", "rbac", "audit", "notifications"} <= packages)
        self.assertNotIn("django", packages)

    def test_leaf_modules_import_no_other_project_app(self):
        forbidden = self.project_packages() - {"notifications"}
        for module in LEAF_MODULES:
            with self.subTest(module=module):
                imported = imported_top_level_modules(APP_DIR / module)
                self.assertFalse(imported & forbidden, f"{module} imports {sorted(imported & forbidden)}")
