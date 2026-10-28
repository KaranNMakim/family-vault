/** RFC 6238 TOTP (HMAC-SHA1, 30 s, 6 digits) using Web Crypto — the same algorithm as Google/Microsoft Authenticator. */

const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
export const STEP = 30;

export function base32Decode(secret: string): Uint8Array {
  const clean = secret.replace(/[\s=]/g, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const ch of clean) {
    const idx = B32.indexOf(ch);
    if (idx < 0) throw new Error("invalid base32 secret");
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return new Uint8Array(out);
}

export async function totpCode(secret: string, nowMs: number = Date.now()): Promise<string> {
  const counter = Math.floor(nowMs / 1000 / STEP);
  const msg = new ArrayBuffer(8);
  const view = new DataView(msg);
  view.setUint32(0, Math.floor(counter / 2 ** 32));
  view.setUint32(4, counter >>> 0);
  const keyBytes = base32Decode(secret);
  const key = await crypto.subtle.importKey("raw", keyBytes.buffer.slice(0) as ArrayBuffer, { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, msg));
  const offset = mac[mac.length - 1] & 0x0f;
  const bin = ((mac[offset] & 0x7f) << 24) | (mac[offset + 1] << 16) | (mac[offset + 2] << 8) | mac[offset + 3];
  return String(bin % 1_000_000).padStart(6, "0");
}

export function secondsLeft(nowMs: number = Date.now()): number {
  return STEP - (Math.floor(nowMs / 1000) % STEP);
}
