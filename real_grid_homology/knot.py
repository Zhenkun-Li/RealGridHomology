from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path

from .io import load_json


class SymmetryKind(str, Enum):
    STRONGLY_INVERTIBLE = "strongly_invertible"
    PERIODIC = "periodic"


@dataclass(frozen=True)
class Knot:
    name: str
    size: int
    o_marks: tuple[int, ...]
    x_marks: tuple[int, ...]
    symmetry_kind: SymmetryKind

    @classmethod
    def from_path(cls, path: Path) -> "Knot":
        payload = load_json(path)
        size = int(payload["size"])
        o_marks = tuple(int(value) for value in payload["O"])
        x_marks = tuple(int(value) for value in payload["X"])
        symmetry_kind = detect_symmetry_kind(size=size, o_marks=o_marks, x_marks=x_marks)
        return cls(
            name=path.stem,
            size=size,
            o_marks=o_marks,
            x_marks=x_marks,
            symmetry_kind=symmetry_kind,
        )

    def reflect_block(self, column: int, row: int) -> tuple[int, int]:
        return (self.size - 1 - row, self.size - 1 - column)

    def reflect_point(self, column: int, row: int) -> tuple[int, int]:
        return ((-row) % self.size, (-column) % self.size)

    def reflected_mark_type(self, mark_type: str) -> str:
        if self.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE:
            return mark_type
        if mark_type == "O":
            return "X"
        return "O"

    def block_is_on_axis(self, column: int, row: int) -> bool:
        return column + row == self.size - 1

    def point_is_on_axis(self, column: int, row: int) -> bool:
        return (column + row) % self.size == 0

    @cached_property
    def o_set(self) -> frozenset[tuple[int, int]]:
        return frozenset((column, row) for column, row in enumerate(self.o_marks))

    @cached_property
    def x_set(self) -> frozenset[tuple[int, int]]:
        return frozenset((column, row) for column, row in enumerate(self.x_marks))


def detect_symmetry_kind(
    *,
    size: int,
    o_marks: tuple[int, ...],
    x_marks: tuple[int, ...],
) -> SymmetryKind:
    o_set = {(column, row) for column, row in enumerate(o_marks)}
    x_set = {(column, row) for column, row in enumerate(x_marks)}

    reflected_o = {(size - 1 - row, size - 1 - column) for column, row in o_set}
    reflected_x = {(size - 1 - row, size - 1 - column) for column, row in x_set}

    if reflected_o == o_set and reflected_x == x_set:
        return SymmetryKind.STRONGLY_INVERTIBLE
    if reflected_o == x_set and reflected_x == o_set:
        return SymmetryKind.PERIODIC

    raise ValueError(
        "The knot data is not symmetric under the anti-diagonal as either a strongly "
        "invertible knot or a periodic knot."
    )
