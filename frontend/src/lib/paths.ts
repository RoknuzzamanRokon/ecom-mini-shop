/**
 * One value placed in an API URL path (BUG-093, TASK-045), encoded so that a
 * "/", "?" or "#" in it stays inside its own segment. A segment that is
 * empty, "." or ".." is refused: the URL parser would drop it or climb a
 * level ("%2e%2e" too), so the request would reach another endpoint.
 */
export function pathSegment(value: string | number): string {
  const text = String(value);
  if (text === "" || text === "." || text === "..") {
    throw new Error(`"${text}" cannot be used as a path segment.`);
  }
  return encodeURIComponent(text);
}
