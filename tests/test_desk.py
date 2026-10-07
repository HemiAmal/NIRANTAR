import json
from collections import Counter

import pytest

from nirantar.chanakya.desk import board, build_plan, candidates
from nirantar.chanakya.plan_service import PlanDesk
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Action, Twin


@pytest.fixture(scope="module")
def start(history):
    return history.snapshot


def run(world, start, actions=(), seed=1, horizon=60):
    return Twin(world, P0, horizon, seed=seed, start=start, actions=actions).run()


# ---------------------------------------------------------------- new twin actions


def _down_pair(world, start):
    """A waiting tail and a donor at the same base, same fleet, down for a different part."""
    by_tail = {}
    for w in start["waiting"]:
        by_tail.setdefault(w["tail"], []).append(w["pn"])
    tails = {t["id"]: t for t in world.tails}
    for r, r_pns in by_tail.items():
        for d, d_pns in by_tail.items():
            if d == r or tails[d]["base"] != tails[r]["base"] or tails[d]["fleet"] != tails[r]["fleet"]:
                continue
            pn = r_pns[0]
            if pn not in d_pns and any(slot[0] == pn for slot in start["installed"][d]):
                return r, d, pn
    pytest.skip("no cannibalisation pair in this history")


def test_cann_flies_one_more_aircraft(world, start):
    recv, donor, pn = _down_pair(world, start)
    base = run(world, start, horizon=3)
    act = run(world, start, (Action("cann", pn, src=donor, tail=recv),), horizon=3)
    assert act.nmcs_by_tail.get(recv, 0) < base.nmcs_by_tail.get(recv, 0)
    assert act.aad > base.aad


def test_cann_never_takes_from_a_flyable_aircraft(world, start):
    recv, _, pn = _down_pair(world, start)
    tails = {t["id"]: t for t in world.tails}
    waiting = {w["tail"] for w in start["waiting"]}
    flyable = next(t["id"] for t in world.tails if t["id"] not in waiting and t["base"] == tails[recv]["base"]
                   and t["fleet"] == tails[recv]["fleet"] and start["work_left"][t["id"]] == 0)
    a = run(world, start, (Action("cann", pn, src=flyable, tail=recv),), horizon=30)
    b = run(world, start, horizon=30)
    assert a.waad == b.waad                       # the action was refused


def test_transfer_and_expedite_move_units(world, start):
    w = start["waiting"][0]
    tails = {t["id"]: t for t in world.tails}
    base = tails[w["tail"]]["base"]
    src = next((b for (b, pn), v in ((tuple(k), v) for k, v in start["stock"].items())
                if pn == w["pn"] and b != base and v), None)
    if src:
        a = run(world, start, (Action("transfer", w["pn"], base=base, src=src),), horizon=5)
        assert a.nmcs_by_tail.get(w["tail"], 0) < run(world, start, horizon=5).nmcs_by_tail.get(w["tail"], 0)
    waiting = {(tails[x["tail"]]["base"], x["pn"]) for x in start["waiting"]}
    slow = max((it for it in start["pipeline"] if it["type"] == "arrive" and (it["base"], it["pn"]) in waiting),
               key=lambda it: it["dt"])
    assert slow["dt"] > 5
    base_run = run(world, start, horizon=30)
    fast = run(world, start, (Action("expedite", slow["pn"], base=slow["base"], serial=slow["sid"]),), horizon=30)
    assert fast.nmcs_days < base_run.nmcs_days       # the waiting aircraft gets its part sooner


def test_no_action_runs_are_unchanged(world, start):
    assert run(world, start, (), seed=3).waad == run(world, start, (), seed=3).waad


# ---------------------------------------------------------------- board and plan


def test_board_matches_snapshot(world, start, model):
    brd = board(world, start, model)
    down = [t for t in brd["tails"] if t["status"] == "NMCS"]
    assert len(down) == len({w["tail"] for w in start["waiting"]})
    assert all(0.0 <= t["risk7"] <= 1.0 for t in brd["tails"])
    for hs in brd["holes"].values():
        days = [h["days"] for h in hs]
        assert days == sorted(days, reverse=True)          # FIFO: longest wait first


def test_candidates_cover_action_kinds(world, start, model):
    brd = board(world, start, model)
    kinds = Counter(c.action.kind for c in candidates(world, start, model, brd, 90))
    assert kinds["cann"] > 0 and kinds["expedite"] > 0


