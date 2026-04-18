from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import GENERATORS_DIR
from ..io import write_jsonl


def _find_first_unassigned(generator: list[int]) -> int:
    for index, value in enumerate(generator):
        if value == -1:
            return index
    return -1


def _reflect_point(column: int, row: int, size: int) -> tuple[int, int]:
    return ((-row) % size, (-column) % size)


@dataclass
class GeneratorStage:
    size: int

    @property
    def output_path(self) -> Path:
        return GENERATORS_DIR / f"size-{self.size}.jsonl"

    def compute(self) -> list[dict]:
        rows = [{"generator": generator} for generator in self._generate_all()]
        write_jsonl(self.output_path, rows)
        return rows

    def _generate_all(self) -> list[list[int]]:
        generators: list[list[int]] = []
        initial_generator = [-1] * self.size
        initial_pool = frozenset(range(self.size))
        self._search(initial_generator, initial_pool, generators)
        return generators

    def _search(
        self,
        generator: list[int],
        pool: frozenset[int],
        output: list[list[int]],
    ) -> None:
        first_index = _find_first_unassigned(generator)
        if first_index == -1:
            output.append(generator.copy())
            return

        for row in sorted(pool):
            reflected_column, reflected_row = _reflect_point(first_index, row, self.size)
            if generator[first_index] not in (-1, row):
                continue
            if generator[reflected_column] not in (-1, reflected_row):
                continue
            if row not in pool:
                continue
            if reflected_row not in pool and reflected_row != row:
                continue

            next_generator = generator.copy()
            next_generator[first_index] = row
            next_generator[reflected_column] = reflected_row

            next_pool = set(pool)
            next_pool.discard(row)
            next_pool.discard(reflected_row)
            self._search(next_generator, frozenset(next_pool), output)
