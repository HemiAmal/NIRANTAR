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

    def __init__(self, results_dir: str | Path, plan_kwargs: dict | None = None, store: str | Path | None = None,
                 auth: "UserStore | None" = None):
        """``store``: a SETU record store. With it the desk, clock and SAARTHI plan from the records
        (world and fleet state estimated, nothing taken from the simulator); without it they use the
        synthetic fleet's hidden truth, as in the demo.

        ``auth``: a RAKSHAK user store. With it every request needs a login, the server enforces each
        user's roles, and decisions and snags are signed with the user's own key. Without it (a demo on
        one machine) anyone at the console may act in any role, signed by the console's key."""
        self.auth = auth
        self.dir = Path(results_dir)
        self.store_path = Path(store) if store else None
        if self.store_path and not self.store_path.exists():
            raise FileNotFoundError(f"{self.store_path} not found; run `python -m nirantar import` first")
        # records mode keeps its own clock and plans, apart from the synthetic demo's
        self.state_dir = self.dir / "records" if self.store_path else self.dir
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
            if self._sim is None and self.store_path:
                self._sim = self._records_context()
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
                    "signals": self.report["drishti"]["table"],
                    "source": {"mode": "synthetic", "label": "BHARAT-FLEET synthetic fleet (hidden truth)"},
                }
            return self._sim

    def _records_context(self) -> dict:
        from nirantar.setu.estimate import estimate
        from nirantar.setu.schema import Store
        cfg = self.report["config"]
        st = Store(self.store_path)
        e = estimate(st)
        world, dm, start = e.world, e.model, e.start
        vals = surrogate_provision_values(world, start, dm, cfg["horizon_days"])
        sp = e.frames["spells"]
        recent = sp[sp["install_day"] > e.now - 365]
        return {
            "world": world, "dm": dm, "start": start, "cfg": cfg, "frailty": e.frailty, "dq": e.dq,
            "n_fail": dict(dm.n_failures_by_pn),
            "smart": tuple(greedy_portfolio(vals, cfg["budget_lakh"], cfg["horizon_days"])),
            "cons": tuple(consumption_portfolio(world, recent, cfg["budget_lakh"])),
            "signals": e.signals.to_dict("records") if len(e.signals) else [],
            "source": {"mode": "records", "label": f"Records as of {st.meta('as_of')}", "as_of": st.meta("as_of"),
                       "store": self.store_path.name, "generator": st.meta("generator"),
                       "counts": st.counts(), "notes": e.notes,
                       "rogues": len(dm.rogue_flags)},
        }

    def source(self) -> dict:
        """Where the desk's picture of the fleet comes from (cheap: does not build the context)."""
        if self._sim is not None:
            return self._sim["source"]
        if not self.store_path:
            return {"mode": "synthetic", "label": "BHARAT-FLEET synthetic fleet (hidden truth)"}
        from nirantar.setu.schema import Store
        st = Store(self.store_path)
        try:
            return {"mode": "records", "label": f"Records as of {st.meta('as_of')}", "as_of": st.meta("as_of"),
                    "store": self.store_path.name, "generator": st.meta("generator"), "counts": st.counts()}
        finally:
            st.close()

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
                                         ctx["signals"], self.ledger, self.signer, day=clk.day)
            return self._desk

    # -- operations clock ------------------------------------------------
    def clock(self) -> OperationsClock:
        ctx = self.sim_context()
        with self._lock:
            if self._clock is None:
                self._clock = OperationsClock(ctx["world"], P0, ctx["start"], self.state_dir / "live" / "clock.pkl")
            return self._clock

    def clock_view(self) -> dict:
        v = self.clock().view()
        v["plan_status"] = self.planner().state["status"]
        return v

    def advance(self, body: dict, session=None) -> dict:
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
                                                 "applied_on_day": d0, "via": "operations clock",
                                                 **({"by": session.display} if session else {})}, self.signer)
        self.planner().build_async()                 # a fresh plan for the new day
        return self.clock_view()

    def disrupt(self, body: dict, session=None) -> dict:
        country = body.get("country")
        if country not in ("RU", "FR"):
            raise ValueError("country must be RU or FR")
        days = int(body.get("days", 120))
        if days not in (30, 60, 120, 180):
            raise ValueError("a disruption lasts 30, 60, 120 or 180 days")
        if self.planner().state["status"] == "building":
            raise ValueError("a plan is being prepared; declare the disruption when it is ready")
        clk = self.clock()
        with self._lock:
            shock = clk.disrupt(country, days)
            self.ledger.append("scenario", {"supplier": country, "state": "disrupted", "from_day": shock["start"],
                                            "to_day": shock["end"], "via": "exercise control"},
                               session.signer if session else self.signer)
        self.planner().build_async()                 # re-plan for the crisis
        return self.clock_view()

    def reset_clock(self) -> dict:
        clk = self.clock()
        if self.planner().state["status"] == "building":
            raise ValueError("a plan is being prepared; reset when it is ready")
        with self._lock:
            clk.reset()
            for f in (self.state_dir / "live").glob("plan_*.json"):
                f.unlink()
            self._clock = self._planner = self._desk = None
        return self.clock_view()

    # -- CHANAKYA decision desk ---------------------------------------------
    def planner(self) -> PlanDesk:
        ctx, clk = self.sim_context(), self.clock()
        with self._lock:
            n_shocks = len(clk.state["shocks"])
            if self._planner is None or (self._planner.day, self._planner.n_shocks) != (clk.day, n_shocks):
                path = self.state_dir / "plan.json" if (clk.day, n_shocks) == (0, 0) else \
                    self.state_dir / "live" / f"plan_day{clk.day}_s{n_shocks}.json"
                self._planner = PlanDesk(ctx["world"], clk.snapshot, ctx["dm"], ctx["n_fail"], ctx["dq"],
                                         self.ledger, self.signer, path, day=clk.day,
                                         scenario=clk.scenario(days=self.plan_kwargs.get("horizon", 90)),
                                         **self.plan_kwargs)
                self._planner.n_shocks = n_shocks
            return self._planner

    def saarthi_confirm(self, body: dict, session=None) -> dict:
        desk = self.desk()
        with self._lock:
            return desk.confirm(body, signer=session.signer if session else None)

    # -- ledger ----------------------------------------------------------
    def ledger_view(self, limit: int = 200) -> dict:
        sth = self.report["ledger"]["tree_head"]
        bad = self.ledger.verify_all(sth)
        rows = [{"seq": e["seq"], "ts": e["ts"], "kind": e["kind"], "actor": e["actor"],
                 "hash": e["entry_hash"][:16], "payload": e["payload"]} for e in self.ledger.entries[-limit:]]
        return {"entries": rows, "count": len(self.ledger.entries), "failed": bad,
                "tree_head": {"size": sth["size"], "root": sth["root"][:24], "witness": sth["witness"]}}

    def decide(self, body: dict, session=None) -> dict:
        verdict = body.get("verdict")
        if verdict not in ("accept", "defer", "reject"):
            raise ValueError("verdict must be accept, defer or reject")
        seq = int(body["ledger_seq"])
        if not (0 <= seq < len(self.ledger.entries)) or self.ledger.entries[seq]["kind"] != "recommendation":
            raise ValueError("ledger_seq does not point at a recommendation")
        reason = str(body.get("reason_code", "WEB_CONSOLE"))[:64]
        role = body.get("role")
        role = str(role)[:40] if role else None
        if session is not None and role not in session.roles:
            raise PermissionError(f"you do not hold the role {role!r}")
        planner = self.planner()
        rec_plan = self.ledger.entries[seq]["payload"].get("plan_id")
        if rec_plan and (planner.plan is None or rec_plan != planner.plan.get("plan_id")):
            raise ValueError("that plan is no longer current; decide on today's plan")
        planner.check_decision(seq, verdict, role, reason)
        payload = {"recommendation_seq": seq, "verdict": verdict, "reason_code": reason, "via": "web console"}
        if role:
            payload["role"] = role
        if session is not None:
            payload["by"] = session.display
        with self._lock:
            e = self.ledger.append("decision", payload, session.signer if session else self.signer)
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


