import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from nirantar.pipeline import Config, run
from nirantar.ui.server import Console, make_handler


@pytest.fixture(scope="module")
def console_url(tmp_path_factory):
    out = tmp_path_factory.mktemp("results")
    run(Config(history_days=730, n_seeds=2, mrv_seeds=2, top_k=2, out_dir=str(out)), log=lambda *_: None)
    console = Console(out, plan_kwargs={"n_seeds": 4, "n_screen": 2, "workers": 1})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(console))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", console
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.read()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_static_and_report(console_url):
    url, _ = console_url
    assert get(url + "/")[0] == 200
    assert get(url + "/app.js")[0] == 200
    status, body = get(url + "/api/report")
    rep = json.loads(body)                       # strict JSON: no NaN
    assert {"experiment", "fan", "opportunities"} <= set(rep)
    assert set(rep["fan"]) == {"normal", "supply_shock"}


def test_path_traversal_blocked(console_url):
    url, _ = console_url
    with pytest.raises(urllib.error.HTTPError) as e:
        get(url + "/../pipeline.py")
    assert e.value.code == 404


def test_decision_signed_and_validated(console_url):
    url, console = console_url
    seq = console.report["opportunities"][0]["ledger_seq"]
    code, r = post(url + "/api/decision", {"ledger_seq": seq, "verdict": "accept"})
    assert code == 200 and r["verdict"] == "accept"
    assert post(url + "/api/decision", {"ledger_seq": 0, "verdict": "accept"})[0] == 400       # not a recommendation
    assert post(url + "/api/decision", {"ledger_seq": seq, "verdict": "ground"})[0] == 400     # invalid verdict
    ledger = json.loads(get(url + "/api/ledger")[1])
    assert ledger["failed"] == []


def test_tamper_demo_never_touches_real_ledger(console_url):
    url, _ = console_url
    code, r = post(url + "/api/ledger/tamper-demo", {"seq": 2})
    assert code == 200 and 2 in r["detected"] and r["real_ledger_intact"]


def test_live_simulation(console_url):
    url, _ = console_url
    code, r = post(url + "/api/simulate", {"policy": "P3", "shock_start": 10, "shock_days": 60, "seeds": 2, "horizon": 60})
    assert code == 200 and 0 < r["mean"] < 1 and len(r["fan"]["p50"]) > 0
    assert post(url + "/api/simulate", {"policy": "PX"})[0] == 400


def test_saarthi_endpoints(console_url):
    url, _ = console_url
    opts = json.loads(get(url + "/api/saarthi/options")[1])
    assert len(opts["tails"]) == 70 and opts["actions"]
    code, r = post(url + "/api/saarthi/parse", {"text": "FI B1 07 doosra hydraulic pump leak, badal diya"})
    assert code == 200 and r["fields"]["tail"] == "FI-B1-07" and r["draft"]["lang"] == "hinglish"
    code, c = post(url + "/api/saarthi/check", {"fields": r["fields"]})
    assert code == 200 and c["ready"]
    code, e = post(url + "/api/saarthi/confirm", {"fields": r["fields"], "transcript": r["draft"]["text"], "input": "typed"})
    assert code == 200 and e["tail"] == "FI-B1-07"
    entries = json.loads(get(url + "/api/saarthi/entries")[1])
    assert entries["entries"][0]["seq"] == e["seq"] and entries["stats"]["entries"] >= 1
    assert post(url + "/api/saarthi/confirm", {"fields": {"tail": "FI-B1-07"}})[0] == 400
    assert post(url + "/api/saarthi/check", {"fields": "nope"})[0] == 400
    assert post(url + "/api/saarthi/parse", [1, 2])[0] == 400
    assert json.loads(get(url + "/api/ledger")[1])["failed"] == []


