"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Keeps only the newest of overlapping requests (BUG-073).
 *
 * Call the returned `begin()` as a request starts. The `isLatest()` it hands
 * back turns false once a newer request has begun or the component has
 * unmounted, so a slow, older response (say, for the filters the user has
 * just changed away from) cannot overwrite the newer one's results:
 *
 *   const isLatest = beginRequest();
 *   const data = await getThings(filters);
 *   if (!isLatest()) return;
 *   setThings(data);
 */
export function useLatestRequest(): () => () => boolean {
  const latest = useRef(0);

  useEffect(() => {
    const counter = latest;
    return () => {
      counter.current += 1;
    };
  }, []);

  return useCallback(() => {
    latest.current += 1;
    const id = latest.current;
    return () => id === latest.current;
  }, []);
}
