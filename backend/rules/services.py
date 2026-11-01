"""
Reading and changing the business rules (rules/registry.py).

A change request is checked as a whole: ranges, then whether someone saved in
between, then the checks between rules on the values after the change.
Only then is it saved, in one transaction, with one RULE_CHANGED audit row
per rule that changed.
"""
from django.db import transaction

from audit.models import AuditLog
from audit.services import AuditService
from .registry import CHECKS, GROUPS, RULES

AUDIT_ACTION = "RULE_CHANGED"
REASON_MAX_LENGTH = 500
#: Audit rows read to find each rule's last change; rule changes are rare.
HISTORY_SCAN_LIMIT = 500


class RuleError(Exception):
    """A change was refused; `errors` maps a rule key, "reason" or "changes" to why."""

    def __init__(self, errors: dict):
        super().__init__(" ".join(errors.values()))
        self.errors = errors


class StaleRuleError(Exception):
    """Someone saved a rule after the page read it; `current` maps each such key to its stored value."""

    def __init__(self, current: dict):
        super().__init__("Someone changed these rules after you opened them.")
        self.current = current


def _whole_number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class RuleService:
    @staticmethod
    def _rows(lock: bool = False, create=()) -> dict:
        """
        Each rule model's singleton row, or an unsaved one holding the
        defaults. Models in `create` get their row saved first, so it can be
        locked and updated.
        """
        rows = {}
        for model in dict.fromkeys(rule.model for rule in RULES.values()):
            if model in create:
                model.objects.get_or_create(pk=1)
            manager = model.objects.select_for_update() if lock else model.objects
            rows[model] = manager.filter(pk=1).first() or model()
        return rows

    @staticmethod
    def _read(rows: dict) -> dict:
        return {key: getattr(rows[rule.model], rule.field) for key, rule in RULES.items()}

    @classmethod
    def values(cls) -> dict:
        """Every rule's current value, by key."""
        return cls._read(cls._rows())

    @staticmethod
    def last_changes() -> dict:
        """Each changed rule's latest RULE_CHANGED row: when, by whom and why."""
        found = {}
        entries = (
            AuditLog.objects.filter(action=AUDIT_ACTION)
            .order_by("-created_at", "-pk")
            .values("metadata", "actor_username", "created_at")[:HISTORY_SCAN_LIMIT]
        )
        for entry in entries:
            metadata = entry["metadata"] or {}
            key = metadata.get("rule")
            if key in RULES and key not in found:
                found[key] = {
                    "at": entry["created_at"],
                    "by": entry["actor_username"],
                    "reason": metadata.get("reason", ""),
                }
        return found

    @classmethod
    def snapshot(cls) -> dict:
        """The Console Rules page: every group, its rules with their values, and the checks between rules."""
        values = cls.values()
        changes = cls.last_changes()
        return {
            "groups": [
                {
                    "key": group.key,
                    "title": group.title,
                    "fixed": list(group.fixed),
                    "rules": [
                        {
                            "key": rule.key,
                            "label": rule.label,
                            "help": rule.help,
                            "unit": rule.unit,
                            "value": values[rule.key],
                            "default": rule.default,
                            "minimum": rule.minimum,
                            "maximum": rule.maximum,
                            "applies_to": rule.applies_to,
                            "takes_effect": rule.takes_effect,
                            "last_change": changes.get(rule.key),
                        }
                        for rule in group.rules
                    ],
                }
                for group in GROUPS
            ],
            "checks": [check.description for check in CHECKS],
        }

    @staticmethod
    def _requested(changes, reason) -> tuple:
        """The shape and range checks, before anything is read: ({key: (seen, to)}, reason)."""
        errors = {}
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason:
            errors["reason"] = "Say why the rules change; the reason goes in the audit log."
        elif len(reason) > REASON_MAX_LENGTH:
            errors["reason"] = f"Keep the reason to {REASON_MAX_LENGTH} characters."
        if not isinstance(changes, dict) or not changes:
            errors["changes"] = "Nothing to change."
            raise RuleError(errors)

        wanted = {}
        for key, change in changes.items():
            rule = RULES.get(key)
            if rule is None:
                errors[key] = "There is no such rule."
            elif not (
                isinstance(change, dict) and _whole_number(change.get("from")) and _whole_number(change.get("to"))
            ):
                errors[key] = "Send the value you saw as `from` and the new value as `to`, both whole numbers."
            elif not rule.minimum <= change["to"] <= rule.maximum:
                errors[key] = f"{rule.label} must be between {rule.minimum:,} and {rule.maximum:,} {rule.unit}."
            else:
                wanted[key] = (change["from"], change["to"])
        if errors:
            raise RuleError(errors)
        return wanted, reason

    @classmethod
    def update(cls, changes, reason, actor, ip_address=None) -> list:
        """
        Applies `changes` ({key: {"from": seen, "to": new}}) for `reason`.
        Raises RuleError when a value or the reason is refused, StaleRuleError
        when a stored value no longer matches what was seen. Returns
        [{key, from, to}] for the rules that changed.
        """
        wanted, reason = cls._requested(changes, reason)
        with transaction.atomic():
            rows = cls._rows(lock=True, create={RULES[key].model for key in wanted})
            current = cls._read(rows)
            stale = {key: current[key] for key, (seen, _to) in wanted.items() if current[key] != seen}
            if stale:
                raise StaleRuleError(stale)
            changed = {key: to for key, (_seen, to) in wanted.items() if to != current[key]}
            if not changed:
                raise RuleError({"changes": "Every value is already what you asked for; nothing changed."})

            after = {**current, **changed}
            errors = {}
            for check in CHECKS:
                errors.update(check.find(after))
            if errors:
                raise RuleError(errors)

            fields = {}
            for key, to in changed.items():
                rule = RULES[key]
                setattr(rows[rule.model], rule.field, to)
                fields.setdefault(rule.model, []).append(rule.field)
            for model, names in fields.items():
                rows[model].save(update_fields=[*names, "updated_at"])
            for key, to in changed.items():
                rule = RULES[key]
                AuditService.log(
                    action=AUDIT_ACTION,
                    target=rows[rule.model],
                    actor=actor,
                    metadata={"rule": key, "label": rule.label, "unit": rule.unit},
                    reason=reason,
                    previous_state=current[key],
                    new_state=to,
                    ip_address=ip_address,
                )
        return [{"key": key, "from": current[key], "to": to} for key, to in changed.items()]
