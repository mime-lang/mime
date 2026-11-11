def solve(xs: list[int], k: int) -> int:
    if k <= 0:
        return 0
    best = 0
    for i in range(len(xs)):
        for j in range(i, len(xs)):
            if len(set(xs[i : j + 1])) >= k:
                if best == 0 or j - i + 1 < best:
                    best = j - i + 1
                break
    return best
