/**
 * Client-side mirror of app/core/masking.py. The API enforces the same rules; this gives instant,
 * friendly feedback before anything leaves the browser.
 */

export const WHY =
  "family-vault only needs the last 4 characters to help your family find the right account. " +
  "Never store full account numbers, ID numbers, passwords, PINs or OTPs here.";

const VISIBLE = /^[A-Za-z0-9]{1,4}$/;
const DATES = /\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b/g;
const DIGIT_RUN = /(?:\d[ -]?){6,}/;
const PAN = /\b[A-Za-z]{5}\d{4}[A-Za-z]\b/;
const SECRET =
  /\b(password|passwd|pwd|pass ?code|m?pin|upi ?pin|otp|cvv|cvc|net ?banking (login|password))\b(\s*(is|was|=|:|-)\s*\S+|\s+\S*\d\S*)/i;

export type Check = { ok: true; value: string } | { ok: false; reason: string };

export function checkMaskedId(value: string): Check {
  if (!value.trim()) return { ok: true, value: "" };
  const visible = value.trim().replace(/^[Xx*•#\-_ ]+/, "").replace(/[ -]/g, "");
  if (!VISIBLE.test(visible)) {
    const digits = (value.match(/\d/g) ?? []).length;
    if (digits > 4 || visible.length > 4) {
      return { ok: false, reason: "This looks like a full number. Enter only the last 4 characters." };
    }
    return { ok: false, reason: "Use letters/digits only, at most 4 visible characters (e.g. XXXX1234)." };
  }
  return { ok: true, value: `XXXX${visible.toUpperCase()}` };
}

export function checkFreeText(value: string): Check {
  if (SECRET.test(value)) return { ok: false, reason: "This looks like a password, PIN or OTP. Never store those." };
  if (PAN.test(value)) return { ok: false, reason: "This looks like a PAN number." };
  if (DIGIT_RUN.test(value.replace(DATES, " "))) {
    return { ok: false, reason: "This contains a long number (account, card or ID number?)." };
  }
  return { ok: true, value };
}
