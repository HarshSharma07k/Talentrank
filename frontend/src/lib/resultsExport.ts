import type { JobMatch } from "./api";
import { formatCategory, toAbsolutePercent } from "./format";

/**
 * "Copy as Markdown" / "Download JSON" (enhancements/13, item 3). Pure
 * string-building here; the DOM side effects (clipboard write, download link) stay
 * in the component that calls these.
 */

function escapeMarkdownCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

export function resultsToMarkdown(results: JobMatch[]): string {
  const header = "| Rank | Job title | Family | Relevance | Semantic match |";
  const divider = "|---|---|---|---|---|";
  const rows = results.map((job) => {
    const relevance = `${toAbsolutePercent(job.scores.cross_encoder_probability).toFixed(1)}%`;
    const semantic = `${toAbsolutePercent(job.scores.bi_encoder).toFixed(1)}%`;
    return `| ${job.rank} | ${escapeMarkdownCell(job.job_title)} | ${formatCategory(job.job_family)} | ${relevance} | ${semantic} |`;
  });
  return [header, divider, ...rows].join("\n");
}

export function resultsToJson(results: JobMatch[]): string {
  return JSON.stringify(results, null, 2);
}
