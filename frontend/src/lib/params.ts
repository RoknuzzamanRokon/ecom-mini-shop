/**
 * The page a `?page=` value asks for: a whole number from 1 up, else 1. A
 * negative or fractional value used to reach the API, which answers 404
 * "Invalid page." for good (BUG-118).
 */
export function pageNumber(raw: string | null | undefined): number {
  const page = Number(raw);
  return Number.isInteger(page) && page >= 1 ? page : 1;
}
