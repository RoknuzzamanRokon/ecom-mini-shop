"""Settings package for the MiniShop backend.

The single ``config/settings.py`` was split here so the test suite can run under
settings of its own:

* :mod:`config.settings.base` — everything shared by every environment.
* :mod:`config.settings.dev`  — local development; the historical default.
* :mod:`config.settings.test` — the automated test suite, tuned for wall clock.
* :mod:`config.settings.prod` — any deployment; every value from the environment.

``manage.py`` defaults to ``config.settings.dev``. ``wsgi.py`` and ``asgi.py``
have no default and refuse to start without ``DJANGO_SETTINGS_MODULE``.
Pick a module with ``DJANGO_SETTINGS_MODULE`` or ``manage.py --settings=``.

This module is intentionally empty: it is imported before whichever environment
module is selected, so anything it defined would apply to all of them.
"""
