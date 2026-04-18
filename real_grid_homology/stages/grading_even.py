from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

from ..config import GENERATORS_DIR, GRADING_DIR, RECTANGLES_DIR
from ..geometry import rectangle_block_set, split_rectangle
from ..io import iter_jsonl, write_jsonl
from ..knot import Knot
from .domains import DomainStage


@dataclass
class EvenGradingStage:
    knot: Knot
    _generators: list[list[int]] = field(init=False, default_factory=list)
    _ungraded_index: dict[str, int] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._load_generators()

    @property
    def generator_path(self) -> Path:
        return GENERATORS_DIR / f"size-{self.knot.size}.jsonl"

    @property
    def rectangle_path(self) -> Path:
        return RECTANGLES_DIR / f"{self.knot.name}.jsonl"

    @property
    def output_path(self) -> Path:
        return GRADING_DIR / f"{self.knot.name}.jsonl"

    def _load_generators(self) -> None:
        for index, row in enumerate(iter_jsonl(self.generator_path)):
            generator = row["generator"]
            self._generators.append(generator)
            self._ungraded_index[self._generator_to_string(generator)] = index

    def _generator_to_string(self, generator: list[int]) -> str:
        return "".join(f"{value % self.knot.size:02d}" for value in generator)

    def _classify_rectangle(
        self,
        lt_input: tuple[int, int],
        rb_input: tuple[int, int],
    ) -> str:
        lt = [lt_input[0], lt_input[1]]
        rb = [rb_input[0], rb_input[1]]

        if (lt[0] + lt[1]) % self.knot.size == 0 and (rb[0] + rb[1]) % self.knot.size == 0:
            return "case1"
        if (lt[0] + lt[1]) % self.knot.size == 0:
            return "case2-1"
        if (rb[0] + rb[1]) % self.knot.size == 0:
            return "case2-2"

        if rb[0] < lt[0]:
            rb[0] += self.knot.size
        if rb[1] > lt[1]:
            rb[1] -= self.knot.size
        rt = [rb[0], lt[1]]
        lb = [lt[0], rb[1]]

        if rb[0] + rb[1] > self.knot.size:
            return "case3-1"
        if rb[0] + rb[1] < 0:
            return "case3-2"
        if rt[0] + rt[1] > self.knot.size:
            return "case4-1"
        if lb[0] + lb[1] < 0:
            return "case4-2"
        return "case5"

    def _base_o_shift(self, lt: tuple[int, int], rb: tuple[int, int]) -> int:
        columns: list[int] = []
        for part in split_rectangle(lt, rb, self.knot.size):
            part_lt0, part_lt1 = part["LT"]
            part_rb0, part_rb1 = part["RB"]
            for column in range(part_lt0, part_rb0):
                row = self.knot.o_marks[column]
                if row >= part_rb1 and row < part_lt1:
                    if column not in columns:
                        columns.append(column)
                    reflected_column = self.knot.size - 1 - row
                    if reflected_column not in columns:
                        columns.append(reflected_column)
        return len(columns)

    def _cross_o_shift(self, lt: tuple[int, int], rb: tuple[int, int]) -> int:
        base_blocks = rectangle_block_set(lt, rb, self.knot.size)
        multiplicities = Counter(base_blocks)
        multiplicities.update(
            self.knot.reflect_block(column, row)
            for column, row in base_blocks
        )
        return sum(multiplicities[point] for point in self.knot.o_set)

    def _domain_shift(self, lt: tuple[int, int], rb: tuple[int, int]) -> int:
        rectangle_case = self._classify_rectangle(lt, rb)
        if rectangle_case in {"case3-1", "case3-2"}:
            return self._cross_o_shift(lt, rb)
        return self._base_o_shift(lt, rb)

    def _build_adjacency(self) -> dict[str, list[tuple[str, tuple[int, int]]]]:
        domain_stage = DomainStage(self.knot)
        adjacency: dict[str, list[tuple[str, tuple[int, int]]]] = {}

        for rectangle in iter_jsonl(self.rectangle_path):
            lt = tuple(rectangle["LT"])
            rb = tuple(rectangle["RB"])
            shift = self._domain_shift(lt, rb)
            forward_delta = (shift, shift - 1)
            backward_delta = (-shift, 1 - shift)

            for row in domain_stage._domains_for_rectangle(lt, rb):
                x_key = self._generator_to_string(row["x"])
                y_key = self._generator_to_string(row["y"])
                adjacency.setdefault(x_key, []).append((y_key, forward_delta))
                adjacency.setdefault(y_key, []).append((x_key, backward_delta))

        return adjacency

    def _solve_gradings(self) -> dict[str, tuple[int, int]]:
        identity_key = self._generator_to_string(list(range(self.knot.size)))
        adjacency = self._build_adjacency()
        gradings: dict[str, tuple[int, int]] = {identity_key: (0, 0)}
        queue: deque[str] = deque([identity_key])

        while queue:
            source_key = queue.popleft()
            source_grading = gradings[source_key]
            for target_key, delta in adjacency.get(source_key, []):
                candidate = (
                    source_grading[0] + delta[0],
                    source_grading[1] + delta[1],
                )
                previous = gradings.get(target_key)
                if previous is None:
                    gradings[target_key] = candidate
                    queue.append(target_key)
                    continue
                if previous != candidate:
                    raise ValueError(
                        "Inconsistent grading assignment in even-size solver for "
                        f"{self.knot.name}: {source_key} -> {target_key} gives "
                        f"{candidate}, existing grading is {previous}."
                    )

        if len(gradings) != len(self._generators):
            missing = [
                self._generator_to_string(generator)
                for generator in self._generators
                if self._generator_to_string(generator) not in gradings
            ]
            raise ValueError(
                f"Even-size grading graph is disconnected for {self.knot.name}. "
                f"Unreached generators: {missing[:5]}"
            )

        return gradings

    def compute(self) -> list[dict]:
        solved_gradings = self._solve_gradings()
        rows: list[dict] = []
        for generator in self._generators:
            generator_key = self._generator_to_string(generator)
            rows.append(
                {
                    "generator": generator,
                    "ungraded_index": self._ungraded_index[generator_key],
                    "grading": list(solved_gradings[generator_key]),
                }
            )
        write_jsonl(self.output_path, rows)
        return rows
