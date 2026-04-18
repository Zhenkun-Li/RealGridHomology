from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=None)
def _split_rectangle_parts(
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    if lt[0] < rb[0] and lt[1] > rb[1]:
        return (((lt[0], lt[1]), (rb[0], rb[1])),)

    output: list[tuple[tuple[int, int], tuple[int, int]]] = []
    if lt[0] < rb[0] and lt[1] < rb[1]:
        if lt[1] != 0:
            output.append(((lt[0], lt[1]), (rb[0], 0)))
        if rb[1] != size:
            output.append(((lt[0], size), (rb[0], rb[1])))
        return tuple(output)

    if lt[0] > rb[0] and lt[1] > rb[1]:
        if lt[0] != size:
            output.append(((lt[0], lt[1]), (size, rb[1])))
        if rb[0] != 0:
            output.append(((0, lt[1]), (rb[0], rb[1])))
        return tuple(output)

    if lt[0] > rb[0] and lt[1] < rb[1]:
        if lt[0] != size and lt[1] != 0:
            output.append(((lt[0], lt[1]), (size, 0)))
        if rb[0] != 0 and rb[1] != size:
            output.append(((0, size), (rb[0], rb[1])))
        if lt[0] != size and rb[1] != size:
            output.append(((lt[0], size), (size, rb[1])))
        if rb[0] != 0 and lt[1] != 0:
            output.append(((0, lt[1]), (rb[0], 0)))
        return tuple(output)

    raise ValueError(f"Invalid rectangle with LT={lt}, RB={rb}")


def find_bounds_for_rb(x_marks: tuple[int, ...], size: int) -> tuple[list[int], int]:
    lower_bounds = [size for _ in range(size)]
    max_index = size
    for index in range(1, size):
        if index == 1:
            lower_bounds[index] = x_marks[index - 1] + 1
        else:
            lower_bounds[index] = max(lower_bounds[index - 1], x_marks[index - 1] + 1)
        if lower_bounds[index] == size:
            max_index = index
            break
    return lower_bounds, max_index


def shift_marks(lt: tuple[int, int], marks: tuple[int, ...], size: int) -> tuple[int, ...]:
    horizontal_shift = lt[0]
    vertical_shift = size - lt[1]
    return tuple(
        (marks[(index + horizontal_shift) % size] + vertical_shift) % size
        for index in range(size)
    )


def split_rectangle(lt: tuple[int, int], rb: tuple[int, int], size: int) -> list[dict]:
    return [
        {"LT": [part_lt[0], part_lt[1]], "RB": [part_rb[0], part_rb[1]]}
        for part_lt, part_rb in _split_rectangle_parts(lt, rb, size)
    ]


@lru_cache(maxsize=None)
def rectangle_block_set(
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> frozenset[tuple[int, int]]:
    blocks: set[tuple[int, int]] = set()
    for part_lt, part_rb in _split_rectangle_parts(lt, rb, size):
        for column in range(part_lt[0], part_rb[0]):
            for row in range(part_rb[1], part_lt[1]):
                blocks.add((column % size, row % size))
    return frozenset(blocks)


@lru_cache(maxsize=None)
def rectangle_closure_points(
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> frozenset[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for part_lt, part_rb in _split_rectangle_parts(lt, rb, size):
        for column in range(part_lt[0], part_rb[0] + 1):
            for row in range(part_rb[1], part_lt[1] + 1):
                points.add((column % size, row % size))
    return frozenset(points)


@lru_cache(maxsize=None)
def rectangle_interior_points(
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> frozenset[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for part_lt, part_rb in _split_rectangle_parts(lt, rb, size):
        for column in range(part_lt[0] + 1, part_rb[0]):
            for row in range(part_rb[1] + 1, part_lt[1]):
                points.add((column % size, row % size))
    return frozenset(points)


def point_in_rectangle_closure(
    point: tuple[int, int],
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> bool:
    return point in rectangle_closure_points(lt, rb, size)


def point_in_rectangle_interior(
    point: tuple[int, int],
    lt: tuple[int, int],
    rb: tuple[int, int],
    size: int,
) -> bool:
    return point in rectangle_interior_points(lt, rb, size)
