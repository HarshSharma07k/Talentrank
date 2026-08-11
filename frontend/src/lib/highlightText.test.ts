import { describe, expect, it } from "vitest";
import { buildParts } from "./highlightText";

describe("buildParts", () => {
  it("highlights terms containing regex metacharacters without throwing", () => {
    // The direct frontend counterpart of skills.py's \b trap (enhancements/04):
    // a naive RegExp built from these terms unescaped either throws (unbalanced
    // group syntax) or matches nothing sensible.
    const { parts, termSet } = buildParts("Experienced with C++, .NET, and (x) automation.", [
      "c++",
      ".net",
      "(x)",
    ]);

    expect(parts.join("")).toBe("Experienced with C++, .NET, and (x) automation.");
    expect(parts).toContain("C++");
    expect(parts).toContain(".NET");
    expect(parts).toContain("(x)");
    expect(termSet).toEqual(new Set(["c++", ".net", "(x)"]));
  });

  it("matches case-insensitively via the lowercased termSet", () => {
    const { parts, termSet } = buildParts("Python and PYTHON and python.", ["Python"]);

    expect(parts.filter((part) => termSet.has(part.toLowerCase()))).toEqual(["Python", "PYTHON", "python"]);
  });

  it("prefers the longest term so it is never shadowed by a shorter one it contains", () => {
    const { parts, termSet } = buildParts("machine learning engineer", ["learning", "machine learning"]);

    expect(parts).toContain("machine learning");
    expect(termSet.has("machine learning")).toBe(true);
  });

  it("returns the whole text as a single unhighlighted part when given no terms", () => {
    const { parts, termSet } = buildParts("plain text", []);

    expect(parts).toEqual(["plain text"]);
    expect(termSet.size).toBe(0);
  });

  it("ignores blank/whitespace-only terms rather than building a matches-everything regex", () => {
    const { parts, termSet } = buildParts("plain text", ["", "   "]);

    expect(parts).toEqual(["plain text"]);
    expect(termSet.size).toBe(0);
  });
});
