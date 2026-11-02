"""Persistance JSONL simple (dossier state/, publié sur la branche git `data`)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _p(root: str | Path, name: str) -> Path:
    Path(root).mkdir(parents=True, exist_ok=True)
    return Path(root) / name


def read(root, name) -> list[dict]:
    p = _p(root, name)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def write_all(root, name, rows: list[dict]) -> None:
    p = _p(root, name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))
    os.replace(tmp, p)


def append(root, name, rows: list[dict]) -> None:
    with _p(root, name).open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
