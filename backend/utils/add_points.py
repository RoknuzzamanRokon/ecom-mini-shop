"""
Superuser point tools.

Staff can only give sellers points their own wallet holds (see
PointService.adjust_points), so every point starts here: a superuser creates
points in their own wallet, and can then hand some of them to a staff member.

Run from backend/ with the venv active:

    python utils/add_points.py                     # add POINT points to rokon's wallet
    python utils/add_points.py 500                 # add 500 instead
    python utils/add_points.py 200 --to finance1   # move 200 from rokon's wallet to finance1's

Or from `python manage.py shell`:

    from utils.add_points import add_points, give_points_to_staff
    add_points("1000")
    give_points_to_staff("200", "finance1")

The password is asked for at a prompt, unless MINISHOP_SUPERUSER_PASSWORD is
set or --password is passed. This file never stores it.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

POINT = "1000"
USERNAME = "rokon"

BACKEND_DIR = Path(__file__).resolve().parent.parent


def parse_points(point) -> int:
    """'1000' or 1000 -> 1000. Anything but a positive whole number is refused."""
    text = str(point).strip()
    if not text.isdecimal() or int(text) <= 0:
        raise ValueError(f"Points must be a positive whole number, got {point!r}.")
    return int(text)


def _authenticate_superuser(username, password):
    from django.contrib.auth import authenticate

    if password is None:
        password = os.environ.get("MINISHOP_SUPERUSER_PASSWORD") or getpass.getpass(
            f"Password for {username}: "
        )
    user = authenticate(username=username, password=password)
    if user is None or not user.is_superuser:
        raise PermissionError("Wrong username or password, or the account is not a superuser.")
    return user


def add_points(point=POINT, username=USERNAME, password=None, reason="Added with utils/add_points.py"):
    """Creates `point` new points in the superuser's own wallet. Returns the new balance."""
    from django.db import transaction

    from audit.services import AuditService
    from points.services import PointService

    amount = parse_points(point)
    user = _authenticate_superuser(username, password)

    with transaction.atomic():
        txn = PointService.mint_points(user, amount, reason)
        AuditService.log(
            action="SUPERUSER_POINTS_MINT",
            target=txn,
            actor=user,
            reason=reason,
            previous_state={"balance": txn.balance_before},
            new_state={"balance": txn.balance_after},
            metadata={"amount": txn.amount, "staff_point_transaction_id": txn.pk},
        )
    return txn.balance_after


def give_points_to_staff(
    point,
    to_username,
    username=USERNAME,
    password=None,
    reason="Sent with utils/add_points.py",
):
    """
    Moves `point` points from the superuser's wallet to a staff member's, so
    that staff member can credit sellers. Returns (superuser balance, their balance).
    """
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from audit.services import AuditService
    from points.services import PointService

    amount = parse_points(point)
    sender = _authenticate_superuser(username, password)
    recipient = get_user_model().objects.filter(username=to_username).first()
    if recipient is None:
        raise LookupError(f"No user named {to_username!r}.")

    with transaction.atomic():
        outgoing, incoming = PointService.transfer_to_staff(sender, recipient, amount, reason)
        AuditService.log(
            action="SUPERUSER_POINTS_TRANSFER",
            target=incoming,
            actor=sender,
            reason=reason,
            metadata={
                "amount": amount,
                "recipient": recipient.username,
                "sender_balance_after": outgoing.balance_after,
                "recipient_balance_after": incoming.balance_after,
                "staff_point_transaction_ids": [outgoing.pk, incoming.pk],
            },
        )
    return outgoing.balance_after, incoming.balance_after


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Add points to a superuser's wallet, or pass them to staff.")
    parser.add_argument("point", nargs="?", default=POINT, help=f"how many points (default {POINT})")
    parser.add_argument("--to", metavar="USERNAME", help="move the points to this staff member instead of creating new ones")
    parser.add_argument("--username", default=USERNAME, help=f"superuser to act as (default {USERNAME})")
    parser.add_argument("--password", help="skip the prompt; note it stays in your shell history")
    parser.add_argument("--reason", help="recorded in the ledger and the audit log")
    args = parser.parse_args(argv)

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()
    from points.services import PointError

    extra = {"reason": args.reason} if args.reason else {}
    try:
        if args.to:
            mine, theirs = give_points_to_staff(
                args.point, args.to, username=args.username, password=args.password, **extra
            )
            print(f"Sent {parse_points(args.point)} points to {args.to}. "
                  f"{args.username}: {mine} points, {args.to}: {theirs} points.")
        else:
            balance = add_points(args.point, username=args.username, password=args.password, **extra)
            print(f"Added {parse_points(args.point)} points. {args.username}'s wallet: {balance} points.")
    except (ValueError, PermissionError, LookupError, PointError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
