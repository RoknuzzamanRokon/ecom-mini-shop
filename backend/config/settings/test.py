"""Settings for the automated test suite.

    python manage.py test --settings=config.settings.test --parallel --keepdb --noinput

Application behaviour is identical to :mod:`config.settings.dev` — same apps,
same middleware, same DRF/JWT configuration, same MySQL engine. Only the cost of
exercising it changes. Nothing here may alter what the code under test does; if
a change would, it belongs in a test, not in this file.
"""

import os

from .base import *  # noqa: F401,F403
from .base import database_config_from_url

# Django's test runner forces ``DEBUG = False`` anyway (``setup_test_environment``);
# stating it here keeps the module honest about what the suite actually runs under.
DEBUG = False

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# --- Password hashing -------------------------------------------------------
# Django's default PBKDF2 work factor costs ~0.95s per hash on this machine, and
# the suite has 178 ``create_user`` / ``create_superuser`` call sites across 512
# test methods, most of them in ``setUp`` and so paid once per test. Worth ~13.6%
# of the suite's wall clock on its own. See config/settings/hashers.py for why
# this is a low-iteration PBKDF2 rather than the usual MD5 swap.
PASSWORD_HASHERS = ["config.settings.hashers.FastPBKDF2PasswordHasher"]

# --- Test database ----------------------------------------------------------
# Still MySQL, deliberately. The suite's concurrency tests rely on real
# ``SELECT ... FOR UPDATE`` row locking, which SQLite accepts and silently
# ignores — running them there would report green while testing nothing.
#
# ``TEST_DATABASE_URL`` lets a run point at a *different* MySQL from the one in
# ``DATABASE_URL`` — typically a local server instead of a remote one. That is
# the single biggest lever on this suite's wall clock: a query against the
# remote development database costs 54-167ms round-trip (measured 2026-09-18),
# against localhost roughly 0.2ms, and the suite is overwhelmingly
# round-trip-bound. Unset, the test database is derived from ``DATABASE_URL``
# exactly as before.
_test_database_url = os.environ.get("TEST_DATABASE_URL")
if _test_database_url:
    DATABASES = {"default": database_config_from_url(_test_database_url)}

# --- Parallelism ------------------------------------------------------------
# Test methods spend nearly all their wall clock blocked on database
# round-trips, not computing: measured CPU utilisation during a run is 5%.
# Blocked time overlaps further than core count allows, so a bare ``--parallel``
# deliberately oversubscribes the CPUs. Django reads this env var in
# ``get_max_test_processes()`` when ``--parallel`` is passed without a number; an
# explicit ``--parallel N``, or a ``DJANGO_TEST_PROCESSES`` already set in the
# environment, still wins.
#
# Full-suite measurements against the remote database: 8 workers 1158s,
# 16 workers 785s, 32 workers 610s. Returns diminish sharply because Django
# partitions parallel work by TestCase *class* (``partition_suite_by_case``), so
# the longest single class is a floor no worker count can beat — ~550s here, as
# ``shop.tests`` and ``sellers`` each take ~9 min run alone even with their own
# classes spread across workers.
#
# 4x cores is the compromise: it captures most of the available speed-up without
# the per-worker cloned database count getting out of hand, and it stays sane if
# TEST_DATABASE_URL points at a local server, where the workload becomes
# CPU-bound instead. Note each worker gets its own cloned test database
# (``test_<name>_1`` ...), created once and then reused by ``--keepdb``.
#
# Lower-case on purpose: Django does not read this as a setting, it reads the
# environment variable below.
_default_test_processes = 4 * (os.cpu_count() or 1)
os.environ.setdefault("DJANGO_TEST_PROCESSES", str(_default_test_processes))
