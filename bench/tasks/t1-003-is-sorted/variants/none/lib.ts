export function w2(xs: number[]): number {
  let acc = 0;
  for (let i = 0; i + 1 < xs.length; i++) if (xs[i] > xs[i + 1]) acc = acc + 1;
  return acc;
}

export function w4(xs: number[]): number {
  let acc = 0;
  for (let i = 0; i + 1 < xs.length; i++) if (xs[i] < xs[i + 1]) acc = acc + 1;
  return acc;
}

export function w1(n: number): boolean {
  return n === 0;
}

export function w3(n: number): boolean {
  return n > 0;
}
