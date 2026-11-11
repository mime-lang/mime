export function solve(xs: number[]): number {
  let n = 0;
  for (const x of xs) {
    if (x > 0) {
      n = n + 1;
    }
  }
  return n;
}
