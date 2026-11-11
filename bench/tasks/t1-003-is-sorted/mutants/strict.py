def solve(xs: list[int]) -> bool:
    return all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))
