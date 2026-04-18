from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import GENERATORS_DIR, GRADING_DIR
from ..geometry import point_in_rectangle_interior, rectangle_block_set
from ..io import iter_jsonl, write_jsonl
from ..knot import Knot
from ..theory import uses_even_strong_grading


@dataclass
class GradingStage:
    knot: Knot
    _generators: list[list[int]] = field(init=False, default_factory=list)
    _ungraded_index: dict[str, int] = field(init=False, default_factory=dict)
    _grading_cache: dict[str, tuple[int, int]] = field(init=False, default_factory=dict)
    _real_domain_mark_cache: dict[tuple[tuple[int, int], tuple[int, int]], tuple[int, int]] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        self._load_generators()
        self._grading_cache[self._generator_to_string(list(range(self.knot.size)))] = (0, 0)

    @property
    def generator_path(self) -> Path:
        return GENERATORS_DIR / f"size-{self.knot.size}.jsonl"

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

    def _count_marks(self, lt: tuple[int, int], rb: tuple[int, int]) -> tuple[int, int]:
        key = (lt, rb)
        if key not in self._real_domain_mark_cache:
            base_blocks = rectangle_block_set(lt, rb, self.knot.size)
            reflected_blocks = frozenset(
                self.knot.reflect_block(column, row)
                for column, row in base_blocks
            )
            real_domain_blocks = base_blocks | reflected_blocks
            self._real_domain_mark_cache[key] = (
                len(self.knot.o_set & real_domain_blocks),
                len(self.knot.x_set & real_domain_blocks),
            )
        return self._real_domain_mark_cache[key]

    def _count_o_marks(self, lt: tuple[int, int], rb: tuple[int, int]) -> int:
        return self._count_marks(lt, rb)[0]

    def _count_x_marks(self, lt: tuple[int, int], rb: tuple[int, int]) -> int:
        return self._count_marks(lt, rb)[1]

    def _count_inner_intersection(self, lt: tuple[int, int], rb: tuple[int, int], generator: list[int]) -> int:
        count = 0
        seen_orbits: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        for column, row in enumerate(generator):
            point = (column, row)
            reflected = self.knot.reflect_point(column, row)
            orbit = tuple(sorted((point, reflected)))
            if orbit in seen_orbits:
                continue

            seen_orbits.add(orbit)
            if not (
                point_in_rectangle_interior(point, lt, rb, self.knot.size)
                or point_in_rectangle_interior(reflected, lt, rb, self.knot.size)
            ):
                continue

            count += 1
            if reflected != point:
                count += 1
        return count

    def compute_single_grading(self, generator: list[int]) -> tuple[int, int]:
        generator_key = self._generator_to_string(generator)
        if generator_key in self._grading_cache:
            return self._grading_cache[generator_key]

        first_index = -1
        second_index = -1
        for index in range(self.knot.size):
            if first_index == -1 and generator[index] != index:
                first_index = index
            if second_index == -1 and generator[index] == first_index:
                second_index = index
                break
        else:
            return self._grading_cache[self._generator_to_string(list(range(self.knot.size)))]

        lt = (first_index, generator[first_index])
        rb = (second_index, generator[second_index])
        rt = (second_index, generator[first_index])

        if first_index == 0:
            axis_index = -1
            for index in range(self.knot.size):
                if generator[index] + index == self.knot.size:
                    axis_index = index
                    break

            reduced = generator.copy()
            reduced[0] = 0
            reduced[second_index] = self.knot.size - axis_index
            reduced[axis_index] = generator[0]

            if generator[axis_index] > generator[first_index]:
                alexander_shift = self._count_x_marks((0, generator[0]), (axis_index, 0)) - self._count_o_marks((0, generator[0]), (axis_index, 0))
                alexander_shift += self._count_x_marks((0, self.knot.size), (axis_index, self.knot.size - axis_index)) - self._count_o_marks((0, self.knot.size), (axis_index, self.knot.size - axis_index))
                maslov_shift = 1 - self._count_o_marks((0, generator[0]), (axis_index, 0)) + self._count_inner_intersection((0, generator[0]), (axis_index, 0), reduced)
                maslov_shift += 0 - self._count_o_marks((0, self.knot.size), (axis_index, self.knot.size - axis_index)) + self._count_inner_intersection((0, self.knot.size), (axis_index, self.knot.size - axis_index), reduced)
                reduced_grading = self.compute_single_grading(reduced)
                grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
                self._grading_cache[generator_key] = grading
                return grading

            alexander_shift = self._count_x_marks((second_index, self.knot.size - axis_index), (self.knot.size, 0)) - self._count_o_marks((second_index, self.knot.size - axis_index), (self.knot.size, 0))
            maslov_shift = 1 - self._count_o_marks((second_index, self.knot.size - axis_index), (self.knot.size, 0)) + self._count_inner_intersection((second_index, self.knot.size - axis_index), (self.knot.size, 0), reduced)
            reduced_grading = self.compute_single_grading(reduced)
            grading = (reduced_grading[0] + alexander_shift, reduced_grading[1] + maslov_shift)
            self._grading_cache[generator_key] = grading
            return grading

        if lt[0] + lt[1] == self.knot.size and rb[0] + rb[1] == self.knot.size:
            reduced = generator.copy()
            reduced[first_index] = first_index
            reduced[second_index] = second_index
            alexander_shift = self._count_x_marks(lt, rb) - self._count_o_marks(lt, rb)
            maslov_shift = 1 - self._count_o_marks(lt, rb) + self._count_inner_intersection(lt, rb, reduced)
            reduced_grading = self.compute_single_grading(reduced)
            grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
            self._grading_cache[generator_key] = grading
            return grading

        if lt[0] + lt[1] == self.knot.size and rb[0] + rb[1] < self.knot.size:
            reduced = generator.copy()
            reduced[lt[0]] = lt[0]
            reduced[rb[0]] = self.knot.size - rb[0]
            reduced[self.knot.size - lt[0]] = self.knot.size - lt[0]
            alexander_shift = self._count_x_marks(lt, rb) - self._count_o_marks(lt, rb)
            maslov_shift = 1 - self._count_o_marks(lt, rb) + self._count_inner_intersection(lt, rb, reduced)
            reduced_grading = self.compute_single_grading(reduced)
            grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
            self._grading_cache[generator_key] = grading
            return grading

        if lt[0] + lt[1] < self.knot.size and rb[0] + rb[1] == self.knot.size:
            reduced = generator.copy()
            reduced[lt[0]] = lt[0]
            reduced[self.knot.size - lt[1]] = lt[1]
            reduced[self.knot.size - lt[0]] = self.knot.size - lt[0]
            alexander_shift = self._count_x_marks(lt, rb) - self._count_o_marks(lt, rb)
            maslov_shift = 1 - self._count_o_marks(lt, rb) + self._count_inner_intersection(lt, rb, reduced)
            reduced_grading = self.compute_single_grading(reduced)
            grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
            self._grading_cache[generator_key] = grading
            return grading

        if rt[0] + rt[1] > self.knot.size:
            reduced = generator.copy()
            reduced[lt[0]] = lt[0]
            reduced[self.knot.size - lt[0]] = self.knot.size - lt[0]
            reduced[rb[0]] = self.knot.size - rb[0]
            reduced[self.knot.size - lt[1]] = lt[1]
            alexander_shift = self._count_x_marks(lt, rb) - self._count_o_marks(lt, rb)
            maslov_shift = 1 - self._count_o_marks(lt, rb) + self._count_inner_intersection(lt, rb, reduced)
            reduced_grading = self.compute_single_grading(reduced)
            grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
            self._grading_cache[generator_key] = grading
            return grading

        reduced = generator.copy()
        reduced[lt[0]] = lt[0]
        reduced[self.knot.size - lt[0]] = self.knot.size - lt[0]
        reduced[rb[0]] = lt[1]
        reduced[self.knot.size - lt[1]] = self.knot.size - rb[0]
        alexander_shift = self._count_x_marks(lt, rb) - self._count_o_marks(lt, rb)
        maslov_shift = 1 - self._count_o_marks(lt, rb) + self._count_inner_intersection(lt, rb, reduced)
        reduced_grading = self.compute_single_grading(reduced)
        grading = (reduced_grading[0] - alexander_shift, reduced_grading[1] - maslov_shift)
        self._grading_cache[generator_key] = grading
        return grading

    def compute(self) -> list[dict]:
        if uses_even_strong_grading(self.knot):
            from .grading_even import EvenGradingStage

            return EvenGradingStage(self.knot).compute()

        rows: list[dict] = []
        for generator in self._generators:
            generator_key = self._generator_to_string(generator)
            rows.append(
                {
                    "generator": generator,
                    "ungraded_index": self._ungraded_index[generator_key],
                    "grading": list(self.compute_single_grading(generator)),
                }
            )
        write_jsonl(self.output_path, rows)
        return rows
