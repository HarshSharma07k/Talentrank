import { describe, expect, it } from "vitest";
import { formatCategory, normalizeScore, toAbsolutePercent } from "./format";

describe("formatCategory", () => {
  it("splits on hyphens and underscores and title-cases each word", () => {
    expect(formatCategory("INFORMATION-TECHNOLOGY")).toBe("Information Technology");
    expect(formatCategory("BUSINESS_DEVELOPMENT")).toBe("Business Development");
  });

  it("handles a single word", () => {
    expect(formatCategory("HEALTHCARE")).toBe("Healthcare");
  });
});

describe("normalizeScore", () => {
  it("maps min to 0 and max to 100", () => {
    expect(normalizeScore(0.2, 0.2, 0.8)).toBe(0);
    expect(normalizeScore(0.8, 0.2, 0.8)).toBe(100);
    expect(normalizeScore(0.5, 0.2, 0.8)).toBeCloseTo(50);
  });

  it("returns 100 when every score in the set is tied, rather than dividing by zero", () => {
    expect(normalizeScore(0.5, 0.5, 0.5)).toBe(100);
  });
});

describe("toAbsolutePercent", () => {
  it("scales a [0,1] fraction to a percent independent of any result set", () => {
    expect(toAbsolutePercent(0)).toBe(0);
    expect(toAbsolutePercent(0.734)).toBeCloseTo(73.4);
    expect(toAbsolutePercent(1)).toBe(100);
  });

  it("does not clamp -- callers (ScoreBar) are responsible for that", () => {
    expect(toAbsolutePercent(-0.1)).toBeCloseTo(-10);
  });
});
