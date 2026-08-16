/**
 * Every number that appears anywhere in the TalentRank frontend must live here and
 * only here, copied verbatim from `.claude/reference/measured-facts.md` -- never
 * typed from memory. See enhancements/10 and CLAUDE.md rule 1.
 */

export const FULL_CORPUS_SIZE = 123_849; // measured 2026-08-08, scripts/prep_data.py
export const FULL_CORPUS_NON_OTHER_FAMILY_PCT = 44.23; // measured 2026-08-10, real code path

export const DEMO_CORPUS_SIZE = 25_911; // measured 2026-08-10, of 25,000 requested
export const DEMO_CORPUS_ARTIFACT_MIB = 77.0; // measured 2026-08-10, jobs_demo.parquet + .faiss
export const FULL_CORPUS_ARTIFACT_MIB = 632.8; // measured 2026-08-08, jobs_clean.parquet + jobs.faiss

export interface NdcgRow {
  stage: string;
  ndcg10: number;
}

// measured-facts.md's latency x NDCG matrix (enhancements/08)
export const NDCG_TABLE: NdcgRow[] = [
  { stage: "Bi-encoder retrieval only (no rerank)", ndcg10: 0.0 },
  { stage: "+ cross-encoder rerank, top_k=100 (pre-tuning)", ndcg10: 0.0071 },
  { stage: "+ cross-encoder rerank, top_k=30 (shipped config)", ndcg10: 0.01 },
];

export interface LatencyRow {
  config: string;
  hardware: string;
  p50Ms: number;
  p95Ms: number;
}

export const LATENCY_TABLE: LatencyRow[] = [
  { config: "Baseline (top_k=100, no truncation)", hardware: "CPU", p50Ms: 666.1, p95Ms: 690.3 },
  { config: "Shipped (top_k=30, max_length=256, truncated)", hardware: "CPU", p50Ms: 138.7, p95Ms: 144.8 },
  {
    config: "Shipped (top_k=30, max_length=256, truncated)",
    hardware: "GPU (RTX 3050 Laptop)",
    p50Ms: 166.8,
    p95Ms: 189.3,
  },
  {
    config: "Shipped config, demo corpus, live",
    hardware: "Hosted (Cloud Run, incl. network)",
    p50Ms: 3164.9,
    p95Ms: 3510.6,
  },
];

export const SPARSE_LABEL_CAVEAT =
  "The absolute NDCG numbers above look low, and that's expected: the evaluation labels " +
  "come from a sparse proxy dictionary, not human relevance judgments. FAISS often returns " +
  "a genuinely strong semantic match -- a Data Scientist resume against a Data Engineer " +
  "posting, say -- that the proxy label set never marked as a match, so it scores as 0 even " +
  "though the result is good. The relative improvement from adding the cross-encoder rerank " +
  "is the meaningful signal, not the absolute score.";

export const GPU_LATENCY_NOTE =
  "GPU measured slower than CPU here (166.8 ms vs 138.7 ms p50) -- a single request's " +
  "cross-encoder pass over only 30 candidates is too small a batch for CUDA's kernel-launch " +
  "and transfer overhead to pay for itself. The hosted demo runs on CPU regardless.";

export const HOSTED_LATENCY_NOTE =
  "The hosted row above is a real measurement from this machine over the public internet, " +
  "not a local number relabeled -- it includes round-trip network time to the host and a " +
  "free 2-vCPU tier, so it's honestly slower than the local figures. That's the real cost " +
  "of a $0/month deployment, not a bug in the pipeline.";

export const DEMO_VS_FULL_NOTE =
  `The hosted demo searches a stratified ${DEMO_CORPUS_SIZE.toLocaleString()}-posting ` +
  `subsample of the full corpus, not all ${FULL_CORPUS_SIZE.toLocaleString()} postings. The ` +
  "subsample keeps every job family represented -- including rare ones like agriculture and " +
  "aviation -- via a per-family floor, so cross-domain matching still works. The full-corpus " +
  "figures on this page are measured locally, not on the hosted demo.";
