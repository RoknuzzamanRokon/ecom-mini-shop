import type { AdminRule, AdminRuleGroup } from "@/lib/admin-api";
import { formatCount } from "@/lib/admin-format";

/** What the inputs hold, by rule key; a rule nobody touched has no entry. */
export type RuleDrafts = Record<string, string>;

/** "1 month", "200 points": the unit comes plural from the API. */
export function formatRuleValue(value: number, unit: string): string {
  const shown = value === 1 && unit.endsWith("s") ? unit.slice(0, -1) : unit;
  return `${formatCount(value)} ${shown}`;
}

/** Why a draft cannot be saved, or null when it can. */
export function draftError(rule: AdminRule, text: string): string | null {
  if (!/^\d+$/.test(text.trim())) return "Enter a whole number.";
  const value = Number(text);
  if (value < rule.minimum || value > rule.maximum) {
    return `Use ${formatCount(rule.minimum)} to ${formatCount(rule.maximum)} ${rule.unit}.`;
  }
  return null;
}

export interface PendingChange {
  rule: AdminRule;
  to: number;
}

/** The drafts that differ from the saved values, in page order. Invalid drafts are left out. */
export function pendingChanges(groups: AdminRuleGroup[], drafts: RuleDrafts): PendingChange[] {
  return groups.flatMap((group) =>
    group.rules.flatMap((rule) => {
      const text = drafts[rule.key];
      if (text === undefined || draftError(rule, text)) return [];
      const to = Number(text);
      return to === rule.value ? [] : [{ rule, to }];
    })
  );
}

/** Whether any touched input holds something that cannot be saved. */
export function hasInvalidDraft(groups: AdminRuleGroup[], drafts: RuleDrafts): boolean {
  return groups.some((group) =>
    group.rules.some((rule) => drafts[rule.key] !== undefined && draftError(rule, drafts[rule.key]) !== null)
  );
}
