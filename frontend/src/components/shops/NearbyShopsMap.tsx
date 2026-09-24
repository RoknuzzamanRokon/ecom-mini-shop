"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { DivIcon, LayerGroup, Map as LeafletMap, Marker } from "leaflet";
import "leaflet/dist/leaflet.css";
import { formatDistance } from "@/lib/geolocation";
import { NearbyShop } from "@/lib/types";

type Leaflet = typeof import("leaflet");

// OpenStreetMap's own tile servers: free, no key, attribution required, and a
// fair-use policy that suits development and light traffic. Point these two at
// another tile provider for heavy production use — no code change needed.
const TILE_URL =
  process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

interface NearbyShopsMapProps {
  center: { latitude: number; longitude: number; accuracy: number };
  radiusKm: number;
  /** In list order; marker numbers match the list's ranks. */
  shops: NearbyShop[];
  selectedShopId: number | null;
  /** A marker was clicked (the shop's id), or its popup was closed (null). */
  onSelectShop: (shopId: number | null) => void;
  className?: string;
}

/**
 * Interactive map of nearby-shop results (Leaflet + OpenStreetMap tiles).
 *
 * Leaflet touches `window` when it is imported, so it is loaded inside an
 * effect rather than at module level; the page still prerenders. The map is
 * never the only way to read the results: the list beside it holds the same
 * shops, in the same order, with the same numbers.
 *
 * Moving or zooming the map never refetches anything.
 */
export default function NearbyShopsMap({
  center,
  radiusKm,
  shops,
  selectedShopId,
  onSelectShop,
  className = "",
}: NearbyShopsMapProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [leaflet, setLeaflet] = useState<{ L: Leaflet; map: LeafletMap } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const markersRef = useRef(new Map<number, Marker>());
  const onSelectRef = useRef(onSelectShop);
  const selectedRef = useRef(selectedShopId);

  useEffect(() => {
    onSelectRef.current = onSelectShop;
  }, [onSelectShop]);

  // 1. Create the map once.
  useEffect(() => {
    let cancelled = false;
    let map: LeafletMap | null = null;

    import("leaflet")
      .then((mod) => {
        const L = ((mod as { default?: Leaflet }).default ?? mod) as Leaflet;
        if (cancelled || !containerRef.current) return;
        map = L.map(containerRef.current, {
          // Scroll-wheel zoom only once the map has focus, so scrolling the
          // page past it never gets captured.
          scrollWheelZoom: false,
          // Half levels let the radius circle fill a small phone-sized map
          // instead of snapping out to a whole zoom level with wasted margin.
          zoomSnap: 0.5,
        });
        L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION }).addTo(map);
        const created = map;
        created.on("focus", () => created.scrollWheelZoom.enable());
        created.on("blur", () => created.scrollWheelZoom.disable());
        setLeaflet({ L, map: created });
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });

    return () => {
      cancelled = true;
      map?.remove();
    };
  }, []);

  // 2. The customer, their accuracy circle and the search radius; fit to the radius.
  useEffect(() => {
    if (!leaflet) return;
    const { L, map } = leaflet;
    const here = L.latLng(center.latitude, center.longitude);
    const group: LayerGroup = L.layerGroup().addTo(map);

    L.circle(here, {
      radius: radiusKm * 1000,
      className: "nearby-map-radius",
      interactive: false,
    }).addTo(group);
    if (center.accuracy > 0) {
      L.circle(here, {
        radius: center.accuracy,
        className: "nearby-map-accuracy",
        interactive: false,
      }).addTo(group);
    }
    L.marker(here, {
      icon: L.divIcon({
        className: "nearby-map-me",
        html: "<span></span>",
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      }),
      interactive: false,
      keyboard: false,
      zIndexOffset: 1000,
    }).addTo(group);

    map.fitBounds(here.toBounds(radiusKm * 2000), { padding: [12, 12] });

    return () => {
      group.remove();
    };
  }, [leaflet, center.latitude, center.longitude, center.accuracy, radiusKm]);

  // 3. One numbered marker per shop, rebuilt whenever the results change.
  useEffect(() => {
    if (!leaflet) return;
    const { L, map } = leaflet;
    const group: LayerGroup = L.layerGroup().addTo(map);
    const markers = markersRef.current;
    markers.clear();

    shops.forEach((shop, index) => {
      if (shop.latitude == null || shop.longitude == null) return;
      const rank = index + 1;
      const marker = L.marker([shop.latitude, shop.longitude], {
        icon: shopPinIcon(L, rank),
        title: `${rank}. ${shop.name} — ${formatDistance(shop.distance_km)} away`,
        riseOnHover: true,
      });
      marker.bindPopup(() => popupContent(shop, (href) => router.push(href)), {
        autoPanPadding: [24, 24],
        maxWidth: 240,
      });
      marker.on("click", () => onSelectRef.current(shop.id));
      // Leaflet gives markers role="button" and opens the popup on Enter (via
      // keypress) but never fires "click" for it, and ignores Space. Select on
      // both, so keyboard users get what a click gives.
      marker.on("keypress", (event) => {
        if ((event.originalEvent as KeyboardEvent).key === "Enter") onSelectRef.current(shop.id);
      });
      marker.on("keydown", (event) => {
        const key = event.originalEvent as KeyboardEvent;
        if (key.key !== " ") return;
        key.preventDefault();
        // Open first, as Leaflet does for click and Enter: opening closes the
        // previous shop's popup, which clears that selection before this one.
        marker.openPopup();
        onSelectRef.current(shop.id);
      });
      // "Selected" means "its popup is open": closing the popup (×, or a click
      // on the map) clears the selection, so "Show on map" can open it again.
      // Opening another shop's popup closes this one first; the check keeps
      // that from clearing the new selection.
      marker.on("popupclose", () => {
        if (selectedRef.current === shop.id) onSelectRef.current(null);
      });
      marker.addTo(group);
      markers.set(shop.id, marker);
    });

    return () => {
      group.remove();
      markers.clear();
    };
  }, [leaflet, shops, router]);

  // 4. Selection (from the list or a marker): highlight its marker and open its popup.
  useEffect(() => {
    selectedRef.current = selectedShopId;
    if (!leaflet) return;
    markersRef.current.forEach((marker, id) => {
      const selected = id === selectedShopId;
      marker.getElement()?.classList.toggle("is-selected", selected);
      marker.setZIndexOffset(selected ? 500 : 0);
    });
    const marker = selectedShopId == null ? undefined : markersRef.current.get(selectedShopId);
    if (marker && !marker.isPopupOpen()) marker.openPopup();
  }, [leaflet, selectedShopId, shops]);

  // 5. Keep Leaflet's idea of its size in step with responsive layouts.
  useEffect(() => {
    const element = containerRef.current;
    if (!leaflet || !element) return;
    const observer = new ResizeObserver(() => leaflet.map.invalidateSize());
    observer.observe(element);
    return () => observer.disconnect();
  }, [leaflet]);

  return (
    // `isolate` keeps Leaflet's internal z-indexes (up to 1000) inside this box,
    // so the map can never paint over the sticky header.
    <div
      className={`relative isolate overflow-hidden rounded-2xl border border-line bg-surface-alt ${className}`}
    >
      <div
        ref={containerRef}
        role="region"
        aria-label="Map of nearby shops. The same shops are listed, in the same order, beside the map."
        className="nearby-map absolute inset-0"
      />
      {!leaflet && !loadFailed && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs font-semibold text-ink-muted">
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] animate-spin">
            progress_activity
          </span>
          Loading map…
        </div>
      )}
      {loadFailed && (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-xs text-ink-muted">
          The map couldn&apos;t be loaded. Every result is still in the list.
        </div>
      )}
    </div>
  );
}

