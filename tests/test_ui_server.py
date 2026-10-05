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
    console = Console(out)
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
