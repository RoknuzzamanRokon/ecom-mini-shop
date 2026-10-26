"""
Bangladeshi mobile numbers as sign-in identifiers (rbac.LoginPhone).

Everything that reads a number typed by a person -- registration and every
sign-in form -- goes through normalize_phone(), so "01712-345678",
"+880 1712 345678" and "8801712345678" all name the same account.
"""
import re

#: Bengali digits typed on a Bangla keyboard read as their ASCII twins.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
#: Spaces, dashes, dots and brackets people put inside a number.
_SEPARATORS = re.compile(r"[\s\-.()]")
#: An operator prefix 013-019 and eight more digits, with or without the
#: country code 88.
_BD_MOBILE = re.compile(r"(?:\+?88)?(01[3-9][0-9]{8})")

INVALID_PHONE = "Enter a Bangladeshi mobile number, e.g. 01712345678."
PHONE_TAKEN = "A user with that phone number already exists."


def normalize_phone(value):
    """
    The E.164 form ("+8801712345678") of a Bangladeshi mobile number written
    any of the usual ways, or None when `value` is not one.
    """
    if not isinstance(value, str):
        return None
    compact = _SEPARATORS.sub("", value.translate(_BENGALI_DIGITS))
    match = _BD_MOBILE.fullmatch(compact)
    return f"+88{match.group(1)}" if match else None


def national_phone(number):
    """"+8801712345678" -> "01712345678", the way people in Bangladesh write it."""
    return number[3:] if number.startswith("+88") else number
