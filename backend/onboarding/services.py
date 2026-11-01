"""
Field onboarding and the tokens it earns (see onboarding/models.py).

The onboarding steps reuse the platform's own services: the seller profile
comes from sellers.services.create_seller_profile, the shop from
ShopService.create_shop and each product from ProductService.create_product,
so every rule those enforce (the Limited Shop Owner caps, the product
creation fee, the audit rows) holds here too. The only difference is that
the shop and products may be added while the seller still awaits approval.

Corrections afterwards need the seller's consent: EditSessionService sends
them a code, and only an open session lets the onboarder edit. Tokens are
cashed through TokenService.request_payout, which an admin accepts or rejects.
"""
import logging
import secrets
from datetime import timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from audit.services import AuditService
from notifications import events
from notifications.publisher import publish
from points.models import PointTransaction, SellerPointPolicy, StaffWallet
from points.services import PointService
from rbac.models import StartingPassword
from rbac.serializers import create_login_account, create_login_phone
from sellers.models import SellerProfile
from sellers.services import approve_seller, create_seller_profile
from shop.models import Product
from shop.services import ProductService
from shops.models import Shop
from shops.services import ShopService
from .models import (
    EditSession,
    OnboardingSettings,
    SellerOnboarding,
    TokenPayoutRequest,
    TokenTransaction,
    TokenWallet,
)

logger = logging.getLogger(__name__)

#: reference_type on the point ledger rows an onboarding writes.
POINTS_REFERENCE = "SELLER_ONBOARDING"
#: reference_type on the ledger rows of points an onboarder sells later.
POINT_SALE_REFERENCE = "POINT_SALE"


#: Seller states in which the onboarder may still correct what they opened.
EDITABLE_SELLER_STATUSES = SellerProfile.AWAITING_APPROVAL_STATUSES + (
    SellerProfile.STATUS_APPROVED,
    SellerProfile.STATUS_ACTIVE,
)
#: The least time between two codes for the same seller.
CODE_RESEND_SECONDS = 60
EDIT_CODE_SALT = "onboarding.EditSession.code"


class OnboardingError(Exception):
    """An onboarding step the seller's current state does not allow."""


class EditSessionError(OnboardingError):
    """A code request or code entry the session's state refuses."""


class EditCodeTooSoon(EditSessionError):
    def __init__(self, wait_seconds: int):
        super().__init__(f"A code was just sent. Ask for a new one in {wait_seconds} seconds.")
        self.wait_seconds = wait_seconds


class EditSessionRequired(OnboardingError):
    """An edit without an open session: the seller has not given their code."""


class PayoutError(OnboardingError):
    """A payout request, or a decision on one, its state does not allow."""


def clock_text(moment) -> str:
    """A time as the onboarder reads it, in the business time zone ("14:35")."""
    return moment.astimezone(ZoneInfo(settings.BUSINESS_TIME_ZONE)).strftime("%H:%M")


