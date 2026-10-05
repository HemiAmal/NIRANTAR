"""Decision-desk service: builds today's plan, signs it, tracks decisions, simulates the approved plan.

Used by the web console and by ``python -m nirantar plan``. The plan is saved as
``plan.json`` next to the ledger; each plan item is a signed ``recommendation``
entry, and every approval, deferral or rejection is a signed ``decision``
entry that names the approving role and a reason code.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from nirantar.bharat_fleet.world import World
from nirantar.chanakya.desk import action_from_item, build_plan, simulate_plan
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import DecisionModel, Policy

ROLES = ("Logistics officer", "CEngO", "BRD Chief Engineer", "HQMC review", "Command logistics")
REASONS = {
    "accept": ("MRV_CI_POSITIVE", "OPERATIONAL_NEED"),
    "defer": ("AWAITING_FUNDS", "NEED_MORE_INFO", "TRANSPORT_UNAVAILABLE"),
    "reject": ("OPERATIONAL_REASON", "DATA_DOUBT", "SAFETY_CONCERN", "DONOR_NEEDED_ELSEWHERE"),
}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


class PlanDesk:
    def __init__(self, world: World, start: dict, dm: DecisionModel, n_fail: dict, dq: dict,
                 ledger: Ledger, signer: Signer, path: str | Path, policy: Policy = P0, day: int = 0,
                 **plan_kwargs):
        self.w, self.start, self.dm, self.n_fail, self.dq = world, start, dm, n_fail, dq
        self.day = day
        self.ledger, self.signer, self.path, self.policy = ledger, signer, Path(path), policy
        self.kwargs = plan_kwargs
        self.plan: dict | None = None
        self.state = {"status": "none", "step": "", "i": 0, "n": 0, "error": ""}
        self._lock = threading.Lock()
        if self.path.exists():
            self.plan = json.loads(self.path.read_text(encoding="utf-8"))
            self.state["status"] = "ready"

    # ------------------------------------------------------------ build

    def build(self, log=lambda *_: None) -> dict:
        def progress(i, n, step):
            self.state.update(i=i, n=n, step=step)

        plan = build_plan(self.w, self.start, self.dm, self.policy, self.n_fail, self.dq,
                          log=log, progress=progress, **self.kwargs)
        plan["plan_id"] = "PLAN-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        plan["day"] = self.day
        for it in plan["items"]:
            e = self.ledger.append("recommendation", {
                "plan_id": plan["plan_id"], "action": it["label"], "kind": it["kind"], "text": it["text"],
                "mrv_aad": it["mrv"], "ci95": it["ci95"], "cost_lakh": it["cost_lakh"],
                "cod_per_day": it.get("cod_per_day"), "evidence_grade": it["grade"],
                "authority": it["authority"], "horizon_days": plan["horizon_days"], "day": self.day,
            }, self.signer)
            it["ledger_seq"] = e["seq"]
            it["ledger_hash"] = e["entry_hash"][:16]
        self.path.write_text(json.dumps(plan, default=_json_default), encoding="utf-8")
        self.plan = plan
        return plan

    def build_async(self) -> dict:
        with self._lock:
            if self.state["status"] == "building":
                return self.state
            self.state = {"status": "building", "step": "starting", "i": 0, "n": 0, "error": ""}

        def work():
            try:
                self.build()
                self.state["status"] = "ready"
            except Exception as exc:                       # surface the error in the UI
                self.state.update(status="error", error=str(exc))

        threading.Thread(target=work, daemon=True).start()
        return self.state

    # ------------------------------------------------------------ decisions

    def decisions(self) -> dict[int, dict]:
        """Latest signed decision per recommendation."""
        out: dict[int, dict] = {}
        for e in self.ledger.entries:
            if e["kind"] == "decision":
                p = e["payload"]
                out[int(p["recommendation_seq"])] = {"verdict": p["verdict"], "reason_code": p.get("reason_code"),
                                                     "role": p.get("role"), "seq": e["seq"],
                                                     "hash": e["entry_hash"][:16], "ts": e["ts"]}
        return out

    def check_decision(self, seq: int, verdict: str, role: str | None, reason: str) -> None:
        """Only the authority named on a plan item may decide it (Action Authority Matrix)."""
        if self.plan is None:
            return
        item = next((i for i in self.plan["items"] if i.get("ledger_seq") == seq), None)
        if item is None:
            return                                          # not a plan item (e.g. a provisioning opportunity)
        if role not in ROLES:
            raise ValueError("choose the role you are acting as")
        if role.split(" ")[0] not in item["authority"] and role not in item["authority"]:
            raise ValueError(f"this action needs {item['authority']}, not {role}")
        if reason not in REASONS[verdict]:
            raise ValueError(f"reason must be one of {', '.join(REASONS[verdict])}")

    def view(self) -> dict:
        out = {"state": self.state, "roles": ROLES, "reasons": REASONS, "day": self.day}
        if self.plan is not None:
            dec = self.decisions()
            for it in self.plan["items"]:
                it["decision"] = dec.get(it.get("ledger_seq"))
            pending = [it for it in self.plan["items"] if it["decision"] is None
                       or it["decision"]["verdict"] == "defer"]
            out["plan"] = self.plan
            out["summary"] = {
                "approved": sum(1 for it in self.plan["items"] if it["decision"] and it["decision"]["verdict"] == "accept"),
                "rejected": sum(1 for it in self.plan["items"] if it["decision"] and it["decision"]["verdict"] == "reject"),
                "pending": len(pending),
                "pending_cod_per_day": round(sum(max(it.get("cod_per_day") or 0.0, 0.0) for it in pending), 2),
            }
        return out

    # ------------------------------------------------------------ outcome

    def approved_unapplied(self, applied: set[int]) -> list[dict]:
        if self.plan is None:
            return []
        dec = self.decisions()
        return [it for it in self.plan["items"] if it.get("ledger_seq") not in applied
                and (dec.get(it.get("ledger_seq")) or {}).get("verdict") == "accept"]

    def outcome(self, which: str = "approved", n_seeds: int = 12) -> dict:
        if self.plan is None:
            raise ValueError("no plan yet")
        dec = self.decisions()
        items = [it for it in self.plan["items"]
                 if which == "all" or (dec.get(it.get("ledger_seq")) or {}).get("verdict") == "accept"]
        from nirantar.pipeline import fan_payload
        acts = tuple(action_from_item(it) for it in items)
        base, plan = simulate_plan(self.w, self.start, self.dm, self.policy, acts, self.plan["horizon_days"],
                                   seeds=range(7100, 7100 + n_seeds))
        av_b = np.array([r.overall_availability for r in base])
        av_p = np.array([r.overall_availability for r in plan])
        return {"which": which, "n_actions": len(acts), "seeds": n_seeds,
                "fan_base": fan_payload(base), "fan_plan": fan_payload(plan),
                "availability_base": round(float(av_b.mean()), 4), "availability_plan": round(float(av_p.mean()), 4),
                "waad_gain": round(float(np.mean([p.waad - b.waad for p, b in zip(plan, base)])), 1),
                "nmcs_days_saved": round(float(np.mean([b.nmcs_days - p.nmcs_days for p, b in zip(plan, base)])), 1)}
