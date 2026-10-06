"""RAKSHAK accounts, sessions and the console's server-side enforcement."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from nirantar.chitragupta.ledger import Ledger
from nirantar.pipeline import Config, run
from nirantar.rakshak import auth as A
from nirantar.rakshak.auth import AuthError, UserStore
from nirantar.ui.server import Console, make_handler, serve

PW = "correct horse battery staple"


def test_accounts_passwords_and_keys(tmp_path):
    st = UserStore(tmp_path / "u.db")
    with pytest.raises(AuthError):
        st.create_user("short", "too short", ["Viewer"])
    with pytest.raises(AuthError):
        st.create_user("bad", PW, ["Wing Commander"])
    u = st.create_user("cengo.b1", PW, ["CEngO"], "Wg Cdr Rao")
    assert u["actor"].startswith("cengo.b1@")
    with pytest.raises(AuthError):
        st.create_user("CENGO.B1", PW, ["Viewer"])                 # usernames are case-insensitive
    token, s = st.login("Cengo.B1", PW)
    assert s.can("decide") and not s.can("clock") and s.signer.actor == u["actor"]
    st.change_password("cengo.b1", PW, PW + "!")                   # same key, re-sealed
    assert st.user("cengo.b1")["actor"] == u["actor"]
    with pytest.raises(AuthError):
        st.login("cengo.b1", PW)
    _, s2 = st.login("cengo.b1", PW + "!")
    assert s2.signer.public_b64 == s.signer.public_b64
    r = st.reset_password("cengo.b1", "a brand new passphrase")    # administrator reset: a new key
    assert r["actor"] != u["actor"] and st.session(token) is None  # and every session ends
    db = (tmp_path / "u.db").read_bytes()
    assert PW.encode() not in db and b"PRIVATE" not in db


def test_lockout_disable_and_session_expiry(tmp_path, monkeypatch):
    st = UserStore(tmp_path / "u.db")
    st.create_user("tech1", PW, ["Technician"])
    for _ in range(A.MAX_FAILS):
        with pytest.raises(AuthError):
            st.login("tech1", "wrong passphrase!!")
    with pytest.raises(AuthError, match="too many"):
        st.login("tech1", PW)                                       # locked even with the right passphrase
    st.set_disabled("tech1", False)                                 # an administrator unlocks
    token, _ = st.login("tech1", PW)
    assert st.session(token) is not None
    monkeypatch.setattr(A, "IDLE_SECONDS", -1)
    assert st.session(token) is None                                # idle sessions expire
    st.set_disabled("tech1", True)
    with pytest.raises(AuthError, match="disabled"):
        st.login("tech1", PW)
    events = [e["event"] for e in st.audit_log()]
    assert "locked" in events and "login" in events and "disabled" in events


@pytest.fixture(scope="module")
def secure(tmp_path_factory):
    out = tmp_path_factory.mktemp("results")
    run(Config(history_days=730, n_seeds=2, mrv_seeds=2, top_k=2, out_dir=str(out)), log=lambda *_: None)
    st = UserStore(out / "users.db")
    st.create_user("logo", PW, ["Logistics officer"], "Sqn Ldr Iyer")
    st.create_user("tech", PW, ["Technician"])
    st.create_user("admin", PW, ["Administrator"])
    console = Console(out, plan_kwargs={"n_seeds": 4, "n_screen": 2, "workers": 1}, auth=st)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(console))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", console
    httpd.shutdown()


def call(url, body=None, cookie=None, headers=None):
    h = {"Content-Type": "application/json", "X-Nirantar": "1", **(headers or {})}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), e.headers


def login(url, user):
    code, me, h = call(url + "/api/login", {"username": user, "password": PW})
    assert code == 200, me
    c = h["Set-Cookie"]
    assert "HttpOnly" in c and "SameSite=Strict" in c
    return c.split(";")[0], me


def test_everything_needs_a_login(secure):
    url, _ = secure
    assert call(url + "/api/report")[0] == 401
    assert call(url + "/api/me")[0] == 401
    assert call(url + "/api/simulate", {"policy": "P3"})[0] == 401
    with urllib.request.urlopen(url + "/") as r:                    # the page itself loads (to show the sign-in)
        assert r.status == 200 and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert call(url + "/api/login", {"username": "logo", "password": "nope nope nope"})[0] == 403


def test_roles_are_enforced_by_the_server(secure):
    url, console = secure
    cookie, me = login(url, "logo")
    assert me["roles"] == ["Logistics officer"] and "decide" in me["permissions"]
    seq = console.report["opportunities"][0]["ledger_seq"]
    body = {"ledger_seq": seq, "verdict": "accept", "reason_code": "MRV_CI_POSITIVE"}
    assert call(url + "/api/decision", {**body, "role": "CEngO"}, cookie)[0] == 403        # not a role they hold
    code, r, _ = call(url + "/api/decision", {**body, "role": "Logistics officer"}, cookie)
    assert code == 200
    e = console.ledger.entries[r["seq"]]
    assert e["actor"] == me["actor"] and e["payload"]["by"] == "Sqn Ldr Iyer"           # signed with their own key
    assert Ledger(console.dir / "ledger.jsonl").verify_all() == []
    assert call(url + "/api/clock/advance", {"days": 1}, cookie)[0] == 403              # exercise control only
    assert call(url + "/api/admin/users", None, cookie)[0] == 403
    tcookie, _ = login(url, "tech")
    assert call(url + "/api/decision", {**body, "role": "Logistics officer"}, tcookie)[0] == 403
    acookie, _ = login(url, "admin")
    code, users, _ = call(url + "/api/admin/users", None, acookie)
    assert code == 200 and {u["username"] for u in users["users"]} == {"logo", "tech", "admin"}
    code, audit, _ = call(url + "/api/admin/audit", None, acookie)
    assert any(a["event"] == "forbidden" for a in audit["audit"])


def test_forgery_and_logout(secure):
    url, _ = secure
    cookie, _ = login(url, "logo")
    req = urllib.request.Request(url + "/api/simulate", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": cookie})
    with pytest.raises(urllib.error.HTTPError) as e:                # no custom header: refused
        urllib.request.urlopen(req)
    assert e.value.code == 403
    assert call(url + "/api/simulate", {"policy": "P3"}, cookie, {"Origin": "http://evil.example"})[0] == 403
    assert call(url + "/api/logout", {}, cookie)[0] == 200
    assert call(url + "/api/me", None, cookie)[0] == 401


def test_network_listening_needs_logins_and_https():
    with pytest.raises(SystemExit, match="refusing"):
        serve(host="0.0.0.0", port=0)
