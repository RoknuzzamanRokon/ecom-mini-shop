from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable audit log recording critical system mutations and operational workflows.
    Tracks actor, action, affected resource, contextual shop/seller, payload metadata, and timestamp.
    """
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="User who initiated or performed this action.",
    )
    action = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Standardized domain action code (e.g. PRODUCT_CREATED, PRODUCT_UPDATED).",
    )
    target_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Model/resource name affected (e.g. Product, Shop, Seller).",
    )
    target_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Primary key / identifier of the target record.",
    )
    target_repr = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable representation of the target.",
    )
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="Optional shop context.",
    )
    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="Optional seller context.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed payload, diff, or operational metadata.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address when available.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {actor_name} -> {self.action} on {self.target_type}:{self.target_id}"
