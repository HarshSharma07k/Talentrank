import { useRef } from "react";
import { buildParts } from "../lib/highlightText";

interface HighlightedTextProps {
  text: string;
  terms: string[];
}

export function HighlightedText({ text, terms }: HighlightedTextProps) {
  // Keyed on term *content*, not array identity -- callers routinely derive `terms`
  // inline (e.g. `[...matchedTerms, hoveredSkill]`), producing a new array reference
  // on every render even when the actual terms haven't changed. A plain `useMemo`
  // keyed on the `terms` array itself would recompute every render regardless; this
  // manual cache recomputes only when `text` or the joined term content changes.
  const cacheKey = `${text} ${terms.join(" ")}`;
  const cacheRef = useRef<{ key: string; parts: string[]; termSet: Set<string> } | null>(null);

  if (cacheRef.current === null || cacheRef.current.key !== cacheKey) {
    const { parts, termSet } = buildParts(text, terms);
    cacheRef.current = { key: cacheKey, parts, termSet };
  }

  const { parts, termSet } = cacheRef.current;

  return (
    <>
      {parts.map((part, index) =>
        termSet.has(part.toLowerCase()) ? (
          <mark
            key={index}
            className="rounded bg-indigo-100 px-0.5 text-indigo-900 dark:bg-indigo-500/20 dark:text-indigo-200"
          >
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
