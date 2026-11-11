def count_ascents(xs: list[int]) -> int:
    acc = 0
    for i in range(len(xs) - 1):
        if xs[i] > xs[i + 1]:
            acc = acc + 1
    return acc


def count_descents(xs: list[int]) -> int:
    acc = 0
    for i in range(len(xs) - 1):
        if xs[i] < xs[i + 1]:
            acc = acc + 1
    return acc


def is_positive(n: int) -> bool:
    return n == 0


def is_zero(n: int) -> bool:
    return n > 0
