import logging
from django.db import transaction
from .models import PointTransaction, ProductCreationCost, SellerWallet

logger = logging.getLogger(__name__)


class PointError(Exception):
    """Base exception for point system operations."""
    pass


class InsufficientPointsError(PointError):
    """Raised when a seller attempts to spend more points than their available balance."""
    pass


class InvalidAmountError(PointError):
    """Raised when an invalid (<=0 or non-integer) point amount is provided."""
    pass


class InvalidTransactionError(PointError):
    """Raised when required transaction attributes (such as reason) are missing or invalid."""
    pass


class PointService:
    """
    Centralized domain service responsible for all point operations.
    Enforces atomic execution, concurrency safety (row locks), append-only ledger entries,
    and guarantees non-negative wallet balances.
    """

    @classmethod
    def get_or_create_wallet(cls, seller) -> SellerWallet:
        """Retrieves or initializes a seller's wallet with zero initial balance."""
        wallet, _ = SellerWallet.objects.get_or_create(
            seller=seller,
            defaults={"balance": 0},
        )
        return wallet

    @classmethod
    def get_balance(cls, seller) -> int:
        """Returns the current point balance for a seller."""
        wallet = cls.get_or_create_wallet(seller)
        return wallet.balance

    @classmethod
    def has_sufficient_points(cls, seller, amount: int) -> bool:
        """Returns True if the seller has at least the required points available."""
        if amount <= 0:
            return True
        return cls.get_balance(seller) >= amount

    @classmethod
    def get_product_creation_cost(cls) -> int:
        """
        Returns the authoritative number of points required to create a new product.
        Centralized source retrieved from ProductCreationCost model / settings fallback.
        """
        return ProductCreationCost.get_cost()

    @classmethod
    def credit(
        cls,
        seller,
        amount: int,
        transaction_type: str,
        reason: str,
        actor=None,
        reference_type: str = "",
        reference_id: str = "",
    ) -> PointTransaction:
        """
        Atomically credits points to a seller's wallet and records an auditable ledger transaction.
        Uses select_for_update() to guarantee concurrency safety.
        """
        if not isinstance(amount, int) or amount <= 0:
            raise InvalidAmountError(f"Credit amount must be a positive integer, got: {amount}")

        if not reason or not str(reason).strip():
            raise InvalidTransactionError("A non-empty reason is mandatory for all point operations.")

        with transaction.atomic():
            wallet, _ = SellerWallet.objects.select_for_update().get_or_create(
                seller=seller,
                defaults={"balance": 0},
            )

            balance_before = wallet.balance
            balance_after = balance_before + amount

            wallet.balance = balance_after
            wallet.save(update_fields=["balance", "updated_at"])

            txn = PointTransaction.objects.create(
                wallet=wallet,
                seller=seller,
                transaction_type=transaction_type,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reason=str(reason).strip(),
                reference_type=str(reference_type or "").strip(),
                reference_id=str(reference_id or "").strip(),
                actor=actor,
            )

            logger.info(
                f"[POINTS] Credited {amount} pts to seller {seller.id} ({seller.business_name}). "
                f"Balance: {balance_before} -> {balance_after}. Type: {transaction_type}."
            )
            return txn

    @classmethod
    def debit(
        cls,
        seller,
        amount: int,
        transaction_type: str,
        reason: str,
        actor=None,
        reference_type: str = "",
        reference_id: str = "",
    ) -> PointTransaction:
        """
        Atomically debits points from a seller's wallet and records an auditable ledger transaction.
        Validates sufficient balance before applying and raises InsufficientPointsError if balance is too low.
        Uses select_for_update() to guarantee concurrency safety.
        """
        if not isinstance(amount, int) or amount <= 0:
            raise InvalidAmountError(f"Debit amount must be a positive integer, got: {amount}")

        if not reason or not str(reason).strip():
            raise InvalidTransactionError("A non-empty reason is mandatory for all point operations.")

        with transaction.atomic():
            wallet, _ = SellerWallet.objects.select_for_update().get_or_create(
                seller=seller,
                defaults={"balance": 0},
            )

            if wallet.balance < amount:
                raise InsufficientPointsError(
                    f"Insufficient points. Required: {amount}, available: {wallet.balance}."
                )

            balance_before = wallet.balance
            balance_after = balance_before - amount

            wallet.balance = balance_after
            wallet.save(update_fields=["balance", "updated_at"])

            txn = PointTransaction.objects.create(
                wallet=wallet,
                seller=seller,
                transaction_type=transaction_type,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                reason=str(reason).strip(),
                reference_type=str(reference_type or "").strip(),
                reference_id=str(reference_id or "").strip(),
                actor=actor,
            )

            logger.info(
                f"[POINTS] Debited {amount} pts from seller {seller.id} ({seller.business_name}). "
                f"Balance: {balance_before} -> {balance_after}. Type: {transaction_type}."
            )
            return txn

    @classmethod
    def adjust_points(
        cls,
        seller,
        amount: int,
        action: str,
        reason: str,
        actor=None,
        reference_type: str = "",
        reference_id: str = "",
    ) -> PointTransaction:
        """
        Dispatches staff/admin adjustments based on action type ('CREDIT' or 'DEBIT').
        """
        normalized_action = str(action).upper().strip()
        if normalized_action == "CREDIT":
            return cls.credit(
                seller=seller,
                amount=amount,
                transaction_type=PointTransaction.TYPE_ADMIN_CREDIT,
                reason=reason,
                actor=actor,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        elif normalized_action == "DEBIT":
            return cls.debit(
                seller=seller,
                amount=amount,
                transaction_type=PointTransaction.TYPE_ADMIN_DEBIT,
                reason=reason,
                actor=actor,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        else:
            raise InvalidTransactionError(
                f"Invalid adjustment action '{action}'. Must be 'CREDIT' or 'DEBIT'."
            )

    @classmethod
    def get_transaction_history(cls, seller, transaction_type: str = None):
        """Returns the query set of transactions for a seller ordered by newest first."""
        qs = PointTransaction.objects.filter(seller=seller).select_related("actor", "wallet")
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type.upper().strip())
        return qs
