"""CHITRAGUPTA: signed, append-only, Merkle-hashed evidence ledger.

Leaves and interior nodes follow RFC 6962 (Certificate Transparency):
leaf = SHA256(0x00 || data), node = SHA256(0x01 || left || right).
Every entry is signed with Ed25519 by its actor. Signed tree heads (STHs)
commit to the whole log; inclusion proofs show an entry is in a given tree;
any edit to a stored entry breaks verification.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    k = _split(len(leaves))
    return node_hash(merkle_root(leaves[:k]), merkle_root(leaves[k:]))


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def inclusion_proof(index: int, leaves: list[bytes]) -> list[bytes]:
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(index, leaves[:k]) + [merkle_root(leaves[k:])]
    return inclusion_proof(index - k, leaves[k:]) + [merkle_root(leaves[:k])]


def verify_inclusion(leaf: bytes, index: int, size: int, proof: list[bytes], root: bytes) -> bool:
    """RFC 9162 style verification of an audit path."""
    if index >= size:
        return False
    fn, sn = index, size - 1
    r = leaf
    for p in proof:
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            r = node_hash(p, r)
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


@dataclass
class Signer:
    actor: str
    key: Ed25519PrivateKey

    @classmethod
    def generate(cls, actor: str) -> "Signer":
        return cls(actor, Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path: str | Path, prefix: str) -> "Signer":
        """A node's long-lived key, kept in ``path``; the actor name carries the key's fingerprint
        so two nodes (or a node whose key was replaced) never share a name."""
        path = Path(path)
        if path.exists():
            key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(path.read_text().strip()))
        else:
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                    serialization.NoEncryption())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(base64.b64encode(raw).decode())
        pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return cls(f"{prefix}@{hashlib.sha256(pub).hexdigest()[:8]}", key)

    @property
    def public_b64(self) -> str:
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    def sign(self, data: bytes) -> str:
        return base64.b64encode(self.key.sign(data)).decode()


def verify_sig(public_b64: str, data: bytes, sig_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(base64.b64decode(sig_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False


class Ledger:
    """Append-only evidence log. Persisted as JSON lines when ``path`` is given."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[dict] = []
        self.keys: dict[str, str] = {}           # actor -> public key (b64)
        if self.path and self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    e = json.loads(line)
                    self.entries.append(e)
                    self.keys.setdefault(e["actor"], e["actor_key"])

    def register(self, signer: Signer) -> None:
        known = self.keys.get(signer.actor)
        if known is not None and known != signer.public_b64:
            # silently re-keying an actor would make all its earlier entries fail verification
            raise ValueError(f"signer {signer.actor!r} is already in the ledger with a different key")
        self.keys[signer.actor] = signer.public_b64

    def append(self, kind: str, payload: dict, signer: Signer) -> dict:
        self.register(signer)
        prev = self.entries[-1]["entry_hash"] if self.entries else "0" * 64
        payload = json.loads(canonical(payload))       # private copy: callers cannot alter a signed entry
        body = {"seq": len(self.entries), "ts": time.time(), "kind": kind, "actor": signer.actor,
                "actor_key": signer.public_b64, "payload": payload, "prev_hash": prev}
        data = canonical(body)
        entry = dict(body)
        entry["entry_hash"] = hashlib.sha256(data).hexdigest()
        entry["signature"] = signer.sign(data)
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        return entry

    # -- verification ----------------------------------------------------
    @staticmethod
    def _body(e: dict) -> dict:
        return {k: e[k] for k in ("seq", "ts", "kind", "actor", "actor_key", "payload", "prev_hash")}

    def leaves(self) -> list[bytes]:
        return [leaf_hash(canonical(self._body(e))) for e in self.entries]

    def tree_head(self, signer: Signer) -> dict:
        root = merkle_root(self.leaves())
        sth = {"size": len(self.entries), "root": root.hex(), "ts": time.time(), "witness": signer.actor}
        sth["signature"] = signer.sign(canonical({k: sth[k] for k in ("size", "root", "ts", "witness")}))
        sth["witness_key"] = signer.public_b64
        return sth

    def prove(self, seq: int) -> list[str]:
        return [p.hex() for p in inclusion_proof(seq, self.leaves())]

    def verify_entry(self, seq: int, sth: dict) -> bool:
        e = self.entries[seq]
        data = canonical(self._body(e))
        if hashlib.sha256(data).hexdigest() != e["entry_hash"]:
            return False
        if not verify_sig(self.keys.get(e["actor"], e["actor_key"]), data, e["signature"]):
            return False
        if seq >= sth["size"]:
            return False
        proof = inclusion_proof(seq, self.leaves()[: sth["size"]])
        return verify_inclusion(leaf_hash(data), seq, sth["size"], proof, bytes.fromhex(sth["root"]))

    def verify_sth(self, sth: dict) -> bool:
        body = canonical({k: sth[k] for k in ("size", "root", "ts", "witness")})
        if not verify_sig(sth["witness_key"], body, sth["signature"]):
            return False
        return merkle_root(self.leaves()[: sth["size"]]).hex() == sth["root"]

    def verify_all(self, sth: dict | None = None) -> list[int]:
        """Return the sequence numbers of entries that fail verification."""
        bad = []
        prev = "0" * 64
        for e in self.entries:
            data = canonical(self._body(e))
            ok = (hashlib.sha256(data).hexdigest() == e["entry_hash"]
                  and e["prev_hash"] == prev
                  and verify_sig(self.keys.get(e["actor"], e["actor_key"]), data, e["signature"]))
            if not ok:
                bad.append(e["seq"])
            prev = e["entry_hash"]
        if sth is not None and not self.verify_sth(sth):
            bad.append(-1)          # tree head no longer matches the log
        return bad
