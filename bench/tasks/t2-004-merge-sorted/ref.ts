export function solve(a: number[], b: number[]): number[] {
  const out: number[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] <= b[j]) {
      out.push(a[i]);
      i++;
    } else {
      out.push(b[j]);
      j++;
    }
  }
  return out.concat(a.slice(i), b.slice(j));
}
