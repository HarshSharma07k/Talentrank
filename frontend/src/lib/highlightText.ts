// c++ and .net (and any other term containing regex metacharacters) will otherwise
// throw or match wildly -- the direct frontend counterpart of the \b trap in
// enhancements/04's skills.py. See enhancements/17 for test coverage.
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildParts(text: string, terms: string[]): { parts: string[]; termSet: Set<string> } {
  const nonEmptyTerms = terms.map((term) => term.trim()).filter((term) => term.length > 0);
  if (nonEmptyTerms.length === 0) {
    return { parts: [text], termSet: new Set<string>() };
  }

  // Longest-first so a longer term is never shadowed by a shorter one it contains.
  const pattern = nonEmptyTerms
    .slice()
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  const regex = new RegExp(`(${pattern})`, "gi");

  return {
    parts: text.split(regex),
    termSet: new Set(nonEmptyTerms.map((term) => term.toLowerCase())),
  };
}