MAX_BODY = 65536
COOKIE = "nirantar_session"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def _which(body: dict) -> str:
    which = body.get("which", "approved")
    if which not in ("approved", "all"):
        raise ValueError("which must be approved or all")
    return which


# path -> (permission, handler(console, session, body))
GET_ROUTES = {
    "/api/report": ("view", lambda c, s, b: c.report),
    "/api/ledger": ("view", lambda c, s, b: c.ledger_view()),
    "/api/plan": ("view", lambda c, s, b: c.planner().view()),
    "/api/clock": ("view", lambda c, s, b: c.clock_view()),
    "/api/source": ("view", lambda c, s, b: c.source()),
    "/api/saarthi/options": ("view", lambda c, s, b: c.desk().options()),
    "/api/saarthi/entries": ("view", lambda c, s, b: {"entries": c.desk().entries[-50:][::-1],
                                                      "stats": c.desk().stats()}),
    "/api/admin/users": ("admin", lambda c, s, b: {"users": c.auth.users()}),
    "/api/admin/audit": ("admin", lambda c, s, b: {"audit": c.auth.audit_log()}),
}
POST_ROUTES = {
    "/api/simulate": ("simulate", lambda c, s, b: c.simulate(b)),
    "/api/decision": ("decide", lambda c, s, b: c.decide(b, s)),
    "/api/ledger/tamper-demo": ("admin", lambda c, s, b: c.tamper_demo(b)),
    "/api/clock/advance": ("clock", lambda c, s, b: c.advance(b, s)),
    "/api/clock/disrupt": ("clock", lambda c, s, b: c.disrupt(b, s)),
    "/api/clock/reset": ("clock", lambda c, s, b: c.reset_clock()),
    "/api/plan/build": ("plan", lambda c, s, b: c.planner().build_async()),
    "/api/plan/outcome": ("view", lambda c, s, b: c.planner().outcome(_which(b))),
    "/api/saarthi/parse": ("snag", lambda c, s, b: c.desk().parse(b.get("text", ""))),
    "/api/saarthi/check": ("snag", lambda c, s, b: c.desk().check(b.get("fields", {}), b.get("findings"))),
    "/api/saarthi/confirm": ("snag", lambda c, s, b: c.saarthi_confirm(b, s)),
}


