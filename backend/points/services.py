import logging
from django.db import transaction

from notifications import events
from notifications.publisher import publish
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import (
    PointExpiryPolicy,
    PointTransaction,
    ProductCreationCost,
    SellerPointLot,
    SellerWallet,
    StaffPointLot,
    StaffPointTransaction,
    StaffWallet,
)
from .permissions import can_perform_point_action

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


class InsufficientStaffPointsError(PointError):
    """Raised when a staff member tries to give away more points than their own wallet holds."""
    pass


#: Upcoming expiries listed on a wallet payload.
UPCOMING_EXPIRY_LIMIT = 5


def seller_points_expire(seller) -> bool:
    """A Full Shop Owner's points never expire; everyone else's do."""
    return seller.seller_type != seller.TYPE_FULL_SHOP_OWNER


def staff_points_expire(wallet) -> bool:
    """A superuser's points never expire; other staff's do unless a superuser turned it off."""
    return wallet.points_expire and not wallet.user.is_superuser


class PointService:
    """
    Centralized domain service responsible for all point operations.
    Enforces atomic execution, concurrency safety (row locks), append-only ledger entries,
    and guarantees non-negative wallet balances.

    Expiry: every point a wallet receives arrives as a lot dated
    PointExpiryPolicy months ahead, and spending takes from the lot that
    expires first. Due lots are expired whenever their wallet is locked or
    read, and by the expire_points command for wallets nobody touches, so an
    expired point can never be spent or moved.
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
        """Returns the current point balance for a seller, after expiring any due points."""
        wallet = cls.expire_due_seller_points(cls.get_or_create_wallet(seller))
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
    def get_ledger_totals(cls, seller) -> dict:
        """
        Lifetime points credited and debited for a seller, aggregated from the
        PointTransaction ledger in a single query.

        Deliberately NOT stored on SellerWallet. The ledger is the one source of
        truth for point movement; a stored total would be a second one, free to
        drift from the transactions that justify it.

        The credit/debit split is taken from `balance_after` vs `balance_before`
        rather than from a hand-maintained list of transaction types. That is the
        same rule `PointTransaction.__str__` already uses, and it means a newly
        added transaction type is classified correctly without this method being
        touched. `amount` is always positive, so the direction cannot be read
        from it.
        """
        expiry = Q(transaction_type=PointTransaction.TYPE_EXPIRY)
        return PointTransaction.objects.filter(seller=seller).aggregate(
            total_earned=Coalesce(
                Sum("amount", filter=Q(balance_after__gte=F("balance_before"))), 0
            ),
            # Expired points were lost, not spent, so they are counted apart.
            total_spent=Coalesce(
                Sum("amount", filter=Q(balance_after__lt=F("balance_before")) & ~expiry), 0
            ),
            total_expired=Coalesce(Sum("amount", filter=expiry), 0),
        )

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
            wallet = cls._lock_seller_wallet(seller)

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
            cls._add_lot(SellerPointLot, wallet, amount, txn)

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
            wallet = cls._lock_seller_wallet(seller)

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
            cls._consume_lots(wallet.lots, amount)

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

        An adjustment moves points between the seller's wallet and the actor's
        own StaffWallet: a CREDIT comes out of the actor's wallet and is refused
        when it does not hold enough, and a DEBIT goes back into it. Superusers
        are no exception; they fill their own wallet with mint_points first.
        """
        normalized_action = str(action).upper().strip()
        if normalized_action == "CREDIT":
            move, transaction_type = cls.credit, PointTransaction.TYPE_ADMIN_CREDIT
            staff_type, from_staff = StaffPointTransaction.TYPE_SELLER_CREDIT, True
        elif normalized_action == "DEBIT":
            move, transaction_type = cls.debit, PointTransaction.TYPE_ADMIN_DEBIT
            staff_type, from_staff = StaffPointTransaction.TYPE_SELLER_DEBIT, False
        else:
            raise InvalidTransactionError(
                f"Invalid adjustment action '{action}'. Must be 'CREDIT' or 'DEBIT'."
            )

        if actor is None:
            raise InvalidTransactionError(
                "A staff adjustment needs an actor: its points move to or from the actor's own wallet."
            )
        cls._validate_movement(amount, reason)

        with transaction.atomic():
            # Staff wallet first, seller wallet second, in both directions, so
            # two concurrent adjustments always lock in the same order.
            staff_wallet = cls._lock_staff_wallet(actor)
            if from_staff:
                cls._require_staff_balance(staff_wallet, amount)

            txn = move(
                seller=seller,
                amount=amount,
                transaction_type=transaction_type,
                reason=reason,
                actor=actor,
                reference_type=reference_type,
                reference_id=reference_id,
            )
            cls._move_staff_points(
                staff_wallet,
                amount,
                staff_type,
                reason,
                actor=actor,
                outgoing=from_staff,
                seller_transaction=txn,
            )
            # Only staff adjustments notify; the credits and debits the
            # platform makes itself (e.g. a product's creation cost) don't.
            publish(
                events.POINTS_ADJUSTED,
                payload={
                    "transaction_id": txn.pk,
                    "seller_id": seller.pk,
                    "transaction_type": txn.transaction_type,
                    "amount": txn.amount,
                    "balance_after": txn.balance_after,
                    "reason": txn.reason,
                },
                aggregate=txn,
                actor=actor,
                idempotency_key=f"points_txn:{txn.pk}",
            )
        return txn

    @classmethod
    def get_transaction_history(cls, seller, transaction_type: str = None):
        """Returns the query set of transactions for a seller ordered by newest first."""
        qs = PointTransaction.objects.filter(seller=seller).select_related("actor", "wallet")
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type.upper().strip())
        return qs

    # ------------------------------------------------------------------
    # Staff wallets
    # ------------------------------------------------------------------
    # Staff never create points: a staff credit is a transfer out of their own
    # wallet. The points they hand out are created by mint_points, which only a
    # superuser may call, and transfer_to_staff passes some of them on so other
    # staff can credit sellers too.

    @classmethod
    def get_or_create_staff_wallet(cls, user) -> StaffWallet:
        """Retrieves or initializes a staff member's wallet with zero initial balance."""
        wallet, _ = StaffWallet.objects.get_or_create(user=user, defaults={"balance": 0})
        return wallet

    @classmethod
    def get_staff_balance(cls, user) -> int:
        """Returns the points a staff member can still give away."""
        return cls.get_or_create_staff_wallet(user).balance

    @classmethod
    def get_staff_ledger_totals(cls, wallet) -> dict:
        """
        Lifetime movement through one StaffWallet, in a single aggregate query.

        `received` is every inflow (mint, transfer in, points taken back from a
        seller or from staff), split by balance direction as get_ledger_totals
        does, so a new inflow type is counted without this method changing. The
        three outflows are reported apart because they mean different things to
        the holder: points given to sellers, points passed on to other staff,
        and points a superuser took back out of this wallet. `expired` is what
        ran out unused.
        """
        return StaffPointTransaction.objects.filter(wallet=wallet).aggregate(
            received=Coalesce(Sum("amount", filter=Q(balance_after__gte=F("balance_before"))), 0),
            given_to_sellers=Coalesce(
                Sum("amount", filter=Q(transaction_type=StaffPointTransaction.TYPE_SELLER_CREDIT)), 0
            ),
            sent_to_staff=Coalesce(
                Sum("amount", filter=Q(transaction_type=StaffPointTransaction.TYPE_TRANSFER_OUT)), 0
            ),
            taken_back=Coalesce(
                Sum("amount", filter=Q(transaction_type=StaffPointTransaction.TYPE_RECLAIM_OUT)), 0
            ),
            expired=Coalesce(
                Sum("amount", filter=Q(transaction_type=StaffPointTransaction.TYPE_EXPIRY)), 0
            ),
        )

    @classmethod
    def mint_points(cls, superuser, amount: int, reason: str) -> StaffPointTransaction:
        """Creates `amount` new points in a superuser's own staff wallet."""
        if not (superuser and superuser.is_active and superuser.is_superuser):
            raise PointError("Only an active superuser can create new points.")
        cls._validate_movement(amount, reason)

        with transaction.atomic():
            wallet = cls._lock_staff_wallet(superuser)
            txn = cls._move_staff_points(
                wallet, amount, StaffPointTransaction.TYPE_MINT, reason,
                actor=superuser, outgoing=False,
            )
        logger.info(
            f"[POINTS] Minted {amount} pts into {superuser.username}'s staff wallet. "
            f"Balance: {txn.balance_before} -> {txn.balance_after}."
        )
        return txn

    @classmethod
    def transfer_to_staff(cls, sender, recipient, amount: int, reason: str):
        """
        Moves `amount` points from a superuser's staff wallet to another staff
        member's. Returns the (outgoing, incoming) ledger entries.

        The recipient must be able to credit sellers; points in any other
        wallet could never be spent.
        """
        if not (sender and sender.is_active and sender.is_superuser):
            raise PointError("Only an active superuser can hand points to staff.")
        if recipient.pk == sender.pk:
            raise PointError("Points cannot be transferred to your own wallet.")
        if not recipient.is_active or not can_perform_point_action(recipient, "CREDIT"):
            raise PointError(
                f"{recipient.username} cannot credit sellers, so points in their wallet could never be used."
            )
        cls._validate_movement(amount, reason)

        with transaction.atomic():
            # Lock both wallets in user-id order so two opposite transfers
            # cannot deadlock each other.
            wallets = {
                user.pk: cls._lock_staff_wallet(user)
                for user in sorted((sender, recipient), key=lambda u: u.pk)
            }
            outgoing = cls._move_staff_points(
                wallets[sender.pk], amount, StaffPointTransaction.TYPE_TRANSFER_OUT, reason,
                actor=sender, outgoing=True, counterparty=recipient,
            )
            incoming = cls._move_staff_points(
                wallets[recipient.pk], amount, StaffPointTransaction.TYPE_TRANSFER_IN, reason,
                actor=sender, outgoing=False, counterparty=sender,
            )
        logger.info(
            f"[POINTS] Transferred {amount} pts from {sender.username} to {recipient.username}. "
            f"Balances: {outgoing.balance_after} / {incoming.balance_after}."
        )
        return outgoing, incoming

    @classmethod
    def reclaim_from_staff(cls, superuser, staff_member, amount: int, reason: str):
        """
        Moves `amount` points from a staff member's wallet back into a
        superuser's own: the reverse of transfer_to_staff. Returns the
        (outgoing, incoming) ledger entries.

        Unlike a transfer, the staff member need not be able to credit sellers,
        or even be active: taking points back from someone who has lost that
        ability is the main reason to do it.
        """
        if not (superuser and superuser.is_active and superuser.is_superuser):
            raise PointError("Only an active superuser can take points back from staff.")
        if staff_member.pk == superuser.pk:
            raise PointError("Points cannot be taken back from your own wallet.")
        cls._validate_movement(amount, reason)

        with transaction.atomic():
            # The same user-id lock order as transfer_to_staff, so a transfer
            # and a take-back between the same two wallets cannot deadlock.
            wallets = {
                user.pk: cls._lock_staff_wallet(user)
                for user in sorted((superuser, staff_member), key=lambda u: u.pk)
            }
            source = wallets[staff_member.pk]
            if source.balance < amount:
                raise InsufficientStaffPointsError(
                    f"Not enough points in {staff_member.username}'s wallet. "
                    f"Required: {amount}, available: {source.balance}."
                )
            outgoing = cls._move_staff_points(
                source, amount, StaffPointTransaction.TYPE_RECLAIM_OUT, reason,
                actor=superuser, outgoing=True, counterparty=superuser,
            )
            incoming = cls._move_staff_points(
                wallets[superuser.pk], amount, StaffPointTransaction.TYPE_RECLAIM_IN, reason,
                actor=superuser, outgoing=False, counterparty=staff_member,
            )
        logger.info(
            f"[POINTS] {superuser.username} took back {amount} pts from {staff_member.username}. "
            f"Balances: {incoming.balance_after} / {outgoing.balance_after}."
        )
        return outgoing, incoming

    @classmethod
    def _validate_movement(cls, amount, reason) -> None:
        if not isinstance(amount, int) or amount <= 0:
            raise InvalidAmountError(f"Point amount must be a positive integer, got: {amount}")
        if not reason or not str(reason).strip():
            raise InvalidTransactionError("A non-empty reason is mandatory for all point operations.")

    @classmethod
    def _lock_staff_wallet(cls, user) -> StaffWallet:
        """
        Must be called inside transaction.atomic(); the lock lasts until it commits.
        Due points are expired first, so they can never be moved.
        """
        wallet, _ = StaffWallet.objects.select_for_update().get_or_create(
            user=user,
            defaults={"balance": 0},
        )
        cls._expire_locked_staff_wallet(wallet)
        return wallet

    @classmethod
    def _require_staff_balance(cls, wallet: StaffWallet, amount: int) -> None:
        if wallet.balance < amount:
            raise InsufficientStaffPointsError(
                f"Not enough points in your wallet. Required: {amount}, available: {wallet.balance}."
            )

    @classmethod
    def _move_staff_points(
        cls,
        wallet: StaffWallet,
        amount: int,
        transaction_type: str,
        reason: str,
        actor,
        outgoing: bool,
        counterparty=None,
        seller_transaction=None,
    ) -> StaffPointTransaction:
        """Applies one movement to a wallet the caller has locked, and records it."""
        if outgoing:
            cls._require_staff_balance(wallet, amount)

        balance_before = wallet.balance
        wallet.balance = balance_before - amount if outgoing else balance_before + amount
        wallet.save(update_fields=["balance", "updated_at"])

        txn = StaffPointTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reason=str(reason).strip(),
            counterparty=counterparty,
            seller_transaction=seller_transaction,
            actor=actor,
        )
        if outgoing:
            cls._consume_lots(wallet.lots, amount)
        else:
            cls._add_lot(StaffPointLot, wallet, amount, txn)
        return txn

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    @classmethod
    def _lock_seller_wallet(cls, seller) -> SellerWallet:
        """
        Must be called inside transaction.atomic(); the lock lasts until it commits.
        Due points are expired first, so they can never be spent.
        """
        wallet, _ = SellerWallet.objects.select_for_update().get_or_create(
            seller=seller,
            defaults={"balance": 0},
        )
        cls._expire_locked_seller_wallet(wallet)
        return wallet

    @staticmethod
    def _add_lot(lot_model, wallet, amount: int, source):
        now = timezone.now()
        return lot_model.objects.create(
            wallet=wallet,
            amount=amount,
            remaining=amount,
            received_at=now,
            expires_at=PointExpiryPolicy.expiry_for(now),
            source=source,
        )

    @staticmethod
    def _consume_lots(lots, amount: int) -> None:
        """
        Takes `amount` from a locked wallet's lots, soonest-expiring first. The
        balance is authoritative: if the lots hold less (a balance edited
        outside PointService), the rest is simply not tracked.
        """
        for lot in lots.filter(remaining__gt=0).order_by("expires_at", "id"):
            if amount <= 0:
                break
            taken = min(lot.remaining, amount)
            lot.remaining -= taken
            lot.save(update_fields=["remaining"])
            amount -= taken

    @staticmethod
    def _due_lots(wallet):
        return wallet.lots.filter(remaining__gt=0, expires_at__lte=timezone.now())

    @classmethod
    def _take_due(cls, wallet) -> int:
        """
        Zeroes a locked wallet's due lots and returns how many points that
        removes, capped at the balance so a drifted wallet never goes negative.
        """
        due = cls._due_lots(wallet)
        total = due.aggregate(total=Coalesce(Sum("remaining"), 0))["total"]
        if not total:
            return 0
        due.update(remaining=0)
        return min(total, wallet.balance)

    @classmethod
    def _expire_locked_seller_wallet(cls, wallet: SellerWallet):
        if not seller_points_expire(wallet.seller):
            return None
        amount = cls._take_due(wallet)
        if not amount:
            return None
        balance_before = wallet.balance
        wallet.balance = balance_before - amount
        wallet.save(update_fields=["balance", "updated_at"])
        txn = PointTransaction.objects.create(
            wallet=wallet,
            seller=wallet.seller,
            transaction_type=PointTransaction.TYPE_EXPIRY,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reason=f"{amount} point{'' if amount == 1 else 's'} expired unused.",
        )
        logger.info(
            f"[POINTS] Expired {amount} pts from seller {wallet.seller_id}. "
            f"Balance: {balance_before} -> {wallet.balance}."
        )
        return txn

    @classmethod
    def _expire_locked_staff_wallet(cls, wallet: StaffWallet):
        if not staff_points_expire(wallet):
            return None
        amount = cls._take_due(wallet)
        if not amount:
            return None
        balance_before = wallet.balance
        wallet.balance = balance_before - amount
        wallet.save(update_fields=["balance", "updated_at"])
        txn = StaffPointTransaction.objects.create(
            wallet=wallet,
            transaction_type=StaffPointTransaction.TYPE_EXPIRY,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reason=f"{amount} point{'' if amount == 1 else 's'} expired unused.",
        )
        logger.info(
            f"[POINTS] Expired {amount} pts from {wallet.user.username}'s staff wallet. "
            f"Balance: {balance_before} -> {wallet.balance}."
        )
        return txn

    @classmethod
    def expire_due_seller_points(cls, wallet: SellerWallet) -> SellerWallet:
        """
        `wallet` with any due points expired, for read paths. Locks only when
        something is due, so a read with nothing to expire stays one query.
        """
        if not seller_points_expire(wallet.seller) or not cls._due_lots(wallet).exists():
            return wallet
        with transaction.atomic():
            locked = SellerWallet.objects.select_for_update().get(pk=wallet.pk)
            cls._expire_locked_seller_wallet(locked)
        return locked

    @classmethod
    def expire_due_staff_points(cls, wallet: StaffWallet) -> StaffWallet:
        """The staff-wallet counterpart of expire_due_seller_points."""
        if not staff_points_expire(wallet) or not cls._due_lots(wallet).exists():
            return wallet
        with transaction.atomic():
            locked = StaffWallet.objects.select_for_update().get(pk=wallet.pk)
            cls._expire_locked_staff_wallet(locked)
        return locked

    @classmethod
    def expire_all_due_points(cls) -> dict:
        """
        Expires due points in every wallet, for the expire_points command.
        Each wallet commits on its own, so one failure loses no other's work.
        """
        result = {"seller_wallets": 0, "staff_wallets": 0, "points": 0}
        now = timezone.now()
        for kind, lot_model, wallet_model, expire in (
            ("seller_wallets", SellerPointLot, SellerWallet, cls._expire_locked_seller_wallet),
            ("staff_wallets", StaffPointLot, StaffWallet, cls._expire_locked_staff_wallet),
        ):
            wallet_ids = (
                lot_model.objects.filter(remaining__gt=0, expires_at__lte=now)
                .values_list("wallet_id", flat=True)
                .distinct()
            )
            for wallet_id in list(wallet_ids):
                with transaction.atomic():
                    wallet = wallet_model.objects.select_for_update().get(pk=wallet_id)
                    txn = expire(wallet)
                if txn is not None:
                    result[kind] += 1
                    result["points"] += txn.amount
        return result

    @staticmethod
    def upcoming_expiries(wallet, limit: int = UPCOMING_EXPIRY_LIMIT) -> list:
        """The wallet's soonest-expiring unspent lots, as {points, expires_at}."""
        return [
            {"points": lot.remaining, "expires_at": lot.expires_at}
            for lot in wallet.lots.filter(remaining__gt=0).order_by("expires_at", "id")[:limit]
        ]

    @staticmethod
    def restart_expiry_clock(wallet) -> int:
        """
        Gives the wallet's unspent points at least a full expiry period from
        now. Used when a holder whose points did not expire starts to (a Full
        Shop Owner made Limited, a staff member's expiry turned back on), so
        old points do not vanish the moment the rule starts to apply.
        Returns how many lots moved.
        """
        fresh = PointExpiryPolicy.expiry_for(timezone.now())
        return wallet.lots.filter(remaining__gt=0, expires_at__lt=fresh).update(expires_at=fresh)

    @classmethod
    def set_staff_points_expire(cls, user, enabled: bool) -> StaffWallet:
        """
        Turns expiry on or off for one staff member's wallet. Turning it on
        restarts the clock on what they hold. A superuser's points never
        expire, so their wallet cannot be switched.
        """
        if user.is_superuser:
            raise PointError(f"{user.username} is a superuser; their points never expire.")
        with transaction.atomic():
            wallet, _ = StaffWallet.objects.select_for_update().get_or_create(
                user=user, defaults={"balance": 0}
            )
            if wallet.points_expire == enabled:
                return wallet
            # Points already due go before the switch, whichever way it turns.
            cls._expire_locked_staff_wallet(wallet)
            wallet.points_expire = enabled
            wallet.save(update_fields=["points_expire", "updated_at"])
            if enabled:
                cls.restart_expiry_clock(wallet)
        return wallet
