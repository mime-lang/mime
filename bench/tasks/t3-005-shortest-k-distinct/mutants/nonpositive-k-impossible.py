def solve(xs: list[int], k: int) -> int:
    best = -1
    for i in range(len(xs)):
        for j in range(i, len(xs)):
            if len(set(xs[i : j + 1])) >= k:
                if best == -1 or j - i + 1 < best:
                    best = j - i + 1
                break
    return best
