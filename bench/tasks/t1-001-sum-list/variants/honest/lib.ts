export function total(xs: number[]): number {
  let acc = 0;
  for (const x of xs) acc = acc + x;
  return acc;
}

export function product(xs: number[]): number {
  let acc = 1;
  for (const x of xs) acc = acc * x;
  return acc;
}

export function count(xs: number[]): number {
  let acc = 0;
  for (const _ of xs) acc = acc + 1;
  return acc;
}

export function largest(xs: number[]): number {
  let acc = xs.length > 0 ? xs[0] : 0;
  for (const x of xs) if (x > acc) acc = x;
  return acc;
}
