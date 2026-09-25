"use client";

import React, { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { RouteSpinner } from "@/components/feedback";
import CustomerLocationControl from "@/components/location/CustomerLocationControl";
import NearbyRadiusPicker from "@/components/shops/NearbyRadiusPicker";
import NearbyShopCard, { NearbyShopCardSkeleton } from "@/components/shops/NearbyShopCard";
import NearbyShopsMap from "@/components/shops/NearbyShopsMap";
import { useCustomerLocation } from "@/context/LocationContext";
import {
  NEARBY_QUERY_MAX_LENGTH,
  NEARBY_RADIUS_OPTIONS,
  getCategories,
  getNearbyShops,
  parseNearbyRadius,
} from "@/lib/api";
import { Category, NearbyShopsResponse } from "@/lib/types";

/**
 * /shops/nearby?q=<product>&radius=<km> — public shops near the customer's
 * current location, optionally only those selling a matching product.
 *
 * The product search and radius live in the URL (back button, shareable). The
 * coordinates never do: they come from LocationContext, in memory only.
 */
export default function NearbyShopsPage() {
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    getCategories().then(setCategories);
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      {/* Sticky Top Navigation Bar (Header + Category Strip) */}
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar categories={categories} />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full flex flex-col gap-5">
        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/" className="hover:text-primary transition-colors">
            Home
          </Link>
          <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
            chevron_right
          </span>
          <Link href="/shops" className="hover:text-primary transition-colors">
            Shops
          </Link>
          <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
            chevron_right
          </span>
          <span className="text-ink font-medium" aria-current="page">
            Nearby
          </span>
        </nav>

        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px] text-accent">
            near_me
          </span>
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink tracking-tight">Nearby Shops</h1>
            <p className="text-xs sm:text-sm text-ink-body mt-0.5">
              Shops closest to where you are right now. Search for a product to see which of them
              have it.
            </p>
          </div>
        </div>

        {/* useSearchParams() needs a Suspense boundary for the static build. */}
        <Suspense fallback={<RouteSpinner label="Loading nearby shops…" />}>
          <NearbyShopsExplorer />
        </Suspense>
      </main>

      <Footer />
    </div>
  );
}

interface NearbyResult {
  key: string;
  data: NearbyShopsResponse | null;
  error: string | null;
}

function requestKeyFor(lat: number, lng: number, radius: number, q: string, attempt: number) {
  return JSON.stringify([lat, lng, radius, q, attempt]);
}

/** The page URL for a product search and radius; a blank search is left out. */
function nearbyUrl(radius: number, q: string) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("radius", String(radius));
  return `/shops/nearby?${params.toString()}`;
}

