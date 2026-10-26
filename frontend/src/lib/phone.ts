/**
 * Bangladeshi mobile numbers, the sign-in identifier beside the username.
 *
 * Mirrors `backend/rbac/phone.py`. The server decides what is a valid number;
 * this only lets a form catch a typo before sending the request.
 */

const BENGALI_DIGITS = "০১২৩৪৫৬৭৮৯";
/** Spaces, dashes, dots and brackets people put inside a number. */
const SEPARATORS = /[\s\-.()]/g;
/** An operator prefix 013-019 and eight more digits, with or without the country code 88. */
const BD_MOBILE = /^(?:\+?88)?(01[3-9][0-9]{8})$/;

/**
 * The E.164 form ("+8801712345678") of a Bangladeshi mobile number written
 * any of the usual ways, Bengali digits included, or null when it is not one.
 */
export function normalizeBangladeshiMobile(value: string): string | null {
  const ascii = value.replace(/[০-৯]/g, (digit) => String(BENGALI_DIGITS.indexOf(digit)));
  const match = BD_MOBILE.exec(ascii.replace(SEPARATORS, ""));
  return match ? `+88${match[1]}` : null;
}

/** "+8801712345678" -> "01712345678", the way people in Bangladesh write it. */
export function formatBangladeshiMobile(number: string): string {
  return number.startsWith("+88") ? number.slice(3) : number;
}
