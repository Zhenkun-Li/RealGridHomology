from __future__ import annotations

from pathlib import Path

from .config import DOMAINS_DIR, GENERATORS_DIR, GRADING_DIR, HAT_DIR, KNOTS_DIR, MINUS_DIR, POLYNOMIAL_DIR, RECTANGLES_DIR
from .io import load_json, save_json
from .knot import Knot, SymmetryKind
from .stages.domains import DomainStage
from .stages.generators import GeneratorStage
from .stages.grading import GradingStage
from .stages.hat_homology import HAT_METHOD_AUTO, HatHomologyStage
from .stages.minus_homology import MinusHomologyStage
from .stages.polynomial import PolynomialStage
from .stages.rectangles import RectangleStage

SIZE_LIMIT_POLYNOMIAL = 17
SIZE_LIMIT_HAT = 13
SIZE_LIMIT_MINUS = 11
VALID_MODES = {"overwrite", "skip", "delete"}


def available_knots() -> list[str]:
    if not KNOTS_DIR.exists():
        return []
    return sorted(path.stem for path in KNOTS_DIR.glob("*.json"))


def _log(message: str, progress_callback=None) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _delete_if_exists(path: Path, progress_callback=None) -> None:
    if path.exists():
        path.unlink()
        _log(f"Deleted existing file: {path}", progress_callback)


def _delete_polynomial_entry(knot_name: str, progress_callback=None) -> None:
    polynomial_path = POLYNOMIAL_DIR / "polynomial.json"
    if not polynomial_path.exists():
        return
    polynomial_results = load_json(polynomial_path)
    if knot_name not in polynomial_results:
        return
    del polynomial_results[knot_name]
    save_json(polynomial_path, polynomial_results)
    _log(f"Removed polynomial entry for {knot_name}", progress_callback)


