"""Settings package for the MiniShop backend.

The single ``config/settings.py`` was split here so the test suite can run under
settings of its own:

* :mod:`config.settings.base` — everything shared by every environment.
* :mod:`config.settings.dev`  — local development; the historical default.
* :mod:`config.settings.test` — the automated test suite, tuned for wall clock.

``manage.py``, ``wsgi.py`` and ``asgi.py`` default to ``config.settings.dev``.
Pick another with ``DJANGO_SETTINGS_MODULE`` or ``manage.py --settings=``.

This module is intentionally empty: it is imported before whichever environment
module is selected, so anything it defined would apply to all of them.
"""
