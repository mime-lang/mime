export function w3(xs: number[]): number {
  let acc = 0;
  for (const x of xs) acc = acc + x;
  return acc;
}

export function w1(xs: number[]): number {
  let acc = 1;
  for (const x of xs) acc = acc * x;
  return acc;
}

export function w4(xs: number[]): number {
  let acc = 0;
  for (const _ of xs) acc = acc + 1;
  return acc;
}

export function w2(xs: number[]): number {
  let acc = xs.length > 0 ? xs[0] : 0;
  for (const x of xs) if (x > acc) acc = x;
  return acc;
}
