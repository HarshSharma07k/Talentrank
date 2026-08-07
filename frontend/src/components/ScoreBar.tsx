interface ScoreBarProps {
  label: string;
  percent: number;
  rawValue: number;
  colorClassName: string;
}

export function ScoreBar({ label, percent, rawValue, colorClassName }: ScoreBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div className="flex items-center gap-2" title={`${label}: ${rawValue.toFixed(4)} (raw score)`}>
      <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-full rounded-full ${colorClassName}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
        {Math.round(clamped)}%
      </span>
    </div>
  );
}
