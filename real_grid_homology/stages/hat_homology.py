from __future__ import annotations

import gc
import os
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import galois
import numpy as np
from galois._domains import _linalg as galois_linalg

from ..config import GRADING_DIR, HAT_DIR
from ..io import iter_jsonl, load_json, save_json
from ..knot import Knot, SymmetryKind
from ..system_memory import (
    available_memory_bytes,
    current_process_rss_bytes,
    macos_effective_available_bytes,
    macos_memory_pressure_level,
)
from ..theory import destabilization_steps

HAT_METHOD_AUTO = "auto"
HAT_METHOD_DENSE = "dense"
HAT_METHOD_LOW_MEMORY = "low_memory"
_VALID_HAT_METHODS = {HAT_METHOD_AUTO, HAT_METHOD_DENSE, HAT_METHOD_LOW_MEMORY}


@dataclass(frozen=True)
class HatMemoryEstimate:
    total_diff_bytes: int
    max_block_bytes: int
    max_composition_bytes: int
    dense_peak_bytes: int
    low_memory_peak_bytes: int


@dataclass
class HatHomologyStage:
    knot: Knot
    check_diff: bool = False
    preferred_method: str = HAT_METHOD_AUTO
    selected_method: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.preferred_method not in _VALID_HAT_METHODS:
            raise ValueError(
                f"Unsupported hat method '{self.preferred_method}'. "
                f"Expected one of {sorted(_VALID_HAT_METHODS)}."
            )

    @property
    def grading_path(self) -> Path:
        return GRADING_DIR / f"{self.knot.name}.jsonl"

    @property
    def domain_path(self) -> Path:
        return HAT_DIR.parent.parent / "domains" / f"{self.knot.name}.jsonl"

    @property
    def output_path(self) -> Path:
        return HAT_DIR / f"{self.knot.name}.json"

    @property
    def metadata_path(self) -> Path:
        return HAT_DIR / f"{self.knot.name}.meta.json"

    def _generator_to_string(self, generator: list[int]) -> str:
        return "".join(f"{value % self.knot.size:02d}" for value in generator)

    def _reference_generator(self) -> list[int]:
        generator = [-1] * self.knot.size
        for column, row in enumerate(self.knot.o_marks):
            generator[(column + 1) % self.knot.size] = row
        return generator

    def load_normalization(self) -> int | None:
        if not self.metadata_path.exists():
            return None
        payload = load_json(self.metadata_path)
        normalization = payload.get("normalization")
        if normalization is None:
            return None
        return int(normalization)

    def load_reference_shift(self) -> tuple[int, int] | None:
        if not self.metadata_path.exists():
            return None
        payload = load_json(self.metadata_path)
        reference_shift = payload.get("reference_shift")
        if reference_shift is None:
            return None
        return (int(reference_shift[0]), int(reference_shift[1]))

    def reference_shift(self) -> tuple[int, int]:
        target_key = self._generator_to_string(self._reference_generator())
        for row in iter_jsonl(self.grading_path):
            generator_key = self._generator_to_string(row["generator"])
            if generator_key == target_key:
                grading = row["grading"]
                return (int(grading[0]), int(grading[1]))
        raise ValueError(f"Reference generator O^NW not found in grading data for knot {self.knot.name}")

    def _load_graded_generators(self) -> tuple[dict[tuple[int, int], dict[str, int]], dict[str, tuple[int, int]]]:
        graded_index: dict[tuple[int, int], dict[str, int]] = {}
        generator_to_grading: dict[str, tuple[int, int]] = {}

        for row in iter_jsonl(self.grading_path):
            grading = (int(row["grading"][0]), int(row["grading"][1]))
            generator_key = self._generator_to_string(row["generator"])
            generator_to_grading[generator_key] = grading
            index_map = graded_index.setdefault(grading, {})
            index_map[generator_key] = len(index_map)
        return graded_index, generator_to_grading

    def _load_maslov_graded_generators(self) -> tuple[dict[int, dict[str, int]], dict[str, int]]:
        graded_index: dict[int, dict[str, int]] = {}
        generator_to_grading: dict[str, int] = {}

        for row in iter_jsonl(self.grading_path):
            maslov_grading = int(row["grading"][1])
            generator_key = self._generator_to_string(row["generator"])
            generator_to_grading[generator_key] = maslov_grading
            index_map = graded_index.setdefault(maslov_grading, {})
            index_map[generator_key] = len(index_map)
        return graded_index, generator_to_grading

    def _block_source_grading_keys(self, graded_index: dict[tuple[int, int], dict[str, int]]) -> list[tuple[int, int]]:
        return [
            grading
            for grading in graded_index
            if (grading[0], grading[1] - 1) in graded_index
        ]

    def _maslov_source_grading_keys(self, graded_index: dict[int, dict[str, int]]) -> list[int]:
        return [grading for grading in graded_index if grading - 1 in graded_index]

    def _estimate_strong_memory(self, graded_index: dict[tuple[int, int], dict[str, int]]) -> HatMemoryEstimate:
        total_diff_bytes = 0
        max_block_bytes = 0
        max_composition_bytes = 0

        channels: dict[int, list[int]] = defaultdict(list)
        for alexander, maslov in graded_index:
            channels[alexander].append(maslov)

        for alexander, maslov_values in channels.items():
            unique = sorted(set(maslov_values))
            for maslov in unique:
                source = (alexander, maslov)
                target = (alexander, maslov - 1)
                if target not in graded_index:
                    continue
                block_bytes = len(graded_index[target]) * len(graded_index[source])
                total_diff_bytes += block_bytes
                max_block_bytes = max(max_block_bytes, block_bytes)

                previous_target = (alexander, maslov - 2)
                if previous_target in graded_index and target in graded_index:
                    composition_bytes = len(graded_index[previous_target]) * len(graded_index[source])
                    max_composition_bytes = max(max_composition_bytes, composition_bytes)

        dense_peak_bytes = total_diff_bytes + 3 * max_block_bytes
        low_memory_peak_bytes = 2 * max_block_bytes
        if self.check_diff:
            dense_peak_bytes += max_composition_bytes
            low_memory_peak_bytes += max_composition_bytes

        return HatMemoryEstimate(
            total_diff_bytes=total_diff_bytes,
            max_block_bytes=max_block_bytes,
            max_composition_bytes=max_composition_bytes,
            dense_peak_bytes=dense_peak_bytes,
            low_memory_peak_bytes=low_memory_peak_bytes,
        )

    def _estimate_periodic_memory(self, graded_index: dict[int, dict[str, int]]) -> HatMemoryEstimate:
        total_diff_bytes = 0
        max_block_bytes = 0
        max_composition_bytes = 0

        for maslov in sorted(graded_index):
            target = maslov - 1
            if target not in graded_index:
                continue
            block_bytes = len(graded_index[target]) * len(graded_index[maslov])
            total_diff_bytes += block_bytes
            max_block_bytes = max(max_block_bytes, block_bytes)

            previous_target = maslov - 2
            if previous_target in graded_index:
                composition_bytes = len(graded_index[previous_target]) * len(graded_index[maslov])
                max_composition_bytes = max(max_composition_bytes, composition_bytes)

        dense_peak_bytes = total_diff_bytes + 3 * max_block_bytes
        low_memory_peak_bytes = 2 * max_block_bytes
        if self.check_diff:
            dense_peak_bytes += max_composition_bytes
            low_memory_peak_bytes += max_composition_bytes

        return HatMemoryEstimate(
            total_diff_bytes=total_diff_bytes,
            max_block_bytes=max_block_bytes,
            max_composition_bytes=max_composition_bytes,
            dense_peak_bytes=dense_peak_bytes,
            low_memory_peak_bytes=low_memory_peak_bytes,
        )

    def _memory_safety_factor(self) -> float:
        return float(os.environ.get("GRID2_HAT_MEMORY_SAFETY_FACTOR", "1.10"))

    def _capture_memory_context(self) -> tuple[int | None, int | None]:
        gc.collect()
        return current_process_rss_bytes(), available_memory_bytes()

    def _effective_available(self, available: int | None) -> int | None:
        """Return the best available-memory estimate for the current platform.

        On macOS, ``psutil.virtual_memory().available`` ignores the kernel's
        ability to compress active pages.  When the memory-pressure level is
        normal (1), we use ``total - wired`` as a more realistic ceiling.
        On other platforms (or if the pressure query fails) we fall back to
        the plain *available* value.
        """
        effective = macos_effective_available_bytes()
        if effective is None:
            return available
        pressure = macos_memory_pressure_level()
        if pressure is not None and pressure <= 1:
            return effective
        return available

    def _resolve_requested_method(self) -> str:
        forced = os.environ.get("GRID2_HAT_FORCE_METHOD")
        if forced is not None:
            if forced not in _VALID_HAT_METHODS:
                raise ValueError(
                    f"Unsupported GRID2_HAT_FORCE_METHOD='{forced}'. "
                    f"Expected one of {sorted(_VALID_HAT_METHODS)}."
                )
            return forced
        return self.preferred_method

    def _select_method(self, estimate: HatMemoryEstimate) -> tuple[str, int | None, int | None]:
        requested = self._resolve_requested_method()
        process_rss, available = self._capture_memory_context()
        effective = self._effective_available(available)
        safety = self._memory_safety_factor()

        def required_bytes(method: str) -> int:
            if method == HAT_METHOD_DENSE:
                return estimate.dense_peak_bytes
            if method == HAT_METHOD_LOW_MEMORY:
                return estimate.low_memory_peak_bytes
            raise ValueError(f"Unsupported hat method '{method}'")

        if requested != HAT_METHOD_AUTO:
            required = required_bytes(requested)
            if effective is not None and effective < int(required * safety):
                raise MemoryError(
                    f"Hat homology method '{requested}' for knot {self.knot.name} is estimated to require "
                    f"{required} additional bytes (process RSS before hat: {process_rss}, safety factor {safety}), "
                    f"but only {effective} bytes appear available (effective)."
                )
            return requested, available, process_rss

        if estimate.max_block_bytes == 0:
            return HAT_METHOD_DENSE, available, process_rss

        if effective is None:
            return HAT_METHOD_LOW_MEMORY, available, process_rss

        if effective >= int(estimate.dense_peak_bytes * safety):
            return HAT_METHOD_DENSE, available, process_rss
        if effective >= int(estimate.low_memory_peak_bytes * safety):
            return HAT_METHOD_LOW_MEMORY, available, process_rss

        raise MemoryError(
            f"Hat homology for knot {self.knot.name} cannot proceed safely. "
            f"Estimated dense peak: {estimate.dense_peak_bytes} bytes, "
            f"estimated low-memory peak: {estimate.low_memory_peak_bytes} bytes, "
            f"process RSS before hat: {process_rss} bytes, "
            f"available memory: {available} bytes (psutil), "
            f"effective available: {effective} bytes, safety factor: {safety}."
        )

    def memory_plan(self) -> dict[str, int | str | None]:
        if self.knot.symmetry_kind is SymmetryKind.PERIODIC:
            graded_index, _ = self._load_maslov_graded_generators()
            estimate = self._estimate_periodic_memory(graded_index)
        else:
            graded_index, _ = self._load_graded_generators()
            estimate = self._estimate_strong_memory(graded_index)

        method, available, process_rss = self._select_method(estimate)
        effective = self._effective_available(available)
        safety = self._memory_safety_factor()
        return {
            "selected_method": method,
            "process_rss_before_hat_bytes": process_rss,
            "available_memory_bytes": available,
            "effective_available_memory_bytes": effective,
            "dense_peak_bytes": estimate.dense_peak_bytes,
            "low_memory_peak_bytes": estimate.low_memory_peak_bytes,
            "dense_required_available_bytes": int(estimate.dense_peak_bytes * safety),
            "low_memory_required_available_bytes": int(estimate.low_memory_peak_bytes * safety),
            "dense_projected_peak_rss_bytes": None if process_rss is None else process_rss + estimate.dense_peak_bytes,
            "low_memory_projected_peak_rss_bytes": None if process_rss is None else process_rss + estimate.low_memory_peak_bytes,
            "total_diff_bytes": estimate.total_diff_bytes,
            "max_block_bytes": estimate.max_block_bytes,
            "max_composition_bytes": estimate.max_composition_bytes,
        }

    def _init_dense_strong_differentials(
        self,
        graded_index: dict[tuple[int, int], dict[str, int]],
    ) -> dict[tuple[int, int], np.ndarray | None]:
        graded_diff: dict[tuple[int, int], np.ndarray | None] = {}
        for grading, index_map in graded_index.items():
            target = (grading[0], grading[1] - 1)
            if target in graded_index:
                graded_diff[grading] = np.zeros((len(graded_index[target]), len(index_map)), dtype=np.uint8)
            else:
                graded_diff[grading] = None
        return graded_diff

    def _init_dense_periodic_differentials(
        self,
        graded_index: dict[int, dict[str, int]],
    ) -> dict[int, np.ndarray | None]:
        graded_diff: dict[int, np.ndarray | None] = {}
        for grading, index_map in graded_index.items():
            target = grading - 1
            if target in graded_index:
                graded_diff[grading] = np.zeros((len(graded_index[target]), len(index_map)), dtype=np.uint8)
            else:
                graded_diff[grading] = None
        return graded_diff

    def _compute_dense_strong_ranks(
        self,
        graded_index: dict[tuple[int, int], dict[str, int]],
        generator_to_grading: dict[str, tuple[int, int]],
    ) -> dict[tuple[int, int], int]:
        graded_diff = self._init_dense_strong_differentials(graded_index)

        for row in iter_jsonl(self.domain_path):
            if row["O-marks"]:
                continue

            x_key = self._generator_to_string(row["x"])
            y_key = self._generator_to_string(row["y"])
            x_grading = generator_to_grading[x_key]
            y_grading = generator_to_grading[y_key]

            if self.check_diff and y_grading != (x_grading[0], x_grading[1] - 1):
                raise ValueError(
                    f"Grading mismatch for domain x={row['x']} y={row['y']}: "
                    f"{x_grading} -> {y_grading}"
                )

            matrix = graded_diff[x_grading]
            if matrix is not None:
                matrix[graded_index[y_grading][y_key], graded_index[x_grading][x_key]] ^= 1

        gf2 = galois.GF(2)
        if self.check_diff:
            for grading, matrix in graded_diff.items():
                previous = (grading[0], grading[1] - 1)
                if matrix is None or previous not in graded_diff or graded_diff[previous] is None:
                    continue
                if not np.all(gf2(graded_diff[previous]) @ gf2(matrix) == 0):
                    raise ValueError(f"D^2 != 0 at grading {grading}")

        ranks: dict[tuple[int, int], int] = {}
        for grading, matrix in graded_diff.items():
            if matrix is None:
                ranks[grading] = 0
            else:
                ranks[grading] = int(np.linalg.matrix_rank(gf2(matrix)))
        return ranks

    def _compute_dense_periodic_ranks(
        self,
        graded_index: dict[int, dict[str, int]],
        generator_to_grading: dict[str, int],
    ) -> dict[int, int]:
        graded_diff = self._init_dense_periodic_differentials(graded_index)

        for row in iter_jsonl(self.domain_path):
            if row["O-marks"]:
                continue

            x_key = self._generator_to_string(row["x"])
            y_key = self._generator_to_string(row["y"])
            x_grading = generator_to_grading[x_key]
            y_grading = generator_to_grading[y_key]

            if self.check_diff and y_grading != x_grading - 1:
                raise ValueError(
                    f"Maslov grading mismatch for domain x={row['x']} y={row['y']}: "
                    f"{x_grading} -> {y_grading}"
                )

            matrix = graded_diff[x_grading]
            if matrix is not None:
                matrix[graded_index[y_grading][y_key], graded_index[x_grading][x_key]] ^= 1

        gf2 = galois.GF(2)
        if self.check_diff:
            for grading, matrix in graded_diff.items():
                previous = grading - 1
                if matrix is None or previous not in graded_diff or graded_diff[previous] is None:
                    continue
                if not np.all(gf2(graded_diff[previous]) @ gf2(matrix) == 0):
                    raise ValueError(f"D^2 != 0 at Maslov grading {grading}")

        ranks: dict[int, int] = {}
        for grading, matrix in graded_diff.items():
            if matrix is None:
                ranks[grading] = 0
            else:
                ranks[grading] = int(np.linalg.matrix_rank(gf2(matrix)))
        return ranks

    def _prepare_spool_paths(self, gradings: list[tuple[int, int]] | list[int], spool_dir: Path) -> dict:
        ordered = sorted(
            gradings,
            key=lambda grading: grading if isinstance(grading, int) else (grading[0], grading[1]),
        )
        return {grading: spool_dir / f"{index:04d}.bin" for index, grading in enumerate(ordered)}

    def _spool_strong_block_entries(
        self,
        graded_index: dict[tuple[int, int], dict[str, int]],
        generator_to_grading: dict[str, tuple[int, int]],
        spool_paths: dict[tuple[int, int], Path],
    ) -> None:
        handles: dict[tuple[int, int], object] = {}
        try:
            for row in iter_jsonl(self.domain_path):
                if row["O-marks"]:
                    continue

                x_key = self._generator_to_string(row["x"])
                y_key = self._generator_to_string(row["y"])
                x_grading = generator_to_grading[x_key]
                y_grading = generator_to_grading[y_key]

                expected = (x_grading[0], x_grading[1] - 1)
                if self.check_diff and y_grading != expected:
                    raise ValueError(
                        f"Grading mismatch for domain x={row['x']} y={row['y']}: "
                        f"{x_grading} -> {y_grading}"
                    )

                if x_grading not in spool_paths:
                    continue

                handle = handles.get(x_grading)
                if handle is None:
                    handle = spool_paths[x_grading].open("ab")
                    handles[x_grading] = handle

                handle.write(
                    struct.pack(
                        "<II",
                        graded_index[y_grading][y_key],
                        graded_index[x_grading][x_key],
                    )
                )
        finally:
            for handle in handles.values():
                handle.close()

    def _spool_periodic_block_entries(
        self,
        graded_index: dict[int, dict[str, int]],
        generator_to_grading: dict[str, int],
        spool_paths: dict[int, Path],
    ) -> None:
        handles: dict[int, object] = {}
        try:
            for row in iter_jsonl(self.domain_path):
                if row["O-marks"]:
                    continue

                x_key = self._generator_to_string(row["x"])
                y_key = self._generator_to_string(row["y"])
                x_grading = generator_to_grading[x_key]
                y_grading = generator_to_grading[y_key]

                expected = x_grading - 1
                if self.check_diff and y_grading != expected:
                    raise ValueError(
                        f"Maslov grading mismatch for domain x={row['x']} y={row['y']}: "
                        f"{x_grading} -> {y_grading}"
                    )

                if x_grading not in spool_paths:
                    continue

                handle = handles.get(x_grading)
                if handle is None:
                    handle = spool_paths[x_grading].open("ab")
                    handles[x_grading] = handle

                handle.write(
                    struct.pack(
                        "<II",
                        graded_index[y_grading][y_key],
                        graded_index[x_grading][x_key],
                    )
                )
        finally:
            for handle in handles.values():
                handle.close()

    def _load_block_matrix(self, path: Path, shape: tuple[int, int]) -> np.ndarray:
        matrix = np.zeros(shape, dtype=np.uint8)
        if not path.exists() or path.stat().st_size == 0:
            return matrix

        with path.open("rb") as handle:
            while True:
                chunk = np.fromfile(handle, dtype=np.uint32, count=32768)
                if chunk.size == 0:
                    break
                pairs = chunk.reshape(-1, 2)
                np.bitwise_xor.at(matrix, (pairs[:, 0], pairs[:, 1]), 1)
        return matrix

    def _low_memory_rank(self, matrix: np.ndarray, field: type[galois.FieldArray]) -> int:
        if matrix.size == 0:
            return 0
        _, pivot_count = galois_linalg.row_reduce_jit(field)(field(matrix, copy=False))
        return int(pivot_count)

    def _verify_low_memory_block_composition(
        self,
        previous_matrix: np.ndarray | None,
        matrix: np.ndarray | None,
        grading: tuple[int, int] | int,
        field: type[galois.FieldArray],
    ) -> None:
        if previous_matrix is None or matrix is None:
            return
        if not np.all(field(previous_matrix, copy=False) @ field(matrix, copy=False) == 0):
            if isinstance(grading, tuple):
                raise ValueError(f"D^2 != 0 at grading {grading}")
            raise ValueError(f"D^2 != 0 at Maslov grading {grading}")

    def _compute_low_memory_strong_ranks(
        self,
        graded_index: dict[tuple[int, int], dict[str, int]],
        spool_paths: dict[tuple[int, int], Path],
    ) -> dict[tuple[int, int], int]:
        field = galois.GF(2)
        ranks: dict[tuple[int, int], int] = {grading: 0 for grading in graded_index}
        channels: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for grading in spool_paths:
            channels[grading[0]].append(grading)

        for channel in channels.values():
            channel.sort(key=lambda grading: grading[1])
            previous_matrix: np.ndarray | None = None
            for grading in channel:
                target = (grading[0], grading[1] - 1)
                shape = (len(graded_index[target]), len(graded_index[grading]))
                matrix = self._load_block_matrix(spool_paths[grading], shape)
                if self.check_diff:
                    self._verify_low_memory_block_composition(previous_matrix, matrix, grading, field)
                ranks[grading] = self._low_memory_rank(matrix, field)
                previous_matrix = matrix if self.check_diff else None
        return ranks

    def _compute_low_memory_periodic_ranks(
        self,
        graded_index: dict[int, dict[str, int]],
        spool_paths: dict[int, Path],
    ) -> dict[int, int]:
        field = galois.GF(2)
        ranks: dict[int, int] = {grading: 0 for grading in graded_index}
        previous_matrix: np.ndarray | None = None

        for grading in sorted(spool_paths):
            target = grading - 1
            shape = (len(graded_index[target]), len(graded_index[grading]))
            matrix = self._load_block_matrix(spool_paths[grading], shape)
            if self.check_diff:
                self._verify_low_memory_block_composition(previous_matrix, matrix, grading, field)
            ranks[grading] = self._low_memory_rank(matrix, field)
            previous_matrix = matrix if self.check_diff else None
        return ranks

    def _compute_tilde_homology(
        self,
        graded_index: dict[tuple[int, int], dict[str, int]],
        ranks: dict[tuple[int, int], int],
    ) -> dict[tuple[int, int], int]:
        homology: dict[tuple[int, int], int] = {}
        for grading, index_map in graded_index.items():
            rank_out = ranks.get(grading, 0)
            rank_in = ranks.get((grading[0], grading[1] + 1), 0)
            dimension = len(index_map) - rank_out - rank_in
            if dimension != 0:
                homology[grading] = dimension
        return dict(sorted(homology.items(), key=lambda item: (item[0][0], item[0][1])))

    @staticmethod
    def from_tilde_to_hat(homology_tilde: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
        if len(homology_tilde) <= 1:
            return dict(homology_tilde)

        homology_hat: dict[tuple[int, int], int] = {}
        for grading, value in homology_tilde.items():
            shifted_up = (grading[0] + 2, grading[1] + 1)
            shifted_down = (grading[0] - 2, grading[1] - 1)
            if shifted_up not in homology_tilde:
                continue
            if shifted_down not in homology_tilde:
                homology_hat[shifted_up] = value
            else:
                homology_hat[shifted_up] = value - homology_hat[grading]
        return homology_hat

    def _normalize_hat(self, homology_tilde: dict[tuple[int, int], int]) -> tuple[dict[tuple[int, int], int], int]:
        current = homology_tilde
        for _ in range(destabilization_steps(self.knot)):
            current = self.from_tilde_to_hat(current)

        if not current:
            return {}, 0

        keys = list(current.keys())
        normalization = (keys[0][0] + keys[-1][0]) // 2
        normalized = {(grading[0] - normalization, grading[1]): value for grading, value in current.items()}
        return normalized, normalization

    def _periodic_destabilization_factor(self) -> int:
        return 1 << destabilization_steps(self.knot)

    def _destabilize_periodic_homology(self, homology_tilde: dict[int, int]) -> dict[int, int]:
        factor = self._periodic_destabilization_factor()
        homology_hat: dict[int, int] = {}
        for grading, dimension in sorted(homology_tilde.items()):
            if dimension % factor != 0:
                raise ValueError(
                    f"Periodic hat homology at Maslov grading {grading} has dimension {dimension}, "
                    f"which is not divisible by destabilization factor {factor}"
                )
            reduced = dimension // factor
            if reduced != 0:
                homology_hat[grading] = reduced
        return homology_hat

    def _shift_maslov_in_bigraded_homology(
        self,
        homology: dict[tuple[int, int], int],
        maslov_shift: int,
    ) -> dict[tuple[int, int], int]:
        return {(grading[0], grading[1] - maslov_shift): value for grading, value in homology.items()}

    def _save_result(
        self,
        *,
        formatted: dict[str, int],
        normalization: int,
        method: str,
        estimate: HatMemoryEstimate,
        available: int | None,
        process_rss: int | None,
        periodic: bool,
        reference_shift: tuple[int, int] | None = None,
    ) -> None:
        save_json(self.output_path, formatted)

        metadata = {
            "method": method,
            "process_rss_before_hat_bytes": process_rss,
            "available_memory_bytes": available,
            "dense_peak_estimate_bytes": estimate.dense_peak_bytes,
            "low_memory_peak_estimate_bytes": estimate.low_memory_peak_bytes,
            "max_block_bytes": estimate.max_block_bytes,
        }
        if periodic:
            metadata.update(
                {
                    "grading_mode": "maslov_only",
                    "destabilization_factor": self._periodic_destabilization_factor(),
                }
            )
        else:
            assert reference_shift is not None
            metadata.update(
                {
                    "normalization": normalization,
                    "reference_shift": [reference_shift[0], reference_shift[1]],
                }
            )

        save_json(self.metadata_path, metadata)

    def _compute_periodic_with_method(
        self,
        *,
        method: str,
        graded_index: dict[int, dict[str, int]],
        generator_to_grading: dict[str, int],
        estimate: HatMemoryEstimate,
        available: int | None,
        process_rss: int | None,
    ) -> tuple[dict[str, int], int]:
        if method == HAT_METHOD_DENSE:
            ranks = self._compute_dense_periodic_ranks(graded_index, generator_to_grading)
        elif method == HAT_METHOD_LOW_MEMORY:
            source_gradings = self._maslov_source_grading_keys(graded_index)
            with TemporaryDirectory() as spool_dir_name:
                spool_dir = Path(spool_dir_name)
                spool_paths = self._prepare_spool_paths(source_gradings, spool_dir)
                self._spool_periodic_block_entries(graded_index, generator_to_grading, spool_paths)
                ranks = self._compute_low_memory_periodic_ranks(graded_index, spool_paths)
        else:
            raise ValueError(f"Unsupported periodic hat method '{method}'")

        homology: dict[int, int] = {}
        for grading, index_map in graded_index.items():
            rank_out = ranks.get(grading, 0)
            rank_in = ranks.get(grading + 1, 0)
            dimension = len(index_map) - rank_out - rank_in
            if dimension != 0:
                homology[grading] = dimension

        destabilized = self._destabilize_periodic_homology(homology)
        formatted = {str(grading): dimension for grading, dimension in destabilized.items()}
        self._save_result(
            formatted=formatted,
            normalization=0,
            method=method,
            estimate=estimate,
            available=available,
            process_rss=process_rss,
            periodic=True,
        )
        return formatted, 0

    def _compute_strong_with_method(
        self,
        *,
        method: str,
        graded_index: dict[tuple[int, int], dict[str, int]],
        generator_to_grading: dict[str, tuple[int, int]],
        estimate: HatMemoryEstimate,
        available: int | None,
        process_rss: int | None,
    ) -> tuple[dict[str, int], int]:
        if method == HAT_METHOD_DENSE:
            ranks = self._compute_dense_strong_ranks(graded_index, generator_to_grading)
        elif method == HAT_METHOD_LOW_MEMORY:
            source_gradings = self._block_source_grading_keys(graded_index)
            with TemporaryDirectory() as spool_dir_name:
                spool_dir = Path(spool_dir_name)
                spool_paths = self._prepare_spool_paths(source_gradings, spool_dir)
                self._spool_strong_block_entries(graded_index, generator_to_grading, spool_paths)
                ranks = self._compute_low_memory_strong_ranks(graded_index, spool_paths)
        else:
            raise ValueError(f"Unsupported strong hat method '{method}'")

        tilde_homology = self._compute_tilde_homology(graded_index, ranks)
        hat_homology, normalization = self._normalize_hat(tilde_homology)
        reference_shift = self.reference_shift()
        shifted = self._shift_maslov_in_bigraded_homology(hat_homology, reference_shift[1])
        formatted = {f"({grading[0]}, {grading[1]})": value for grading, value in shifted.items()}
        self._save_result(
            formatted=formatted,
            normalization=normalization,
            method=method,
            estimate=estimate,
            available=available,
            process_rss=process_rss,
            periodic=False,
            reference_shift=reference_shift,
        )
        return formatted, normalization

    def compute(self) -> tuple[dict[str, int], int]:
        if self.knot.symmetry_kind is SymmetryKind.PERIODIC:
            graded_index, generator_to_grading = self._load_maslov_graded_generators()
            estimate = self._estimate_periodic_memory(graded_index)
            method, available, process_rss = self._select_method(estimate)
            self.selected_method = method
            return self._compute_periodic_with_method(
                method=method,
                graded_index=graded_index,
                generator_to_grading=generator_to_grading,
                estimate=estimate,
                available=available,
                process_rss=process_rss,
            )

        graded_index, generator_to_grading = self._load_graded_generators()
        estimate = self._estimate_strong_memory(graded_index)
        method, available, process_rss = self._select_method(estimate)
        self.selected_method = method
        return self._compute_strong_with_method(
            method=method,
            graded_index=graded_index,
            generator_to_grading=generator_to_grading,
            estimate=estimate,
            available=available,
            process_rss=process_rss,
        )
