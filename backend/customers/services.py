import logging
from typing import Any, Dict, Optional
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from audit.services import AuditService
from .models import Address, CustomerProfile, Review

logger = logging.getLogger(__name__)
User = get_user_model()


class ReviewAlreadyExistsError(Exception):
    """Raised when a customer attempts to review a product they've already reviewed."""
    pass


class CustomerService:
    """
    Domain service managing customer profile lifecycle and audit operations.
    """

    @classmethod
    def get_or_create_profile(cls, user) -> CustomerProfile:
        """
        Retrieves or initializes the CustomerProfile for a User.
        """
        profile, created = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={
                "display_name": (f"{user.first_name} {user.last_name}".strip() or user.username),
            },
        )
        return profile

    @classmethod
    def update_profile(
        cls,
        user,
        data: Dict[str, Any],
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> CustomerProfile:
        """
        Updates profile fields and logs audit record.
        """
        profile = cls.get_or_create_profile(user)
        changed_fields = {}

        for field in ["display_name", "phone", "avatar", "date_of_birth", "gender"]:
            if field in data:
                old_val = getattr(profile, field)
                new_val = data[field]
                if old_val != new_val:
                    changed_fields[field] = {"old": str(old_val), "new": str(new_val)}
                    setattr(profile, field, new_val)

        # Update User first/last name if provided
        user_changed = False
        for user_field in ["first_name", "last_name"]:
            if user_field in data:
                old_user_val = getattr(user, user_field)
                new_user_val = data[user_field]
                if old_user_val != new_user_val:
                    changed_fields[f"user_{user_field}"] = {
                        "old": str(old_user_val),
                        "new": str(new_user_val),
                    }
                    setattr(user, user_field, new_user_val)
                    user_changed = True

        if user_changed:
            user.save(update_fields=["first_name", "last_name"])

        if changed_fields:
            profile.save()
            AuditService.log(
                action="PROFILE_UPDATED",
                target=profile,
                actor=actor or user,
                metadata={"changed_fields": changed_fields},
                ip_address=ip_address,
            )

        return profile


class AddressService:
    """
    Domain service for managing customer addresses with atomic default switching
    and concurrency safety.
    """

    @classmethod
    @transaction.atomic
    def create_address(
        cls,
        user,
        data: Dict[str, Any],
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> Address:
        """
        Creates an address for a user.
        - Concurrency safe via select_for_update().
        - If first address, automatically set as default.
        - If is_default=True, demotes existing default address.
        - Logs ADDRESS_CREATED audit.
        """
        # Lock user's existing addresses to prevent concurrent race conditions
        existing_addresses = Address.objects.select_for_update().filter(user=user)
        has_existing = existing_addresses.exists()

        is_default = data.get("is_default", False)
        if not has_existing:
            # First address auto-default rule
            is_default = True

        if is_default:
            # Demote existing default address atomically
            existing_addresses.filter(is_default=True).update(is_default=False, default_flag=None)

        address_data = dict(data)
        address_data["user"] = user
        address_data["is_default"] = is_default
        address_data["default_flag"] = 1 if is_default else None

        address = Address.objects.create(**address_data)

        AuditService.log(
            action="ADDRESS_CREATED",
            target=address,
            actor=actor or user,
            metadata={
                "label": address.label,
                "city": address.city,
                "is_default": address.is_default,
            },
            ip_address=ip_address,
        )
        return address

    @classmethod
    @transaction.atomic
    def update_address(
        cls,
        address: Address,
        data: Dict[str, Any],
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> Address:
        """
        Updates an address.
        - Concurrency safe via select_for_update().
        - If setting is_default=True, demote any other default address for user.
        - Logs ADDRESS_UPDATED audit.
        """
        user = address.user
        # Lock user's addresses
        Address.objects.select_for_update().filter(user=user)

        target_is_default = data.get("is_default", address.is_default)
        if target_is_default and not address.is_default:
            # Promoting to default: demote all other addresses for this user
            Address.objects.filter(user=user, is_default=True).exclude(pk=address.pk).update(
                is_default=False, default_flag=None
            )

        changed_fields = {}
        for key, value in data.items():
            if hasattr(address, key) and key not in ["id", "user", "created_at", "updated_at"]:
                old_val = getattr(address, key)
                if old_val != value:
                    changed_fields[key] = {"old": str(old_val), "new": str(value)}
                    setattr(address, key, value)

        if target_is_default:
            address.is_default = True
            address.default_flag = 1
        else:
            address.is_default = False
            address.default_flag = None

        address.save()

        if changed_fields:
            AuditService.log(
                action="ADDRESS_UPDATED",
                target=address,
                actor=actor or user,
                metadata={"changed_fields": changed_fields},
                ip_address=ip_address,
            )

        return address

    @classmethod
    @transaction.atomic
    def delete_address(
        cls,
        address: Address,
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Deletes an address.
        - If the deleted address was default, promotes the most recently updated remaining address.
        - If no remaining addresses, leaves 0 defaults.
        - Logs ADDRESS_DELETED audit.
        """
        user = address.user
        was_default = address.is_default
        address_id = address.pk
        metadata = {
            "address_id": address_id,
            "label": address.label,
            "city": address.city,
            "was_default": was_default,
        }

        # Lock user's addresses
        Address.objects.select_for_update().filter(user=user)

        # Log audit entry before deletion while target is still present
        AuditService.log(
            action="ADDRESS_DELETED",
            target=address,
            actor=actor or user,
            metadata=metadata,
            ip_address=ip_address,
        )

        address.delete()

        if was_default:
            remaining = Address.objects.filter(user=user).order_by("-updated_at", "-created_at").first()
            if remaining:
                remaining.is_default = True
                remaining.default_flag = 1
                remaining.save(update_fields=["is_default", "default_flag", "updated_at"])
                AuditService.log(
                    action="ADDRESS_DEFAULT_PROMOTED",
                    target=remaining,
                    actor=actor or user,
                    metadata={
                        "promoted_address_id": remaining.pk,
                        "reason": "Previous default address deleted",
                    },
                    ip_address=ip_address,
                )

    @classmethod
    @transaction.atomic
    def set_default_address(
        cls,
        address: Address,
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> Address:
        """
        Sets a specific address as default, demoting any previous default.
        """
        user = address.user
        Address.objects.select_for_update().filter(user=user)
        Address.objects.filter(user=user, is_default=True).exclude(pk=address.pk).update(
            is_default=False, default_flag=None
        )
        address.is_default = True
        address.default_flag = 1
        address.save(update_fields=["is_default", "default_flag", "updated_at"])

        AuditService.log(
            action="ADDRESS_DEFAULT_SET",
            target=address,
            actor=actor or user,
            metadata={"address_id": address.pk, "label": address.label},
            ip_address=ip_address,
        )
        return address


class ReviewService:
    """
    Domain service for customer product reviews.
    """

    @classmethod
    @transaction.atomic
    def create_review(cls, user, product_id: int, rating: int, comment: str = "") -> Review:
        """
        Creates a review for a product, computing is_verified_purchase once at
        creation time from the user's DELIVERED order history. Raises
        ReviewAlreadyExistsError if the user has already reviewed this product.
        """
        from shop.models import Order, OrderItem

        is_verified_purchase = OrderItem.objects.filter(
            order__user=user,
            order__status=Order.STATUS_DELIVERED,
            product_id=product_id,
        ).exists()

        try:
            review = Review.objects.create(
                user=user,
                product_id=product_id,
                rating=rating,
                comment=comment,
                is_verified_purchase=is_verified_purchase,
            )
        except IntegrityError:
            raise ReviewAlreadyExistsError(
                "You have already reviewed this product. Edit your existing review instead."
            )

        AuditService.log(
            action="REVIEW_CREATED",
            target=review,
            actor=user,
            metadata={"product_id": product_id, "rating": rating},
        )
        return review

    @classmethod
    @transaction.atomic
    def update_review(cls, review: Review, data: Dict[str, Any]) -> Review:
        """Updates a review's rating/comment."""
        changed_fields = {}
        for field in ["rating", "comment"]:
            if field in data:
                old_val = getattr(review, field)
                new_val = data[field]
                if old_val != new_val:
                    changed_fields[field] = {"old": str(old_val), "new": str(new_val)}
                    setattr(review, field, new_val)

        if changed_fields:
            review.save()
            AuditService.log(
                action="REVIEW_UPDATED",
                target=review,
                actor=review.user,
                metadata={"changed_fields": changed_fields},
            )
        return review

    @classmethod
    @transaction.atomic
    def delete_review(cls, review: Review) -> None:
        """Deletes a review."""
        AuditService.log(
            action="REVIEW_DELETED",
            target=review,
            actor=review.user,
            metadata={"product_id": review.product_id, "rating": review.rating},
        )
        review.delete()
