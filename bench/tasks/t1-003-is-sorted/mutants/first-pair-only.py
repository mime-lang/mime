def solve(xs: list[int]) -> bool:
    return len(xs) < 2 or xs[0] <= xs[1]
