import { describe, expect, it } from "vitest";
import { decodeShare, encodeShare, isShareOversize, MAX_ENCODED_SHARE_LENGTH, type SharePayload } from "./share";

function payload(overrides: Partial<SharePayload> = {}): SharePayload {
  return {
    v: 1,
    r: "Registered nurse, 6 years ICU, ACLS and BLS certified.",
    k: 30,
    n: 10,
    f: { job_families: ["HEALTHCARE"], min_score: 0.2 },
    ...overrides,
  };
}

describe("share", () => {
  it("roundtrip", () => {
    const original = payload();
    const decoded = decodeShare(encodeShare(original));
    expect(decoded).toEqual(original);
  });

  it("roundtrip: unicode and emoji", () => {
    const original = payload({
      r: "Café résumé writer 🚀 with naïve enthusiasm — 日本語 also present.",
    });
    const decoded = decodeShare(encodeShare(original));
    expect(decoded).toEqual(original);
  });

  it("roundtrip: C++, newlines, and null filters", () => {
    const original = payload({
      r: "Experienced with C++, .NET, and\nmulti-line\nformatting in a resume.",
      f: { job_families: null, min_score: null },
    });
    const decoded = decodeShare(encodeShare(original));
    expect(decoded).toEqual(original);
  });

  it("decode_garbage_returns_null", () => {
    expect(decodeShare("not even close to valid")).toBeNull();
    expect(decodeShare("#s=")).toBeNull();
    expect(decodeShare("")).toBeNull();
    expect(decodeShare("#s=%%%not-lz-string%%%")).toBeNull();
  });

  it("decode_garbage_returns_null: valid lz-string that isn't a SharePayload", () => {
    const encodedNonPayload = encodeShare({ v: 1, r: "x", k: 1, n: 1, f: {} } as SharePayload);
    // Corrupt it into decoding to plain JSON that isn't shaped like a SharePayload.
    const notAPayload = encodeShare({} as unknown as SharePayload);
    expect(decodeShare(notAPayload)).toBeNull();
    expect(decodeShare(encodedNonPayload)).not.toBeNull(); // sanity: valid shape still decodes
  });

  it("oversize_payload_flagged", () => {
    const small = encodeShare(payload());
    expect(isShareOversize(small)).toBe(false);

    // A repeated character compresses to almost nothing with lz-string -- use
    // high-entropy content so the encoded output is actually large, the way a
    // real oversized resume (varied text, not padding) would be.
    const highEntropy = Array.from({ length: 50_000 }, () => Math.random().toString(36)).join("");
    const huge = encodeShare(payload({ r: highEntropy }));
    expect(huge.length).toBeGreaterThan(MAX_ENCODED_SHARE_LENGTH);
    expect(isShareOversize(huge)).toBe(true);
  });

  it("decodeShare accepts both a raw hash and a bare encoded string", () => {
    const encoded = encodeShare(payload());
    expect(decodeShare(`#s=${encoded}`)).toEqual(payload());
    expect(decodeShare(`s=${encoded}`)).toEqual(payload());
    expect(decodeShare(encoded)).toEqual(payload());
  });
});