class TokenService:
    """Earning and taking back tokens. Every movement is one TokenTransaction."""

    @staticmethod
    def get_balance(user) -> int:
        return TokenWallet.objects.filter(user=user).values_list("balance", flat=True).first() or 0

    @staticmethod
    def _lock_wallet(user) -> TokenWallet:
        """Must be called inside transaction.atomic(); the lock lasts until it commits."""
        wallet, _ = TokenWallet.objects.select_for_update().get_or_create(user=user, defaults={"balance": 0})
        return wallet

    @staticmethod
    def _move(wallet, amount: int, transaction_type: str, reason: str, seller, actor, outgoing: bool,
              payout_request=None):
        balance_before = wallet.balance
        wallet.balance = balance_before - amount if outgoing else balance_before + amount
        wallet.save(update_fields=["balance", "updated_at"])
        return TokenTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reason=reason,
            seller=seller,
            payout_request=payout_request,
            actor=actor,
        )

    @classmethod
    def earn(cls, user, amount: int, seller, actor, reason: str) -> Optional[TokenTransaction]:
        """Adds `amount` tokens to `user`'s wallet; None when `amount` is 0."""
        if amount <= 0:
            return None
        with transaction.atomic():
            return cls._move(
                cls._lock_wallet(user), amount, TokenTransaction.TYPE_EARNED, reason, seller, actor, outgoing=False
            )

    @classmethod
    def take_back(cls, user, amount: int, seller, actor, reason: str) -> int:
        """
        Takes up to `amount` tokens out of `user`'s wallet and returns how
        many it took: fewer only if the wallet holds fewer, which happens once
        tokens are held for or paid out through a payout request.
        """
        if amount <= 0:
            return 0
        with transaction.atomic():
            wallet = cls._lock_wallet(user)
            taken = min(amount, wallet.balance)
            if taken:
                cls._move(wallet, taken, TokenTransaction.TYPE_TAKEN_BACK, reason, seller, actor, outgoing=True)
            return taken

    # -- Payouts --------------------------------------------------------------

    @staticmethod
    def pending_payout(user) -> Optional[TokenPayoutRequest]:
        return TokenPayoutRequest.objects.filter(requested_by=user, status=TokenPayoutRequest.STATUS_PENDING).first()

    @classmethod
    def request_payout(cls, user, tokens: int, note: str = "", ip_address=None) -> TokenPayoutRequest:
        """
        Holds `tokens` of `user`'s tokens on a new pending request for real
        payment, valued at OnboardingSettings.taka_per_token. One pending
        request at a time, checked under the wallet's lock.
        """
        config = OnboardingSettings.current()
        if tokens < 1:
            raise PayoutError("Ask for at least 1 token.")
        with transaction.atomic():
            wallet = cls._lock_wallet(user)
            if cls.pending_payout(user) is not None:
                raise PayoutError("You already have a payout request waiting. Cancel it, or wait for the decision.")
            if tokens > wallet.balance:
                raise PayoutError(f"You hold {wallet.balance} tokens, so ask for {wallet.balance} at most.")
            payout = TokenPayoutRequest.objects.create(
                requested_by=user,
                tokens=tokens,
                taka_per_token=config.taka_per_token,
                amount_taka=tokens * config.taka_per_token,
                note=note.strip(),
            )
            cls._move(
                wallet, tokens, TokenTransaction.TYPE_PAYOUT_HELD, f"Held for payout request #{payout.pk}",
                seller=None, actor=user, outgoing=True, payout_request=payout,
            )
            publish(
                events.TOKEN_PAYOUT_REQUESTED,
                payload={
                    "payout_id": payout.pk,
                    "requested_by": user.username,
                    "tokens": payout.tokens,
                    "amount_taka": payout.amount_taka,
                },
                aggregate=payout,
                actor=user,
                idempotency_key=f"token_payout_requested:{payout.pk}",
            )
            AuditService.log(
                action="TOKEN_PAYOUT_REQUESTED",
                target=payout,
                actor=user,
                new_state={"status": payout.status, "tokens": payout.tokens, "amount_taka": payout.amount_taka},
                metadata={"taka_per_token": payout.taka_per_token, "wallet_balance": wallet.balance},
                ip_address=ip_address,
            )
        return payout

    @classmethod
    def _lock_pending(cls, payout_id) -> TokenPayoutRequest:
        payout = TokenPayoutRequest.objects.select_for_update().select_related("requested_by").get(pk=payout_id)
        if payout.status != TokenPayoutRequest.STATUS_PENDING:
            raise PayoutError(f"This payout request is already {payout.get_status_display().lower()}.")
        return payout

    @classmethod
    def _release(cls, payout, actor, reason: str):
        cls._move(
            cls._lock_wallet(payout.requested_by), payout.tokens, TokenTransaction.TYPE_PAYOUT_RELEASED, reason,
            seller=None, actor=actor, outgoing=False, payout_request=payout,
        )

    @classmethod
    def _decide(cls, payout, decider, status_value: str, note: str, ip_address, audit_action: str):
        previous_status = payout.status
        payout.status = status_value
        payout.decided_by = decider if status_value != TokenPayoutRequest.STATUS_CANCELLED else None
        payout.decided_at = timezone.now()
        payout.decision_note = note
        payout.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
        if status_value != TokenPayoutRequest.STATUS_CANCELLED:
            publish(
                events.TOKEN_PAYOUT_DECIDED,
                payload={
                    "payout_id": payout.pk,
                    "requested_by_id": payout.requested_by_id,
                    "status": payout.status,
                    "tokens": payout.tokens,
                    "amount_taka": payout.amount_taka,
                    "note": note,
                },
                aggregate=payout,
                actor=decider,
                idempotency_key=f"token_payout_decided:{payout.pk}",
            )
        AuditService.log(
            action=audit_action,
            target=payout,
            actor=decider,
            reason=note,
            previous_state={"status": previous_status},
            new_state={"status": payout.status},
            metadata={
                "tokens": payout.tokens,
                "amount_taka": payout.amount_taka,
                "requested_by": payout.requested_by.username,
            },
            ip_address=ip_address,
        )
        return payout

    @classmethod
    def cancel_payout(cls, user, payout_id, ip_address=None) -> TokenPayoutRequest:
        """The onboarder withdraws their pending request; the held tokens come back."""
        with transaction.atomic():
            payout = cls._lock_pending(payout_id)
            if payout.requested_by_id != user.pk:
                raise PayoutError("Only the person who asked can cancel a payout request.")
            cls._release(payout, user, f"Payout request #{payout.pk} cancelled")
            return cls._decide(
                payout, user, TokenPayoutRequest.STATUS_CANCELLED, "", ip_address, "TOKEN_PAYOUT_CANCELLED"
            )

    @classmethod
    def accept_payout(cls, admin, payout_id, note: str = "", ip_address=None) -> TokenPayoutRequest:
        """An admin accepts a pending request: its tokens move to the admin's wallet."""
        with transaction.atomic():
            payout = cls._lock_pending(payout_id)
            if payout.requested_by_id == admin.pk:
                raise PayoutError("Someone else has to settle your own payout request.")
            cls._move(
                cls._lock_wallet(admin), payout.tokens, TokenTransaction.TYPE_PAYOUT_RECEIVED,
                f"Payout request #{payout.pk} from {payout.requested_by.username}",
                seller=None, actor=admin, outgoing=False, payout_request=payout,
            )
            return cls._decide(
                payout, admin, TokenPayoutRequest.STATUS_ACCEPTED, note.strip(), ip_address, "TOKEN_PAYOUT_ACCEPTED"
            )

    @classmethod
    def reject_payout(cls, admin, payout_id, reason: str, ip_address=None) -> TokenPayoutRequest:
        """An admin rejects a pending request; the held tokens go back to the onboarder."""
        reason = reason.strip()
        if not reason:
            raise PayoutError("A reason is required to reject a payout request.")
        with transaction.atomic():
            payout = cls._lock_pending(payout_id)
            if payout.requested_by_id == admin.pk:
                raise PayoutError("Someone else has to settle your own payout request.")
            cls._release(payout, admin, f"Payout request #{payout.pk} rejected")
            return cls._decide(
                payout, admin, TokenPayoutRequest.STATUS_REJECTED, reason, ip_address, "TOKEN_PAYOUT_REJECTED"
            )