def run_workflow(
    knot_name: str,
    *,
    mode: str = "overwrite",
    check_diff: bool = False,
    hat_method: str = HAT_METHOD_AUTO,
    progress_callback=None,
) -> dict:
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode '{mode}'. Expected one of {sorted(VALID_MODES)}.")

    knot_path = KNOTS_DIR / f"{knot_name}.json"
    if not knot_path.exists():
        raise FileNotFoundError(f"Knot data file not found: {knot_path}")

    knot = Knot.from_path(knot_path)
    size = knot.size
    summary: dict[str, object] = {
        "knot": knot.name,
        "size": size,
        "symmetry_kind": knot.symmetry_kind.value,
        "mode": mode,
    }
    _log(
        f"Loaded knot '{knot_name}' ({knot.symmetry_kind.value}) with grid size {size}",
        progress_callback,
    )

    if size > SIZE_LIMIT_POLYNOMIAL:
        summary["status"] = "skipped_all"
        _log(f"Size {size} > {SIZE_LIMIT_POLYNOMIAL}: no computation performed", progress_callback)
        return summary

    compute_polynomial = (
        knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE
        and size <= SIZE_LIMIT_POLYNOMIAL
    )
    compute_hat = size <= SIZE_LIMIT_HAT
    compute_minus = (
        knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE
        and size <= SIZE_LIMIT_MINUS
    )

    generator_path = GENERATORS_DIR / f"size-{size}.jsonl"
    if generator_path.exists() and mode == "skip":
        _log("Step 1: Generators exist (skipping)", progress_callback)
    else:
        if mode == "delete":
            _delete_if_exists(generator_path, progress_callback)
        _log("Step 1: Generating generators...", progress_callback)
        GeneratorStage(size).compute()
    summary["generator_path"] = str(generator_path)

    rectangle_path = RECTANGLES_DIR / f"{knot_name}.jsonl"
    if rectangle_path.exists() and mode == "skip":
        _log("Step 2: Rectangles exist (skipping)", progress_callback)
    else:
        if mode == "delete":
            _delete_if_exists(rectangle_path, progress_callback)
        _log("Step 2: Generating rectangles...", progress_callback)
        RectangleStage(knot).compute()
    summary["rectangle_path"] = str(rectangle_path)

    domain_path = DOMAINS_DIR / f"{knot_name}.jsonl"
    if domain_path.exists() and mode == "skip":
        _log("Step 3: Domains exist (skipping)", progress_callback)
    else:
        if mode == "delete":
            _delete_if_exists(domain_path, progress_callback)
        _log("Step 3: Generating domains...", progress_callback)
        DomainStage(knot).compute()
    summary["domain_path"] = str(domain_path)

    grading_path = GRADING_DIR / f"{knot_name}.jsonl"
    if grading_path.exists() and mode == "skip":
        _log("Step 4: Gradings exist (skipping)", progress_callback)
    else:
        if mode == "delete":
            _delete_if_exists(grading_path, progress_callback)
        _log("Step 4: Computing gradings...", progress_callback)
        GradingStage(knot).compute()
    summary["grading_path"] = str(grading_path)

    polynomial_path = POLYNOMIAL_DIR / "polynomial.json"
    if compute_polynomial:
        polynomial_results = load_json(polynomial_path) if polynomial_path.exists() else {}
        if knot_name in polynomial_results and mode == "skip":
            _log("Step 5: Polynomial exists (skipping)", progress_callback)
        else:
            _log("Step 5: Computing polynomial...", progress_callback)
            PolynomialStage(knot).compute()
        summary["polynomial_path"] = str(polynomial_path)
    else:
        if mode == "delete":
            _delete_polynomial_entry(knot_name, progress_callback)
        if knot.symmetry_kind is SymmetryKind.PERIODIC:
            _log("Step 5: Polynomial skipped (periodic setup)", progress_callback)
        else:
            _log(f"Step 5: Polynomial skipped (size {size} > {SIZE_LIMIT_POLYNOMIAL})", progress_callback)
        summary["polynomial_path"] = None

    hat_path = HAT_DIR / f"{knot_name}.json"
    hat_meta_path = HAT_DIR / f"{knot_name}.meta.json"
    if compute_hat:
        if hat_path.exists() and mode == "skip":
            _log("Step 6: Hat homology exists (skipping)", progress_callback)
        else:
            if mode == "delete":
                _delete_if_exists(hat_path, progress_callback)
                _delete_if_exists(hat_meta_path, progress_callback)
            _log("Step 6: Computing hat homology...", progress_callback)
            hat_stage = HatHomologyStage(
                knot,
                check_diff=check_diff,
                preferred_method=hat_method,
            )
            hat_stage.compute()
            summary["hat_method"] = hat_stage.selected_method
        summary["hat_path"] = str(hat_path)
        summary["hat_metadata_path"] = str(hat_meta_path)
    else:
        _log(f"Step 6: Hat homology skipped (size {size} > {SIZE_LIMIT_HAT})", progress_callback)
        summary["hat_path"] = None
        summary["hat_metadata_path"] = None

    minus_path = MINUS_DIR / f"{knot_name}.json"
    if compute_minus:
        if minus_path.exists() and mode == "skip":
            _log("Step 7: Minus homology exists (skipping)", progress_callback)
        else:
            if mode == "delete":
                _delete_if_exists(minus_path, progress_callback)
            _log("Step 7: Computing minus homology...", progress_callback)
            MinusHomologyStage(knot, check_diff=check_diff).compute()
        summary["minus_path"] = str(minus_path)
    else:
        if knot.symmetry_kind is SymmetryKind.PERIODIC:
            _log("Step 7: Minus homology skipped (periodic setup)", progress_callback)
        else:
            _log(f"Step 7: Minus homology skipped (size {size} > {SIZE_LIMIT_MINUS})", progress_callback)
        summary["minus_path"] = None

    summary["status"] = "completed"
    _log(f"Workflow completed for '{knot_name}'", progress_callback)
    return summary
