export function count_descents(xs: number[]): number {
  let acc = 0;
  for (let i = 0; i + 1 < xs.length; i++) if (xs[i] > xs[i + 1]) acc = acc + 1;
  return acc;
}

export function count_ascents(xs: number[]): number {
  let acc = 0;
  for (let i = 0; i + 1 < xs.length; i++) if (xs[i] < xs[i + 1]) acc = acc + 1;
  return acc;
}

export function is_zero(n: number): boolean {
  return n === 0;
}

export function is_positive(n: number): boolean {
  return n > 0;
}
