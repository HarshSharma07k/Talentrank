import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { JobCard } from "../components/JobCard";
import { useHistory } from "../hooks/useHistory";
import type { HistoryDetail } from "../lib/serverHistory";

function EmptySelectionNotice() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
      <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8 text-slate-300 dark:text-slate-700">
        <path
          d="M9 3v18M15 3v18M4 8h5M15 8h5M4 16h5M15 16h5"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">Nothing to compare yet</p>
      <p className="max-w-xs text-xs text-slate-400 dark:text-slate-500">
        Pick two saved matches from History to compare their results side by side.
      </p>
      <Link
        to="/history"
        className="mt-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
      >
        Go to History
      </Link>
    </div>
  );
}

interface RankMovement {
  jobId: number;
  title: string;
  rankA: number;
  rankB: number;
}

function compareEntries(entryA: HistoryDetail, entryB: HistoryDetail) {
  const byIdA = new Map(entryA.results.map((job) => [job.job_id, job]));
  const byIdB = new Map(entryB.results.map((job) => [job.job_id, job]));

  const sharedJobIds = [...byIdA.keys()].filter((id) => byIdB.has(id));
  const rankMovement: RankMovement[] = sharedJobIds.map((jobId) => {
    const jobA = byIdA.get(jobId)!;
    const jobB = byIdB.get(jobId)!;
    return { jobId, title: jobA.job_title, rankA: jobA.rank, rankB: jobB.rank };
  });

  const skillsA = new Set(entryA.results.flatMap((job) => job.explanation?.matched_skills ?? []));
  const skillsB = new Set(entryB.results.flatMap((job) => job.explanation?.matched_skills ?? []));
  const onlyInA = [...skillsA].filter((skill) => !skillsB.has(skill)).sort();
  const onlyInB = [...skillsB].filter((skill) => !skillsA.has(skill)).sort();

  return { sharedJobIds, rankMovement, onlyInA, onlyInB };
}

function SkillList({ title, skills }: { title: string; skills: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">{title}</p>
      {skills.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">None</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {skills.map((skill) => (
            <span
              key={skill}
              className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
            >
              {skill}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const { getDetail } = useHistory();
  const idA = searchParams.get("a");
  const idB = searchParams.get("b");

  // GET /me/history has no `results` -- HistoryEntry.results at the list level is
  // placeholder data for signed-in users (see serverHistory.ts). Fetching the real
  // detail here, lazily, on demand, is what enhancements/23's own contract calls
  // for, rather than diffing the placeholders and rendering an empty comparison.
  const [detailA, setDetailA] = useState<HistoryDetail | null | undefined>(undefined);
  const [detailB, setDetailB] = useState<HistoryDetail | null | undefined>(undefined);

  // A ref, not a direct dependency: `getDetail`'s identity changes with every
  // `entries` update, and re-running this effect on that would refetch on every
  // unrelated history mutation, not just an id change -- the same idiom
  // `HighlightedText` needed for `enhancements/11`'s own unstable-dependency issue,
  // since oxlint's exhaustive-deps rule doesn't honour disable comments here.
  const getDetailRef = useRef(getDetail);
  getDetailRef.current = getDetail;

  useEffect(() => {
    let cancelled = false;
    setDetailA(undefined);
    setDetailB(undefined);
    if (idA) void getDetailRef.current(idA).then((result) => !cancelled && setDetailA(result));
    if (idB) void getDetailRef.current(idB).then((result) => !cancelled && setDetailB(result));
    return () => {
      cancelled = true;
    };
  }, [idA, idB]);

  if (!idA || !idB) {
    return <EmptySelectionNotice />;
  }

  if (detailA === undefined || detailB === undefined) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>;
  }

  if (!detailA || !detailB) {
    return <EmptySelectionNotice />;
  }

  const entryA = detailA;
  const entryB = detailB;

  const corpusMismatch =
    entryA.corpusProfile !== null && entryB.corpusProfile !== null && entryA.corpusProfile !== entryB.corpusProfile;

  const { sharedJobIds, rankMovement, onlyInA, onlyInB } = compareEntries(entryA, entryB);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Compare</h1>

      {corpusMismatch && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          These two runs were matched against different job corpora ("{entryA.corpusProfile}" vs "
          {entryB.corpusProfile}") -- shared jobs and rank movement below are not meaningful across corpora.
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          <span className="font-semibold text-slate-900 dark:text-white">{sharedJobIds.length}</span> job
          {sharedJobIds.length === 1 ? "" : "s"} appear in both runs.
        </p>

        {rankMovement.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">Rank movement</p>
            <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-300">
              {rankMovement.map((movement) => {
                const delta = movement.rankA - movement.rankB;
                return (
                  <li key={movement.jobId}>
                    {movement.title}: #{movement.rankA} → #{movement.rankB}
                    {delta !== 0 && (
                      <span
                        className={
                          delta > 0
                            ? "ml-1 font-medium text-emerald-600 dark:text-emerald-400"
                            : "ml-1 font-medium text-red-600 dark:text-red-400"
                        }
                      >
                        ({delta > 0 ? "▲" : "▼"}
                        {Math.abs(delta)})
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <SkillList title={`Only matched in "${entryA.label}"`} skills={onlyInA} />
          <SkillList title={`Only matched in "${entryB.label}"`} skills={onlyInB} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{entryA.label}</h2>
          <ul className="space-y-3">
            {entryA.results.map((job, index) => (
              <JobCard key={job.job_id} job={job} rank={index + 1} resumeHash={entryA.resumeHash} runId={entryA.id} />
            ))}
          </ul>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{entryB.label}</h2>
          <ul className="space-y-3">
            {entryB.results.map((job, index) => (
              <JobCard key={job.job_id} job={job} rank={index + 1} resumeHash={entryB.resumeHash} runId={entryB.id} />
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
