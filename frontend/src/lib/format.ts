export function formatCategory(category: string): string {
  return category
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ");
}

// Relative to the current result set -- rank 1 always renders 100%, the last
// always renders 0%, regardless of actual quality. Kept for an explicitly-labelled
// "rank within this shortlist" secondary visual -- see enhancements/11. The
// headline score bars use toAbsolutePercent instead.
export function normalizeScore(score: number, min: number, max: number): number {
  if (max === min) return 100;
  return ((score - min) / (max - min)) * 100;
}

// scores.cross_encoder_probability, scores.bi_encoder, and explanation.overlap_score
// are each already meaningful on their own (a calibrated sigmoid, a cosine
// similarity, and a matched/detected ratio respectively) -- this just converts the
// [0, 1]-ish fraction to a percent for display. ScoreBar clamps to [0, 100] itself,
// so a bi_encoder cosine that dips slightly negative still renders sanely as 0%.
export function toAbsolutePercent(fraction: number): number {
  return fraction * 100;
}
