/**
 * Reads the stored JWT access token. The legacy key fallbacks exist because
 * earlier builds wrote the token under different names.
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return (
    localStorage.getItem("minishop_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    null
  );
}
