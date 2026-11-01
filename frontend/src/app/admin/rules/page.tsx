"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  AdminApiError,
  getAdminRules,
  updateAdminRules,
  type AdminRule,
  type AdminRules,
} from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import { AdminConfirmModal } from "@/components/admin/shared";
import { useLatestRequest } from "@/hooks/useLatestRequest";
import {
  draftError,
  formatRuleValue,
  hasInvalidDraft,
  pendingChanges,
  type RuleDrafts,
} from "./ruleDrafts";

const INPUT_CLASS =
  "w-24 bg-surface border border-line rounded-lg text-sm font-bold text-ink text-right tabular-nums transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary px-2.5 py-1.5";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function errorsOf(err: unknown): Record<string, string> {
  if (!(err instanceof AdminApiError) || !err.data || typeof err.data !== "object") return {};
  const errors = (err.data as { errors?: unknown }).errors;
  return errors && typeof errors === "object" ? (errors as Record<string, string>) : {};
}

export default function AdminRulesPage() {
  const { user } = useAuth();
  const canView = hasAnyPermission(user, ADMIN_PERMISSIONS.rulesView);

  const [rules, setRules] = useState<AdminRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<RuleDrafts>({});
  const [ruleErrors, setRuleErrors] = useState<Record<string, string>>({});
  const [alert, setAlert] = useState<{ message: string; reload: boolean } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const beginRequest = useLatestRequest();

  const fetchRules = useCallback((): Promise<void> => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setLoadError("No active session token was found. Please sign in again.");
      });
    }
    return getAdminRules(token)
      .then((data) => {
        if (!isLatest()) return;
        setRules(data);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (!isLatest()) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load the rules.");
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [beginRequest]);

  useEffect(() => {
    if (!canView) return;
    fetchRules();
  }, [canView, fetchRules]);

  const reload = useCallback(() => {
    setLoading(true);
    setDrafts({});
    setRuleErrors({});
    setAlert(null);
    fetchRules();
  }, [fetchRules]);

  const groups = useMemo(() => rules?.groups ?? [], [rules]);
  const changes = useMemo(() => pendingChanges(groups, drafts), [groups, drafts]);
  const invalid = hasInvalidDraft(groups, drafts);

  const setDraft = (rule: AdminRule, text: string) => {
    setDrafts((prev) => ({ ...prev, [rule.key]: text }));
    setRuleErrors((prev) => {
      if (!(rule.key in prev)) return prev;
      const next = { ...prev };
      delete next[rule.key];
      return next;
    });
    setNotice(null);
  };

  const discard = () => {
    setDrafts({});
    setRuleErrors({});
    setAlert(null);
  };

  const save = (reason: string): Promise<void> => {
    const token = getAuthToken();
    if (!token) {
      setSubmitError("No active session token was found. Please sign in again.");
      return Promise.resolve();
    }
    setSubmitError(null);
    const payload = Object.fromEntries(changes.map(({ rule, to }) => [rule.key, { from: rule.value, to }]));
    return updateAdminRules(token, payload, reason)
      .then((result) => {
        const { changed, ...snapshot } = result;
        setRules(snapshot);
        setDrafts({});
        setRuleErrors({});
        setAlert(null);
        setConfirmOpen(false);
        setNotice(`Saved ${changed.length === 1 ? "1 change" : `${changed.length} changes`}. They apply from now on.`);
      })
      .catch((err: unknown) => {
        const errors = errorsOf(err);
        if (errors.reason) {
          setSubmitError(errors.reason);
          return;
        }
        setConfirmOpen(false);
        if (err instanceof AdminApiError && err.status === 409) {
          setAlert({ message: err.message, reload: true });
          return;
        }
        setRuleErrors(errors);
        setAlert({ message: err instanceof Error ? err.message : "The rules could not be saved.", reload: false });
      });
  };

  if (!canView) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
          <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            The business rules need <code className="font-mono text-[11px]">rules.view</code> to see
            them, or <code className="font-mono text-[11px]">rules.manage</code> to change them.
          </p>
          <Link
            href="/admin"
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Return to Overview
          </Link>
        </div>
      </div>
    );
  }

  const canManage = rules?.can_manage ?? false;

  return (
    <div className="space-y-6 pb-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Rules</h1>
        <p className="text-xs text-ink-muted">
          The costs, periods and limits MiniShop runs on. A change applies from now on: point dates,
          running listing periods and past onboardings keep what they were given.
        </p>
      </div>

      {notice && (
        <div role="status" className="rounded-xl border border-success/30 bg-success/10 p-3 flex items-start gap-2">
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-success shrink-0">
            check_circle
          </span>
          <p className="text-xs font-semibold text-success">{notice}</p>
        </div>
      )}

      {alert && (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/10 p-3 flex items-start justify-between gap-3"
        >
          <p className="text-xs font-semibold text-danger">{alert.message}</p>
          {alert.reload && (
            <button type="button" onClick={reload} className="text-xs font-bold text-danger underline shrink-0 cursor-pointer">
              Reload
            </button>
          )}
        </div>
      )}

      {rules && !canManage && (
        <p className="text-xs text-ink-muted">
          You can see the rules. Changing them needs{" "}
          <code className="font-mono text-[11px]">rules.manage</code> (Administrators).
        </p>
      )}

      {loading && !rules ? (
        <div className="flex items-center justify-center py-24">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" aria-label="Loading rules" />
        </div>
      ) : loadError && !rules ? (
        <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 p-4 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold text-danger">{loadError}</p>
          <button type="button" onClick={reload} className="text-xs font-bold text-danger underline shrink-0 cursor-pointer">
            Try Again
          </button>
        </div>
      ) : (
        <>
          {groups.map((group) => (
            <section
              key={group.key}
              aria-labelledby={`rules-${group.key}`}
              className="bg-surface rounded-2xl border border-line shadow-xs"
            >
              <h2 id={`rules-${group.key}`} className="px-4 sm:px-5 pt-4 text-sm font-black text-ink">
                {group.title}
              </h2>
              <ul className="divide-y divide-line-subtle">
                {group.rules.map((rule) => {
                  const draft = drafts[rule.key];
                  const inputError = draft !== undefined ? draftError(rule, draft) : null;
                  const error = inputError ?? ruleErrors[rule.key];
                  const edited = draft !== undefined && !inputError && Number(draft) !== rule.value;
                  const inputId = `rule-${rule.key}`;
                  return (
                    <li
                      key={rule.key}
                      className={`px-4 sm:px-5 py-4 flex flex-col sm:flex-row sm:items-start gap-3 ${
                        edited ? "bg-primary/5" : ""
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        {canManage ? (
                          <label htmlFor={inputId} className="block text-sm font-bold text-ink">
                            {rule.label}
                          </label>
                        ) : (
                          <p className="text-sm font-bold text-ink">{rule.label}</p>
                        )}
                        <p className="text-xs text-ink-muted mt-0.5">{rule.help}</p>
                        <p className="text-[11px] text-ink-muted mt-1.5">
                          <span className="font-semibold text-ink-body">{rule.applies_to}</span>
                          {" · "}Takes effect: {rule.takes_effect}
                        </p>
                        <p className="text-[11px] text-ink-faint mt-0.5">
                          Default {formatRuleValue(rule.default, rule.unit)}
                          {rule.last_change &&
                            ` · Changed ${formatDate(rule.last_change.at)} by @${rule.last_change.by}`}
                        </p>
                        {edited && (
                          <p className="text-[11px] font-semibold text-primary mt-1">
                            Was {formatRuleValue(rule.value, rule.unit)}
                          </p>
                        )}
                        {error && (
                          <p id={`${inputId}-error`} className="text-[11px] font-semibold text-danger mt-1">
                            {error}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 sm:pt-0.5 shrink-0">
                        {canManage ? (
                          <>
                            <input
                              id={inputId}
                              type="number"
                              inputMode="numeric"
                              min={rule.minimum}
                              max={rule.maximum}
                              step={1}
                              value={draft ?? String(rule.value)}
                              onChange={(e) => setDraft(rule, e.target.value)}
                              aria-invalid={Boolean(error)}
                              aria-describedby={error ? `${inputId}-error` : undefined}
                              className={`${INPUT_CLASS} ${error ? "border-danger" : ""}`}
                            />
                            <span className="text-xs text-ink-muted w-16">{rule.unit}</span>
                          </>
                        ) : (
                          <span className="text-sm font-black text-ink tabular-nums">
                            {formatRuleValue(rule.value, rule.unit)}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {group.fixed.length > 0 && (
                <div className="px-4 sm:px-5 py-3 border-t border-line bg-surface-alt/40 rounded-b-2xl">
                  <p className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5">
                    Fixed in code
                  </p>
                  <ul className="space-y-1">
                    {group.fixed.map((text) => (
                      <li key={text} className="text-xs text-ink-body flex gap-1.5">
                        <span aria-hidden="true" className="text-ink-faint">•</span>
                        <span>{text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          ))}

          {rules && rules.checks.length > 0 && (
            <section aria-labelledby="rules-checks" className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-5">
              <h2 id="rules-checks" className="text-sm font-black text-ink mb-1.5">
                Checked together
              </h2>
              <ul className="space-y-1">
                {rules.checks.map((text) => (
                  <li key={text} className="text-xs text-ink-body">
                    {text}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {canManage && (changes.length > 0 || invalid) && (
        <div className="sticky bottom-4 z-10 rounded-2xl border border-line bg-surface shadow-lg p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p className="text-xs font-semibold text-ink">
            {changes.length === 1 ? "1 unsaved change" : `${changes.length} unsaved changes`}
            {invalid && <span className="text-danger"> · fix the marked values first</span>}
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={discard} className={`${BUTTON_BASE} border border-line hover:bg-surface-alt text-ink`}>
              Discard
            </button>
            <button
              type="button"
              disabled={invalid || changes.length === 0}
              onClick={() => {
                setSubmitError(null);
                setConfirmOpen(true);
              }}
              className={`${BUTTON_BASE} bg-primary hover:bg-primary-hover text-on-primary`}
            >
              Review &amp; save
            </button>
          </div>
        </div>
      )}

      <AdminConfirmModal
        open={confirmOpen}
        title={changes.length === 1 ? "Change 1 rule?" : `Change ${changes.length} rules?`}
        icon="tune"
        message={
          <>
            <ul className="space-y-1 mb-2">
              {changes.map(({ rule, to }) => (
                <li key={rule.key}>
                  <strong className="text-ink">{rule.label}</strong>: {formatRuleValue(rule.value, rule.unit)} →{" "}
                  <strong className="text-ink">{formatRuleValue(to, rule.unit)}</strong>
                </li>
              ))}
            </ul>
            <p>The new values apply from now on. The reason goes in the audit log.</p>
            {submitError && <p className="mt-2 font-semibold text-danger">{submitError}</p>}
          </>
        }
        confirmLabel="Save"
        requireReason
        reasonRequired
        reasonLabel="Why are the rules changing?"
        reasonPlaceholder="e.g. New point prices from 1 December"
        onConfirm={save}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
