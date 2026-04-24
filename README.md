# RealGridHomology

RealGridHomology is a standalone Python implementation for computing real grid-homological data from anti-diagonally symmetric grid diagrams. The repository is prepared as a public-facing research codebase and ships only the runtime code plus a single template knot dataset, `3_1`.

Algorithm based on the following paper: https://arxiv.org/abs/2604.21240

## Features

- Generator, rectangle, domain, and grading construction for symmetric grid diagrams
- Hat homology computation
- Minus homology computation for strongly invertible knots
- Polynomial computation for strongly invertible knots
- A simple command-line workflow for running the full pipeline locally

## Installation

```bash
python3 -m pip install -r requirements.txt
```

## Quick Start

Run the bundled template knot:

```bash
python3 -m real_grid_homology 3_1
```

Launch the Tk desktop UI:

```bash
python3 ui.py
```

List bundled template knots:

```bash
python3 -m real_grid_homology --list
```

Reuse existing intermediate files when present:

```bash
python3 -m real_grid_homology 3_1 --mode skip
```

Write a machine-readable summary:

```bash
python3 -m real_grid_homology 3_1 --json
```

## Supported Diagram Types

The current codebase supports two anti-diagonal symmetry types:

- `strongly_invertible`
- `(doubly) periodic`

These names are part of the implementation and are detected directly from the grid data by checking how the anti-diagonal reflection acts on `O` and `X` marks.

## Conventions

The implementation uses the anti-diagonal symmetry axis, with the following conventions:

- Odd-size strongly invertible diagrams: reflection preserves `O` marks and preserves `X` marks, with exactly one axis `O` and one axis `X`.
- Even-size strongly invertible diagrams: reflection preserves `O` marks and preserves `X` marks, with two axis `O`s and no axis `X`.
- Periodic diagrams: reflection swaps `O` and `X`, and thus no marks can be on axis.

## Grading Convention

When the workflow computes generator gradings, it uses the identity generator `(1, 2, ..., n)` as the reference generator in mathematical indexing. In the code this is represented as the zero-based list `[0, 1, ..., n - 1]`, and that generator is assigned grading `(0, 0)` at the grading stage.

Normalization is then applied only when the downstream real invariants are formed:

- Strongly invertible case: the Alexander grading is normalized so that the maximum and minimum non-vanishing Alexander gradings sum to `0`, and the Maslov grading is re-referenced using the `O^{NW}` generator.
- Periodic case: no additional normalization is applied. There is no Alexander grading for periodic case and `O^{NW}` does not make sense either.

## Invariants And Current Limits

The current workflow limits are practical computational limits. They are primarily driven by memory growth in the grading-sliced linear algebra: as grid size increases, the differential blocks become much larger and eventually cease to fit comfortably in memory.

- Polynomial: implemented for strongly invertible diagrams up to grid size `17`. It is not computed for periodic diagrams in the current code.
- Hat homology: implemented up to grid size `13`. For strongly invertible diagrams, the output is bigraded. For periodic diagrams, the current implementation keeps only a single grading.
- Minus homology: implemented for strongly invertible diagrams up to grid size `12`.
- Main constraint comes from the way we compute homology, explained below.

## Performance And Memory Notes

This repository prioritizes transparency and ease of modification by staying in Python. That choice is convenient for research iteration, but not necessarily optimal for raw speed. A native implementation of the linear-algebra core in Rust or C++ could plausibly run faster.

The main memory-sensitive stage is the computation for homology. The code currently divides the whole differential matrix intro blocks via gradings (Alexander, Maslov, or Delta), but still load the full block of the matrix into the memory (at current border case, takes up few GBs, next size expecting few hundreds GB). A more aggressive optimization would stream smaller clusters of columns within a grading block rather than loading the whole block at once.

The current code also performs a pre-computation memory check using estimated block sizes and available system memory. This is intentionally conservative, but on macOS it may still reject computations that would in practice complete because the operating system can reclaim or compress memory dynamically. The current code already tries to account for macOS behavior, but the estimate remains heuristic rather than exact.

## Trustworthiness

The trustworthiness claims for this repository are project-specific and should not be read as formal certification. The current code has the following provenance and validation summary.

- The generator, domain, and grading layers were developed by hand and tested against a size-5 trefoil example.
- The polynomial and homology computation layers were implemented with coding-agent assistance.
- Direct comparison was performed on the trefoil, the only non-trivial example noted in the local trustworthiness record as hand-computable.
- Differential consistency checks of the form `d^2 = 0` were used as a validation criterion.
- An intermediate tilde-homology divisibility property was checked across tested examples.
- Symmetry of computed polynomials and homologies was also used as a consistency check on small-crossing examples.

## Repository Layout

- `real_grid_homology/`: runtime package
- `ui.py`: desktop interface for creating/loading diagrams and running computations
- `data/knots/3_1.json`: bundled template knot
- `data/`: generated outputs are written here at runtime

## Notes

- The only bundled knot input is `3_1`, which serves as a template for additional public datasets.
- Intermediate and output files are generated locally under `data/` when the workflow is executed.
- The UI uses `matplotlib` together with the standard-library `tkinter` module.

## Authors

- Zhenkun Li
- OpenAI Codex, repository packaging and implementation support

## License

Released under the MIT License. See [LICENSE](LICENSE).
