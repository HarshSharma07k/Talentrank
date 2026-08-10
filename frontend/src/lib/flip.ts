/**
 * Minimal FLIP (First, Last, Invert, Play) reorder animation. No dependency.
 *
 * Usage: capture element positions before a reorder, let React re-render into the
 * new order, then play() to animate each surviving element from its old position to
 * its new one via the Web Animations API. See enhancements/11 -- this is what makes
 * the rerank's reordering visible rather than an instant, jarring jump.
 */

export interface Rect {
  top: number;
  left: number;
}

export function captureRects(elements: Map<string, HTMLElement>): Map<string, Rect> {
  const rects = new Map<string, Rect>();
  for (const [key, element] of elements) {
    const rect = element.getBoundingClientRect();
    rects.set(key, { top: rect.top, left: rect.left });
  }
  return rects;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Animates each element from its position in `previousRects` to wherever it now sits
 * in the DOM. Elements with no previous position (newly added) are left alone.
 * Skips the animation entirely under prefers-reduced-motion -- not shortened, not
 * replaced with a fade, just skipped, per the design system's motion rules.
 */
export function playFlip(elements: Map<string, HTMLElement>, previousRects: Map<string, Rect>): void {
  if (prefersReducedMotion()) return;

  for (const [key, element] of elements) {
    const previous = previousRects.get(key);
    if (!previous) continue;

    const current = element.getBoundingClientRect();
    const dx = previous.left - current.left;
    const dy = previous.top - current.top;
    if (dx === 0 && dy === 0) continue;

    element.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], {
      duration: 300,
      easing: "ease-out",
    });
  }
}