function NearbyShopsExplorer() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const radius = parseNearbyRadius(searchParams.get("radius"));
  const q = (searchParams.get("q") ?? "").trim().slice(0, NEARBY_QUERY_MAX_LENGTH);
  const { status, position, error, permission, requestLocation } = useCustomerLocation();

  // Locate on arrival only when the browser won't show a prompt for it (D6).
  // At most once per visit, and never once a position has been seen here, so
  // "Clear" isn't undone a moment later.
  const autoLocated = useRef(false);
  useEffect(() => {
    if (position) autoLocated.current = true;
    if (autoLocated.current || permission !== "granted") return;
    autoLocated.current = true;
    requestLocation();
  }, [permission, position, requestLocation]);

  const lat = position?.latitude;
  const lng = position?.longitude;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<NearbyResult | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // One request per (location, radius, search, retry). Changing any of them
  // quickly aborts the stale request; its late response can never overwrite a newer one.
  useEffect(() => {
    if (lat === undefined || lng === undefined) return;
    const key = requestKeyFor(lat, lng, radius, q, attempt);
    const controller = new AbortController();
    getNearbyShops({ latitude: lat, longitude: lng, radiusKm: radius, q }, controller.signal)
      .then((data) => setResult({ key, data, error: null }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setResult({
          key,
          data: null,
          error: err instanceof Error ? err.message : "Nearby shops couldn't be loaded.",
        });
      });
    return () => controller.abort();
  }, [lat, lng, radius, q, attempt]);

  const requestKey =
    lat === undefined || lng === undefined ? null : requestKeyFor(lat, lng, radius, q, attempt);
  const current = result && result.key === requestKey ? result : null;
  const loading = requestKey !== null && current === null;
  const shops = current?.data?.results ?? [];
  const selectedShopId = shops.some((s) => s.id === selectedId) ? selectedId : null;

  const mapRef = useRef<HTMLDivElement>(null);
  const isDesktop = () => window.matchMedia("(min-width: 1024px)").matches;

  // Marker → card: on desktop the list is beside the map, so bring the card
  // into view. On smaller screens the list is below the map; the marker's
  // popup already shows the shop, so the page stays where it is.
  const selectFromMap = useCallback((shopId: number | null) => {
    setSelectedId(shopId);
    if (shopId !== null && isDesktop()) {
      document
        .getElementById(`nearby-shop-${shopId}`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, []);

  // Card → map: on smaller screens the map is above the list, so scroll up to it.
  const showOnMap = useCallback((shopId: number) => {
    setSelectedId(shopId);
    if (!isDesktop()) mapRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, []);

  const changeRadius = (next: number) => {
    router.replace(nearbyUrl(next, q), { scroll: false });
  };

  // A new search is a step the back button should undo; a radius change is not.
  const changeQuery = (next: string) => {
    router.push(nearbyUrl(radius, next.trim()), { scroll: false });
  };

  const widerRadius = NEARBY_RADIUS_OPTIONS.find((km) => km > radius);

  // Location changes are announced by CustomerLocationControl; this covers results.
  let announcement = "";
  if (loading) announcement = `Loading shops within ${radius} km…`;
  else if (current?.error) announcement = current.error;
  else if (current?.data) announcement = resultSummary(current.data, radius, q);

  return (
    <>
      <section
        aria-label="Search settings"
        className="bg-surface border border-line rounded-2xl shadow-xs p-4 sm:p-5 flex flex-col gap-4"
      >
        {/* Keyed on q so the box shows the URL's search again after back/forward. */}
        <NearbyProductSearch key={q} initialQuery={q} onSearch={changeQuery} />
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 pt-4 border-t border-line-subtle">
          <div className="min-w-0 flex-1">
            <CustomerLocationControl showStartActions={false} />
          </div>
          <NearbyRadiusPicker value={radius} onChange={changeRadius} />
        </div>
      </section>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {!position ? (
        status === "locating" ? (
          <ResultsSkeleton />
        ) : error ? (
          <LocationProblem />
        ) : (
          <LocationPrompt q={q} />
        )
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Map first on small screens; beside the list (and sticky) on desktop. */}
          <div ref={mapRef} className="lg:col-span-7 lg:order-2 lg:sticky lg:top-32 scroll-mt-32">
            <NearbyShopsMap
              center={position}
              radiusKm={radius}
              shops={shops}
              selectedShopId={selectedShopId}
              onSelectShop={selectFromMap}
              className="h-72 sm:h-96 lg:h-[calc(100dvh-10rem)] lg:min-h-105 lg:max-h-190"
            />
          </div>

          <div className="lg:col-span-5 lg:order-1 min-w-0">
            {loading ? (
              <ResultsSkeleton />
            ) : current?.error ? (
              <StateCard
                icon="cloud_off"
                tone="danger"
                title="Couldn't load nearby shops"
                body={current.error}
                action={
                  <button type="button" onClick={() => setAttempt((n) => n + 1)} className={PRIMARY_BUTTON}>
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      refresh
                    </span>
                    Retry
                  </button>
                }
              />
            ) : current?.data && current.data.results.length === 0 ? (
              <StateCard
                icon={q ? "search_off" : "wrong_location"}
                title={q ? `No shops within ${radius} km have “${q}”` : `No shops within ${radius} km`}
                body={
                  q
                    ? "Try a wider area, a shorter search (one word often finds more), or see every shop nearby."
                    : "No shop on MiniShop has a location inside this area yet."
                }
                action={
                  <>
                    {widerRadius && (
                      <button type="button" onClick={() => changeRadius(widerRadius)} className={PRIMARY_BUTTON}>
                        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                          zoom_out_map
                        </span>
                        Search within {widerRadius} km
                      </button>
                    )}
                    {q ? (
                      <button type="button" onClick={() => changeQuery("")} className={SECONDARY_LINK}>
                        Show all nearby shops
                      </button>
                    ) : (
                      <Link href="/shops" className={SECONDARY_LINK}>
                        Browse all shops
                      </Link>
                    )}
                  </>
                }
              />
            ) : current?.data ? (
              <div className="flex flex-col gap-3">
                <p className="text-sm font-semibold text-ink-body">{resultSummary(current.data, radius, q)}</p>
                <ol className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-3">
                  {shops.map((shop, index) => (
                    <li key={shop.id}>
                      <NearbyShopCard
                        shop={shop}
                        rank={index + 1}
                        selected={shop.id === selectedShopId}
                        onSelect={setSelectedId}
                        onShowOnMap={showOnMap}
                      />
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}

function resultSummary(data: NearbyShopsResponse, radius: number, q: string) {
  const shown = data.results.length;
  const noun = data.count === 1 ? "shop" : "shops";
  const scope = q ? ` that ${data.count === 1 ? "has" : "have"} “${q}”` : "";
  if (data.count > shown) {
    return `Showing the nearest ${shown} of ${data.count} ${noun} within ${radius} km${scope}`;
  }
  return `${data.count} ${noun} within ${radius} km${scope}`;
}

/** "What are you looking for?": the product half of the search. Blank shows every nearby shop. */
function NearbyProductSearch({
  initialQuery,
  onSearch,
}: {
  initialQuery: string;
  onSearch: (q: string) => void;
}) {
  const [value, setValue] = useState(initialQuery);

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(value);
      }}
      className="flex flex-col gap-1.5"
    >
      <label
        htmlFor="nearby-product-search"
        className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted"
      >
        What are you looking for?
      </label>
      <div className="flex gap-2">
        <div className="relative flex-1 min-w-0">
          <span
            aria-hidden="true"
            className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-ink-muted"
          >
            search
          </span>
          <input
            id="nearby-product-search"
            type="search"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={NEARBY_QUERY_MAX_LENGTH}
            placeholder="A product, e.g. Task Desk Lamp"
            className="w-full rounded-lg border border-line bg-surface-sunken py-2.5 pl-9 pr-9 text-sm text-ink placeholder-ink-faint focus:outline-hidden focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary [&::-webkit-search-cancel-button]:hidden"
          />
          {value && (
            <button
              type="button"
              onClick={() => {
                setValue("");
                if (initialQuery) onSearch("");
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 flex h-6 w-6 items-center justify-center rounded-full text-ink-muted hover:bg-surface-alt hover:text-ink cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                close
              </span>
              <span className="sr-only">Clear product search</span>
            </button>
          )}
        </div>
        <button type="submit" className={PRIMARY_BUTTON}>
          <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
            travel_explore
          </span>
          <span className="hidden sm:inline">Find nearby</span>
          <span className="sm:hidden">Find</span>
        </button>
      </div>
    </form>
  );
}

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

const SECONDARY_LINK =
  "inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg border border-line bg-surface hover:bg-surface-alt text-xs font-bold text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function StateCard({
  icon,
  title,
  body,
  action,
  tone = "neutral",
}: {
  icon: string;
  title: string;
  body: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "danger";
}) {
  return (
    <div className="bg-surface border border-line rounded-2xl shadow-xs px-6 py-12 flex flex-col items-center text-center gap-3">
      <span
        aria-hidden="true"
        className={`w-14 h-14 rounded-2xl flex items-center justify-center ${
          tone === "danger" ? "bg-danger/10 text-danger" : "bg-primary/10 text-primary"
        }`}
      >
        <span className="material-symbols-outlined text-[30px]">{icon}</span>
      </span>
      <h2 className="text-lg font-bold text-ink">{title}</h2>
      <div className="text-sm text-ink-body max-w-md leading-relaxed">{body}</div>
      {action && <div className="mt-2 flex flex-col sm:flex-row items-center gap-2">{action}</div>}
    </div>
  );
}

/** No location yet, and nothing has been asked: explain, then let the customer choose. */
function LocationPrompt({ q }: { q: string }) {
  const { requestLocation } = useCustomerLocation();
  return (
    <StateCard
      icon="location_searching"
      title={q ? `Find “${q}” near you` : "Find shops near you"}
      body={
        <>
          <p>
            {q
              ? "Share your current location to see which shops close to you have it, how far away they are, and where they are on a map."
              : "Share your current location to see the closest shops, how far away they are, and where they are on a map."}
          </p>
          <p className="mt-2 text-xs text-ink-muted">
            Your location is only used for this search. It isn&apos;t saved to your account or
            anywhere else.
          </p>
        </>
      }
      action={
        <>
          <button type="button" onClick={() => requestLocation()} className={PRIMARY_BUTTON}>
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              my_location
            </span>
            Use My Current Location
          </button>
          <Link href="/shops" className={SECONDARY_LINK}>
            Browse all shops
          </Link>
        </>
      }
    />
  );
}

/** Locating failed and there is no earlier position to fall back on. */
function LocationProblem() {
  const { error, requestLocation } = useCustomerLocation();
  if (!error) return null;

  const help: Record<string, string> = {
    denied:
      "To allow it, open your browser's site settings (usually the icon next to the address), set Location to Allow, then try again.",
    insecure: "This page was opened over plain http. Open it over https:// (or on localhost) to use your location.",
    unsupported: "You can still browse every shop on MiniShop.",
    unavailable: "Make sure location services are on for your device and browser.",
    timeout: "A weak GPS or network signal can cause this.",
  };
  const canRetry = error.kind !== "unsupported" && error.kind !== "insecure";

  return (
    <StateCard
      icon="location_off"
      tone="danger"
      title="We couldn't get your location"
      body={
        <>
          <p>{error.message}</p>
          <p className="mt-2 text-xs text-ink-muted">{help[error.kind]}</p>
        </>
      }
      action={
        <>
          {canRetry && (
            <button type="button" onClick={() => requestLocation()} className={PRIMARY_BUTTON}>
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try again
            </button>
          )}
          <Link href="/shops" className={SECONDARY_LINK}>
            Browse all shops
          </Link>
        </>
      }
    />
  );
}

function ResultsSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-3">
      <div className="h-4 w-40 rounded bg-surface-alt animate-pulse" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <NearbyShopCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
