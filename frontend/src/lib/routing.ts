import { roundCoordinate } from "@/lib/geolocation";

/**
 * Road routes for the nearby-shops map, from an OSRM server.
 *
 * The default is FOSSGIS's public OSRM (the one openstreetmap.org's own
 * directions use): free, no key, attribution required, and a fair-use policy
 * that suits development and light traffic — like the OSM tile servers
 * (NearbyShopsMap.tsx). Point NEXT_PUBLIC_ROUTE_URL at another OSRM server for
 * heavy production use. `{mode}` becomes `foot` or `car`; `{from}` and `{to}`
 * become `lng,lat`.
 *
 * Privacy: a route request sends the customer's location and the shop's to
 * that server, so the map asks for one only after the customer picks a shop.
 */
const ROUTE_URL =
  process.env.NEXT_PUBLIC_ROUTE_URL ||
  "https://routing.openstreetmap.de/routed-{mode}/route/v1/driving/{from};{to}?overview=full&geometries=geojson";

export const ROUTE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_ROUTE_ATTRIBUTION ||
  'Routes &copy; <a href="https://project-osrm.org/">OSRM</a> / <a href="https://routing.openstreetmap.de/about.html">FOSSGIS</a>';

export type TravelMode = "foot" | "car";

export interface LatLng {
  latitude: number;
  longitude: number;
}

export interface RoadRoute {
  /** The road path as [lat, lng] pairs, from the road nearest the start to the road nearest the end. */
  path: [number, number][];
  distanceKm: number;
  durationMinutes: number;
}

interface OsrmResponse {
  code: string;
  message?: string;
  routes?: {
    distance: number;
    duration: number;
    geometry: { coordinates: [number, number][] };
  }[];
}

function lngLat(point: LatLng) {
  return `${roundCoordinate(point.longitude, 6)},${roundCoordinate(point.latitude, 6)}`;
}

/**
 * The shortest road route between two points. Throws a customer-facing
 * message when the server is unreachable or finds no route; an abort passes
 * through untouched.
 */
export async function getRoadRoute(
  from: LatLng,
  to: LatLng,
  mode: TravelMode,
  signal?: AbortSignal
): Promise<RoadRoute> {
  const url = ROUTE_URL.replace("{mode}", mode)
    .replace("{from}", lngLat(from))
    .replace("{to}", lngLat(to));

  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", signal });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new Error("The route service couldn't be reached.");
  }

  const data = (await res.json().catch(() => null)) as OsrmResponse | null;
  const route = data?.code === "Ok" ? data.routes?.[0] : undefined;
  if (!route || route.geometry.coordinates.length < 2) {
    throw new Error(
      data?.code === "NoRoute" || data?.code === "NoSegment"
        ? "No road route was found to this shop."
        : "The route couldn't be loaded."
    );
  }

  return {
    // GeoJSON is [lng, lat]; Leaflet wants [lat, lng].
    path: route.geometry.coordinates.map(([lng, lat]) => [lat, lng]),
    distanceKm: route.distance / 1000,
    durationMinutes: route.duration / 60,
  };
}

/** "25 min" / "1 h 5 min", rounded up to whole minutes. */
export function formatDuration(minutes: number): string {
  const total = Math.max(1, Math.ceil(minutes));
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