def test_plan_build_decide_and_outcome(console_url):
    import time
    url, _ = console_url
    v = json.loads(get(url + "/api/plan")[1])
    if v["state"]["status"] != "ready":
        assert post(url + "/api/plan/build", {})[0] == 200
        for _ in range(240):
            v = json.loads(get(url + "/api/plan")[1])
            if v["state"]["status"] in ("ready", "error"):
                break
            time.sleep(0.5)
    assert v["state"]["status"] == "ready", v["state"]
    item = v["plan"]["items"][0]
    role = next(r for r in v["roles"] if r.split(" ")[0] in item["authority"])
    other = next(r for r in v["roles"] if r.split(" ")[0] not in item["authority"])
    seq = item["ledger_seq"]
    assert post(url + "/api/decision", {"ledger_seq": seq, "verdict": "accept", "role": other,
                                        "reason_code": "MRV_CI_POSITIVE"})[0] == 400
    code, r = post(url + "/api/decision", {"ledger_seq": seq, "verdict": "accept", "role": role,
                                           "reason_code": "MRV_CI_POSITIVE"})
    assert code == 200
    v = json.loads(get(url + "/api/plan")[1])
    assert v["summary"]["approved"] == 1
    code, o = post(url + "/api/plan/outcome", {"which": "approved"})
    assert code == 200 and o["n_actions"] == 1
    assert post(url + "/api/plan/outcome", {"which": "everything"})[0] == 400
    assert json.loads(get(url + "/api/ledger")[1])["failed"] == []


def test_clock_applies_approved_actions_and_retires_the_old_plan(console_url):
    import time
    url, console = console_url
    v = json.loads(get(url + "/api/plan")[1])
    assert v["state"]["status"] == "ready"
    plan_id = v["plan"]["plan_id"]
    approved = [it for it in v["plan"]["items"] if it["decision"] and it["decision"]["verdict"] == "accept"]
    assert approved                                    # from the previous test
    pending = next((it for it in v["plan"]["items"] if it["decision"] is None), None)
    assert post(url + "/api/clock/advance", {"days": 3})[0] == 400       # only 1 or 7
    code, c = post(url + "/api/clock/advance", {"days": 1})
    assert code == 200 and c["day"] == 1 and len(c["applied"]) == len(approved) and len(c["log"]) == 1
    executions = [e for e in console.ledger.entries if e["kind"] == "execution"]
    assert {e["payload"]["recommendation_seq"] for e in executions} >= {it["ledger_seq"] for it in approved}
    for _ in range(240):                               # a new plan for day 1 is prepared in the background
        v = json.loads(get(url + "/api/plan")[1])
        if v["state"]["status"] in ("ready", "error"):
            break
        time.sleep(0.5)
    assert v["state"]["status"] == "ready" and v["day"] == 1 and v["plan"]["plan_id"] != plan_id
    if pending:
        role = next(r for r in v["roles"] if r.split(" ")[0] in pending["authority"])
        assert post(url + "/api/decision", {"ledger_seq": pending["ledger_seq"], "verdict": "accept",
                                            "role": role, "reason_code": "MRV_CI_POSITIVE"})[0] == 400
    code, c = post(url + "/api/clock/reset", {})
    assert code == 200 and c["day"] == 0 and c["log"] == []
    assert json.loads(get(url + "/api/plan")[1])["plan"]["plan_id"] == plan_id
    assert json.loads(get(url + "/api/ledger")[1])["failed"] == []


def test_declare_disruption_replans_for_the_crisis(console_url):
    import time
    url, console = console_url
    assert post(url + "/api/clock/disrupt", {"country": "XX", "days": 120})[0] == 400
    assert post(url + "/api/clock/disrupt", {"country": "RU", "days": 45})[0] == 400
    code, c = post(url + "/api/clock/disrupt", {"country": "RU", "days": 120})
    assert code == 200 and c["shocks"][-1]["active"]
    assert console.ledger.entries[-1]["kind"] == "scenario"
    for _ in range(240):
        v = json.loads(get(url + "/api/plan")[1])
        if v["state"]["status"] in ("ready", "error"):
            break
        time.sleep(0.5)
    assert v["state"]["status"] == "ready" and v["plan"]["scenario"][0][:2] == ["RU", "disrupted"]
    assert post(url + "/api/clock/reset", {})[0] == 200
    assert json.loads(get(url + "/api/clock")[1])["shocks"] == []
