def solve(xs: list[int], k: int) -> int:
    if k <= 0:
        return 0
    counts: dict[int, int] = {}
    best = -1
    left = 0
    for right, x in enumerate(xs):
        counts[x] = counts.get(x, 0) + 1
        while len(counts) >= k:
            width = right - left + 1
            if best == -1 or width < best:
                best = width
            y = xs[left]
            counts[y] -= 1
            if counts[y] == 0:
                del counts[y]
            left += 1
    return best
