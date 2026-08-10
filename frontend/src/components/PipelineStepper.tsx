export type PipelineStage = "idle" | "retrieving" | "shortlisted" | "ranked" | "error";

const STEPS = [
  { key: "embed", label: "Embed" },
  { key: "shortlist", label: "FAISS shortlist" },
  { key: "rerank", label: "Cross-encoder rerank" },
  { key: "ranked", label: "Ranked" },
] as const;

type StepKey = (typeof STEPS)[number]["key"];
type StepStatus = "pending" | "active" | "done";

const STEP_ORDER: StepKey[] = ["embed", "shortlist", "rerank", "ranked"];

function statusFor(stepKey: StepKey, stage: PipelineStage): StepStatus {
  const stepIndex = STEP_ORDER.indexOf(stepKey);

  switch (stage) {
    case "idle":
      return "pending";
    case "retrieving":
      // A single POST /retrieve covers both embedding and FAISS search -- there is
      // no client-observable boundary between them, so both light up together.
      return stepIndex <= 1 ? "active" : "pending";
    case "shortlisted":
      return stepIndex <= 1 ? "done" : stepIndex === 2 ? "active" : "pending";
    case "ranked":
      return "done";
    case "error":
      // Whatever completed before the failure stays lit; nothing after it did.
      return stepIndex <= 1 ? "done" : "pending";
  }
}

export function PipelineStepper({ stage }: { stage: PipelineStage }) {
  if (stage === "idle") return null;

  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" aria-label="Match pipeline progress">
      {STEPS.map((step, index) => {
        const status = statusFor(step.key, stage);
        return (
          <li key={step.key} className="flex items-center gap-1.5">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold ${
                status === "done"
                  ? "bg-indigo-600 text-white"
                  : status === "active"
                    ? "animate-pulse bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400"
                    : "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-600"
              }`}
            >
              {status === "done" ? "✓" : index + 1}
            </span>
            <span
              className={
                status === "pending"
                  ? "text-slate-400 dark:text-slate-600"
                  : status === "active"
                    ? "font-medium text-indigo-600 dark:text-indigo-400"
                    : "text-slate-500 dark:text-slate-400"
              }
            >
              {step.label}
            </span>
            {index < STEPS.length - 1 && <span className="text-slate-300 dark:text-slate-700">→</span>}
          </li>
        );
      })}
    </ol>
  );
}
