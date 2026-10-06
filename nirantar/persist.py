"""Safe persistence helpers: tagged JSON (no pickle), atomic writes and a cross-process file lock.

Pickle runs code from the file it loads, so a tampered state file could take
over the node. State is therefore stored as JSON, with tags for what JSON lacks
(numpy arrays, tuples, dictionaries with non-text keys).
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np


TAGS = {"__nd__", "__t__", "__s__", "__d__"}


def _enc(o):
    if isinstance(o, np.ndarray):
        return {"__nd__": o.tolist(), "dtype": str(o.dtype)}
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, tuple):
        return {"__t__": [_enc(x) for x in o]}
    if isinstance(o, (set, frozenset)):
        return {"__s__": [_enc(x) for x in sorted(o, key=repr)]}
    if isinstance(o, dict):
        if all(isinstance(k, str) for k in o) and not TAGS & o.keys():
            return {k: _enc(v) for k, v in o.items()}
        return {"__d__": [[_enc(k), _enc(v)] for k, v in o.items()]}
    if isinstance(o, list):
        return [_enc(x) for x in o]
    return o


def _dec(o):
    if isinstance(o, list):
        return [_dec(x) for x in o]
    if isinstance(o, dict):
        if "__nd__" in o:
            return np.array(o["__nd__"], dtype=o["dtype"])
        if "__t__" in o:
            return tuple(_dec(x) for x in o["__t__"])
        if "__s__" in o:
            return {_dec(x) for x in o["__s__"]}
        if "__d__" in o:
            return {_hashable(_dec(k)): _dec(v) for k, v in o["__d__"]}
        return {k: _dec(v) for k, v in o.items()}
    return o


def _hashable(k):
    return tuple(_hashable(x) for x in k) if isinstance(k, list) else k


def dumps(obj) -> str:
    return json.dumps(_enc(obj), allow_nan=True, separators=(",", ":"))


def loads(text: str):
    return _dec(json.loads(text))


def atomic_write_text(path: str | Path, text: str) -> None:
    """Write to a temporary file in the same folder, flush to disk, then rename over the target:
    a crash leaves either the old file or the new one, never half of each."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def file_lock(path: str | Path):
    """Exclusive lock shared by every process on this machine (Windows and POSIX)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()
