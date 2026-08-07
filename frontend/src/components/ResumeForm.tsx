import { useId } from "react";
import { SAMPLE_RESUME } from "../lib/sampleResume";

const MIN_LENGTH = 40;

interface ResumeFormProps {
  resumeText: string;
  onResumeTextChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export function ResumeForm({ resumeText, onResumeTextChange, onSubmit, loading }: ResumeFormProps) {
  const textareaId = useId();
  const trimmedLength = resumeText.trim().length;
  const tooShort = trimmedLength > 0 && trimmedLength < MIN_LENGTH;
  const canSubmit = trimmedLength >= MIN_LENGTH && !loading;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (canSubmit) onSubmit();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && canSubmit) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex items-center justify-between">
        <label htmlFor={textareaId} className="text-sm font-medium text-slate-700 dark:text-slate-200">
          Resume text
        </label>
        <button
          type="button"
          onClick={() => onResumeTextChange(SAMPLE_RESUME)}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
        >
          Load sample resume
        </button>
      </div>

      <textarea
        id={textareaId}
        value={resumeText}
        onChange={(event) => onResumeTextChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Paste a resume (or a summary of experience and skills) here…"
        rows={10}
        className="w-full resize-y rounded-xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-600"
      />

      <div className="flex items-center justify-between gap-4">
        <p
          className={`text-xs ${tooShort ? "text-amber-600 dark:text-amber-400" : "text-slate-500 dark:text-slate-400"}`}
        >
          {tooShort
            ? `Add a bit more detail (min ${MIN_LENGTH} characters).`
            : `${resumeText.length.toLocaleString()} characters`}
        </p>

        <button
          type="submit"
          disabled={!canSubmit}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:disabled:opacity-40"
        >
          {loading && (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v3a5 5 0 0 0-5 5H4Z" />
            </svg>
          )}
          {loading ? "Matching…" : "Find matching jobs"}
        </button>
      </div>
    </form>
  );
}
