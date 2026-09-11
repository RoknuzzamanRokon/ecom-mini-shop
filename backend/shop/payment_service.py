import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from audit.services import AuditService
from shop.models import Order, Payment, Refund

logger = logging.getLogger(__name__)
User = get_user_model()


class PaymentService:
    """
    Dedicated server-authoritative service for Order payment processing,
    status transitions, concurrency protection, idempotency guards, and refunds.
    """

    @classmethod
    def generate_payment_number(cls) -> str:
        """Generates unique payment identifier: PAY-YYYYMMDD-XXXXXXXX."""
        date_str = timezone.now().strftime("%Y%m%d")
        random_suffix = uuid.uuid4().hex[:8].upper()
        return f"PAY-{date_str}-{random_suffix}"

    @classmethod
    def generate_refund_number(cls) -> str:
        """Generates unique refund identifier: REF-YYYYMMDD-XXXXXXXX."""
        date_str = timezone.now().strftime("%Y%m%d")
        random_suffix = uuid.uuid4().hex[:8].upper()
        return f"REF-{date_str}-{random_suffix}"

    @classmethod
    def create_or_get_payment(
        cls,
        order: Order,
        payment_method: str = Payment.METHOD_CASH_ON_DELIVERY,
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> Payment:
        """
        Creates or retrieves an authoritative payment record for an Order.
        Enforces:
          - Server-authoritative payable amount derived directly from order.total_amount.
          - Row-level locking on Order to avoid concurrent double creation.
          - Rejects payment initiation for cancelled orders.
          - Idempotency guard: rejects if order is already PAID.
          - Reuses pending/processing payment if available.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().filter(pk=order.pk).first()
            if not locked_order:
                raise ValidationError({"order": "Order not found."})

            if locked_order.status == Order.STATUS_CANCELLED:
                raise ValidationError({"order": "Cannot initiate payment for a cancelled order."})

            # Check if order already has a successful PAID payment
            paid_payment = locked_order.payments.filter(status=Payment.STATUS_PAID).first()
            if paid_payment:
                raise ValidationError({"payment": "Order is already paid."})

            # Check for existing PENDING or PROCESSING payment
            pending_payment = (
                locked_order.payments.select_for_update()
                .filter(status__in=[Payment.STATUS_PENDING, Payment.STATUS_PROCESSING])
                .first()
            )
            if pending_payment:
                # Update method if changed
                if payment_method and pending_payment.payment_method != payment_method:
                    pending_payment.payment_method = payment_method
                    pending_payment.save(update_fields=["payment_method", "updated_at"])
                return pending_payment

            # Calculate server-authoritative payable amount
            payable_amount = locked_order.total_amount
            payment_number = cls.generate_payment_number()

            payment = Payment.objects.create(
                order=locked_order,
                user=locked_order.user,
                payment_number=payment_number,
                payment_method=payment_method or Payment.METHOD_CASH_ON_DELIVERY,
                status=Payment.STATUS_PENDING,
                amount=payable_amount,
                currency="BDT",
                provider="internal",
            )

            AuditService.log(
                action="PAYMENT_CREATED",
                target=payment,
                actor=actor or locked_order.user,
                metadata={
                    "payment_number": payment.payment_number,
                    "order_number": locked_order.order_number,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                    "payment_method": payment.payment_method,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Payment created: payment_number=%s order=%s amount=%s",
                payment.payment_number,
                locked_order.order_number,
                payment.amount,
            )
            return payment

    @classmethod
    def process_payment_success(
        cls,
        payment: Union[Payment, int],
        transaction_id: str = "",
        provider: str = "internal",
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Payment:
        """
        Processes successful payment verification/callback.
        Enforces:
          - Row-level locking on Payment record.
          - Idempotency: if already PAID, returns successfully without duplicate actions.
          - State machine validation.
          - Order state check (cannot mark paid if order was cancelled).
          - Immutable audit trail.
        """
        payment_id = payment.pk if isinstance(payment, Payment) else payment
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
            if not locked_payment:
                raise ValidationError({"payment": "Payment record not found."})

            # Idempotency guard
            if locked_payment.status == Payment.STATUS_PAID:
                logger.info("Payment %s is already PAID; idempotent return.", locked_payment.payment_number)
                return locked_payment

            if not locked_payment.can_transition_to(Payment.STATUS_PAID):
                raise ValidationError({
                    "payment": f"Cannot transition payment in status '{locked_payment.status}' to PAID."
                })

            locked_order = Order.objects.select_for_update().filter(pk=locked_payment.order_id).first()
            if locked_order and locked_order.status == Order.STATUS_CANCELLED:
                raise ValidationError({
                    "payment": "Cannot complete payment for a cancelled order."
                })

            old_status = locked_payment.status
            locked_payment.transition_to(Payment.STATUS_PAID)

            if transaction_id:
                locked_payment.transaction_id = transaction_id
            if provider:
                locked_payment.provider = provider
            if metadata:
                locked_payment.metadata.update(metadata)
            locked_payment.save(update_fields=["transaction_id", "provider", "metadata", "updated_at"])

            AuditService.log(
                action="PAYMENT_SUCCESS",
                target=locked_payment,
                actor=actor,
                metadata={
                    "payment_number": locked_payment.payment_number,
                    "order_number": locked_order.order_number if locked_order else "",
                    "old_status": old_status,
                    "new_status": locked_payment.status,
                    "amount": str(locked_payment.amount),
                    "transaction_id": locked_payment.transaction_id,
                    "provider": locked_payment.provider,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Payment success recorded: payment=%s order=%s amount=%s",
                locked_payment.payment_number,
                locked_order.order_number if locked_order else "",
                locked_payment.amount,
            )
            return locked_payment

    @classmethod
    def process_payment_failure(
        cls,
        payment: Union[Payment, int],
        reason: str = "",
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Payment:
        """
        Records a failed payment attempt.
        """
        payment_id = payment.pk if isinstance(payment, Payment) else payment
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
            if not locked_payment:
                raise ValidationError({"payment": "Payment record not found."})

            if locked_payment.status == Payment.STATUS_FAILED:
                return locked_payment

            if not locked_payment.can_transition_to(Payment.STATUS_FAILED):
                raise ValidationError({
                    "payment": f"Cannot transition payment in status '{locked_payment.status}' to FAILED."
                })

            old_status = locked_payment.status
            locked_payment.failure_reason = reason
            if metadata:
                locked_payment.metadata.update(metadata)
            locked_payment.transition_to(Payment.STATUS_FAILED)

            AuditService.log(
                action="PAYMENT_FAILED",
                target=locked_payment,
                actor=actor,
                metadata={
                    "payment_number": locked_payment.payment_number,
                    "old_status": old_status,
                    "new_status": locked_payment.status,
                    "reason": reason,
                },
                ip_address=ip_address,
            )

            logger.info("Payment failed: payment=%s reason=%s", locked_payment.payment_number, reason)
            return locked_payment

    @classmethod
    def process_refund(
        cls,
        payment: Union[Payment, int],
        amount: Optional[Union[Decimal, float, str]] = None,
        reason: str = "",
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
        transaction_id: str = "",
    ) -> Refund:
        """
        Issues a server-authoritative full or partial refund for a paid order.
        Enforces:
          - Row-level locking on Payment and Order to prevent race conditions.
          - Payment must be in PAID or PARTIALLY_REFUNDED status.
          - Authoritative remaining refundable calculation: payment.amount - sum(completed_refunds).
          - Rejects refund amount <= 0 or refund amount > remaining refundable.
          - Atomic creation of immutable Refund ledger record.
          - Idempotent state progression: moves to PARTIALLY_REFUNDED or REFUNDED.
          - Immutable AuditLog entry.
        """
        payment_id = payment.pk if isinstance(payment, Payment) else payment
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
            if not locked_payment:
                raise ValidationError({"payment": "Payment record not found."})

            if locked_payment.status not in (Payment.STATUS_PAID, Payment.STATUS_PARTIALLY_REFUNDED):
                raise ValidationError({
                    "refund": f"Payment in status '{locked_payment.status}' is not eligible for refund."
                })

            locked_order = Order.objects.select_for_update().filter(pk=locked_payment.order_id).first()

            # Calculate server-authoritative cumulative refunded sum
            completed_sum = (
                Refund.objects.filter(payment=locked_payment, status=Refund.STATUS_COMPLETED)
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0.00")
            )
            remaining_refundable = locked_payment.amount - completed_sum

            if remaining_refundable <= Decimal("0.00"):
                raise ValidationError({"refund": "Payment has already been fully refunded."})

            # Default to full remaining refund if amount not specified
            if amount is None:
                refund_amount = remaining_refundable
            else:
                try:
                    refund_amount = Decimal(str(amount))
                except Exception:
                    raise ValidationError({"amount": "Invalid numeric refund amount."})

            if refund_amount <= Decimal("0.00"):
                raise ValidationError({"amount": "Refund amount must be greater than zero."})

            if refund_amount > remaining_refundable:
                raise ValidationError({
                    "amount": f"Refund amount ({refund_amount}) exceeds remaining refundable amount ({remaining_refundable})."
                })

            refund_number = cls.generate_refund_number()
            refund = Refund.objects.create(
                refund_number=refund_number,
                payment=locked_payment,
                order=locked_order,
                amount=refund_amount,
                currency="BDT",
                reason=reason or "Operational refund",
                status=Refund.STATUS_COMPLETED,
                processed_by=actor if getattr(actor, "is_authenticated", False) else None,
                transaction_id=transaction_id,
            )

            # Update Payment status
            new_cumulative_refunded = completed_sum + refund_amount
            if new_cumulative_refunded >= locked_payment.amount:
                locked_payment.transition_to(Payment.STATUS_REFUNDED)
            else:
                locked_payment.transition_to(Payment.STATUS_PARTIALLY_REFUNDED)

            AuditService.log(
                action="REFUND_PROCESSED",
                target=refund,
                actor=actor,
                metadata={
                    "refund_number": refund.refund_number,
                    "payment_number": locked_payment.payment_number,
                    "order_number": locked_order.order_number if locked_order else "",
                    "amount": str(refund.amount),
                    "currency": refund.currency,
                    "reason": refund.reason,
                    "is_full_refund": (new_cumulative_refunded >= locked_payment.amount),
                    "remaining_refundable": str(max(Decimal("0.00"), locked_payment.amount - new_cumulative_refunded)),
                },
                ip_address=ip_address,
            )

            logger.info(
                "Refund processed: refund=%s payment=%s amount=%s status=%s",
                refund.refund_number,
                locked_payment.payment_number,
                refund.amount,
                locked_payment.status,
            )
            return refund

    @classmethod
    def handle_order_cancellation(
        cls,
        order: Order,
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ):
        """
        Integrates payment state with Order cancellation.
        - If payment is PENDING or PROCESSING: transitions to CANCELLED.
        - If payment is PAID or PARTIALLY_REFUNDED: automatically issues full remaining refund.
        - Idempotent: ensures no duplicate financial records or double refunding.
        """
        with transaction.atomic():
            payments = order.payments.select_for_update().all()
            for p in payments:
                if p.status in (Payment.STATUS_PENDING, Payment.STATUS_PROCESSING):
                    p.transition_to(Payment.STATUS_CANCELLED)
                    AuditService.log(
                        action="PAYMENT_CANCELLED",
                        target=p,
                        actor=actor,
                        metadata={
                            "payment_number": p.payment_number,
                            "order_number": order.order_number,
                            "reason": "Order cancelled",
                        },
                        ip_address=ip_address,
                    )
                elif p.status in (Payment.STATUS_PAID, Payment.STATUS_PARTIALLY_REFUNDED):
                    completed_sum = (
                        Refund.objects.filter(payment=p, status=Refund.STATUS_COMPLETED)
                        .aggregate(total=Sum("amount"))["total"]
                        or Decimal("0.00")
                    )
                    remaining = p.amount - completed_sum
                    if remaining > Decimal("0.00"):
                        cls.process_refund(
                            payment=p,
                            amount=remaining,
                            reason="Order cancellation automatic refund",
                            actor=actor,
                            ip_address=ip_address,
                        )