def make_handler(console: Console, tls: bool = False):
    from nirantar.rakshak.auth import AuthError

    class Handler(BaseHTTPRequestHandler):
        server_version = "NIRANTAR"
        sys_version = ""

        def log_message(self, fmt, *args):     # quiet console
            pass

        def _send(self, code: int, body: bytes, ctype: str, cookie: str | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            if tls:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200, cookie: str | None = None) -> None:
            self._send(code, json.dumps(clean_json(obj), default=str, allow_nan=False).encode(), "application/json",
                       cookie)

        def _token(self) -> str | None:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE:
                    return v
            return None

        def _cookie(self, token: str, max_age: int) -> str:
            return (f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
                    + ("; Secure" if tls else ""))

        def _session(self):
            """(allowed, session): demo mode has no sessions; with auth a valid session is required."""
            if console.auth is None:
                return True, None
            s = console.auth.session(self._token())
            return s is not None, s

        def _call(self, routes: dict, path: str, body: dict):
            perm, fn = routes[path]
            ok, s = self._session()
            if not ok:
                return self._json({"error": "please log in"}, 401)
            if s is not None and not s.can(perm):
                console.auth.audit(s.username, "forbidden", path, self.client_address[0])
                return self._json({"error": "your role does not allow this"}, 403)
            if console.auth is None and perm == "admin" and path.startswith("/api/admin"):
                return self._json({"error": "no user accounts in demo mode"}, 404)
            return self._json(fn(console, s, body))

        def _guard(self, handler):
            try:
                return handler()
            except AuthError as exc:
                return self._json({"error": str(exc)}, 403)
            except PermissionError as exc:
                return self._json({"error": str(exc)}, 403)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)
            except Exception:                    # never leak internals; keep the trace on the server
                import traceback
                traceback.print_exc()
                return self._json({"error": "internal error"}, 500)

        def do_GET(self):
            self._guard(self._get)

        def _get(self):
            path = urlparse(self.path).path
            if path == "/api/me":
                ok, s = self._session()
                if console.auth is None:
                    return self._json({"mode": "demo"})
                return self._json({"mode": "secure", **s.view()} if ok else {"error": "please log in"}, 200 if ok else 401)
            if path in GET_ROUTES:
                return self._call(GET_ROUTES, path, {})
            if path in ("/", "/index.html"):
                path = "/index.html"
            f = (STATIC / path.lstrip("/")).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._json({"error": "not found"}, 404)
            self._send(200, f.read_bytes(), CONTENT_TYPES.get(f.suffix, "application/octet-stream"))

        def do_POST(self):
            self._guard(self._post)

        def _post(self):
            path = urlparse(self.path).path
            # cross-site request forgery: a custom header (needs a CORS preflight we never grant) and same origin
            if self.headers.get("X-Nirantar") != "1":
                return self._json({"error": "missing request header"}, 403)
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self._json({"error": "cross-origin request refused"}, 403)
            n = int(self.headers.get("Content-Length", "0"))
            if n > MAX_BODY:
                return self._json({"error": "request too large"}, 413)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
            if path == "/api/login":
                if console.auth is None:
                    return self._json({"mode": "demo"})
                token, s = console.auth.login(str(body.get("username", ""))[:64], str(body.get("password", ""))[:256],
                                              self.client_address[0])
                return self._json({"mode": "secure", **s.view()}, cookie=self._cookie(token, 10 * 3600))
            if path == "/api/logout":
                if console.auth is not None:
                    console.auth.logout(self._token())
                return self._json({"ok": True}, cookie=self._cookie("", 0))
            if path == "/api/me/password":
                ok, s = self._session()
                if console.auth is None or not ok:
                    return self._json({"error": "please log in"}, 401)
                console.auth.change_password(s.username, str(body.get("old", "")), str(body.get("new", "")))
                return self._json({"ok": True})
            if path in POST_ROUTES:
                return self._call(POST_ROUTES, path, body)
            return self._json({"error": "not found"}, 404)

    return Handler


