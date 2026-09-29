"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";

import { getAuthToken } from "@/lib/auth";
import {
  NOTIFICATION_INBOX_PATHS,
  getNotificationPreferences,
  notificationIcon,
  updateNotificationPreferences,
  type NotificationAudience,
  type NotificationChannelKey,
  type NotificationPreference,
} from "@/lib/notifications";

const CHANNELS: { key: NotificationChannelKey; label: string; unused: string }[] = [
  { key: "in_app", label: "In-app", unused: "Not shown in-app" },
  { key: "email", label: "Email", unused: "Not sent by email" },
];

interface Loaded {
  key: string;
  rows: NotificationPreference[];
  error: string | null;
}

type Notice = { type: "success" | "error"; text: string } | null;

/** `rows` with one channel of one category switched to `enabled`. */
function withToggle(
  rows: NotificationPreference[],
  category: string,
  channel: NotificationChannelKey,
  enabled: boolean
): NotificationPreference[] {
  return rows.map((row) => {
    const state = row.channels[channel];
    if (row.category !== category || !state) return row;
    return { ...row, channels: { ...row.channels, [channel]: { ...state, enabled } } };
  });
}

/**
 * The categories × channels toggles for one audience's inbox
 * (docs/NOTIFICATION_SYSTEM.md §3 D8, §9), shared by the three
 * /…/notifications/settings pages. Each switch saves on its own; a locked
 * channel is shown switched on, disabled, and marked "Required". The backend
 * refuses a locked change anyway, so the lock here is only a preview.
 */
