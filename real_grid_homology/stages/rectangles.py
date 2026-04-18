from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import RECTANGLES_DIR
from ..geometry import find_bounds_for_rb, rectangle_block_set, shift_marks, split_rectangle
from ..io import write_jsonl
from ..knot import Knot


@dataclass
class RectangleStage:
    knot: Knot

    @property
    def output_path(self) -> Path:
        return RECTANGLES_DIR / f"{self.knot.name}.jsonl"

    def compute(self) -> list[dict]:
        rows: list[dict] = []
        for column in range(self.knot.size):
            for row in range(1, self.knot.size - column + 1):
                rows.extend(self._rectangles_for_lt((column, row)))
        write_jsonl(self.output_path, rows)
        return rows

    def _rectangles_for_lt(self, lt: tuple[int, int]) -> list[dict]:
        shifted_x = shift_marks(lt, self.knot.x_marks, self.knot.size)
        lower_bounds, max_index = find_bounds_for_rb(shifted_x, self.knot.size)
        rows: list[dict] = []

        for horizontal_offset in range(1, max_index):
            for vertical_offset in range(lower_bounds[horizontal_offset], self.knot.size):
                rb = [
                    (lt[0] + horizontal_offset) % self.knot.size,
                    (lt[1] + vertical_offset) % self.knot.size,
                ]
                if rb[0] == 0:
                    rb[0] = self.knot.size

                if (lt[0] + lt[1]) % self.knot.size == 0 and rb[0] + rb[1] > self.knot.size:
                    continue

                if not self._real_domain_avoids_x(lt, (rb[0], rb[1])):
                    continue

                rows.append(
                    {
                        "LT": [lt[0], lt[1]],
                        "RB": [rb[0], rb[1]],
                        "elementary_parts": split_rectangle(lt, (rb[0], rb[1]), self.knot.size),
                    }
                )
        return rows

    def _real_domain_avoids_x(self, lt: tuple[int, int], rb: tuple[int, int]) -> bool:
        base_blocks = rectangle_block_set(lt, rb, self.knot.size)
        reflected_blocks = {
            self.knot.reflect_block(column, row)
            for column, row in base_blocks
        }
        real_domain_blocks = base_blocks | reflected_blocks
        return real_domain_blocks.isdisjoint(self.knot.x_set)
