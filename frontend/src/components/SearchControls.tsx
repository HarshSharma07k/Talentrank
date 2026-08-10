import { useEffect, useId, useState } from "react";
import { getJobFamilies, type JobFamilyCount } from "../lib/api";

export type SortOption = "relevance" | "semantic" | "skill_coverage";

export interface SearchControlsValue {
  topK: number;
  topN: number;
  jobFamilies: string[];
  minScore: number; // 0-1, applied server-side to cross_encoder_probability
  sort: SortOption;
}

interface SearchControlsProps {
  value: SearchControlsValue;
  onChange: (value: SearchControlsValue) => void;
  resultSummary: { filtered: number; total: number } | null;
}

const TOP_K_MIN = 10;
const TOP_K_MAX = 100;
const TOP_N_MIN = 5;
const TOP_N_MAX = 25;

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "semantic", label: "Semantic" },
  { value: "skill_coverage", label: "Skill coverage" },
];

export function SearchControls({ value, onChange, resultSummary }: SearchControlsProps) {
  const [open, setOpen] = useState(false);
  // Never hardcoded: fetched from the server so this list can't drift from the
  // data, and each chip carries its measured count. See enhancements/05.
  const [families, setFamilies] = useState<JobFamilyCount[]>([]);
  const panelId = useId();

  useEffect(() => {
    const controller = new AbortController();
    getJobFamilies(controller.signal)
      .then(setFamilies)
      .catch(() => {
        // Degrades to "no family filter available" rather than a page-level error.
      });
    return () => controller.abort();
  }, []);

  function toggleFamily(family: string) {
    const next = value.jobFamilies.includes(family)
      ? value.jobFamilies.filter((existing) => existing !== family)
      : [...value.jobFamilies, family];
    onChange({ ...value, jobFamilies: next });
  }

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-200"
      >
        <span>Search options</span>
        <svg viewBox="0 0 24 24" fill="none" className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}>
          <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div id={panelId} className="space-y-5 border-t border-slate-200 px-4 py-4 dark:border-slate-800">
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">
              Shortlist size (top_k): {value.topK}
            </label>
            <input
              type="range"
              min={TOP_K_MIN}
              max={TOP_K_MAX}
              step={5}
              value={value.topK}
              onChange={(event) => onChange({ ...value, topK: Number(event.target.value) })}
              className="mt-1 w-full accent-indigo-600"
            />
            <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
              How many candidates the bi-encoder retrieves before reranking. A larger shortlist means more
              rerank work.
            </p>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">
              Results (top_n): {value.topN}
            </label>
            <input
              type="range"
              min={TOP_N_MIN}
              max={TOP_N_MAX}
              step={1}
              value={value.topN}
              onChange={(event) => onChange({ ...value, topN: Number(event.target.value) })}
              className="mt-1 w-full accent-indigo-600"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">
              Minimum relevance: {Math.round(value.minScore * 100)}%
            </label>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(value.minScore * 100)}
              onChange={(event) => onChange({ ...value, minScore: Number(event.target.value) / 100 })}
              className="mt-1 w-full accent-indigo-600"
            />
          </div>

          <div>
            <p className="text-xs font-medium text-slate-600 dark:text-slate-300">Job family</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {families.length === 0 && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500">Loading families…</p>
              )}
              {families.map((family) => {
                const selected = value.jobFamilies.includes(family.family);
                return (
                  <button
                    key={family.family}
                    type="button"
                    onClick={() => toggleFamily(family.family)}
                    className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                      selected
                        ? "bg-indigo-600 text-white"
                        : "border border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600"
                    }`}
                  >
                    {family.label} ({family.count.toLocaleString()})
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="text-xs font-medium text-slate-600 dark:text-slate-300">Sort by</p>
            <div className="mt-1.5 flex gap-1.5">
              {SORT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onChange({ ...value, sort: option.value })}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    value.sort === option.value
                      ? "bg-indigo-600 text-white"
                      : "border border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {resultSummary !== null && resultSummary.filtered < resultSummary.total && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              {resultSummary.filtered.toLocaleString()} of {resultSummary.total.toLocaleString()} candidates
              matched your filter.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
