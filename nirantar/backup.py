"""Backup, verification and restore of a NIRANTAR node.

A backup is a folder holding:

* consistent copies of the SQLite databases (record store, user accounts),
  taken with SQLite's online backup while the console may be running;
* the evidence ledger, copied under its write lock, and the console's plans
  and operations-clock state;
* ``manifest.json``: every file's SHA-256 and size, the ledger's length and
  head hash, and the checks run, signed with the node's key
  (``manifest.sig``).

``verify`` re-hashes every file, runs SQLite's integrity check on each
database, and verifies the ledger's hash chain and signatures. ``restore``
verifies first, and refuses to overwrite existing files unless forced.

Private signing keys are left out unless asked for (``with_keys``): a backup
with keys must be kept like the keys themselves. Without them, a restored
node signs under a new name, and earlier entries still verify.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from nirantar.chitragupta.ledger import Ledger, Signer, verify_sig
from nirantar.persist import atomic_write_text, file_lock

RESULT_FILES = ("ledger.jsonl", "milestone1_report.json", "plan.json")
RESULT_DIRS = ("live", "records")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)                     # consistent snapshot even while others write
    finally:
        d.close()
        s.close()
    c = sqlite3.connect(dst)            # a self-contained file, not WAL
    try:
        c.execute("PRAGMA journal_mode = DELETE")
    finally:
        c.close()


def _integrity(db: Path) -> str:
    c = sqlite3.connect(db)
    try:
        return c.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        c.close()


def backup(results_dir: str | Path, out_root: str | Path, dbs: dict[str, str | Path] | None = None,
           with_keys: bool = False, signer: Signer | None = None) -> Path:
    """``dbs``: name -> path of SQLite databases to include (e.g. {"store": ..., "users": ...})."""
    res = Path(results_dir)
    out = Path(out_root) / datetime.now().strftime("nirantar-backup-%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    files: dict[str, dict] = {}

    def add(rel: str, kind: str, origin: str) -> None:
        p = out / rel
        files[rel] = {"sha256": _sha(p), "bytes": p.stat().st_size, "kind": kind, "origin": origin}

    for name, path in (dbs or {}).items():
        if path and Path(path).exists():
            rel = f"db/{name}.db"
            _sqlite_copy(Path(path), out / rel)
            add(rel, "sqlite", str(path))
    ledger = res / "ledger.jsonl"
    if ledger.exists():
        (out / "results").mkdir(exist_ok=True)
        with file_lock(ledger.with_name(ledger.name + ".lock")):     # no half-written entry
            shutil.copy2(ledger, out / "results/ledger.jsonl")
        add("results/ledger.jsonl", "ledger", str(ledger))
    for f in RESULT_FILES[1:]:
        if (res / f).exists():
            (out / "results").mkdir(exist_ok=True)
            shutil.copy2(res / f, out / "results" / f)
            add(f"results/{f}", "file", str(res / f))
    for d in RESULT_DIRS:
        for p in sorted((res / d).rglob("*")) if (res / d).exists() else []:
            if p.is_file() and not p.name.endswith((".tmp", ".lock")):
                rel = f"results/{p.relative_to(res).as_posix()}"
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out / rel)
                add(rel, "file", str(p))
    if with_keys:
        for p in sorted((res / "keys").glob("*")) if (res / "keys").exists() else []:
            if p.is_file():
                rel = f"results/keys/{p.name}"
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out / rel)
                add(rel, "secret", str(p))
    L = Ledger(out / "results/ledger.jsonl") if (out / "results/ledger.jsonl").exists() else None
    manifest = {
        "created": datetime.now().isoformat(timespec="seconds"), "results_dir": str(res),
        "files": files, "contains_private_keys": with_keys,
        "ledger": {"entries": len(L.entries), "head": L.entries[-1]["entry_hash"] if L and L.entries else None}
        if L else None,
        "checks": {rel: _integrity(out / rel) for rel, f in files.items() if f["kind"] == "sqlite"},
    }
    text = json.dumps(manifest, indent=1, sort_keys=True)
    atomic_write_text(out / "manifest.json", text)
    if signer is not None:
        atomic_write_text(out / "manifest.sig", json.dumps({"actor": signer.actor, "key": signer.public_b64,
                                                            "signature": signer.sign(text.encode())}))
    return out


def verify(folder: str | Path) -> dict:
    folder = Path(folder)
    text = (folder / "manifest.json").read_text(encoding="utf-8")
    m = json.loads(text)
    problems = []
    for rel, f in m["files"].items():
        p = folder / rel
        if not p.exists():
            problems.append(f"missing {rel}")
        elif _sha(p) != f["sha256"]:
            problems.append(f"changed {rel}")
        elif f["kind"] == "sqlite" and _integrity(p) != "ok":
            problems.append(f"database damaged {rel}")
    extra = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} \
        - set(m["files"]) - {"manifest.json", "manifest.sig"}
    problems += [f"unexpected {x}" for x in sorted(extra)]
    ledger_ok = None
    if (folder / "results/ledger.jsonl").exists():
        bad = Ledger(folder / "results/ledger.jsonl").verify_all()
        ledger_ok = bad == []
        if bad:
            problems.append(f"ledger entries fail verification: {bad[:10]}")
    sig = None
    if (folder / "manifest.sig").exists():
        s = json.loads((folder / "manifest.sig").read_text())
        sig = {"actor": s["actor"], "valid": verify_sig(s["key"], text.encode(), s["signature"])}
        if not sig["valid"]:
            problems.append("manifest signature does not verify")
    return {"ok": not problems, "problems": problems, "files": len(m["files"]), "ledger_verified": ledger_ok,
            "signature": sig, "created": m["created"], "contains_private_keys": m["contains_private_keys"]}


def restore(folder: str | Path, results_dir: str | Path, dbs: dict[str, str | Path] | None = None,
            force: bool = False) -> list[str]:
    """Copy a verified backup back into place. Returns the files written."""
    folder = Path(folder)
    v = verify(folder)
    if not v["ok"]:
        raise ValueError("backup does not verify: " + "; ".join(v["problems"]))
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    targets = []
    for rel, f in m["files"].items():
        if rel.startswith("db/"):
            name = Path(rel).stem
            if not dbs or name not in dbs or not dbs[name]:
                continue
            targets.append((folder / rel, Path(dbs[name])))
        else:
            targets.append((folder / rel, Path(results_dir) / rel[len("results/"):]))
    clash = [str(t) for _, t in targets if t.exists()]
    if clash and not force:
        raise FileExistsError(f"{len(clash)} files already exist (e.g. {clash[0]}); restore with force to replace")
    written = []
    for src, dst in targets:
        dst.parent.mkdir(parents=True, exist_ok=True)
        for side in (dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
            if side.exists():
                side.unlink()
        shutil.copy2(src, dst)
        written.append(str(dst))
    return written
