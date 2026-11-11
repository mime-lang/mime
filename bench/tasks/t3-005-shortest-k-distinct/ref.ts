export function solve(xs: number[], k: number): number {
  if (k <= 0) {
    return 0;
  }
  const counts = new Map<number, number>();
  let best = -1;
  let left = 0;
  for (let right = 0; right < xs.length; right++) {
    const x = xs[right];
    counts.set(x, (counts.get(x) ?? 0) + 1);
    while (counts.size >= k) {
      const width = right - left + 1;
      if (best === -1 || width < best) {
        best = width;
      }
      const y = xs[left];
      const c = (counts.get(y) ?? 0) - 1;
      if (c === 0) {
        counts.delete(y);
      } else {
        counts.set(y, c);
      }
      left++;
    }
  }
  return best;
}
