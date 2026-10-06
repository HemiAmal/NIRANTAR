import pytest

from nirantar.chitragupta.ledger import (Ledger, Signer, inclusion_proof, leaf_hash, merkle_root,
                                         verify_inclusion)


@pytest.mark.parametrize("n", list(range(1, 18)))
def test_inclusion_proofs_all_sizes(n):
    leaves = [leaf_hash(bytes([i])) for i in range(n)]
    root = merkle_root(leaves)
    for i in range(n):
        assert verify_inclusion(leaves[i], i, n, inclusion_proof(i, leaves), root)
    if n > 1:
        assert not verify_inclusion(leaves[0], 1, n, inclusion_proof(1, leaves), root)


def test_sign_verify_and_tamper(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    s, w = Signer.generate("tech"), Signer.generate("witness")
    for i in range(7):
        led.append("decision", {"i": i, "verdict": "accept"}, s)
    sth = led.tree_head(w)
    assert led.verify_all(sth) == []
    assert all(led.verify_entry(i, sth) for i in range(7))

    reloaded = Ledger(tmp_path / "l.jsonl")
    assert reloaded.verify_all(sth) == []

    led.entries[3]["payload"]["verdict"] = "reject"
    assert 3 in led.verify_all(sth) and -1 in led.verify_all(sth)
    assert not led.verify_entry(3, sth)


def test_forged_signature_rejected():
    led = Ledger()
    s, mallory = Signer.generate("tech"), Signer.generate("mallory")
    e = led.append("decision", {"v": 1}, s)
    e["signature"] = mallory.sign(b"something else")
    assert led.verify_all() == [0]


def test_caller_cannot_mutate_signed_payload():
    led = Ledger()
    s = Signer.generate("tech")
    payload = {"verdict": "accept"}
    led.append("decision", payload, s)
    payload["verdict"] = "reject"          # caller keeps editing its own dict
    assert led.entries[0]["payload"]["verdict"] == "accept"
    assert led.verify_all() == []


def test_node_key_survives_restart_and_rekeying_is_refused(tmp_path):
    key = tmp_path / "keys" / "node.key"
    a = Signer.load_or_create(key, "web-console")
    led = Ledger(tmp_path / "l.jsonl")
    led.append("note", {"n": 1}, a)
    b = Signer.load_or_create(key, "web-console")             # restart: same key, same actor
    assert b.actor == a.actor and b.actor.startswith("web-console@")
    again = Ledger(tmp_path / "l.jsonl")
    again.append("note", {"n": 2}, b)
    assert again.verify_all() == []
    with pytest.raises(ValueError):
        again.append("note", {"n": 3}, Signer.generate(a.actor))   # same name, different key


def test_processes_appending_together_never_fork_the_chain(tmp_path):
    """A console and an import (or two consoles) writing at once: the file lock keeps one chain."""
    import subprocess
    import sys
    code = ("import sys\nfrom nirantar.chitragupta.ledger import Ledger, Signer\n"
            "L = Ledger(sys.argv[1]); s = Signer.generate('w' + sys.argv[2])\n"
            "for i in range(60): L.append('t', {'i': i}, s)\n")
    path = tmp_path / "l.jsonl"
    procs = [subprocess.Popen([sys.executable, "-c", code, str(path), str(k)]) for k in range(3)]
    assert all(p.wait() == 0 for p in procs)
    L = Ledger(path)
    assert len(L.entries) == 180 and L.verify_all() == []
    assert [e["seq"] for e in L.entries] == list(range(180))
