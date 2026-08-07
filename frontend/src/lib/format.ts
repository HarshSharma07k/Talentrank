export function formatCategory(category: string): string {
  return category
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ");
}

export function normalizeScore(score: number, min: number, max: number): number {
  if (max === min) return 100;
  return ((score - min) / (max - min)) * 100;
}
