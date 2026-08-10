import { compressToEncodedURIComponent, decompressFromEncodedURIComponent } from "lz-string";
import type { MatchFilters } from "./api";

/**
 * Share links carry their payload in the URL fragment (`/#s=<encoded>`), never sent
 * to a server by the browser -- "shareable with zero server-side storage" is
 * literally true and checkable in the network tab. See enhancements/12.
 *
 * Encodes *inputs* only, never results: keeps the payload small, and a shared link
 * always reflects the current model rather than freezing someone else's scores from
 * weeks ago.
 */
export interface SharePayload {
  v: 1;
  r: string; // resume text
  k: number; // top_k
  n: number; // top_n
  f: MatchFilters;
}

// ~8 KB -- some clients truncate or choke on much longer URLs. Checked separately
// from encodeShare (which always succeeds) so the caller can warn before handing
// out a link that won't work everywhere.
export const MAX_ENCODED_SHARE_LENGTH = 8_000;

export function encodeShare(payload: SharePayload): string {
  return compressToEncodedURIComponent(JSON.stringify(payload));
}

export function isShareOversize(encoded: string): boolean {
  return encoded.length > MAX_ENCODED_SHARE_LENGTH;
}

function isSharePayload(value: unknown): value is SharePayload {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    candidate.v === 1 &&
    typeof candidate.r === "string" &&
    typeof candidate.k === "number" &&
    typeof candidate.n === "number" &&
    typeof candidate.f === "object" &&
    candidate.f !== null
  );
}

/**
 * Accepts a raw `location.hash` value (e.g. `"#s=N4Igzg..."`) or a bare encoded
 * string. Never throws -- a malformed, truncated, or hand-edited hash decodes to
 * `null` rather than crashing the page that receives it.
 */
export function decodeShare(hash: string): SharePayload | null {
  if (!hash) return null;

  const match = /^#?s=(.+)$/.exec(hash);
  const encoded = match ? match[1] : hash;
  if (!encoded) return null;

  let json: string | null;
  try {
    json = decompressFromEncodedURIComponent(encoded);
  } catch {
    return null;
  }
  if (!json) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return null;
  }

  return isSharePayload(parsed) ? parsed : null;
}
