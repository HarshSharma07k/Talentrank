interface ScoreBarProps {
  label: string;
  percent: number;
  rawValue: number;
  colorClassName: string;
  // "absolute" (default): the percent means something on its own -- a calibrated
  // sigmoid, a cosine similarity, a matched/detected ratio. "relative": normalized
  // against the current result set (rank 1 = 100%), so the tooltip says so rather
  // than implying an absolute quality judgment. See enhancements/11.
  mode?: "absolute" | "relative";
}

export function ScoreBar({ label, percent, rawValue, colorClassName, mode = "absolute" }: ScoreBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));
  const title =
    mode === "absolute"
      ? `${label}: ${rawValue.toFixed(4)} (raw score)`
      : `${label}: ${rawValue.toFixed(4)} (raw score) -- shown relative to this result set, not absolute`;

  return (
    <div className="flex items-center gap-2" title={title}>
      <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div className={`h-full rounded-full ${colorClassName}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
        {Math.round(clamped)}%
      </span>
    </div>
  );
}
