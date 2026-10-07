# Production deployment: accounts, roles, storage, backup and air-gapped install

> **Status:** built and tested (124 tests passing in the whole repository). NIRANTAR can run as a multi-user node on a closed network:
> - people sign in, and the server enforces what each role may do;
> - decisions are signed with each person's own key;
> - storage is safe when several processes write at once;
> - backups are verified and signed;
> - installation needs no internet and is checked against a signed list of hashes.
>
> This is engineering for accreditation, not the accreditation itself. That needs a sponsor, a security review and the unit's own procedures (§8).

---

## 1. Two modes

| | Demo mode (default) | Secure mode (`serve --auth ...`) |
|---|---|---|
| Who can use it | Anyone at this machine | People with accounts |
| Role | Chosen in "Acting as" | Fixed by the account; only the account's roles are offered |
| Signatures | The console's node key | **The person's own key** (decisions, snags, declared disruptions) |
| Guided demo, tamper demo | Available | Guided demo hidden; tamper demo for administrators |
| Network | This machine only | Other machines, over HTTPS |

The server refuses to listen beyond this machine without both logins and HTTPS (`--allow-insecure` exists for isolated test benches only).

---

## 2. Setting up a node

```bash
# 1. install (see §6 for machines without internet)
python -m nirantar selftest

# 2. analysis results the console shows (synthetic demo; records mode below)
python -m nirantar demo

# 3. user accounts (on the server, never over the network)
python -m nirantar users add iyer   --roles "Logistics officer" --display "Sqn Ldr Iyer"
python -m nirantar users add rao    --roles "CEngO"             --display "Wg Cdr Rao"
python -m nirantar users add tech07 --roles "Technician"
python -m nirantar users add exctl  --roles "Exercise control"
python -m nirantar users add admin  --roles "Administrator"
python -m nirantar users list

# 4. certificate (or use one from the unit's certificate authority)
python -m nirantar make-cert --host nirantar.b1.local --host 10.1.2.3

# 5. serve
python -m nirantar serve --host 0.0.0.0 --port 8443 \
    --auth experiments/results/users.db \
    --cert experiments/results/keys/console-cert.pem --key experiments/results/keys/console-key.pem \
    [--db data/nirantar.db]          # plan from imported records (docs/10)
```

Users open `https://nirantar.b1.local:8443`. Each workstation must trust the certificate, or the unit's certificate authority that issued it.

---

## 3. Accounts, roles and sessions (RAKSHAK, `nirantar/rakshak`)

**Roles and what they allow.** The server checks this on every request; the browser only reflects it.

| Permission | Roles |
|---|---|
| View the console, run what-if simulations | every role |
| Log snags (SAARTHI) | Technician, Logistics officer, CEngO, Exercise control |
| Decide plan items | Logistics officer, CEngO, BRD Chief Engineer, HQMC review, Command logistics. Each item also needs the authority named on it (Action Authority Matrix, docs/06). |
| Re-plan | the deciding roles, Exercise control |
| Advance the operations clock, declare disruptions, reset | Exercise control |
| Data imports and refits | Data steward, Administrator (command line) |
| See accounts and the access log; tamper demo | Administrator |

**Passphrases.** At least 12 characters, hashed with scrypt.

**Personal signing keys.** Each account has its own Ed25519 key. The private key is stored encrypted with AES-GCM under a key derived from the person's passphrase. It is unlocked at sign-in, held only in server memory for the session, and forgotten at sign-out or restart. A decision in the ledger therefore names the person (e.g. `rao@1f3a…`) and is signed with a key only they could unlock. Changing your own passphrase keeps your key. An administrator's reset issues a new key and so a new ledger name; earlier entries still verify.

**Sessions.**
- A random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS).
- Sessions expire after 30 minutes idle and 10 hours absolute.
- Role changes, resets and disabling sign the person out everywhere.

**Lockout and audit.**
- Five failed sign-ins lock the account for 15 minutes.
- Unknown usernames take as long to refuse as wrong passphrases, so names cannot be probed.
- Sign-ins, failures, lockouts, refused requests and account changes go to an audit table. Administrators see it in **Data & ledger → Access**, or with `users audit`.

**Request hardening.**
- Every state-changing request needs a custom header and the same origin; a plain cross-site form cannot send these.
- Request bodies are limited to 64 KB.
- Security headers are sent: Content-Security-Policy (scripts only from the node), X-Frame-Options, Referrer-Policy, and HSTS over HTTPS.
- Internal errors are reported as "internal error", with details kept on the server.