class EditSessionService:
    """
    The seller's code that lets their onboarder correct the seller, its shops
    and the products the onboarder added (EditSession).
    """

    @staticmethod
    def code_digest(seller_id: int, code: str) -> str:
        return salted_hmac(EDIT_CODE_SALT, f"{seller_id}:{code}", algorithm="sha256").hexdigest()

    @staticmethod
    def latest(seller, onboarder=None):
        sessions = EditSession.objects.filter(seller=seller)
        if onboarder is not None:
            sessions = sessions.filter(onboarder=onboarder)
        return sessions.order_by("-created_at", "-pk").first()

    @staticmethod
    def describe(session, now=None) -> dict:
        """GET .../edit-session/: the state and its times, for the onboarder's screen."""
        now = now or timezone.now()
        if session is None:
            return {"state": "none", "code_expires_at": None, "expires_at": None, "attempts_left": None}
        state = session.state(now)
        return {
            "state": state,
            "code_expires_at": session.code_expires_at if state == "waiting" else None,
            "expires_at": session.expires_at if state == "open" else None,
            "attempts_left": EditSession.MAX_CODE_ATTEMPTS - session.failed_attempts if state == "waiting" else None,
        }

    @staticmethod
    def _check_seller(seller):
        if seller.status not in EDITABLE_SELLER_STATUSES:
            raise EditSessionError(
                f"{seller.business_name} is {seller.get_status_display().lower()}, so it can no longer be edited here."
            )

    @classmethod
    def request_code(cls, onboarder, seller, ip_address=None) -> EditSession:
        """
        Sends a new code to the seller's account (onboarding.edit_code). A code
        still waiting is replaced; an open session has to be closed first.
        """
        cls._check_seller(seller)
        config = OnboardingSettings.current()
        now = timezone.now()
        with transaction.atomic():
            # One request at a time per seller.
            SellerProfile.objects.select_for_update().filter(pk=seller.pk).first()
            latest = cls.latest(seller)
            if latest is not None and latest.is_open(now):
                raise EditSessionError(
                    f"Editing is already open until {clock_text(latest.expires_at)}. Close it to ask for a new code."
                )
            if latest is not None:
                waited = (now - latest.created_at).total_seconds()
                if waited < CODE_RESEND_SECONDS:
                    raise EditCodeTooSoon(int(CODE_RESEND_SECONDS - waited) + 1)
                if latest.is_waiting(now):
                    latest.closed_at = now
                    latest.save(update_fields=["closed_at"])

            code = f"{secrets.randbelow(1_000_000):06d}"
            session = EditSession.objects.create(
                seller=seller,
                onboarder=onboarder,
                code_digest=cls.code_digest(seller.pk, code),
                code_expires_at=now + timedelta(minutes=config.edit_code_minutes),
            )
            publish(
                events.ONBOARDING_EDIT_CODE,
                payload={
                    "seller_id": seller.pk,
                    "business_name": seller.business_name,
                    "code": code,
                    "onboarder_name": onboarder.get_full_name() or onboarder.username,
                    "valid_minutes": config.edit_code_minutes,
                    "edit_minutes": config.edit_window_minutes,
                },
                aggregate=seller,
                actor=onboarder,
                idempotency_key=f"onboarding_edit_code:{session.pk}",
            )
            AuditService.log(
                action="ONBOARDING_EDIT_CODE_SENT",
                target=seller,
                actor=onboarder,
                seller=seller,
                metadata={"edit_session_id": session.pk, "code_expires_at": session.code_expires_at.isoformat()},
                ip_address=ip_address,
            )
        return session

    @classmethod
    def verify(cls, onboarder, seller, code: str, ip_address=None) -> EditSession:
        """
        Opens the session when `code` is the seller's code, for
        OnboardingSettings.edit_window_minutes. A wrong code counts as a try,
        and MAX_CODE_ATTEMPTS of them void it; the count is kept even though
        the answer is an error.
        """
        cls._check_seller(seller)
        now = timezone.now()
        with transaction.atomic():
            session = (
                EditSession.objects.select_for_update()
                .filter(seller=seller, onboarder=onboarder)
                .order_by("-created_at", "-pk")
                .first()
            )
            if session is not None and session.is_open(now):
                return session
            if session is None or session.closed_at is not None or session.opened_at is not None:
                raise EditSessionError("No code is waiting for this seller. Ask for a new one.")
            if session.failed_attempts >= EditSession.MAX_CODE_ATTEMPTS:
                raise EditSessionError("That code was entered wrong too many times. Ask for a new one.")
            if session.code_expires_at <= now:
                raise EditSessionError("That code has expired. Ask for a new one.")

            if constant_time_compare(session.code_digest, cls.code_digest(seller.pk, code.strip())):
                session.opened_at = now
                session.expires_at = now + timedelta(minutes=OnboardingSettings.current().edit_window_minutes)
                session.save(update_fields=["opened_at", "expires_at"])
                AuditService.log(
                    action="ONBOARDING_EDIT_SESSION_OPENED",
                    target=seller,
                    actor=onboarder,
                    seller=seller,
                    metadata={"edit_session_id": session.pk, "expires_at": session.expires_at.isoformat()},
                    ip_address=ip_address,
                )
                return session

            session.failed_attempts += 1
            if session.failed_attempts >= EditSession.MAX_CODE_ATTEMPTS:
                session.closed_at = now
            session.save(update_fields=["failed_attempts", "closed_at"])
            left = EditSession.MAX_CODE_ATTEMPTS - session.failed_attempts
        if left:
            raise EditSessionError(f"Wrong code. {left} {'try' if left == 1 else 'tries'} left.")
        raise EditSessionError("Wrong code too many times. Ask for a new one.")

    @classmethod
    def close(cls, onboarder, seller) -> Optional[EditSession]:
        """Ends a waiting or open session early; None when there is none."""
        now = timezone.now()
        with transaction.atomic():
            session = (
                EditSession.objects.select_for_update()
                .filter(seller=seller, onboarder=onboarder, closed_at__isnull=True)
                .order_by("-created_at", "-pk")
                .first()
            )
            if session is None or session.state(now) == "ended":
                return None
            session.closed_at = now
            session.save(update_fields=["closed_at"])
        return session

    @classmethod
    def require_open(cls, onboarder, seller) -> EditSession:
        """The onboarder's open session for `seller`, or EditSessionRequired."""
        session = cls.latest(seller, onboarder)
        if session is None or not session.is_open(timezone.now()):
            raise EditSessionRequired(
                "Editing needs the seller's consent: ask for a code, and enter it when the seller tells you."
            )
        cls._check_seller(seller)
        return session


