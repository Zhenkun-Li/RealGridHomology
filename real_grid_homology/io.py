import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="ascii") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict) -> None:
    ensure_parent(path)
    with path.open("w", encoding="ascii") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="ascii") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="ascii") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="ascii") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
