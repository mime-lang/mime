export function solve(xs: number[]): boolean {
  for (let i = 0; i + 1 < xs.length; i++) {
    if (xs[i] > xs[i + 1]) {
      return false;
    }
  }
  return true;
}
