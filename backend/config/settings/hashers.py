"""Password hashers for the test settings only. Never used outside tests."""

from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """PBKDF2 with the work factor turned down, for the test suite only.

    Django 5.2 defaults to 1,200,000 iterations, measured at ~0.95s per hash on
    the current dev machine. The suite has 178 ``create_user`` /
    ``create_superuser`` call sites spread over 512 test methods, most of them in
    ``setUp`` and so paid once per test, and no test asserts anything about the
    cost of hashing. Worth ~13.6% of the suite's wall clock, measured on a serial
    29-test control subset (174.4s -> 150.7s with only this changed). Real, but
    not the main cost — that is database round-trip latency; see test.py.

    Subclassing PBKDF2 rather than swapping in Django's ``MD5PasswordHasher``
    (the usual recipe) is deliberate. The encoded hash keeps its
    ``pbkdf2_sha256$`` prefix, which is what keeps the credential-leak assertion
    in ``shop.test_staff_orders`` —
    ``test_staff_order_detail_exposes_operational_data_and_sanitizes_secrets``,
    which asserts ``assertNotIn("pbkdf2", raw_json.lower())`` — meaningful. Under
    an MD5 hasher a leaked hash would start ``md5$``, so that assertion would
    pass whether or not a hash had leaked.
    """

    iterations = 1
