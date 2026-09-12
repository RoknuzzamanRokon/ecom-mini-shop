import logging
from typing import Any, Dict, Optional
from django.contrib.auth import get_user_model
from .models import AuditLog

logger = logging.getLogger(__name__)
User = get_user_model()


class AuditService:
    """
    Domain service for immutable audit recording.
    Executes within the active database transaction to ensure transactional consistency.
    """

    @classmethod
    def log(
        cls,
        action: str,
        target: Any,
        actor: Optional[Any] = None,
        shop: Optional[Any] = None,
        seller: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
        previous_state: Optional[Any] = None,
        new_state: Optional[Any] = None,
    ) -> AuditLog:
        """
        Creates and persists an AuditLog entry.
        Automatically resolves target_type, target_id, and target_repr from target object.
        Supports recording reason, previous_state, and new_state in the immutable audit payload.
        """
        target_type = target.__class__.__name__ if hasattr(target, "__class__") else str(type(target))
        target_id = str(getattr(target, "pk", getattr(target, "id", "")))
        target_repr = str(target)[:255]

        # Infer shop/seller if not explicitly provided
        if shop is None and hasattr(target, "shop"):
            shop = getattr(target, "shop")
        if seller is None and hasattr(target, "seller"):
            seller = getattr(target, "seller")
        if seller is None and hasattr(target, "owner"):
            # If target is Shop, target.owner is seller
            owner = getattr(target, "owner")
            if owner and hasattr(owner, "business_name"):
                seller = owner

        # Ensure actor is an authenticated User or None
        user_actor = None
        if actor and getattr(actor, "is_authenticated", False):
            user_actor = actor

        payload = dict(metadata or {})
        if reason:
            payload["reason"] = str(reason)
        if previous_state is not None:
            payload["previous_state"] = previous_state
        if new_state is not None:
            payload["new_state"] = new_state

        audit_entry = AuditLog.objects.create(
            actor=user_actor,
            action=action.upper().strip(),
            target_type=target_type,
            target_id=target_id,
            target_repr=target_repr,
            shop=shop,
            seller=seller,
            metadata=payload,
            ip_address=ip_address,
        )

        logger.info(
            "Audit recorded: action=%s target=%s:%s actor=%s",
            audit_entry.action,
            audit_entry.target_type,
            audit_entry.target_id,
            user_actor.username if user_actor else "System",
        )
        return audit_entry
