"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useProfile } from "@/context/ProfileContext";
import {
  canViewSellers,
  getManagementRoleLabel,
  hasAnyPermission,
  isManagementUser,
} from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { getMyStaffWallet, type StaffWalletSummary } from "@/lib/admin-api";
import { formatCount, formatDate } from "@/lib/admin-format";
import { formatImageUrl } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import PointsBalanceTile, {
  POINTS_TILE_HEADER_LINK,
  POINTS_TILE_PRIMARY_ACTION,
} from "@/components/points/PointsBalanceTile";
import PointMovementList from "@/components/points/PointMovementList";
import {
  DJANGO_ADMIN_PROFILE_URL,
  WILDCARD_PERMISSION,
  countConcretePermissions,
  formatRoleLabel,
  groupPermissions,
  hasFullPlatformAccess,
  toStaffMovementRow,
  type PermissionGroup,
} from "./adminProfile";

const CARD = "bg-surface rounded-2xl border border-line shadow-xs";
const CARD_TITLE = "text-sm font-extrabold text-ink uppercase tracking-wider";
const SECONDARY_BUTTON =
  "inline-flex items-center justify-center gap-1.5 min-h-10 px-4 rounded-lg border border-line bg-surface text-ink text-xs font-extrabold uppercase tracking-wider hover:bg-surface-alt transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

// Material Symbols ignores Tailwind's text-[Npx] (the Google Fonts stylesheet
// wins the cascade), so a glyph that must sit below 24px is sized inline.
const ICON_16 = { fontSize: 16 } as const;
const ICON_18 = { fontSize: 18 } as const;

const STAT_TONES = {
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  accent: "bg-accent/15 text-accent",
} as const;

