import type { AdminEditSession } from "@/lib/admin-api";

/** The state as of `now`: the server's "open" or "waiting" ends by itself when its time passes. */
export function liveState(session: AdminEditSession | null, now: number): AdminEditSession["state"] {
  if (!session) return "none";
  if (session.state === "open") {
    return session.expires_at && Date.parse(session.expires_at) > now ? "open" : "ended";
  }
  if (session.state === "waiting") {
    return session.code_expires_at && Date.parse(session.code_expires_at) > now ? "waiting" : "ended";
  }
  return session.state;
}

/** "12:05" left until `iso`, or "0:00" once it has passed. */
export function timeLeft(iso: string | null, now: number): string {
  const seconds = iso ? Math.max(0, Math.ceil((Date.parse(iso) - now) / 1000)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** A clock time in the viewer's zone, e.g. "14:35". */
export function clockTime(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false }).format(
    new Date(iso)
  );
}

/** The 6 digits the seller read out, or null while it is not a whole code. */
export function cleanCode(text: string): string | null {
  const digits = text.replace(/\s+/g, "");
  return /^\d{6}$/.test(digits) ? digits : null;
}

/** The keys of `draft` whose value differs from `original`: only those are sent. */
export function changedFields<T extends object>(original: T, draft: T): Partial<T> {
  const changes: Partial<T> = {};
  for (const key of Object.keys(draft) as (keyof T)[]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(original[key])) changes[key] = draft[key];
  }
  return changes;
}

/** "01711111111, 01822222222" -> ["01711111111", "01822222222"]. */
export function phoneList(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((phone) => phone.trim())
    .filter(Boolean);
}

/** The backend's 403 when the session ended while a form was open. */
export function isSessionRequired(data: unknown): boolean {
  return typeof data === "object" && data !== null && (data as { code?: unknown }).code === "edit_session_required";
}
