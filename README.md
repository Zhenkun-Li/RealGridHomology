# RealGridHomology

RealGridHomology is a standalone Python implementation for computing real grid-homological data from anti-diagonally symmetric grid diagrams. The repository is prepared as a public-facing research codebase and ships only the runtime code plus a single template knot dataset, `3_1`.

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
- `periodic`

These names are part of the implementation and are detected directly from the grid data by checking how the anti-diagonal reflection acts on `O` and `X` marks.

## Conventions

The implementation uses the anti-diagonal symmetry axis. The following are implementation conventions, not universal mathematical conventions:

- Odd-size strongly invertible diagrams: reflection preserves `O` marks and preserves `X` marks, with exactly one axis `O` and one axis `X`.
- Periodic diagrams: reflection swaps `O` and `X`, and the current implementation requires no marks on the axis.
- The backend also contains a separate even-size strongly invertible path. This should be regarded as a distinct parity-dependent setup from the odd strongly invertible convention above.

In the current packaged interface, periodic diagrams are the no-axis-mark convention. The desktop UI exposes sizes `2` through `17` and applies parity-dependent validation rules, while the backend contains additional logic for the even strongly invertible case.

## Grading Convention

When the workflow computes generator gradings, it uses the identity generator `(1, 2, ..., n)` as the reference generator in mathematical indexing. In the code this is represented as the zero-based list `[0, 1, ..., n - 1]`, and that generator is assigned grading `(0, 0)` at the grading stage.

Normalization is then applied only when the downstream real invariants are formed:

- Strongly invertible case: the Alexander grading is normalized so that the maximum and minimum non-vanishing Alexander gradings sum to `0`, and the Maslov grading is re-referenced using the `O^{NW}` generator.
- Periodic case: no additional normalization is applied. In the current implementation, the periodic output keeps only a single grading.

## Invariants And Current Limits

The current workflow limits are practical computational limits. They are primarily driven by memory growth in the grading-sliced linear algebra: as grid size increases, the differential blocks become much larger and eventually cease to fit comfortably in memory.

- Polynomial: implemented for strongly invertible diagrams up to grid size `17`. It is not computed for periodic diagrams in the current code.
- Hat homology: implemented up to grid size `13`. For strongly invertible diagrams, the output is bigraded. For periodic diagrams, the current implementation keeps only a single grading.
- Minus homology: implemented for strongly invertible diagrams up to grid size `11`.

Additional scope notes:

- Odd-size strongly invertible and periodic diagrams are the primary public-facing paths in the current repository.
- Periodic even-size destabilization is not implemented in the current theory/backend, so periodic computations should presently be treated as an odd-size path.
- The backend includes an even strongly invertible grading path, but this is not exposed through the current odd-size UI controls.
- The desktop UI currently exposes sizes `2` through `17`, with parity-dependent validation rules for the supported setups.
- The command-line workflow can still be used on additional datasets placed in `data/knots/`, subject to the code restrictions above.

## Performance And Memory Notes

This repository prioritizes transparency and ease of modification by staying in Python. That choice is convenient for research iteration, but not necessarily optimal for raw speed. A native implementation of the linear-algebra core in Rust or C++ could plausibly run faster.

The main memory-sensitive stage is hat homology. The code currently uses two backends:

- `dense`: materializes each differential block by grading
- `low_memory`: spools entries to disk and then loads one full grading block at a time

The current low-memory path is lower-memory than the dense path, but it still loads whole grading blocks into memory. This is the main reason the size limits are memory-driven. A more aggressive optimization would stream smaller clusters of columns within a grading block rather than loading the whole block at once.

The hat stage also performs a pre-computation memory check using estimated block sizes and available system memory. This is intentionally conservative, but on macOS it may still reject computations that would in practice complete because the operating system can reclaim or compress memory dynamically. The current code already tries to account for macOS behavior, but the estimate remains heuristic rather than exact.

## Trustworthiness

The trustworthiness claims for this repository are project-specific and should not be read as formal certification. The current code has the following provenance and validation summary.

- The generator, domain, and grading layers were developed by hand and tested against a size-5 trefoil example.
- The polynomial and homology computation layers were implemented with coding-agent assistance.
- Direct comparison was performed on the trefoil, the only non-trivial example noted in the local trustworthiness record as hand-computable.
- Differential consistency checks of the form `d^2 = 0` were used as a validation criterion.
- An intermediate tilde-homology divisibility property was checked across tested examples.
- Symmetry of computed polynomials and homologies was also used as a consistency check on small-crossing examples.

This is a reasonable level of evidence for a research code release, but it is still best interpreted as validated computational software rather than formally verified software.

## Repository Layout

- `real_grid_homology/`: runtime package
- `ui.py`: desktop interface for creating/loading diagrams and running computations
- `data/knots/3_1.json`: bundled template knot
- `data/`: generated outputs are written here at runtime

## Notes

- This repository intentionally excludes development notes, migration scratch files, and private local tooling.
- The only bundled knot input is `3_1`, which serves as a template for additional public datasets.
- Intermediate and output files are generated locally under `data/` when the workflow is executed.
- The UI uses `matplotlib` together with the standard-library `tkinter` module.

## Authors

- Zhenkun Li
- OpenAI Codex, repository packaging and implementation support

## License

Released under the MIT License. See [LICENSE](LICENSE).
