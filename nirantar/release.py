"""Offline (air-gapped) installation bundle, its verification, and a self-test.

On a machine with internet access::

    python -m nirantar bundle --out dist/offline --target win_amd64:3.14 --target manylinux2014_x86_64:3.11

builds NIRANTAR's wheel, downloads every dependency as a binary wheel for each
target platform and Python version, writes install scripts, and lists every
file's SHA-256 in ``SHA256SUMS``, signed with a release key (Ed25519).

On the air-gapped machine the installer first checks every file against
``SHA256SUMS`` with the Python standard library, and prints the SHA-256 of
``SHA256SUMS`` itself. Compare it with the value the release officer gave out
by a separate channel. Once installed, ``python -m nirantar verify-bundle``
also checks the release signature, and ``python -m nirantar selftest`` checks
the node works.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEPENDENCIES = ["numpy>=1.24", "scipy>=1.10", "pandas>=2.0", "cryptography>=41"]

INSTALL_PS1 = r'''# NIRANTAR offline install (Windows). Run in PowerShell from this folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1            (into .\nirantar-env)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -User      (into your user site, if venvs are blocked)
param([switch]$User, [string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& $Python install_check.py
if ($LASTEXITCODE -ne 0) { throw "bundle check failed: do not install" }
if ($User) {
  & $Python -m pip install --user --no-index --find-links wheels nirantar
  & $Python -m pip install --user --no-index --no-deps --find-links wheels vosk
  Write-Host "Installed for this user. Run:  $Python -m nirantar selftest"
} else {
  & $Python -m venv nirantar-env
  & .\nirantar-env\Scripts\python.exe -m pip install --no-index --find-links wheels nirantar
  & .\nirantar-env\Scripts\python.exe -m pip install --no-index --no-deps --find-links wheels vosk
  Write-Host "Installed. Run:  .\nirantar-env\Scripts\python.exe -m nirantar selftest"
}
'''

INSTALL_SH = '''#!/bin/sh
# NIRANTAR offline install (Linux). Run from this folder:  sh install.sh [python3]
set -e
cd "$(dirname "$0")"
PY="${1:-python3}"
"$PY" install_check.py
"$PY" -m venv nirantar-env
./nirantar-env/bin/python -m pip install --no-index --find-links wheels nirantar
./nirantar-env/bin/python -m pip install --no-index --no-deps --find-links wheels vosk
echo "Installed. Run:  ./nirantar-env/bin/python -m nirantar selftest"
'''

INSTALL_CHECK = '''"""Check every file of this bundle against SHA256SUMS (standard library only)."""
import hashlib
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sums = (here / "SHA256SUMS").read_bytes()
bad = []
for line in sums.decode().splitlines():
    digest, name = line.split("  ", 1)
    p = here / name
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        bad.append(name)
listed = {line.split("  ", 1)[1] for line in sums.decode().splitlines()}
extra = [p.relative_to(here).as_posix() for p in here.rglob("*") if p.is_file()
         and p.relative_to(here).as_posix() not in listed | {"SHA256SUMS", "SHA256SUMS.sig"}
         and "nirantar-env" not in p.parts and "__pycache__" not in p.parts]
print("SHA256SUMS fingerprint:", hashlib.sha256(sums).hexdigest())
print("  compare it with the value the release officer gave you by another channel")
if bad or extra:
    print("FAILED. Changed or missing:", bad, "Unexpected:", extra)
    sys.exit(1)
print("All", len(listed), "files match.")
'''

README = """NIRANTAR offline installation bundle
===================================

Contents: wheels/ (NIRANTAR and every dependency, per platform), install scripts,
SHA256SUMS (every file's SHA-256) and SHA256SUMS.sig (release signature).

1. Copy this folder to the air-gapped machine (approved removable media).
2. Check and install:
     Windows:  powershell -ExecutionPolicy Bypass -File install.ps1   (add -User if venvs are blocked)
     Linux:    sh install.sh
   The installer refuses to continue if any file differs from SHA256SUMS, and prints the
   fingerprint of SHA256SUMS itself: compare it with the one the release officer gave you.
3. Verify the release signature and the node:
     python -m nirantar verify-bundle <this folder>
     python -m nirantar selftest
4. Accounts, certificate and console: see docs/12_PRODUCTION_DEPLOYMENT.md.
5. Voice input: models/ holds the speech models included (if any); serve with
     --asr-model en=models/<model folder>
   (docs/13_SAARTHI_FIELD.md).

Python: the bundle was built for {targets}.
"""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_bundle(out: str | Path, targets: list[str], project: str | Path = ".", key: str | Path | None = None,
                 log=print, speech_models: list[str] | None = None) -> Path:
    """``targets``: 'platform:python', e.g. 'win_amd64:3.14', 'manylinux2014_x86_64:3.11'."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists; choose a new folder")
    wheels = out / "wheels"
    wheels.mkdir(parents=True)
    log("building the NIRANTAR wheel ...")
    subprocess.run([sys.executable, "-m", "pip", "wheel", str(project), "--no-deps", "-q", "-w", str(wheels)],
                   check=True)
    for t in targets:
        plat, py = t.split(":")
        log(f"downloading dependencies for {plat}, Python {py} ...")
        subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--only-binary=:all:", "--platform", plat,
                        "--python-version", py, "--implementation", "cp", "-d", str(wheels), *DEPENDENCIES],
                       check=True)
        # speech engine for SAARTHI voice input: its native library only (no subtitle/download extras)
        subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--only-binary=:all:", "--no-deps", "--platform",
                        plat, "--python-version", py, "--implementation", "cp", "-d", str(wheels), "vosk"], check=True)
    for m in speech_models or []:                   # model folders the unit obtained from a verified source
        src = Path(m)
        log(f"adding speech model {src.name} ...")
        import shutil
        shutil.copytree(src, out / "models" / src.name)
    seal(out, targets, key or Path(project) / "experiments/results/keys/release.key", log)
    return out