function shopPinIcon(L: Leaflet, rank: number): DivIcon {
  return L.divIcon({
    className: "nearby-map-pin",
    // `rank` is a number, so this HTML never carries user data.
    html: `<span class="nearby-map-pin-body"><span class="nearby-map-pin-rank">${rank}</span></span>`,
    iconSize: [30, 38],
    iconAnchor: [15, 37],
    popupAnchor: [0, -34],
  });
}

/**
 * Popup body, built from DOM nodes: shop names and addresses are user data
 * and must never go through innerHTML. "View Shop" navigates client-side so
 * the in-memory location survives the trip. <div>s rather than <p>s, because
 * Leaflet's stylesheet gives popup paragraphs large margins.
 */
function popupContent(shop: NearbyShop, navigate: (href: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "nearby-map-popup";

  const title = document.createElement("div");
  title.className = "nearby-map-popup-title";
  title.textContent = shop.name;

  const meta = document.createElement("div");
  meta.className = "nearby-map-popup-meta";
  const rating =
    (shop.review_count ?? 0) > 0
      ? ` · ★ ${(shop.average_rating ?? 0).toFixed(1)} (${shop.review_count})`
      : "";
  meta.textContent = `${formatDistance(shop.distance_km)} away${rating}`;
  root.append(title, meta);

  if (shop.address) {
    const address = document.createElement("div");
    address.className = "nearby-map-popup-address";
    address.textContent = shop.address;
    root.append(address);
  }

  const href = `/shop/${encodeURIComponent(shop.slug)}`;
  const link = document.createElement("a");
  link.className = "nearby-map-popup-link";
  link.href = href;
  link.textContent = "View Shop →";
  link.addEventListener("click", (event) => {
    // Let modified clicks (new tab, new window) behave like any other link.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(href);
  });
  root.append(link);

  return root;
}