export default function AdminProfilePage() {
  const { user, isLoading } = useAuth();
  const { profile } = useProfile();

  const [wallet, setWallet] = useState<StaffWalletSummary | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<string | null>(null);

  // State is only set in the promise callbacks, so the effect below never
  // updates state synchronously; a retry flips the loading flag itself first.
  const fetchWallet = useCallback(
    () =>
      getMyStaffWallet(getAuthToken() ?? "")
        .then((summary) => {
          setWallet(summary);
          setWalletError(null);
        })
        .catch((err: unknown) => {
          setWalletError(err instanceof Error ? err.message : "The request failed.");
        })
        .finally(() => setWalletLoading(false)),
    []
  );

  const retryWallet = useCallback(() => {
    setWalletLoading(true);
    setWalletError(null);
    fetchWallet();
  }, [fetchWallet]);

  useEffect(() => {
    if (user) fetchWallet();
  }, [user, fetchWallet]);

  const roles = useMemo(() => user?.roles ?? [], [user]);
  const permissions = useMemo(() => user?.permissions ?? [], [user]);
  const groups = useMemo(() => groupPermissions(permissions), [permissions]);
  const movements = useMemo(() => (wallet?.recent ?? []).map(toStaffMovementRow), [wallet]);
  const fullAccess = hasFullPlatformAccess(user);
  const concreteCount = countConcretePermissions(permissions);

  const backLink = (
    <Link
      href="/admin"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
        arrow_back
      </span>
      Back to Dashboard
    </Link>
  );

  // AdminGuard already blocks unauthenticated access and non-management users,
  // so this only covers the brief window while the session is being restored.
  if (isLoading || !user) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="flex items-center justify-center py-24" aria-busy="true">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      </div>
    );
  }

  const fullName = `${user.first_name} ${user.last_name}`.trim();
  const displayName = profile?.display_name?.trim() || fullName || user.username;
  const roleLabel = getManagementRoleLabel(user);
  const initial = (displayName[0] || "A").toUpperCase();
  const balance = wallet?.balance ?? null;
  const canGivePoints =
    hasAnyPermission(user, ADMIN_PERMISSIONS.pointsCredit) && canViewSellers(user);
  const showLedgerLink = user.is_staff && (wallet?.transaction_count ?? 0) > 0;

  let tileCaption: React.ReactNode = "Points you can give to sellers.";
  const nextExpiry = wallet?.points_expire ? wallet.upcoming_expiries[0] : undefined;
  if (wallet && wallet.balance === 0) {
    tileCaption = wallet.can_mint
      ? "No points yet. As a superuser you create them with utils/add_points.py."
      : "No points yet. A superuser sends staff the points they give to sellers.";
  } else if (nextExpiry) {
    tileCaption = `Points you can give to sellers. ${formatCount(nextExpiry.points)} pts expire on ${formatDate(nextExpiry.expires_at)}.`;
  }

  return (
    <div className="space-y-6">
      {backLink}

      {/* Hero: who you are, beside what you can give */}
      <section aria-labelledby="profile-name" className={`${CARD} overflow-hidden`}>
        <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
          <div className="flex flex-col justify-center gap-5 min-w-0">
            <div className="flex flex-col sm:flex-row sm:items-start gap-4 min-w-0">
              {profile?.avatar ? (
                <Image
                  src={formatImageUrl(profile.avatar)}
                  alt=""
                  width={80}
                  height={80}
                  className="w-20 h-20 shrink-0 rounded-2xl object-cover border border-line"
                />
              ) : (
                <div
                  aria-hidden="true"
                  className="w-20 h-20 shrink-0 rounded-2xl bg-primary/10 text-primary flex items-center justify-center font-black text-3xl border border-primary/20"
                >
                  {initial}
                </div>
              )}

              <div className="min-w-0">
                <ul aria-label="Access" className="flex flex-wrap gap-1.5">
                  <li className="inline-flex items-center gap-1 min-h-7 px-2.5 rounded-full text-[11px] font-extrabold bg-primary/10 text-primary border border-primary/20">
                    <span aria-hidden="true" className="material-symbols-outlined" style={ICON_16}>
                      {user.is_superuser ? "workspace_premium" : "shield_person"}
                    </span>
                    {roleLabel}
                  </li>
                  {user.is_staff && (
                    <li className="inline-flex items-center min-h-7 px-2.5 rounded-full text-[11px] font-extrabold bg-surface-alt text-ink-body border border-line">
                      Staff
                    </li>
                  )}
                  {roles
                    .map(formatRoleLabel)
                    .filter((label) => label !== roleLabel)
                    .map((label) => (
                      <li
                        key={label}
                        className="inline-flex items-center min-h-7 px-2.5 rounded-full text-[11px] font-extrabold bg-surface-alt text-ink-body border border-line"
                      >
                        {label}
                      </li>
                    ))}
                </ul>
                <h1
                  id="profile-name"
                  className="mt-2.5 text-2xl sm:text-3xl font-black text-ink tracking-tight break-words"
                >
                  <span className="sr-only">My profile: </span>
                  {displayName}
                </h1>
                <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-muted">
                  <MetaItem icon="alternate_email">{user.username}</MetaItem>
                  {user.email && <MetaItem icon="mail">{user.email}</MetaItem>}
                  {profile?.phone && <MetaItem icon="call">{profile.phone}</MetaItem>}
                </ul>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 sm:pl-24">
              <Link href="/profile/settings" className={SECONDARY_BUTTON}>
                <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
                  edit
                </span>
                Edit details
              </Link>
              {user.is_staff && (
                <a href={DJANGO_ADMIN_PROFILE_URL} className={SECONDARY_BUTTON}>
                  <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
                    open_in_new
                  </span>
                  Django admin profile
                </a>
              )}
            </div>
          </div>

          <PointsBalanceTile
            balance={balance}
            loading={walletLoading && !wallet}
            error={walletError}
            onRetry={retryWallet}
            caption={tileCaption}
            headerAction={
              wallet && !walletError ? (
                <a href="#points" className={POINTS_TILE_HEADER_LINK}>
                  History
                  <span aria-hidden="true" className="material-symbols-outlined" style={ICON_16}>
                    south
                  </span>
                </a>
              ) : null
            }
          >
            {canGivePoints && (balance ?? 0) > 0 && (
              <div className="mt-1">
                <Link href="/admin/sellers" className={POINTS_TILE_PRIMARY_ACTION}>
                  <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
                    storefront
                  </span>
                  Give points to a seller
                </Link>
              </div>
            )}
          </PointsBalanceTile>
        </div>

        <dl className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-line border-t border-line">
          <HeroStat icon="badge" tone="primary" label="Roles" value={formatCount(roles.length)} />
          <HeroStat
            icon="verified_user"
            tone="success"
            label={fullAccess ? `${formatCount(concreteCount)} permissions` : "Permissions"}
            value={fullAccess ? "All" : formatCount(concreteCount)}
          />
          <HeroStat icon="category" tone="primary" label="Domains" value={formatCount(groups.length)} />
          <HeroStat
            icon="storefront"
            tone="accent"
            label="Points given to sellers"
            value={wallet ? formatCount(wallet.given_to_sellers) : "—"}
          />
        </dl>
      </section>

      {/* Points wallet */}
      <section id="points" aria-labelledby="points-title" className={`${CARD} p-5 sm:p-6 scroll-mt-24`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="points-title" className={CARD_TITLE}>
              Points wallet
            </h2>
            <p className="text-xs text-ink-muted mt-1">
              Points start with a superuser, pass to staff, and staff give them to sellers.
            </p>
          </div>
          {showLedgerLink && (
            <a
              href={`${DJANGO_ADMIN_PROFILE_URL}#points`}
              className="inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Full ledger
              <span aria-hidden="true" className="material-symbols-outlined" style={ICON_16}>
                open_in_new
              </span>
            </a>
          )}
        </div>

        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          <WalletFigure label="Received" value={wallet?.received} loading={walletLoading && !wallet} />
          <WalletFigure
            label="Given to sellers"
            value={wallet?.given_to_sellers}
            loading={walletLoading && !wallet}
          />
          <WalletFigure
            label="Sent to staff"
            value={wallet?.sent_to_staff}
            loading={walletLoading && !wallet}
          />
          <WalletFigure
            label="Taken back by a superuser"
            value={wallet?.taken_back}
            loading={walletLoading && !wallet}
          />
        </dl>

        <div className="mt-6">
          <h3 className="text-[11px] font-extrabold uppercase tracking-wider text-ink-muted mb-3">
            Recent movements
          </h3>
          {walletLoading && !wallet ? (
            <div className="space-y-3" aria-hidden="true">
              {[0, 1, 2].map((key) => (
                <div key={key} className="h-12 rounded-xl bg-surface-alt animate-pulse" />
              ))}
            </div>
          ) : walletError ? (
            <p className="text-xs text-ink-muted">Movements appear here once your points load.</p>
          ) : movements.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl border border-dashed border-line bg-surface-alt/40 p-4">
              <span
                aria-hidden="true"
                className="material-symbols-outlined w-10 h-10 shrink-0 rounded-xl bg-accent/15 text-accent flex items-center justify-center"
              >
                savings
              </span>
              <div className="min-w-0">
                <p className="text-xs font-bold text-ink">Nothing has moved through your wallet yet</p>
                <p className="text-[11px] text-ink-muted mt-0.5 leading-relaxed">
                  {wallet?.can_mint
                    ? "Create points with utils/add_points.py, then pass some to staff or give them to a seller from the seller's page."
                    : "When a superuser sends you points they land here, and so does every credit you give a seller."}
                </p>
              </div>
            </div>
          ) : (
            <>
              <PointMovementList rows={movements} label="Recent wallet movements" />
              {wallet && wallet.transaction_count > movements.length && (
                <p className="text-[11px] text-ink-muted mt-4 pt-3 border-t border-line-subtle">
                  Showing the latest {movements.length} of {formatCount(wallet.transaction_count)} movements.
                </p>
              )}
            </>
          )}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Account */}
        <section aria-labelledby="account-title" className={`${CARD} p-5 sm:p-6`}>
          <h2 id="account-title" className={`${CARD_TITLE} mb-3`}>
            Account
          </h2>
          <dl>
            <InfoRow label="User ID" value={`#${user.id}`} />
            <InfoRow label="Username" value={user.username} />
            <InfoRow label="Email" value={user.email} />
            <InfoRow label="Name" value={fullName} />
            <InfoRow label="Display name" value={profile?.display_name} />
            <InfoRow label="Phone" value={profile?.phone} />
          </dl>
        </section>

        {/* Management access */}
        <section aria-labelledby="access-title" className={`${CARD} p-5 sm:p-6`}>
          <h2 id="access-title" className={`${CARD_TITLE} mb-3`}>
            Management access
          </h2>
          <ul className="space-y-3 text-xs">
            <AccessLine
              granted={isManagementUser(user)}
              label="Management portal access"
              detail="The same check the console's route guard uses."
            />
            <AccessLine granted={user.is_staff} label="Django staff" detail="is_staff on the account." />
            <AccessLine
              granted={user.is_superuser}
              label="Superuser"
              detail="Bypasses every backend permission check."
            />
          </ul>
        </section>
      </div>

      {/* Roles & permissions */}
      <section aria-labelledby="perm-title" className={`${CARD} p-5 sm:p-6`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
          <h2 id="perm-title" className={CARD_TITLE}>
            Roles &amp; permissions
          </h2>
          <p className="text-[11px] text-ink-muted">
            {formatCount(concreteCount)} permissions across {formatCount(groups.length)} domains
          </p>
        </div>

        {roles.length === 0 ? (
          <p className="text-xs text-ink-muted mb-5">
            No roles assigned.
            {user.is_superuser
              ? " This account is a Django superuser, which bypasses role checks entirely."
              : ""}
          </p>
        ) : (
          <ul aria-label="Roles" className="flex flex-wrap gap-2 mb-5">
            {roles.map((role) => (
              <li key={role} className="rounded-xl border border-line bg-surface-alt/40 px-3 py-2">
                <p className="text-xs font-bold text-ink">{formatRoleLabel(role)}</p>
                <p className="text-[10px] font-mono text-ink-muted">{role}</p>
              </li>
            ))}
          </ul>
        )}

        {fullAccess && (
          <div className="flex items-start gap-3 rounded-xl border border-success/25 bg-success/10 px-4 py-3 mb-5">
            <span aria-hidden="true" className="material-symbols-outlined text-success shrink-0">
              verified_user
            </span>
            <div className="min-w-0">
              <p className="text-xs font-extrabold text-success">Full platform access</p>
              <p className="text-[11px] text-ink-body mt-0.5">
                This account holds the{" "}
                <code className="font-mono bg-success/15 px-1 rounded">{WILDCARD_PERMISSION}</code>{" "}
                wildcard, so every backend permission check passes whatever the individual grants
                below say.
              </p>
            </div>
          </div>
        )}

        {concreteCount === 0 ? (
          <p className="text-xs text-ink-muted">
            {fullAccess
              ? "No individual permission codes are listed, but the wildcard above grants full access."
              : "No permissions assigned."}
          </p>
        ) : fullAccess ? (
          <details className="group rounded-xl border border-line">
            <summary className="flex items-center justify-between gap-3 cursor-pointer list-none px-4 py-3 text-xs font-bold text-ink hover:bg-surface-alt/50 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
              <span>
                Browse all {formatCount(concreteCount)} permissions
              </span>
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-ink-muted transition-transform group-open:rotate-180"
              >
                expand_more
              </span>
            </summary>
            <div className="border-t border-line p-4">
              <PermissionGrid groups={groups} />
            </div>
          </details>
        ) : (
          <PermissionGrid groups={groups} />
        )}

        <p className="text-[11px] text-ink-faint mt-5">
          This is what the backend reported for this session, shown for reference. The backend
          re-checks every request and stays the only authority.
        </p>
      </section>
    </div>
  );
}

