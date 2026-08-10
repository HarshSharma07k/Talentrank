import type { ReactNode } from "react";
import { useOutletContext } from "react-router";
import type { RootLayoutContext } from "../layouts/RootLayout";
import {
  DEMO_CORPUS_ARTIFACT_MIB,
  DEMO_CORPUS_SIZE,
  DEMO_VS_FULL_NOTE,
  FULL_CORPUS_ARTIFACT_MIB,
  FULL_CORPUS_NON_OTHER_FAMILY_PCT,
  FULL_CORPUS_SIZE,
  GPU_LATENCY_NOTE,
  LATENCY_TABLE,
  NDCG_TABLE,
  SPARSE_LABEL_CAVEAT,
} from "../lib/measured";

const STAGES = [
  { title: "Resume text", detail: "Pasted, uploaded, or the sample resume" },
  { title: "Bi-encoder", detail: "sentence-transformers embeds the resume" },
  { title: "FAISS", detail: "Approximate nearest-neighbor retrieval, top_k candidates" },
  { title: "Cross-encoder", detail: "Reranks the shortlist for precision" },
  { title: "Ranked results", detail: "Top_n jobs, with scores and lexical evidence" },
];

function ArchitectureDiagram() {
  const boxWidth = 172;
  const boxHeight = 64;
  const gap = 36;
  const totalWidth = STAGES.length * boxWidth + (STAGES.length - 1) * gap;
  const height = 120;

  return (
    <svg
      viewBox={`0 0 ${totalWidth} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label="Pipeline: resume text, bi-encoder embedding, FAISS retrieval, cross-encoder rerank, ranked results"
    >
      {STAGES.map((stage, index) => {
        const x = index * (boxWidth + gap);
        const y = (height - boxHeight) / 2;
        const isModel = stage.title === "Bi-encoder" || stage.title === "Cross-encoder";

        return (
          <g key={stage.title}>
            <rect
              x={x}
              y={y}
              width={boxWidth}
              height={boxHeight}
              rx={12}
              className={
                isModel
                  ? "fill-indigo-600"
                  : "fill-white stroke-slate-200 dark:fill-slate-900 dark:stroke-slate-700"
              }
              strokeWidth={isModel ? 0 : 1.5}
            />
            <text
              x={x + boxWidth / 2}
              y={y + boxHeight / 2 - 6}
              textAnchor="middle"
              className={`text-[13px] font-semibold ${isModel ? "fill-white" : "fill-slate-800 dark:fill-slate-100"}`}
            >
              {stage.title}
            </text>
            <foreignObject x={x + 8} y={y + boxHeight / 2 + 2} width={boxWidth - 16} height={boxHeight / 2 - 4}>
              <p
                className={`text-center text-[9.5px] leading-tight ${isModel ? "text-indigo-100" : "text-slate-500 dark:text-slate-400"}`}
              >
                {stage.detail}
              </p>
            </foreignObject>

            {index < STAGES.length - 1 && (
              <path
                d={`M ${x + boxWidth} ${y + boxHeight / 2} L ${x + boxWidth + gap} ${y + boxHeight / 2}`}
                className="stroke-slate-300 dark:stroke-slate-600"
                strokeWidth={2}
                markerEnd="url(#arrowhead)"
              />
            )}
          </g>
        );
      })}
      <defs>
        <marker id="arrowhead" markerWidth={8} markerHeight={8} refX={6} refY={4} orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" className="fill-slate-300 dark:fill-slate-600" />
        </marker>
      </defs>
    </svg>
  );
}

function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
      {children}
    </section>
  );
}

export function HowItWorksPage() {
  const { health } = useOutletContext<RootLayoutContext>();

  return (
    <div className="flex flex-col gap-6">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
          How it works
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          A two-stage semantic search pipeline: fast approximate retrieval narrows a large corpus down
          to a shortlist, then a slower, more accurate model reranks that shortlist for the final order.
        </p>
      </div>

      <SectionCard title="Pipeline">
        <ArchitectureDiagram />
      </SectionCard>

      <SectionCard title="Retrieval quality (NDCG@10)">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                <th className="py-2 pr-4 font-medium">Stage</th>
                <th className="py-2 font-medium">NDCG@10</th>
              </tr>
            </thead>
            <tbody>
              {NDCG_TABLE.map((row) => (
                <tr key={row.stage} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                  <td className="py-2 pr-4 text-slate-700 dark:text-slate-200">{row.stage}</td>
                  <td className="py-2 font-mono text-slate-600 dark:text-slate-300">
                    {row.ndcg10.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{SPARSE_LABEL_CAVEAT}</p>
      </SectionCard>

      <SectionCard title="Serving latency">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                <th className="py-2 pr-4 font-medium">Config</th>
                <th className="py-2 pr-4 font-medium">Hardware</th>
                <th className="py-2 pr-4 font-medium">p50</th>
                <th className="py-2 font-medium">p95</th>
              </tr>
            </thead>
            <tbody>
              {LATENCY_TABLE.map((row) => (
                <tr
                  key={`${row.config}-${row.hardware}`}
                  className="border-b border-slate-100 last:border-0 dark:border-slate-800/60"
                >
                  <td className="py-2 pr-4 text-slate-700 dark:text-slate-200">{row.config}</td>
                  <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">{row.hardware}</td>
                  <td className="py-2 pr-4 font-mono text-slate-600 dark:text-slate-300">
                    {row.p50Ms.toFixed(1)} ms
                  </td>
                  <td className="py-2 font-mono text-slate-600 dark:text-slate-300">{row.p95Ms.toFixed(1)} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{GPU_LATENCY_NOTE}</p>
      </SectionCard>

      <SectionCard title="Full corpus vs. hosted demo">
        <p className="text-sm text-slate-600 dark:text-slate-300">{DEMO_VS_FULL_NOTE}</p>
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-slate-400 dark:text-slate-500">Full corpus</dt>
            <dd className="font-mono text-slate-700 dark:text-slate-200">{FULL_CORPUS_SIZE.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400 dark:text-slate-500">Demo subsample</dt>
            <dd className="font-mono text-slate-700 dark:text-slate-200">{DEMO_CORPUS_SIZE.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400 dark:text-slate-500">Family coverage (full)</dt>
            <dd className="font-mono text-slate-700 dark:text-slate-200">{FULL_CORPUS_NON_OTHER_FAMILY_PCT}%</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400 dark:text-slate-500">Artifacts (full vs. demo)</dt>
            <dd className="font-mono text-slate-700 dark:text-slate-200">
              {FULL_CORPUS_ARTIFACT_MIB} / {DEMO_CORPUS_ARTIFACT_MIB} MiB
            </dd>
          </div>
        </dl>
        {health !== null && (
          <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
            This instance is currently serving the <span className="font-semibold">{health.corpus_profile}</span>{" "}
            profile — {health.corpus_size.toLocaleString()} postings.
          </p>
        )}
      </SectionCard>
    </div>
  );
}
