from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import DOMAINS_DIR, RECTANGLES_DIR
from ..geometry import rectangle_block_set, rectangle_closure_points
from ..io import iter_jsonl, write_jsonl
from ..knot import Knot


def _find_first_unassigned(values: list[int]) -> int:
    for index, value in enumerate(values):
        if value == -1:
            return index
    return -1


@dataclass
class DomainStage:
    knot: Knot

    @property
    def rectangle_path(self) -> Path:
        return RECTANGLES_DIR / f"{self.knot.name}.jsonl"

    @property
    def output_path(self) -> Path:
        return DOMAINS_DIR / f"{self.knot.name}.jsonl"

    def compute(self) -> list[dict]:
        rows: list[dict] = []
        for rectangle in iter_jsonl(self.rectangle_path):
            rows.extend(self._domains_for_rectangle(tuple(rectangle["LT"]), tuple(rectangle["RB"])))
        write_jsonl(self.output_path, rows)
        return rows

    def _real_domain_geometry(
        self,
        lt: tuple[int, int],
        rb: tuple[int, int],
    ) -> tuple[frozenset[tuple[int, int]], tuple[int, ...]]:
        base_blocks = rectangle_block_set(lt, rb, self.knot.size)
        reflected_blocks = frozenset(
            self.knot.reflect_block(column, row)
            for column, row in base_blocks
        )
        real_domain_blocks = base_blocks | reflected_blocks

        base_closure = rectangle_closure_points(lt, rb, self.knot.size)
        reflected_closure = frozenset(
            self.knot.reflect_point(column, row)
            for column, row in base_closure
        )
        real_domain_closure = base_closure | reflected_closure
        o_marks = tuple(sorted(column for column, row in real_domain_blocks if (column, row) in self.knot.o_set))
        return real_domain_closure, o_marks

    def _enumerate_generators(
        self,
        *,
        x: list[int],
        y: list[int],
        pool: frozenset[int],
        real_domain_closure: frozenset[tuple[int, int]],
        o_marks: tuple[int, ...],
        output: list[dict],
    ) -> None:
        first_index = _find_first_unassigned(x)
        if first_index == -1:
            output.append({"x": x.copy(), "y": y.copy(), "O-marks": list(o_marks)})
            return

        for row in sorted(pool):
            if (first_index, row) in real_domain_closure:
                continue

            reflected_column = (-row) % self.knot.size
            reflected_row = (-first_index) % self.knot.size

            next_x = x.copy()
            next_y = y.copy()
            next_pool = set(pool)

            if next_x[first_index] not in (-1, row) or next_y[first_index] not in (-1, row):
                continue
            if next_x[reflected_column] not in (-1, reflected_row):
                continue
            if next_y[reflected_column] not in (-1, reflected_row):
                continue

            next_x[first_index] = row
            next_y[first_index] = row
            next_x[reflected_column] = reflected_row
            next_y[reflected_column] = reflected_row

            next_pool.discard(row)
            next_pool.discard(reflected_row)
            self._enumerate_generators(
                x=next_x,
                y=next_y,
                pool=frozenset(next_pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=output,
            )

    def _domains_for_rectangle(self, lt_input: tuple[int, int], rb_input: tuple[int, int]) -> list[dict]:
        lt = [lt_input[0], lt_input[1]]
        rb = [rb_input[0], rb_input[1]]
        real_domain_closure, o_marks = self._real_domain_geometry(lt_input, rb_input)

        x = [-1] * self.knot.size
        y = [-1] * self.knot.size
        pool = set(range(self.knot.size))
        rows: list[dict] = []

        if (lt[0] + lt[1]) % self.knot.size == 0 and (rb[0] + rb[1]) % self.knot.size == 0:
            rt = [rb[0], lt[1]]
            lb = [lt[0], rb[1]]
            x[lb[0] % self.knot.size] = lb[1] % self.knot.size
            x[rt[0] % self.knot.size] = rt[1] % self.knot.size
            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            pool.discard(lt[1] % self.knot.size)
            pool.discard(rb[1] % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if (lt[0] + lt[1]) % self.knot.size == 0:
            if (rb[0] - lt[0]) % self.knot.size > (lt[1] - rb[1]) % self.knot.size:
                rb = [(-rb[1]) % self.knot.size, (-rb[0]) % self.knot.size]

            x[lt[0] % self.knot.size] = rb[1] % self.knot.size
            x[rb[0] % self.knot.size] = (-rb[0]) % self.knot.size
            x[(-rb[1]) % self.knot.size] = lt[1] % self.knot.size

            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size

            pool.discard(rb[1] % self.knot.size)
            pool.discard((-rb[0]) % self.knot.size)
            pool.discard(lt[1] % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if (rb[0] + rb[1]) % self.knot.size == 0:
            if (rb[0] - lt[0]) % self.knot.size > (lt[1] - rb[1]) % self.knot.size:
                lt = [(-lt[1]) % self.knot.size, (-lt[0]) % self.knot.size]

            x[lt[0] % self.knot.size] = (-lt[0]) % self.knot.size
            x[rb[0] % self.knot.size] = lt[1] % self.knot.size
            x[(-lt[1]) % self.knot.size] = rb[1] % self.knot.size

            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size

            pool.discard(lt[1] % self.knot.size)
            pool.discard((-lt[0]) % self.knot.size)
            pool.discard(rb[1] % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if rb[0] < lt[0]:
            rb[0] += self.knot.size
        if rb[1] > lt[1]:
            rb[1] -= self.knot.size
        rt = [rb[0], lt[1]]
        lb = [lt[0], rb[1]]

        if (rt[0] + rt[1]) % self.knot.size == 0 or (lb[0] + lb[1]) % self.knot.size == 0:
            return rows

        if rb[0] + rb[1] > self.knot.size:
            x[rt[0] % self.knot.size] = rt[1] % self.knot.size
            x[lb[0] % self.knot.size] = lb[1] % self.knot.size
            x[(-rt[1]) % self.knot.size] = (-rt[0]) % self.knot.size
            x[(-lb[1]) % self.knot.size] = (-lb[0]) % self.knot.size

            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size
            y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size

            pool.discard(rb[1] % self.knot.size)
            pool.discard(lt[1] % self.knot.size)
            pool.discard((-rb[0]) % self.knot.size)
            pool.discard((-lt[0]) % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if rb[0] + rb[1] < 0:
            x[rt[0] % self.knot.size] = rt[1] % self.knot.size
            x[lb[0] % self.knot.size] = lb[1] % self.knot.size
            x[(-rt[1]) % self.knot.size] = (-rt[0]) % self.knot.size
            x[(-lb[1]) % self.knot.size] = (-lb[0]) % self.knot.size

            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size
            y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size

            pool.discard(rb[1] % self.knot.size)
            pool.discard(lt[1] % self.knot.size)
            pool.discard((-rb[0]) % self.knot.size)
            pool.discard((-lt[0]) % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if rt[0] + rt[1] > self.knot.size:
            x[lb[0] % self.knot.size] = lb[1] % self.knot.size
            x[(-lb[1]) % self.knot.size] = (-lb[0]) % self.knot.size
            x[(-lt[1]) % self.knot.size] = lt[1] % self.knot.size
            x[rb[0] % self.knot.size] = (-rb[0]) % self.knot.size

            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size
            y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size

            pool.discard(rb[1] % self.knot.size)
            pool.discard((-lt[0]) % self.knot.size)
            pool.discard(lt[1] % self.knot.size)
            pool.discard((-rb[0]) % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        if lb[0] + lb[1] < 0:
            x[rt[0] % self.knot.size] = rt[1] % self.knot.size
            x[(-rt[1]) % self.knot.size] = (-rt[0]) % self.knot.size
            x[lt[0] % self.knot.size] = (-lt[0]) % self.knot.size
            x[(-rb[1]) % self.knot.size] = rb[1] % self.knot.size

            y[rb[0] % self.knot.size] = rb[1] % self.knot.size
            y[lt[0] % self.knot.size] = lt[1] % self.knot.size
            y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size
            y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size

            pool.discard(rt[1] % self.knot.size)
            pool.discard((-lt[0]) % self.knot.size)
            pool.discard(rb[1] % self.knot.size)
            pool.discard((-rb[0]) % self.knot.size)
            self._enumerate_generators(
                x=x,
                y=y,
                pool=frozenset(pool),
                real_domain_closure=real_domain_closure,
                o_marks=o_marks,
                output=rows,
            )
            return rows

        x[lb[0] % self.knot.size] = lb[1] % self.knot.size
        x[rt[0] % self.knot.size] = rt[1] % self.knot.size
        x[(-lb[1]) % self.knot.size] = (-lb[0]) % self.knot.size
        x[(-rt[1]) % self.knot.size] = (-rt[0]) % self.knot.size

        y[lt[0] % self.knot.size] = lt[1] % self.knot.size
        y[rb[0] % self.knot.size] = rb[1] % self.knot.size
        y[(-lt[1]) % self.knot.size] = (-lt[0]) % self.knot.size
        y[(-rb[1]) % self.knot.size] = (-rb[0]) % self.knot.size

        pool.discard(lt[1] % self.knot.size)
        pool.discard(rb[1] % self.knot.size)
        pool.discard((-lt[0]) % self.knot.size)
        pool.discard((-rb[0]) % self.knot.size)
        self._enumerate_generators(
            x=x,
            y=y,
            pool=frozenset(pool),
            real_domain_closure=real_domain_closure,
            o_marks=o_marks,
            output=rows,
        )
        return rows