function MetaItem({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <li className="inline-flex items-center gap-1.5 min-w-0 break-all">
      <span aria-hidden="true" className="material-symbols-outlined text-ink-faint" style={ICON_16}>
        {icon}
      </span>
      {children}
    </li>
  );
}

function HeroStat({
  icon,
  tone,
  label,
  value,
}: {
  icon: string;
  tone: keyof typeof STAT_TONES;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-surface flex items-center gap-3 px-4 sm:px-5 py-4 min-w-0">
      <span
        aria-hidden="true"
        className={`material-symbols-outlined w-10 h-10 shrink-0 rounded-xl flex items-center justify-center ${STAT_TONES[tone]}`}
      >
        {icon}
      </span>
      <div className="flex flex-col-reverse min-w-0">
        <dt className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted leading-snug break-words">
          {label}
        </dt>
        <dd className="text-lg font-black text-ink leading-tight tabular-nums">{value}</dd>
      </div>
    </div>
  );
}

function WalletFigure({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface-alt/60 border border-line-subtle px-4 py-3 flex flex-col-reverse">
      <dt className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">{label}</dt>
      <dd className="text-xl font-black text-ink tabular-nums leading-tight">
        {loading ? (
          <span className="block h-6 w-16 rounded-md bg-surface-sunken animate-pulse" />
        ) : (
          <>
            {value === undefined ? "—" : formatCount(value)}
            <span className="text-xs font-bold text-ink-muted ml-1">pts</span>
          </>
        )}
      </dd>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line-subtle last:border-0 text-xs">
      <dt className="sm:w-28 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className={`min-w-0 break-words ${empty ? "text-ink-faint" : "text-ink font-medium"}`}>
        {empty ? "Not set" : value}
      </dd>
    </div>
  );
}

