"""
Field onboarding and the tokens it earns (see onboarding/models.py).

The onboarding steps reuse the platform's own services: the seller profile
comes from sellers.services.create_seller_profile, the shop from
ShopService.create_shop and each product from ProductService.create_product,
so every rule those enforce (the Limited Shop Owner caps, the product
creation fee, the audit rows) holds here too. The only difference is that
the shop and products may be added while the seller still awaits approval.
"""
import logging
from typing import Optional

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from audit.services import AuditService
from points.models import StaffWallet
from points.services import PointService
from rbac.serializers import create_login_account, create_login_phone
from sellers.models import SellerProfile
from sellers.services import approve_seller, create_seller_profile
from shop.models import Product
from shop.services import ProductService
from shops.models import Shop
from shops.services import ShopService
from .models import OnboardingSettings, SellerOnboarding, TokenTransaction, TokenWallet

logger = logging.getLogger(__name__)

#: reference_type on the point ledger rows an onboarding writes.
POINTS_REFERENCE = "SELLER_ONBOARDING"


class OnboardingError(Exception):
    """An onboarding step the seller's current state does not allow."""


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
    def _move(wallet, amount: int, transaction_type: str, reason: str, seller, actor, outgoing: bool):
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
        many it took: fewer only if the wallet holds fewer, which can happen
        once tokens can be spent.
        """
        if amount <= 0:
            return 0
        with transaction.atomic():
            wallet = cls._lock_wallet(user)
            taken = min(amount, wallet.balance)
            if taken:
                cls._move(wallet, taken, TokenTransaction.TYPE_TAKEN_BACK, reason, seller, actor, outgoing=True)
            return taken


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
        return {
            "points": points,
            "tokens": TokenService.get_balance(user),
            "starting_points": config.starting_points,
            "tokens_per_seller": config.tokens_per_seller,
            "product_creation_cost": PointService.get_product_creation_cost(),
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