---

## 4. Storage safe for several users and processes

- **Evidence ledger.** Each append takes a file lock shared by all processes and first reads entries others have added. The console, an import and a refit writing at the same moment keep one hash chain. This is tested with 3 writer processes; without the lock the chain forked. Each entry is flushed to disk before the write returns.
- **Record store and accounts.** SQLite in WAL mode (readers never block the writer), with a busy timeout. Numbered schema migrations upgrade older stores; a store written by a newer version is refused rather than misread.
- **No pickle.** Operations-clock state is JSON with tags for arrays and tuples, written atomically (temporary file, fsync, rename). Clock state saved by earlier versions (`clock.pkl`) is not read; the clock starts again at day 0.

---

## 5. Backup and restore

```bash
python -m nirantar backup --results experiments/results --db data/nirantar.db --users experiments/results/users.db --out /media/backup
python -m nirantar backup-verify /media/backup/nirantar-backup-20261006-1830
python -m nirantar restore /media/backup/nirantar-backup-20261006-1830 --results experiments/results --db data/nirantar.db --users experiments/results/users.db
```

**What a backup contains:**
- consistent copies of the databases, taken with SQLite's online backup while the console runs;
- the ledger, copied under its lock;
- plans and clock state;
- a manifest of every file's SHA-256, signed with the node key.

**Verification** re-hashes every file, rejects missing or extra files, runs SQLite's integrity check, and verifies the ledger's chain and signatures.

**Restore** verifies first, and does not overwrite anything without `--force`.

Private signing keys are left out unless `--with-keys` is given. A backup with keys must be guarded like the keys.

---

## 6. Installing on a machine without internet

On a machine with internet (once per release):

```bash
python -m nirantar bundle --out dist/nirantar-0.1.0-offline --target win_amd64:3.14 --target manylinux2014_x86_64:3.11
```

This builds NIRANTAR's wheel and downloads every dependency (numpy, scipy, pandas, cryptography and theirs) as binary wheels for each target platform and Python version. It writes install scripts, lists every file's SHA-256 in `SHA256SUMS`, and signs that list with the release key. It prints the list's fingerprint. Give the fingerprint to the receiving unit by a channel other than the media the bundle travels on.

On the air-gapped machine:

```
Windows:  powershell -ExecutionPolicy Bypass -File install.ps1        (add -User where virtual environments are blocked)
Linux:    sh install.sh
then:     python -m nirantar verify-bundle <bundle folder> --trusted-key <release public key>
          python -m nirantar selftest
```

The installer checks every file against `SHA256SUMS` using only the Python standard library, before anything is installed. It refuses if a file was changed, is missing or was added. It uses `python -m pip --no-index` throughout, so it works where application-control policy blocks `pip.exe`.

`selftest` checks the dependencies, the digital twin, a reliability fit on real data, ledger signing, the record store, accounts and TLS.

This was tested here: a bundle for Windows/Python 3.14 and Linux/Python 3.11 (130 MB) installed into a clean environment with no package index. The self-test passed, the signature verified, and a bundle with one changed byte was refused before installation.

---

## 7. Running the node

- **Start at boot.** On Windows use Task Scheduler ("At startup", run `python -m nirantar serve ...` as a service account). On Linux use a systemd unit. Keep `experiments/results/keys/` readable only by that account.
- **Daily.** Import the day's e-MMS and IMMOLS exports (`import`, signed into the ledger). After a significant data change, run `refit` (docs/11). Take a backup to separate media.
- **People.** Add, change roles, disable and reset with `users`. Review `users audit` for lockouts and refused requests.

---

## 8. What this does not do yet

- **One node.** There is no replication between bases or to command; each node has its own ledger. Linking ledgers (signed tree heads exchanged between nodes) is designed (docs/03) but not built.
- **SQLite.** It is sized for a station: tens of users and millions of records. A command-wide deployment would move the store to PostgreSQL. The SQL is plain enough, but this is not done.
- **Passphrases only.** There is no smart-card or PKI sign-in and no second factor. Integrating the service's PKI is the natural next step, and depends on access to it.
- **Sessions live in memory.** A restart signs everyone out. This is deliberate, since unlocked keys must not persist, but it should be planned for.
- **Lockout is per account,** not per network address. There is no log shipping to a security monitoring system.
- **The console still needs the analysis report** (`nirantar demo`) for its readiness room, even when planning from records. A report generated from the record store is part of the remaining work.
- **No accreditation.** A security review, penetration test and the unit's procedures are required before operational use (Not-done item 6).