def _loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def serve(results_dir: str = "experiments/results", host: str = "127.0.0.1", port: int = 8050,
          store: str | None = None, auth_db: str | None = None, cert: str | None = None, key: str | None = None,
          allow_insecure: bool = False) -> None:
    """Demo on this machine (no logins), or a multi-user node: ``auth_db`` for logins and roles,
    ``cert``/``key`` for HTTPS. Listening beyond this machine needs both, unless ``allow_insecure``."""
    if not _loopback(host) and not allow_insecure and not (auth_db and cert and key):
        raise SystemExit("refusing to listen beyond this machine without logins (--auth) and HTTPS (--cert, --key); "
                         "use --allow-insecure only on an isolated test network")
    auth = None
    if auth_db:
        from nirantar.rakshak.auth import UserStore
        auth = UserStore(auth_db)
        if not auth.users():
            raise SystemExit(f"no user accounts in {auth_db}: add one with `python -m nirantar users add`")
    console = Console(results_dir, store=store, auth=auth)
    httpd = ThreadingHTTPServer((host, port), make_handler(console, tls=bool(cert)))
    if cert:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    scheme = "https" if cert else "http"
    print(f"NIRANTAR console on {scheme}://{host}:{port}  (Ctrl+C to stop)"
          + (f"  planning from records in {store}" if store else "")
          + ("  logins required" if auth else "  demo mode: no logins"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
