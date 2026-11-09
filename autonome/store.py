"""Persistance JSONL simple (dossier state/, publié sur la branche git `data`).

- Lecture tolérante : une ligne illisible (écriture interrompue, édition à la main) est ignorée, comptée dans
  `BAD` et copiée dans `quarantaine.jsonl` ; jamais d'exception, jamais de passage bloqué.
- Écritures atomiques : fichier temporaire, fsync, puis `os.replace`. Un passage tué au milieu (timeout) laisse
  l'ancien fichier intact, jamais une ligne tronquée.
- UTF-8 partout (indépendant de la locale du runner).
- Rotation : les lignes anciennes partent dans `archives/<nom>-AAAA-MM.jsonl.gz` (rien n'est détruit).
"""
from __future__ import annotations

import gzip
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

QUARANTINE = "quarantaine.jsonl"
ARCHIVES = "archives"
BAD: dict[str, int] = {}     # lignes illisibles nouvellement mises en quarantaine pendant ce processus (nom -> nombre)


def _p(root: str | Path, name: str) -> Path:
    Path(root).mkdir(parents=True, exist_ok=True)
    return Path(root) / name


def _tmp(p: Path) -> Path:
    # jamais with_suffix : « obs-2026-11.jsonl.gz » deviendrait « obs-2026-11.jsonl.tmp »
    return p.with_name(p.name + ".tmp")


def replace_bytes(p: Path, data: bytes) -> None:
    """Écriture atomique : l'ancien contenu reste intact tant que le nouveau n'est pas entièrement sur le disque."""
    p = Path(p)
    tmp = _tmp(p)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _split(data: bytes) -> list[str]:
    # split("\n") et non splitlines() : ce dernier coupe aussi sur U+2028, U+0085… que json.dumps(ensure_ascii=False)
    # laisse tels quels dans un nom d'équipe venu d'une page tierce (la ligne deviendrait illisible).
    return [x[:-1] if x.endswith("\r") else x for x in data.decode("utf-8", errors="replace").split("\n")]


def _dump(rows: list[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode("utf-8")


def _quarantine(root, name: str, lines: list[str]) -> None:
    """Copie les lignes illisibles (une fois chacune) : write_all réécrit le fichier sans elles, rien n'est perdu."""
    if name == QUARANTINE:
        return
    have = {(r.get("fichier"), r.get("ligne")) for r in read(root, QUARANTINE)}
    new = [x for x in dict.fromkeys(lines) if (name, x) not in have]
    if new:
        now = datetime.now(timezone.utc).isoformat()
        append(root, QUARANTINE, [{"fichier": name, "ligne": x, "vu": now} for x in new])
        BAD[name] = BAD.get(name, 0) + len(new)


def read(root, name) -> list[dict]:
    p = _p(root, name)
    if not p.exists():
        return []
    rows, bad = [], []
    for line in _split(p.read_bytes()):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad.append(line)
            continue
        if isinstance(r, dict):
            rows.append(r)
        else:
            bad.append(line)
    if bad:
        _quarantine(root, name, bad)
    return rows


def write_all(root, name, rows: list[dict]) -> None:
    replace_bytes(_p(root, name), _dump(rows))


def append(root, name, rows: list[dict]) -> None:
    """Ajout atomique (copie + remplacement) : jamais de ligne à moitié écrite."""
    if not rows:
        return
    p = _p(root, name)
    old = p.read_bytes() if p.exists() else b""
    if old and not old.endswith(b"\n"):
        old += b"\n"  # dernière ligne sans fin de ligne : gardée telle quelle (illisible => quarantaine à la lecture)
    replace_bytes(p, old + _dump(rows))


def _when(line: str) -> datetime | None:
    """Horodatage `at` d'une ligne (UTC), None si illisible ou absent."""
    try:
        r = json.loads(line)
        t = datetime.fromisoformat(str(r["at"]).replace("Z", "+00:00"))
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _read_gz(p: Path) -> list[str]:
    if not p.exists():
        return []
    with gzip.open(p, "rb") as f:
        return [x for x in _split(f.read()) if x.strip()]


def rotate(root, name: str, now: datetime, keep_days: float, max_bytes: int = 16_000_000,
           target_bytes: int = 12_000_000) -> int:
    """Déplace les lignes de plus de `keep_days` jours (champ `at`) dans archives/<nom>-AAAA-MM.jsonl.gz.

    Si le fichier dépasse `max_bytes`, les plus anciennes partent aussi jusqu'à `target_bytes` (le fichier chaud reste
    sous la limite des 20 Mo vérifiée par ci.yml). Ne fait rien tant que la plus vieille ligne a moins de keep_days + 1 j
    (une rotation par jour au plus). Les lignes sans date lisible restent dans le fichier chaud. Ordre sûr : archives
    écrites et relues d'abord, fichier chaud réécrit ensuite ; un arrêt entre les deux ne duplique rien (les lignes
    déjà archivées ne sont pas réajoutées). Renvoie le nombre de lignes déplacées."""
    p = _p(root, name)
    if not p.exists():
        return 0
    raw = p.read_bytes()
    lines = [x for x in _split(raw) if x.strip()]
    cutoff = now - timedelta(days=keep_days)
    first = next((t for t in map(_when, lines) if t is not None), None)
    too_big = len(raw) > max_bytes
    if not too_big and (first is None or first >= cutoff - timedelta(days=1)):
        return 0
    when = [_when(x) for x in lines]
    move = [t is not None and t < cutoff for t in when]
    if too_big:
        size = sum(len(x.encode("utf-8")) + 1 for x, m in zip(lines, move) if not m)
        for i, x in enumerate(lines):  # fichier en ordre chronologique : on retire les plus anciennes
            if size <= target_bytes:
                break
            if when[i] is not None and not move[i]:
                move[i] = True
                size -= len(x.encode("utf-8")) + 1
    by_month: dict[str, list[str]] = {}
    for x, t, m in zip(lines, when, move):
        if m:
            by_month.setdefault(t.astimezone(timezone.utc).strftime("%Y-%m"), []).append(x)
    if not by_month:
        return 0
    stem = name[:-len(".jsonl")] if name.endswith(".jsonl") else name
    adir = Path(root) / ARCHIVES
    adir.mkdir(parents=True, exist_ok=True)
    for month, moved in sorted(by_month.items()):
        ap = adir / f"{stem}-{month}.jsonl.gz"
        have = _read_gz(ap)
        missing = Counter(moved) - Counter(have)  # déjà archivées (arrêt au milieu d'une rotation) : pas en double
        add = []
        for x in moved:
            if missing[x] > 0:
                add.append(x)
                missing[x] -= 1
        if add:
            body = ("\n".join(have + add) + "\n").encode("utf-8")
            replace_bytes(ap, gzip.compress(body, mtime=0))
        if Counter(moved) - Counter(_read_gz(ap)):  # relecture : chaque ligne déplacée doit être dans l'archive
            raise RuntimeError(f"rotation {name} : archive {ap.name} incomplète, fichier chaud laissé intact")
    keep = [x for x, m in zip(lines, move) if not m]
    replace_bytes(p, ("".join(x + "\n" for x in keep)).encode("utf-8"))
    return sum(move)


def oversized(root, limit: int = 20_000_000) -> list[tuple[str, int]]:
    """Fichiers d'état plus gros que `limit` octets (hors .git) : GitHub avertit à 50 Mo et refuse à 100 Mo."""
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            size = os.path.getsize(os.path.join(d, f))
            if size > limit:
                out.append((os.path.relpath(os.path.join(d, f), root), size))
    return sorted(out)
