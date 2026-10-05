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
from nirantar.chanakya.plan_service import PlanDesk
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.pipeline import clean_json, fan_payload
from nirantar.records import to_frames
from nirantar.saarthi.service import SaarthiDesk
from nirantar.chanakya.desk import action_from_item
from nirantar.sanjaya.clock import OperationsClock
from nirantar.sanjaya.ensemble import P0, P2, P3, run_ensemble, summarise
from nirantar.sanjaya.twin import Scenario, Twin
from nirantar.satya.quality import check_spells, dq_scores
from nirantar.sushruta.agency import flag_rogues, serial_frailty

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}
POLICIES = {"P0": P0, "P2": P2, "P3": P3}
MAX_SEEDS = 16


class Console:
    """Server-side state: report, ledger and a lazily built simulation context."""

    def __init__(self, results_dir: str | Path, plan_kwargs: dict | None = None):
        self.dir = Path(results_dir)
        self.plan_kwargs = plan_kwargs or {}
        self.report_path = self.dir / "milestone1_report.json"
        if not self.report_path.exists():
            raise FileNotFoundError(f"{self.report_path} not found; run `python -m nirantar demo` first")
        self.report = clean_json(json.loads(self.report_path.read_text()))
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.signer = Signer.load_or_create(self.dir / "keys" / "web-console.key", "web-console")
        self._lock = threading.Lock()
        self._sim = None
        self._desk = None
        self._planner = None
        self._clock = None

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
                frailty = serial_frailty(dm, fr["spells"], family_of)
                dm.rogue_flags = flag_rogues(frailty, p_min=0.5)
                start = hist.snapshot
                vals = surrogate_provision_values(world, start, dm, cfg["horizon_days"])
                recent = fr["spells"][fr["spells"]["install_day"] > cfg["history_days"] - 365]
                issues = check_spells(fr["spells"], fr["repairs"], horizon_day=cfg["history_days"])
                dq = dq_scores(fr["spells"], issues).set_index("pn")["dq"].to_dict()
                self._sim = {
                    "world": world, "dm": dm, "start": start, "cfg": cfg, "frailty": frailty,
                    "dq": dq, "n_fail": dict(dm.n_failures_by_pn),
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

    # -- SAARTHI snag desk -----------------------------------------------
    def desk(self) -> SaarthiDesk:
        ctx, clk = self.sim_context(), self.clock()
        with self._lock:
            if self._desk is None or self._desk.day != clk.day:
                self._desk = SaarthiDesk(ctx["world"], clk.snapshot, ctx["frailty"], ctx["dm"].rogue_flags,
                                         self.report["drishti"]["table"], self.ledger, self.signer, day=clk.day)
            return self._desk

    # -- operations clock ------------------------------------------------
    def clock(self) -> OperationsClock:
        ctx = self.sim_context()
        with self._lock:
            if self._clock is None:
                self._clock = OperationsClock(ctx["world"], P0, ctx["start"], self.dir / "live" / "clock.pkl")
            return self._clock

    def clock_view(self) -> dict:
        v = self.clock().view()
        v["plan_status"] = self.planner().state["status"]
        return v

    def advance(self, body: dict) -> dict:
        days = int(body.get("days", 1))
        if days not in (1, 7):
            raise ValueError("advance 1 or 7 days")
        planner, clk = self.planner(), self.clock()
        if planner.state["status"] == "building":
            raise ValueError("a plan is being prepared; advance when it is ready")
        items = planner.approved_unapplied(clk.applied_seqs())
        acts = tuple(action_from_item(it) for it in items)
        meta = tuple({"recommendation_seq": it["ledger_seq"], "text": it["text"], "kind": it["kind"],
                      "plan_id": planner.plan["plan_id"]} for it in items)
        with self._lock:
            d0 = clk.day
            clk.advance(days, acts, meta)
            for it in items:
                self.ledger.append("execution", {"recommendation_seq": it["ledger_seq"], "action": it["label"],
                                                 "applied_on_day": d0, "via": "operations clock"}, self.signer)
        self.planner().build_async()                 # a fresh plan for the new day
        return self.clock_view()

    def reset_clock(self) -> dict:
        clk = self.clock()
        if self.planner().state["status"] == "building":
            raise ValueError("a plan is being prepared; reset when it is ready")
        with self._lock:
            clk.reset()
            for f in (self.dir / "live").glob("plan_day*.json"):
                f.unlink()
            self._clock = self._planner = self._desk = None
        return self.clock_view()

    # -- CHANAKYA decision desk ---------------------------------------------
    def planner(self) -> PlanDesk:
        ctx, clk = self.sim_context(), self.clock()
        with self._lock:
            if self._planner is None or self._planner.day != clk.day:
                path = self.dir / "plan.json" if clk.day == 0 else self.dir / "live" / f"plan_day{clk.day}.json"
                self._planner = PlanDesk(ctx["world"], clk.snapshot, ctx["dm"], ctx["n_fail"], ctx["dq"],
                                         self.ledger, self.signer, path, day=clk.day, **self.plan_kwargs)
            return self._planner

    def saarthi_confirm(self, body: dict) -> dict:
        desk = self.desk()
        with self._lock:
            return desk.confirm(body)

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
        role = body.get("role")
        role = str(role)[:40] if role else None
        planner = self.planner()
        rec_plan = self.ledger.entries[seq]["payload"].get("plan_id")
        if rec_plan and (planner.plan is None or rec_plan != planner.plan.get("plan_id")):
            raise ValueError("that plan is no longer current; decide on today's plan")
        planner.check_decision(seq, verdict, role, reason)
        payload = {"recommendation_seq": seq, "verdict": verdict, "reason_code": reason, "via": "web console"}
        if role:
            payload["role"] = role
        with self._lock:
            e = self.ledger.append("decision", payload, self.signer)
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
            if path == "/api/plan":
                return self._json(console.planner().view())
            if path == "/api/clock":
                return self._json(console.clock_view())
            if path == "/api/saarthi/options":
                return self._json(console.desk().options())
            if path == "/api/saarthi/entries":
                desk = console.desk()
                return self._json({"entries": desk.entries[-50:][::-1], "stats": desk.stats()})
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
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                if path == "/api/simulate":
                    return self._json(console.simulate(body))
                if path == "/api/decision":
                    return self._json(console.decide(body))
                if path == "/api/ledger/tamper-demo":
                    return self._json(console.tamper_demo(body))
                if path == "/api/clock/advance":
                    return self._json(console.advance(body))
                if path == "/api/clock/reset":
                    return self._json(console.reset_clock())
                if path == "/api/plan/build":
                    return self._json(console.planner().build_async())
                if path == "/api/plan/outcome":
                    which = body.get("which", "approved")
                    if which not in ("approved", "all"):
                        raise ValueError("which must be approved or all")
                    return self._json(console.planner().outcome(which))
                if path == "/api/saarthi/parse":
                    return self._json(console.desk().parse(body.get("text", "")))
                if path == "/api/saarthi/check":
                    return self._json(console.desk().check(body.get("fields", {}), body.get("findings")))
                if path == "/api/saarthi/confirm":
                    return self._json(console.saarthi_confirm(body))
                return self._json({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
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