function AccessLine({
  granted,
  label,
  detail,
}: {
  granted: boolean;
  label: string;
  detail: string;
}) {
  return (
    <li className="flex items-start gap-2.5">
      <span
        aria-hidden="true"
        className={`material-symbols-outlined shrink-0 ${granted ? "text-success" : "text-ink-faint"}`}
      >
        {granted ? "check_circle" : "cancel"}
      </span>
      <span className="min-w-0">
        <span className={`font-bold ${granted ? "text-ink" : "text-ink-muted"}`}>{label}</span>
        <span className="sr-only">{granted ? " — granted" : " — not granted"}</span>
        <span className="block text-[11px] text-ink-muted mt-0.5">{detail}</span>
      </span>
    </li>
  );
}

function PermissionGrid({ groups }: { groups: PermissionGroup[] }) {
  return (
    // Columns rather than a grid, so a 1-code domain is not stretched to the
    // height of an 8-code one beside it.
    <div className="columns-1 sm:columns-2 xl:columns-3 gap-4">
      {groups.map((group) => (
        <section
          key={group.key}
          aria-label={`${group.label} permissions`}
          className="rounded-xl border border-line p-3.5 mb-4 break-inside-avoid"
        >
          <h3 className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-2 flex items-center justify-between gap-2">
            <span>{group.label}</span>
            <span className="text-ink-faint font-bold">{group.codes.length}</span>
          </h3>
          <ul className="space-y-1">
            {group.codes.map((code) => (
              <li key={code} className="flex items-start gap-1.5 text-[11px]">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-success shrink-0"
                  style={ICON_16}
                >
                  check
                </span>
                <code className="font-mono text-ink break-all">{code}</code>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