class OnboardingService:

    @staticmethod
    def onboarded_sellers():
        """Every seller opened through field onboarding."""
        return SellerProfile.objects.filter(onboarding__isnull=False)

    @classmethod
    def sellers_of(cls, user):
        """The sellers `user` onboarded, newest first."""
        return cls.onboarded_sellers().filter(created_by=user).order_by("-created_at", "-pk")

    @classmethod
    def products_of(cls, user):
        """The products `user` added for the sellers they onboarded (Product.onboarded_by)."""
        return Product.objects.filter(onboarded_by=user, shop__owner__in=cls.sellers_of(user))

    @classmethod
    def awaiting_approval(cls):
        """Onboarded sellers staff have not approved or rejected yet, oldest first."""
        return cls.onboarded_sellers().filter(
            status__in=SellerProfile.AWAITING_APPROVAL_STATUSES
        ).order_by("created_at", "pk")

    @classmethod
    def summary(cls, user) -> dict:
        """What the onboarder's home screen shows: points, tokens, costs and their sellers by state."""
        config = OnboardingSettings.current()
        wallet = StaffWallet.objects.filter(user=user).first()
        points = PointService.expire_due_staff_points(wallet).balance if wallet else 0
        counts = cls.sellers_of(user).aggregate(
            total=Count("pk"),
            awaiting_approval=Count("pk", filter=Q(status__in=SellerProfile.AWAITING_APPROVAL_STATUSES)),
            live=Count("pk", filter=Q(status__in=(SellerProfile.STATUS_APPROVED, SellerProfile.STATUS_ACTIVE))),
            rejected=Count("pk", filter=Q(status=SellerProfile.STATUS_REJECTED)),
        )
        pending = TokenService.pending_payout(user)
        return {
            "points": points,
            "tokens": TokenService.get_balance(user),
            "taka_per_token": config.taka_per_token,
            "pending_payout_tokens": pending.tokens if pending else 0,
            "starting_points": config.starting_points,
            "tokens_per_seller": config.tokens_per_seller,
            "product_creation_cost": PointService.get_product_creation_cost(),
            "minimum_point_sale": SellerPointPolicy.current().minimum_purchase,
            "can_onboard": points >= config.starting_points,
            "sellers": counts,
        }

    @classmethod
    def onboard_seller(cls, onboarder, account: dict, seller_fields: dict, ip_address=None) -> SellerProfile:
        """
        Opens a login account and a PENDING seller profile for it, moves the
        starting points from the onboarder's wallet to the seller's, and
        credits the onboarder's tokens, all in one transaction. Raises
        InsufficientStaffPointsError, before anything is kept, when the
        onboarder's wallet holds fewer than the starting points.
        """
        config = OnboardingSettings.current()
        with transaction.atomic():
            user = create_login_account(
                username=account["username"],
                email=account.get("email", ""),
                password=account["password"],
                first_name=account.get("first_name", "").strip(),
                last_name=account.get("last_name", "").strip(),
            )
            if account.get("phone"):
                create_login_phone(user, account["phone"])
            # The onboarder knows this password; the seller replaces it at first sign-in.
            StartingPassword.objects.create(user=user, set_by=onboarder)
            seller = create_seller_profile(user, created_by=onboarder, **seller_fields)
            SellerOnboarding.objects.create(
                seller=seller,
                starting_points=config.starting_points,
                tokens_awarded=config.tokens_per_seller,
            )
            if config.starting_points:
                PointService.adjust_points(
                    seller=seller,
                    amount=config.starting_points,
                    action="CREDIT",
                    reason=f"Starting points: onboarded by {onboarder.username}",
                    actor=onboarder,
                    reference_type=POINTS_REFERENCE,
                    reference_id=str(seller.pk),
                )
            TokenService.earn(
                onboarder,
                config.tokens_per_seller,
                seller=seller,
                actor=onboarder,
                reason=f"Onboarded {seller.business_name}",
            )
            AuditService.log(
                action="SELLER_ONBOARDED",
                target=seller,
                actor=onboarder,
                seller=seller,
                new_state={
                    "seller_id": seller.pk,
                    "user_id": user.pk,
                    "username": user.username,
                    "business_name": seller.business_name,
                    "seller_type": seller.seller_type,
                    "status": seller.status,
                    "starting_points": config.starting_points,
                    "tokens_awarded": config.tokens_per_seller,
                },
                ip_address=ip_address,
            )
        logger.info(
            "Seller onboarded: seller=%s by=%s points=%s tokens=%s",
            seller.pk, onboarder.username, config.starting_points, config.tokens_per_seller,
        )
        return seller

    @classmethod
    def add_shop(cls, onboarder, seller, ip_address=None, **fields) -> Shop:
        """
        Adds a shop for an onboarded seller, submitted for review. Raises
        IneligibleSellerError for a rejected or suspended seller and
        ShopLimitExceededError past a Limited Shop Owner's one shop.
        """
        with transaction.atomic():
            shop = ShopService.create_shop(seller=seller, submit_for_review=True, for_onboarding=True, **fields)
            AuditService.log(
                action="ONBOARDING_SHOP_CREATED",
                target=shop,
                actor=onboarder,
                shop=shop,
                seller=seller,
                new_state={"shop_id": shop.pk, "name": shop.name, "slug": shop.slug, "status": shop.status},
                ip_address=ip_address,
            )
        return shop

    @classmethod
    def add_product(cls, onboarder, shop, data: dict, image=None, ip_address=None) -> Product:
        """
        Adds a product to an onboarded seller's shop. The seller's wallet pays
        the creation fee, as for any product; the product starts SUBMITTED.
        """
        return ProductService.create_product(
            seller=shop.owner,
            name=data["name"],
            category=data["category_id"],
            shop=shop,
            description=data["description"],
            price=data["price"],
            old_price=data.get("old_price"),
            stock=data.get("stock", 0),
            badge=data.get("badge", ""),
            image=image,
            is_active=data.get("is_active", True),
            actor=onboarder,
            ip_address=ip_address,
            for_onboarding=True,
        )

    @classmethod
    def sell_points(cls, onboarder, seller, amount: int, ip_address=None) -> PointTransaction:
        """
        Moves `amount` points from the onboarder's wallet to one of their
        sellers, who paid the onboarder outside the system. Only once staff
        approved the seller: a rejection returns just the starting points, so
        points sold before it would stay with a rejected seller.
        PointService.adjust_points enforces the minimum purchase and the
        onboarder's balance. Writes ONBOARDING_POINTS_SOLD.
        """
        if not seller.is_operational:
            raise OnboardingError(
                f"{seller.business_name} is {seller.get_status_display().lower()}; "
                "points are sold only to approved sellers."
            )
        with transaction.atomic():
            txn = PointService.adjust_points(
                seller=seller,
                amount=amount,
                action="CREDIT",
                reason=f"Points sold by {onboarder.username}",
                actor=onboarder,
                reference_type=POINT_SALE_REFERENCE,
            )
            AuditService.log(
                action="ONBOARDING_POINTS_SOLD",
                target=txn,
                actor=onboarder,
                seller=seller,
                previous_state={"balance": txn.balance_before},
                new_state={"balance": txn.balance_after},
                metadata={
                    "amount": txn.amount,
                    "point_transaction_id": txn.pk,
                    "expires_at": txn.lot.expires_at.isoformat(),
                    "onboarder_wallet_balance": txn.staff_counterpart.balance_after,
                },
                ip_address=ip_address,
            )
        return txn

    @classmethod
    def approve(cls, seller, approver, ip_address=None) -> dict:
        """
        Approves an onboarded seller awaiting approval together with its
        waiting shops and products: the seller and shops become ACTIVE and
        the submitted products are approved and published. A shop or product
        staff already rejected one by one stays as it is. Every step writes
        the same audit row its own Console action would.
        """
        with transaction.atomic():
            seller = SellerProfile.objects.select_for_update().get(pk=seller.pk)
            onboarding = SellerOnboarding.objects.select_for_update().filter(seller=seller).first()
            if onboarding is None:
                raise OnboardingError("This seller was not onboarded in the field.")
            if seller.status not in SellerProfile.AWAITING_APPROVAL_STATUSES:
                raise OnboardingError(
                    f"Only a seller awaiting approval can be approved with its onboarding; this one is {seller.status}."
                )

            reason = "Approved with its field onboarding"
            previous_status = seller.status
            approve_seller(seller, approver)
            AuditService.log(
                action="ADMIN_SELLER_APPROVE",
                target=seller,
                actor=approver,
                seller=seller,
                reason=reason,
                previous_state={"status": previous_status},
                new_state={"status": seller.status},
                ip_address=ip_address,
            )

            shops_approved = 0
            waiting_shops = Shop.objects.select_for_update().filter(
                owner=seller, status__in=(Shop.STATUS_DRAFT, Shop.STATUS_PENDING)
            )
            for shop in waiting_shops:
                previous_status = shop.status
                ShopService.approve_shop(shop, approver)
                AuditService.log(
                    action="ADMIN_SHOP_APPROVE",
                    target=shop,
                    actor=approver,
                    shop=shop,
                    seller=seller,
                    reason=reason,
                    previous_state={"status": previous_status},
                    new_state={"status": shop.status},
                    ip_address=ip_address,
                )
                shops_approved += 1

            # Read after the seller and shops are approved, so publish() sees them live.
            products_published = 0
            waiting_products = (
                Product.objects.select_for_update()
                .select_related("shop", "shop__owner")
                .filter(shop__owner=seller, status__in=(Product.STATUS_SUBMITTED, Product.STATUS_APPROVED))
            )
            for product in waiting_products:
                if product.shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
                    continue
                if product.status == Product.STATUS_SUBMITTED:
                    ProductService.approve(product, approver, reason=reason, ip_address=ip_address)
                ProductService.publish(product, approver, reason=reason, ip_address=ip_address)
                products_published += 1

            onboarding.approved_by = approver
            onboarding.approved_at = timezone.now()
            onboarding.save(update_fields=["approved_by", "approved_at"])
            result = {"shops_approved": shops_approved, "products_published": products_published}
            AuditService.log(
                action="SELLER_ONBOARDING_APPROVED",
                target=seller,
                actor=approver,
                seller=seller,
                metadata=result,
                ip_address=ip_address,
            )
        return result

    @classmethod
    def reverse_rewards(cls, seller, staff_user) -> Optional[SellerOnboarding]:
        """
        Called by sellers.services.reject_seller, inside its transaction: a
        rejected onboarded seller gives its starting points back to the
        onboarder, and the onboarder gives back the tokens it earned. The
        creation fees of its products, none of which ever went live, are
        refunded to the seller first, so the whole grant can go back. Once
        per onboarding; None for a seller that was not onboarded.
        """
        onboarding = SellerOnboarding.objects.select_for_update().filter(
            seller=seller, reversed_at__isnull=True
        ).first()
        if onboarding is None:
            return None
        onboarder = seller.created_by
        reason = f"{seller.business_name} was rejected"

        for product in Product.objects.filter(shop__owner=seller).select_related("shop", "shop__owner"):
            ProductService.refund_creation_fee(product, actor=staff_user)

        points = 0
        if onboarder is not None and onboarding.starting_points:
            points = min(onboarding.starting_points, PointService.get_balance(seller))
            if points:
                PointService.adjust_points(
                    seller=seller,
                    amount=points,
                    action="DEBIT",
                    reason=f"Starting points returned to {onboarder.username}: {reason}",
                    actor=staff_user,
                    reference_type=POINTS_REFERENCE,
                    reference_id=str(seller.pk),
                    wallet_owner=onboarder,
                )
        tokens = 0
        if onboarder is not None:
            tokens = TokenService.take_back(
                onboarder, onboarding.tokens_awarded, seller=seller, actor=staff_user, reason=reason
            )

        onboarding.reversed_at = timezone.now()
        onboarding.points_returned = points
        onboarding.tokens_taken_back = tokens
        onboarding.save(update_fields=["reversed_at", "points_returned", "tokens_taken_back"])
        AuditService.log(
            action="SELLER_ONBOARDING_REVERSED",
            target=seller,
            actor=staff_user,
            seller=seller,
            metadata={
                "onboarded_by": onboarder.username if onboarder else None,
                "points_returned": points,
                "tokens_taken_back": tokens,
            },
        )
        return onboarding

    # -- Corrections in an edit session ---------------------------------------

    @staticmethod
    def _apply(instance, data: dict, fields) -> tuple:
        """Sets the changed `fields`; returns (previous_state, new_state)."""
        previous_state, new_state = {}, {}
        for field in fields:
            if field in data and getattr(instance, field) != data[field]:
                previous_state[field] = getattr(instance, field)
                new_state[field] = data[field]
                setattr(instance, field, data[field])
        return previous_state, new_state

    #: What an onboarder may correct on a seller: the business details, not
    #: the seller type (it decides the shop and product limits) or the login.
    SELLER_FIELDS = ("business_name", "business_email", "business_phone", "tax_id", "description")
    SHOP_FIELDS = ("name", "description", "phone", "additional_phones", "address")

    @classmethod
    def edit_seller(cls, onboarder, seller, data: dict, ip_address=None) -> SellerProfile:
        session = EditSessionService.require_open(onboarder, seller)
        with transaction.atomic():
            seller = SellerProfile.objects.select_for_update().get(pk=seller.pk)
            previous_state, new_state = cls._apply(seller, data, cls.SELLER_FIELDS)
            if new_state:
                seller.save()
                AuditService.log(
                    action="ONBOARDING_SELLER_UPDATED",
                    target=seller,
                    actor=onboarder,
                    seller=seller,
                    previous_state=previous_state,
                    new_state=new_state,
                    metadata={"edit_session_id": session.pk},
                    ip_address=ip_address,
                )
        return seller

    @classmethod
    def edit_shop(cls, onboarder, shop, data: dict, location=None, ip_address=None) -> Shop:
        """
        `data` holds SHOP_FIELDS, `additional_phones` already normalized
        against the primary phone; `location` is a (latitude, longitude) pair
        already validated, or None to leave it.
        """
        session = EditSessionService.require_open(onboarder, shop.owner)
        with transaction.atomic():
            shop = Shop.objects.select_for_update().select_related("owner").get(pk=shop.pk)
            previous_state, new_state = cls._apply(shop, data, cls.SHOP_FIELDS)
            if location is not None:
                from shops.fields import Point

                old_coords = (shop.latitude, shop.longitude)
                if tuple(location) != old_coords:
                    previous_state["latitude"], previous_state["longitude"] = old_coords
                    new_state["latitude"], new_state["longitude"] = location
                    shop.location = Point(longitude=location[1], latitude=location[0])
            if new_state:
                shop.save()
                AuditService.log(
                    action="ONBOARDING_SHOP_UPDATED",
                    target=shop,
                    actor=onboarder,
                    shop=shop,
                    seller=shop.owner,
                    previous_state=previous_state,
                    new_state=new_state,
                    metadata={"edit_session_id": session.pk},
                    ip_address=ip_address,
                )
        return shop

    @classmethod
    def edit_product(cls, onboarder, product, data: dict, ip_address=None) -> Product:
        """ProductService.update_product, as the seller's own edit would, inside the session."""
        session = EditSessionService.require_open(onboarder, product.shop.owner)
        return ProductService.update_product(
            product=product,
            seller=product.shop.owner,
            data=data,
            actor=onboarder,
            ip_address=ip_address,
            for_onboarding=True,
            audit_metadata={"edited_via": "onboarding", "edit_session_id": session.pk},
        )
