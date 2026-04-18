from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..config import POLYNOMIAL_DIR
from ..io import iter_jsonl, load_json, save_json
from ..knot import Knot, SymmetryKind
from .hat_homology import HatHomologyStage
from ..theory import destabilization_steps

_POLYNOMIAL_RESULTS_CACHE: dict[Path, dict] = {}


@dataclass
class PolynomialStage:
    knot: Knot

    @property
    def grading_path(self) -> Path:
        return POLYNOMIAL_DIR.parent / "grading" / f"{self.knot.name}.jsonl"

    @property
    def output_path(self) -> Path:
        return POLYNOMIAL_DIR / "polynomial.json"

    def _load_existing_results(self) -> dict:
        cached = _POLYNOMIAL_RESULTS_CACHE.get(self.output_path)
        if cached is not None:
            return cached

        if self.output_path.exists():
            cached = load_json(self.output_path)
        else:
            cached = {}
        _POLYNOMIAL_RESULTS_CACHE[self.output_path] = cached
        return cached

    def _parse_grading_coefficients(self) -> dict[int, int]:
        coefficients: dict[int, int] = defaultdict(int)
        for row in iter_jsonl(self.grading_path):
            alexander, maslov = row["grading"]
            coefficients[alexander] += 1 if maslov % 2 == 0 else -1
        return dict(coefficients)

    def _from_tilde_to_hat(self, values: list[int]) -> list[int]:
        if len(values) <= 2:
            return values.copy()

        result = [-values[0], -values[1]]
        for index in range(2, len(values) - 2):
            result.append(result[index - 2] - values[index])
        return result

    def _center_alexander_support(self, minimal_grading: int, values: list[int]) -> int:
        non_zero_indices = [index for index, value in enumerate(values) if value != 0]
        if not non_zero_indices:
            return 0

        min_grading = minimal_grading + non_zero_indices[0]
        max_grading = minimal_grading + non_zero_indices[-1]
        return minimal_grading - ((min_grading + max_grading) // 2)

    def _reference_maslov_shift(self) -> int:
        if self.knot.symmetry_kind is not SymmetryKind.STRONGLY_INVERTIBLE:
            return 0
        return HatHomologyStage(self.knot).reference_shift()[1]

    def _format_coefficients(self, coefficients: dict[int, int]) -> dict:
        non_zero_keys = [key for key, value in coefficients.items() if value != 0]
        if not non_zero_keys:
            return {"minimal_non-zero_grading": 0, "coefficients": []}

        min_key = min(non_zero_keys)
        max_key = max(non_zero_keys)
        values = [coefficients.get(key, 0) for key in range(min_key, max_key + 1)]

        iterations = destabilization_steps(self.knot)
        for _ in range(iterations):
            values = self._from_tilde_to_hat(values)

        minimal_grading = min_key + 2 * iterations
        if self.knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE:
            if self._reference_maslov_shift() % 2 != 0:
                values = [-value for value in values]
            minimal_grading = self._center_alexander_support(minimal_grading, values)

        return {
            "minimal_non-zero_grading": minimal_grading,
            "coefficients": values,
        }

    def compute(self) -> dict:
        if self.knot.symmetry_kind is SymmetryKind.PERIODIC:
            raise ValueError(
                "Polynomial invariants are not defined for periodic knots in this migration."
            )
        results = self._load_existing_results()
        formatted = self._format_coefficients(self._parse_grading_coefficients())
        if results.get(self.knot.name) != formatted:
            results[self.knot.name] = formatted
            save_json(self.output_path, results)
        return formatted
