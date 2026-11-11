def solve(xs: list[int]) -> int:
    n = 0
    for x in xs:
        if x >= 0:
            n = n + 1
    return n
