def solve(xs: list[int], k: int) -> int:
    if k <= 0:
        return 0
    for i in range(len(xs) - k + 1):
        if len(set(xs[i : i + k])) == k:
            return k
    return -1
