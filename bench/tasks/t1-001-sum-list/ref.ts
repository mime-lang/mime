export function solve(xs: number[]): number {
  let total = 0;
  for (const x of xs) {
    total += x;
  }
  return total;
}