def seal(out: Path, targets: list[str], key: str | Path, log=print) -> str:
    """Write the install scripts, SHA256SUMS of every file, and its release signature."""
    from nirantar.chitragupta.ledger import Signer
    out = Path(out)
    (out / "install.ps1").write_text(INSTALL_PS1, encoding="utf-8")
    (out / "install.sh").write_text(INSTALL_SH, encoding="utf-8", newline="\n")
    (out / "install_check.py").write_text(INSTALL_CHECK, encoding="utf-8")
    (out / "README-INSTALL.txt").write_text(README.format(targets=", ".join(targets)), encoding="utf-8")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name not in ("SHA256SUMS", "SHA256SUMS.sig"))
    sums = "".join(f"{_sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files)
    (out / "SHA256SUMS").write_bytes(sums.encode())
    signer = Signer.load_or_create(key, "release")
    (out / "SHA256SUMS.sig").write_text(json.dumps({"actor": signer.actor, "key": signer.public_b64,
                                                    "signature": signer.sign(sums.encode()),
                                                    "built": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    fp = hashlib.sha256(sums.encode()).hexdigest()
    log(f"{len(files)} files; SHA256SUMS fingerprint {fp}; signed by {signer.actor}")
    return fp


def verify_bundle(folder: str | Path, trusted_key: str | None = None) -> dict:
    from nirantar.chitragupta.ledger import verify_sig
    folder = Path(folder)
    sums = (folder / "SHA256SUMS").read_bytes()
    bad = []
    for line in sums.decode().splitlines():
        digest, name = line.split("  ", 1)
        p = folder / name
        if not p.exists() or _sha(p) != digest:
            bad.append(name)
    sig = json.loads((folder / "SHA256SUMS.sig").read_text(encoding="utf-8"))
    valid = verify_sig(sig["key"], sums, sig["signature"])
    trusted = trusted_key is None or trusted_key == sig["key"]
    return {"ok": not bad and valid and trusted, "files_changed": bad, "signature_valid": valid,
            "signed_by": sig["actor"], "release_key": sig["key"], "key_trusted": trusted,
            "sums_fingerprint": hashlib.sha256(sums).hexdigest()}


def selftest(log=print) -> bool:
    """Acceptance check on a fresh node: everything NIRANTAR needs works here."""
    checks = []

    def check(name, fn):
        t0 = time.time()
        try:
            detail = fn()
            checks.append((name, True))
            log(f"  ok    {name} ({time.time() - t0:.1f} s){': ' + detail if detail else ''}")
        except Exception as exc:                   # report every failure, keep going
            checks.append((name, False))
            log(f"  FAIL  {name}: {exc!r}")

    def deps():
        import cryptography
        import numpy
        import pandas
        import scipy
        return f"numpy {numpy.__version__}, scipy {scipy.__version__}, pandas {pandas.__version__}, " \
               f"cryptography {cryptography.__version__}, Python {sys.version.split()[0]}"

    def twin():
        from nirantar.bharat_fleet.world import make_world
        from nirantar.sanjaya.ensemble import P0
        from nirantar.sanjaya.twin import Twin
        r = Twin(make_world(seed=7), P0, 120, seed=1, record=True).run()
        assert 0 < r.overall_availability < 1
        return f"availability {r.overall_availability:.3f}"

    def fit():
        from nirantar.dhanvantari.tier_c import fit_tier_c
        from nirantar.pariksha import public as P
        sp, fam = P.genfan()
        m = fit_tier_c(sp, fam, hessian=False)
        assert 0.5 < m.params("GEN-FAN", "field")[0] < 3
        return "reliability fit on real fan data"

    def ledger():
        from nirantar.chitragupta.ledger import Ledger, Signer
        with tempfile.TemporaryDirectory() as d:
            L, s = Ledger(Path(d) / "l.jsonl"), Signer.generate("selftest")
            for i in range(3):
                L.append("t", {"i": i}, s)
            assert Ledger(Path(d) / "l.jsonl").verify_all() == []
        return "Ed25519 signing, hash chain"

    def store():
        from nirantar.setu.schema import Store
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            assert st.con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            st.close()
        return "SQLite with WAL"

    def accounts():
        from nirantar.rakshak.auth import UserStore
        with tempfile.TemporaryDirectory() as d:
            u = UserStore(Path(d) / "u.db")
            u.create_user("selftest", "a long selftest passphrase", ["Viewer"])
            assert u.login("selftest", "a long selftest passphrase")[1].can("view")
            u.con.close()
        return "scrypt, AES-GCM key sealing"

    def tls():
        import ssl
        from nirantar.rakshak.tls import make_self_signed
        with tempfile.TemporaryDirectory() as d:
            c, k = make_self_signed(d, ["localhost"])
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(c, k)
        return "certificate and TLS"

    def speech():
        import importlib.util
        if importlib.util.find_spec("vosk") is None:
            return "not installed (voice input off; typing works)"
        from nirantar.saarthi.asr import _Lib
        _Lib.get()
        return "Vosk library loads"

    for name, fn in (("dependencies", deps), ("digital twin", twin), ("reliability fit", fit),
                     ("evidence ledger", ledger), ("record store", store), ("user accounts", accounts),
                     ("HTTPS", tls), ("speech engine", speech)):
        check(name, fn)
    ok = all(c[1] for c in checks)
    log("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return ok

