def solve(xs: list[int]) -> bool:
    for i in range(len(xs) - 1):
        if xs[i] > xs[i + 1]:
            return False
    return True
