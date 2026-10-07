"""Offline bundle sealing/verification and the node self-test."""
import subprocess
import sys

from nirantar.release import seal, selftest, verify_bundle


def test_sealed_bundle_verifies_and_tampering_is_refused(tmp_path):
    b = tmp_path / "bundle"
    (b / "wheels").mkdir(parents=True)
    (b / "wheels" / "nirantar-0.1.0-py3-none-any.whl").write_bytes(b"not really a wheel")
    fp = seal(b, ["win_amd64:3.14"], tmp_path / "release.key", log=lambda *_: None)
    v = verify_bundle(b)
    assert v["ok"] and v["sums_fingerprint"] == fp and v["signature_valid"]
    assert not verify_bundle(b, trusted_key="someone else's key")["ok"]
    ok = subprocess.run([sys.executable, str(b / "install_check.py")], capture_output=True, text=True)
    assert ok.returncode == 0 and fp in ok.stdout
    (b / "wheels" / "nirantar-0.1.0-py3-none-any.whl").write_bytes(b"swapped")
    (b / "wheels" / "extra.whl").write_bytes(b"planted")
    bad = subprocess.run([sys.executable, str(b / "install_check.py")], capture_output=True, text=True)
    assert bad.returncode == 1 and "nirantar-0.1.0" in bad.stdout and "extra.whl" in bad.stdout
    assert not verify_bundle(b)["ok"]


def test_selftest_passes_here():
    assert selftest(log=lambda *_: None)
