from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import GRADING_DIR, MINUS_DIR
from ..io import iter_jsonl, save_json
from ..knot import Knot, SymmetryKind
from .hat_homology import HatHomologyStage
from ..theory import destabilization_steps, uses_even_strong_grading


@dataclass
class MinusHomologyStage:
    knot: Knot
    normalization: int | None = None
    check_diff: bool = False
    _generator_to_index: dict[str, int] = field(init=False, default_factory=dict)
    _index_to_delta: dict[int, int] = field(init=False, default_factory=dict)
    _delta_to_indices: dict[int, list[int]] = field(init=False, default_factory=dict)
    _delta_local_index: dict[int, dict[int, int]] = field(init=False, default_factory=dict)
    _index_to_i: dict[int, int] = field(init=False, default_factory=dict)
    _index_to_j: dict[int, int] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if self.knot.symmetry_kind is not SymmetryKind.STRONGLY_INVERTIBLE:
            raise ValueError("Minus homology is only defined for strongly invertible knots in this migration.")
        self._load_graded_generators()

    @property
    def grading_path(self) -> Path:
        return GRADING_DIR / f"{self.knot.name}.jsonl"

    @property
    def domain_path(self) -> Path:
        return MINUS_DIR.parent.parent / "domains" / f"{self.knot.name}.jsonl"

    @property
    def output_path(self) -> Path:
        return MINUS_DIR / f"{self.knot.name}.json"

    def _generator_to_string(self, generator: list[int]) -> str:
        return "".join(f"{value % self.knot.size:02d}" for value in generator)

    def _load_graded_generators(self) -> None:
        bi_grading: dict[int, dict[int, list[str]]] = {}
        i_max = i_min = j_max = j_min = None

        for row in iter_jsonl(self.grading_path):
            generator_key = self._generator_to_string(row["generator"])
            i_grading, j_grading = row["grading"]
            i_max = i_grading if i_max is None else max(i_max, i_grading)
            i_min = i_grading if i_min is None else min(i_min, i_grading)
            j_max = j_grading if j_max is None else max(j_max, j_grading)
            j_min = j_grading if j_min is None else min(j_min, j_grading)
            bi_grading.setdefault(i_grading, {}).setdefault(j_grading, []).append(generator_key)

        index = 0
        assert i_max is not None and i_min is not None and j_max is not None and j_min is not None
        for i_grading in range(i_max, i_min - 1, -1):
            for j_grading in range(j_min, j_max + 1):
                for generator_key in bi_grading.get(i_grading, {}).get(j_grading, []):
                    self._generator_to_index[generator_key] = index
                    delta = j_grading - i_grading
                    self._index_to_delta[index] = delta
                    self._delta_to_indices.setdefault(delta, []).append(index)
                    self._index_to_i[index] = i_grading
                    self._index_to_j[index] = j_grading
                    index += 1

        for delta, indices in self._delta_to_indices.items():
            self._delta_local_index[delta] = {
                global_index: local_index
                for local_index, global_index in enumerate(indices)
            }

    def _load_delta_bands(self) -> dict[int, list[int]]:
        columns_by_delta = {
            delta: [0] * len(indices)
            for delta, indices in self._delta_to_indices.items()
        }

        for row in iter_jsonl(self.domain_path):
            x_index = self._generator_to_index[self._generator_to_string(row["x"])]
            y_index = self._generator_to_index[self._generator_to_string(row["y"])]
            delta = self._index_to_delta[x_index]
            target_delta = self._index_to_delta[y_index]
            if target_delta != delta - 1:
                raise ValueError(
                    f"Unexpected delta transition for knot {self.knot.name}: "
                    f"{delta} -> {target_delta}"
                )
            local_x = self._delta_local_index[delta][x_index]
            local_y = self._delta_local_index[target_delta][y_index]
            columns_by_delta[delta][local_x] ^= 1 << local_y

        return columns_by_delta

    def _get_normalization(self) -> int:
        if self.normalization is not None:
            return self.normalization
        hat_stage = HatHomologyStage(self.knot)
        normalization = hat_stage.load_normalization()
        if normalization is not None:
            return normalization
        _, normalization = hat_stage.compute()
        return normalization

    def _get_reference_shift(self) -> tuple[int, int]:
        hat_stage = HatHomologyStage(self.knot)
        reference_shift = hat_stage.load_reference_shift()
        if reference_shift is not None:
            return reference_shift
        return hat_stage.reference_shift()

    def _expected_free_rank(self) -> int:
        factor = 1 << destabilization_steps(self.knot)
        if uses_even_strong_grading(self.knot):
            return factor << 1
        return factor

    def _destabilize_bigraded_counts(
        self,
        grading_counts: dict[tuple[int, int], int],
    ) -> dict[tuple[int, int], int]:
        current = dict(sorted(grading_counts.items(), key=lambda item: (item[0][0], item[0][1])))
        for _ in range(destabilization_steps(self.knot)):
            current = HatHomologyStage.from_tilde_to_hat(current)
        return current

    def _shift_bigraded_counts(
        self,
        grading_counts: dict[tuple[int, int], int],
    ) -> dict[str, int]:
        normalization = self._get_normalization()
        reference_shift = self._get_reference_shift()
        return {
            f"({grading[0] - normalization}, {grading[1] - reference_shift[1]})": count
            for grading, count in grading_counts.items()
        }

    @staticmethod
    def _pivot_row(column: int) -> int:
        if column == 0:
            return -1
        return column.bit_length() - 1

    def _reduce_delta_band(
        self,
        delta: int,
        columns: list[int],
        available_rows_mask: int,
    ) -> tuple[dict[int, int], int]:
        row_global_indices = self._delta_to_indices.get(delta - 1, [])
        column_global_indices = self._delta_to_indices[delta]
        pivot_to_column: dict[int, int] = {}
        reduced_columns = [0] * len(columns)
        bars: dict[int, int] = {}
        birth_mask = 0

        for local_column_index, column in enumerate(columns):
            reduced = column & available_rows_mask
            while reduced != 0:
                pivot = self._pivot_row(reduced)
                previous_column = pivot_to_column.get(pivot)
                if previous_column is None:
                    pivot_to_column[pivot] = local_column_index
                    break
                reduced ^= reduced_columns[previous_column]
            reduced_columns[local_column_index] = reduced

        for local_column_index, reduced in enumerate(reduced_columns):
            global_column_index = column_global_indices[local_column_index]
            pivot = self._pivot_row(reduced)
            if pivot == -1:
                bars[global_column_index] = -1
                birth_mask |= 1 << local_column_index
                continue
            bars[row_global_indices[pivot]] = global_column_index

        return bars, birth_mask

    def _verify_differential(self, columns_by_delta: dict[int, list[int]]) -> None:
        for delta, columns in columns_by_delta.items():
            previous = columns_by_delta.get(delta - 1)
            if previous is None:
                continue

            for local_column_index, column in enumerate(columns):
                image = 0
                current = column
                while current != 0:
                    least_bit = current & -current
                    row_index = least_bit.bit_length() - 1
                    image ^= previous[row_index]
                    current ^= least_bit

                if image != 0:
                    global_index = self._delta_to_indices[delta][local_column_index]
                    raise ValueError(
                        f"d^2 != 0 for knot {self.knot.name} at generator "
                        f"({self._index_to_i[global_index]}, {self._index_to_j[global_index]})"
                    )

    def _process_bars(self, bars: dict[int, int]) -> dict:
        raw = {"free": [], "torsion": {}}
        for start, end in bars.items():
            if end == -1:
                raw["free"].append(start)
                continue
            order = self._index_to_i[start] - self._index_to_i[end]
            if order == 0:
                continue
            raw["torsion"].setdefault(order, []).append((self._index_to_i[start], self._index_to_j[start]))

        expected_dimension = self._expected_free_rank()
        if len(raw["free"]) != expected_dimension:
            raise ValueError(
                f"Knot {self.knot.name}: free part has dimension {len(raw['free'])}, "
                f"expected {expected_dimension}"
            )

        free_counts: dict[tuple[int, int], int] = {}
        for index in raw["free"]:
            grading = (self._index_to_i[index], self._index_to_j[index])
            free_counts[grading] = free_counts.get(grading, 0) + 1
        normalized_free = self._shift_bigraded_counts(self._destabilize_bigraded_counts(free_counts))
        if len(normalized_free) == 1:
            free_grading, free_count = next(iter(normalized_free.items()))
            free_result: str | dict[str, int]
            if free_count == 1:
                free_result = free_grading
            else:
                free_result = {free_grading: free_count}
        else:
            free_result = normalized_free

        result = {"free": free_result}

        torsion_result = {}
        for order, generators in raw["torsion"].items():
            grading_counts: dict[tuple[int, int], int] = {}
            for grading in generators:
                grading_counts[grading] = grading_counts.get(grading, 0) + 1
            torsion_result[str(order)] = self._shift_bigraded_counts(
                self._destabilize_bigraded_counts(grading_counts)
            )

        result["torsion"] = torsion_result
        return result

    def compute(self) -> dict:
        columns_by_delta = self._load_delta_bands()
        if self.check_diff:
            self._verify_differential(columns_by_delta)

        bars: dict[int, int] = {}
        live_births_by_delta: dict[int, int] = {}
        for delta in sorted(self._delta_to_indices):
            available_rows_mask = live_births_by_delta.get(delta - 1, 0)
            band_bars, birth_mask = self._reduce_delta_band(
                delta,
                columns_by_delta[delta],
                available_rows_mask,
            )
            bars.update(band_bars)
            live_births_by_delta[delta] = birth_mask

        result = self._process_bars(bars)
        save_json(self.output_path, result)
        return result