@pytest.fixture(scope="module")
def small_plan(world, start, model):
    n_fail = dict(model.n_failures_by_pn)
    return build_plan(world, start, model, P0, n_fail, {}, n_seeds=6, n_screen=3, workers=1)


def test_plan_respects_conflicts_and_budget(world, small_plan):
    items = small_plan["items"]
    assert items and small_plan["cost_lakh"] <= small_plan["budget_lakh"]
    tails_used = Counter(t for it in items if it["kind"] == "cann" for t in (it["src"], it["tail"]))
    assert all(n == 1 for n in tails_used.values())         # one aircraft, one cannibalisation
    serials = Counter(it["serial"] for it in items if it["serial"] is not None)
    assert all(n == 1 for n in serials.values())
    for it in items:
        assert it["ci95"][0] > 0 and it["grade"] in ("E1", "E2", "E3")
        assert it["authority"] != "Not recommended"
    j = small_plan["joint"]
    assert j["availability_with_plan"] > j["availability_today_procedures"]


def test_parallel_pricing_matches_serial(world, start, model):
    n_fail = dict(model.n_failures_by_pn)
    a = build_plan(world, start, model, P0, n_fail, {}, n_seeds=4, n_screen=2, workers=1)
    b = build_plan(world, start, model, P0, n_fail, {}, n_seeds=4, n_screen=2, workers=2)
    for k in ("created", "runtime_s"):
        a.pop(k), b.pop(k)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_plan_desk_signs_enforces_authority_and_reloads(world, start, model, tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    signer = Signer.load_or_create(tmp_path / "keys" / "c.key", "web-console")
    kw = dict(n_seeds=4, n_screen=2, workers=1)
    desk = PlanDesk(world, start, model, dict(model.n_failures_by_pn), {}, led, signer, tmp_path / "plan.json", **kw)
    plan = desk.build()
    assert all(led.entries[it["ledger_seq"]]["kind"] == "recommendation" for it in plan["items"])
    it = plan["items"][0]
    wrong = next(r for r in ("CEngO", "Logistics officer") if r.split(" ")[0] not in it["authority"])
    with pytest.raises(ValueError):
        desk.check_decision(it["ledger_seq"], "accept", wrong, "MRV_CI_POSITIVE")
    right = "CEngO" if "CEngO" in it["authority"] else "Logistics officer" if "Logistics" in it["authority"] \
        else "BRD Chief Engineer"
    with pytest.raises(ValueError):
        desk.check_decision(it["ledger_seq"], "accept", right, "SAFETY_CONCERN")    # a reject reason
    desk.check_decision(it["ledger_seq"], "accept", right, "MRV_CI_POSITIVE")
    led.append("decision", {"recommendation_seq": it["ledger_seq"], "verdict": "accept",
                            "reason_code": "MRV_CI_POSITIVE", "role": right}, signer)
    again = PlanDesk(world, start, model, {}, {}, Ledger(tmp_path / "ledger.jsonl"), signer,
                     tmp_path / "plan.json", **kw)
    v = again.view()
    assert v["summary"]["approved"] == 1 and v["plan"]["plan_id"] == plan["plan_id"]
    out = again.outcome("approved", n_seeds=3)
    assert out["n_actions"] == 1 and len(out["fan_plan"]["p50"]) > 0
    assert Ledger(tmp_path / "ledger.jsonl").verify_all() == []


def test_crisis_routing_candidates(world, start, model):
    from nirantar.sanjaya.twin import Scenario
    shock = Scenario("ru", (("RU", "disrupted", 0.0, 120.0),))
    brd = board(world, start, model, scenario=shock)
    cands = candidates(world, start, model, brd, 90, shock)
    routes = {(c.action.pn, c.action.agency) for c in cands if c.action.kind == "route"}
    ru_default = {pn for pn, p in world.pns.items() if p.default_agency == "OEM-RU"}
    assert {pn for pn, _ in routes} == ru_default
    assert all(world.agencies[g].country == "IN" for _, g in routes)
    text = next(c.reason for c in cands if c.action.kind == "route")
    assert "disrupted" in text and "less durable" in text
    calm = Scenario("calm", (("RU", "normal", 0.0, 120.0),))
    brd = board(world, start, model, scenario=calm)
    assert not [c for c in candidates(world, start, model, brd, 90, calm) if c.action.kind == "route"]
