def count(xs: list[int]) -> int:
    acc = 0
    for x in xs:
        acc = acc + x
    return acc


def total(xs: list[int]) -> int:
    acc = 1
    for x in xs:
        acc = acc * x
    return acc


def largest(xs: list[int]) -> int:
    acc = 0
    for _ in xs:
        acc = acc + 1
    return acc


def product(xs: list[int]) -> int:
    acc = xs[0] if xs else 0
    for x in xs:
        if x > acc:
            acc = x
    return acc
