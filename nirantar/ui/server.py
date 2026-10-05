"""NIRANTAR web console: a dependency-free local server for the dashboards.

Runs on the Python standard library only (air-gap friendly): static files plus
a small JSON API over the Milestone-1 results, the signed ledger and the live
digital twin.

    python -m nirantar serve [--port 8050] [--results experiments/results]
"""
from __future__ import annotations

import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from nirantar.bharat_fleet.world import make_world
from nirantar.chanakya.mrv import consumption_portfolio, greedy_portfolio, surrogate_provision_values
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.pipeline import clean_json, fan_payload
from nirantar.records import to_frames
from nirantar.sanjaya.ensemble import P0, P2, P3, run_ensemble, summarise
from nirantar.sanjaya.twin import Scenario, Twin
from nirantar.sushruta.agency import flag_rogues, serial_frailty

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}
POLICIES = {"P0": P0, "P2": P2, "P3": P3}
MAX_SEEDS = 16


class Console:
    """Server-side state: report, ledger and a lazily built simulation context."""

    def __init__(self, results_dir: str | Path):
        self.dir = Path(results_dir)
        self.report_path = self.dir / "milestone1_report.json"
        if not self.report_path.exists():
            raise FileNotFoundError(f"{self.report_path} not found; run `python -m nirantar demo` first")
        self.report = clean_json(json.loads(self.report_path.read_text()))
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.signer = Signer.generate("web-console")
        self._lock = threading.Lock()
        self._sim = None

    # -- simulation context (built once, on first use) -----------------
    def sim_context(self) -> dict:
        with self._lock:
            if self._sim is None:
                cfg = self.report["config"]
                world = make_world(seed=cfg["world_seed"])
                family_of = {p: v.family for p, v in world.pns.items()}
                hist = Twin(world, P0, cfg["history_days"], seed=cfg["history_seed"], record=True).run()
                fr = to_frames(hist.records)
                dm = fit_tier_c(fr["spells"], family_of)
                dm.rogue_flags = flag_rogues(serial_frailty(dm, fr["spells"], family_of), p_min=0.5)
                start = hist.snapshot
                vals = surrogate_provision_values(world, start, dm, cfg["horizon_days"])
                recent = fr["spells"][fr["spells"]["install_day"] > cfg["history_days"] - 365]
                self._sim = {
                    "world": world, "dm": dm, "start": start, "cfg": cfg,
                    "smart": tuple(greedy_portfolio(vals, cfg["budget_lakh"], cfg["horizon_days"])),
                    "cons": tuple(consumption_portfolio(world, recent, cfg["budget_lakh"])),
                }
            return self._sim

    def simulate(self, body: dict) -> dict:
        ctx = self.sim_context()
        policy = POLICIES.get(body.get("policy", "P3"))
        if policy is None:
            raise ValueError("policy must be one of P0, P2, P3")
        seeds = max(2, min(int(body.get("seeds", 8)), MAX_SEEDS))
        horizon = max(30, min(int(body.get("horizon", ctx["cfg"]["horizon_days"])), 730))
        start_day = float(body.get("shock_start", 0))
        duration = float(body.get("shock_days", 0))
        country = body.get("country", "RU")
        if country not in ("RU", "FR"):
            raise ValueError("country must be RU or FR")
        scen = Scenario("custom", ((country, "disrupted", start_day, start_day + duration),)) if duration > 0 \
            else Scenario("normal")
        acts = ctx["smart"] if policy is P3 else ctx["cons"]
        t0 = time.time()
        res = run_ensemble(ctx["world"], policy, horizon, range(5000, 5000 + seeds), scen, acts,
                           ctx["dm"], ctx["start"])
        s = summarise(res)
        return {"policy": policy.name, "scenario": scen.name, "seeds": seeds, "horizon": horizon,
                "shock": {"country": country, "start": start_day, "days": duration},
                "fan": fan_payload(res), "mean": s.mean, "ci95": s.ci95, "rar10": s.rar, "crar10": s.crar,
                "by_fleet": s.by_fleet, "runtime_s": round(time.time() - t0, 2)}

    # -- ledger ----------------------------------------------------------
    def ledger_view(self, limit: int = 200) -> dict:
        sth = self.report["ledger"]["tree_head"]
        bad = self.ledger.verify_all(sth)
        rows = [{"seq": e["seq"], "ts": e["ts"], "kind": e["kind"], "actor": e["actor"],
                 "hash": e["entry_hash"][:16], "payload": e["payload"]} for e in self.ledger.entries[-limit:]]
        return {"entries": rows, "count": len(self.ledger.entries), "failed": bad,
                "tree_head": {"size": sth["size"], "root": sth["root"][:24], "witness": sth["witness"]}}

    def decide(self, body: dict) -> dict:
        verdict = body.get("verdict")
        if verdict not in ("accept", "defer", "reject"):
            raise ValueError("verdict must be accept, defer or reject")
        seq = int(body["ledger_seq"])
        if not (0 <= seq < len(self.ledger.entries)) or self.ledger.entries[seq]["kind"] != "recommendation":
            raise ValueError("ledger_seq does not point at a recommendation")
        reason = str(body.get("reason_code", "WEB_CONSOLE"))[:64]
        with self._lock:
            e = self.ledger.append("decision", {"recommendation_seq": seq, "verdict": verdict,
                                                "reason_code": reason, "via": "web console"}, self.signer)
        return {"seq": e["seq"], "hash": e["entry_hash"][:16], "verdict": verdict}

    def tamper_demo(self, body: dict) -> dict:
        """Edit a *copy* of the ledger and show that verification catches it."""
        sth = self.report["ledger"]["tree_head"]
        target = int(body.get("seq", 0))
        shadow = copy.deepcopy(self.ledger)
        if not (0 <= target < len(shadow.entries)):
            raise ValueError("seq out of range")
        payload = shadow.entries[target]["payload"]
        before = json.dumps(payload, sort_keys=True)[:160]
        if "verdict" in payload:
            payload["verdict"] = "reject" if payload["verdict"] != "reject" else "accept"
        else:
            payload["tampered"] = True
        return {"edited_seq": target, "before": before, "after": json.dumps(payload, sort_keys=True)[:160],
                "detected": shadow.verify_all(sth), "real_ledger_intact": self.ledger.verify_all(sth) == []}


def make_handler(console: Console):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NIRANTAR/0.1"

        def log_message(self, fmt, *args):     # quiet console
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(clean_json(obj), default=str, allow_nan=False).encode(), "application/json")

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/report":
                return self._json(console.report)
            if path == "/api/ledger":
                return self._json(console.ledger_view())
            if path in ("/", "/index.html"):
                path = "/index.html"
            f = (STATIC / path.lstrip("/")).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._json({"error": "not found"}, 404)
            self._send(200, f.read_bytes(), CONTENT_TYPES.get(f.suffix, "application/octet-stream"))

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                if path == "/api/simulate":
                    return self._json(console.simulate(body))
                if path == "/api/decision":
                    return self._json(console.decide(body))
                if path == "/api/ledger/tamper-demo":
                    return self._json(console.tamper_demo(body))
                return self._json({"error": "not found"}, 404)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)

    return Handler


def serve(results_dir: str = "experiments/results", host: str = "127.0.0.1", port: int = 8050) -> None:
    console = Console(results_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(console))
    print(f"NIRANTAR console on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
