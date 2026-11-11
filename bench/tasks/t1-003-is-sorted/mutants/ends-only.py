def solve(xs: list[int]) -> bool:
    return not xs or xs[0] <= xs[-1]
