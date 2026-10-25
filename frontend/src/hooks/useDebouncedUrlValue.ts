"use client";

import { useEffect, useState } from "react";

/**
 * A text filter kept in the URL (?search=...): the input updates as the user
 * types, and the URL follows once typing pauses for `delay` ms.
 *
 * - `commit` writes the value to the URL. Pass a callback built on the
 *   page's current updateParams, so a commit never rewrites the URL from an
 *   old snapshot and drops a filter changed meanwhile (BUG-074).
 * - When the URL changes from outside (back/forward, "Clear filters"), the
 *   input follows it. When it changes because this hook committed, it does
 *   not: the user may already have typed more while the navigation was in
 *   flight, and resetting the input would drop those keystrokes (BUG-117).
 */
export function useDebouncedUrlValue(
  urlValue: string,
  commit: (value: string) => void,
  delay = 350
): [string, (value: string) => void] {
  const [input, setInput] = useState(urlValue);
  const [syncedUrlValue, setSyncedUrlValue] = useState(urlValue);
  // Values this hook committed whose navigation has not arrived yet.
  const [pending, setPending] = useState<string[]>([]);

  // Adjusted during render, not in an effect, so no stale frame shows.
  if (urlValue !== syncedUrlValue) {
    setSyncedUrlValue(urlValue);
    const arrived = pending.indexOf(urlValue);
    if (arrived === -1) setInput(urlValue);
    else setPending(pending.slice(arrived + 1));
  }

  useEffect(() => {
    if (input === urlValue) return;
    const timer = setTimeout(() => {
      setPending((values) => [...values, input]);
      commit(input);
    }, delay);
    return () => clearTimeout(timer);
  }, [input, urlValue, commit, delay]);

  return [input, setInput];
}
