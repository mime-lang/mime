def w2(xs: list[int]) -> int:
    acc = 0
    for i in range(len(xs) - 1):
        if xs[i] > xs[i + 1]:
            acc = acc + 1
    return acc


def w4(xs: list[int]) -> int:
    acc = 0
    for i in range(len(xs) - 1):
        if xs[i] < xs[i + 1]:
            acc = acc + 1
    return acc


def w1(n: int) -> bool:
    return n == 0


def w3(n: int) -> bool:
    return n > 0