export default function NotificationPreferences({ audience }: { audience: NotificationAudience }) {
  const [reload, setReload] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const requestKey = `${audience}|${reload}`;

  useEffect(() => {
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getNotificationPreferences(token, audience)
      .then((rows) => {
        if (!cancelled) setLoaded({ key: requestKey, rows, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Notification settings couldn't be loaded.";
        setLoaded({ key: requestKey, rows: [], error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [audience, requestKey]);

  const current = loaded?.key === requestKey ? loaded : null;

  const toggle = async (row: NotificationPreference, channel: NotificationChannelKey, enabled: boolean) => {
    const token = getAuthToken();
    if (!token || !current) return;
    const before = current.rows;
    const channelLabel = channel === "email" ? "email" : "in-app";
    // Show the switch moved at once; every switch waits until the answer is in.
    setLoaded({ ...current, rows: withToggle(before, row.category, channel, enabled) });
    setSaving(true);
    setNotice(null);
    try {
      const rows = await updateNotificationPreferences(
        token,
        [{ category: row.category, channels: { [channel]: { enabled } } }],
        audience
      );
      setLoaded((previous) => previous && { ...previous, rows });
      setNotice({
        type: "success",
        text: `${row.label}: ${channelLabel} notifications ${enabled ? "on" : "off"}.`,
      });
    } catch (err: unknown) {
      setLoaded((previous) => previous && { ...previous, rows: before });
      setNotice({
        type: "error",
        text: err instanceof Error ? err.message : "Notification settings couldn't be saved.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href={NOTIFICATION_INBOX_PATHS[audience]}
          className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wider text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
            arrow_back
          </span>
          Notifications
        </Link>
        <h1 className="text-xl font-bold text-ink mt-2">Notification settings</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Choose which notifications also reach you by email. Everything always appears in your inbox, and your
          choices apply to your whole MiniShop account.
        </p>
      </div>

      {current === null ? (
        <div className="flex flex-col items-center justify-center py-20 text-center" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            tune
          </span>
          <p className="text-sm text-ink-body mt-2">Loading your settings…</p>
        </div>
      ) : current.error ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center" role="alert">
          <p className="text-sm text-danger font-medium">{current.error}</p>
          <button
            type="button"
            onClick={() => setReload((n) => n + 1)}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : current.rows.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-10 text-center">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-faint">
            tune
          </span>
          <p className="text-sm text-ink-body mt-2">There&apos;s nothing to set up here yet.</p>
        </div>
      ) : (
        <div className="bg-surface rounded-2xl border border-line overflow-hidden">
          <table className="w-full text-left">
            <caption className="sr-only">Notification settings: categories and the channels they reach you on</caption>
            <thead className="bg-surface-alt">
              <tr>
                <th scope="col" className="px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                  Category
                </th>
                {CHANNELS.map((channel) => (
                  <th
                    key={channel.key}
                    scope="col"
                    className="w-24 sm:w-32 px-2 py-3 text-center text-[11px] font-bold uppercase tracking-wider text-ink-muted"
                  >
                    {channel.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle">
              {current.rows.map((row) => (
                <tr key={row.category}>
                  <th scope="row" className="px-4 py-3 font-normal">
                    <span className="flex items-center gap-3">
                      <span
                        aria-hidden="true"
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"
                      >
                        <span className="material-symbols-outlined text-[18px]">{notificationIcon(row.category)}</span>
                      </span>
                      <span className="text-sm font-medium text-ink leading-snug">{row.label}</span>
                    </span>
                  </th>
                  {CHANNELS.map((channel) => (
                    <td key={channel.key} className="px-2 py-3 text-center align-middle">
                      <ChannelSwitch
                        id={`notification-${row.category}-${channel.key}`}
                        label={`${row.label}, ${channel.label}`}
                        unused={channel.unused}
                        state={row.channels[channel.key]}
                        busy={saving}
                        onChange={(enabled) => toggle(row, channel.key, enabled)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p
        aria-live="polite"
        className={clsx(
          "text-sm font-medium min-h-5",
          notice?.type === "error" ? "text-danger" : "text-success"
        )}
      >
        {notice?.text}
      </p>
    </div>
  );
}

/**
 * One cell: a switch, a locked "Required" switch, or a dash when the
 * category never uses this channel. Every cell keeps a caption line, blank
 * unless locked, so the switches in a row line up.
 */
function ChannelSwitch({
  id,
  label,
  unused,
  state,
  busy,
  onChange,
}: {
  id: string;
  label: string;
  unused: string;
  state: NotificationPreference["channels"][NotificationChannelKey];
  busy: boolean;
  onChange: (enabled: boolean) => void;
}) {
  if (!state) {
    return (
      <span className="inline-flex flex-col items-center gap-1 text-ink-faint">
        <span aria-hidden="true" className="flex h-5 items-center text-sm">
          —
        </span>
        <span aria-hidden="true" className="invisible text-[10px] font-semibold">
          Required
        </span>
        <span className="sr-only">{unused}</span>
      </span>
    );
  }

  const disabled = state.locked || busy;
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <label
        htmlFor={id}
        className={clsx("relative inline-flex", state.locked ? "cursor-not-allowed" : busy ? "cursor-wait" : "cursor-pointer")}
      >
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={state.enabled}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          aria-label={label}
          aria-describedby={state.locked ? `${id}-required` : undefined}
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className={clsx(
            "relative block h-5 w-9 rounded-full border transition-colors",
            "border-line bg-surface-sunken peer-checked:border-primary peer-checked:bg-primary",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-focus peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-surface",
            "after:absolute after:left-0.5 after:top-1/2 after:h-3.5 after:w-3.5 after:-translate-y-1/2 after:rounded-full after:bg-ink-muted after:transition-transform",
            "peer-checked:after:translate-x-4 peer-checked:after:bg-on-primary",
            state.locked && "opacity-60"
          )}
        />
      </label>
      {state.locked ? (
        <span id={`${id}-required`} className="text-[10px] font-semibold text-ink-muted">
          Required
        </span>
      ) : (
        <span aria-hidden="true" className="invisible text-[10px] font-semibold">
          Required
        </span>
      )}
    </span>
  );
}
