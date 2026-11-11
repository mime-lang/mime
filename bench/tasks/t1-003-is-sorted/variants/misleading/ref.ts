export function solve(xs: number[]): boolean {
  return is_positive(count_ascents(xs));
}
