import pytest

from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.saarthi.evaluate import generate, score
from nirantar.saarthi.extract import Extractor, normalise, tokens_of
from nirantar.saarthi.service import SaarthiDesk
from nirantar.sushruta.agency import serial_frailty

from saarthi_gold import GOLD


@pytest.fixture(scope="module")
def x(world):
    return Extractor(world)


def fields(x, text):
    return {k: v["value"] for k, v in x.extract(text).as_dict()["fields"].items()}


# ---------------------------------------------------------------- extractor


def test_normalise_unifies_devanagari_variants():
    assert normalise("ऑयल") == normalise("ओयल")
    assert normalise("ज़ंग") == normalise("जंग")
    assert tokens_of("१२ FI-B1-07") == ["12", "fi", "b1", "07"]


def test_three_languages_same_record(x):
    want = {"tail": "FI-B1-07", "part": "FH-HP-03", "position": 2, "mode": "leak", "action": "replaced"}
    for text in ("FI-B1-07 number 2 hydraulic pump leak, replaced",
                 "Fighter B1 ka saat number, doosra hydraulic pump leak, badal diya",
                 "एफ आई बी वन जीरो सेवन, दूसरा हाइड्रोलिक पंप लीक, बदल दिया"):
        got = fields(x, text)
        assert {k: got[k] for k in want} == want, text


def test_language_detection(x):
    assert x.extract("FI B1 07 fuel pump 1 leak").lang == "en"
    assert x.extract("FI B1 07 ka fuel pump 1 leak kar raha hai").lang == "hinglish"
    assert x.extract("एफ आई बी वन जीरो सेवन रडार").lang == "hi"


def test_negated_finding_is_not_the_finding(x):
    d = x.extract("FI B1 07 oil pump 2, chip detector clean, pressure kam, oil sample bhej diya")
    f = {k: v.value for k, v in d.fields.items()}
    assert f["mode"] == "pressure_low"
    assert f["action"] == "reported"                 # the sample was sent, not the pump
    assert any("Chip detected: negative" in s for s in d.findings)


def test_fixed_it_is_not_a_negation(x):
    assert fields(x, "FI B1 07 fuel pump 1 leak, theek kiya")["mode"] == "leak"
    assert fields(x, "FI B1 07 fuel pump 1 leak theek hai")["mode"] is None


def test_asks_instead_of_guessing(x):
    d = x.extract("B1 05 pump leaking").as_dict()["fields"]
    assert d["tail"]["source"] == "ambiguous" and set(d["tail"]["options"]) == {"FI-B1-05", "HE-B1-05"}
    assert d["part"]["source"] == "ambiguous" and "FH-HP-03" in d["part"]["options"]
    d = x.extract("FI B1 32 radar bite fail").as_dict()["fields"]
    assert d["tail"]["value"] is None and "No aircraft FI-B1-32" in d["tail"]["error"]
    d = x.extract("FI B1 07 fuel pump 3 leak").as_dict()["fields"]
    assert d["position"]["value"] is None and "2 positions" in d["position"]["error"]


def test_only_schema_values(x, world):
    """Whatever is said, every filled value exists in the fleet schema."""
    tails = {t["id"] for t in world.tails}
    for text in ("FI B9 99 warp drive exploded", "radar radar radar 77", "HE B3 02 swashplate bite fail", ""):
        f = fields(x, text)
        assert f["tail"] in tails | {None}
        assert f["part"] in set(world.pns) | {None}
        if f["part"] and f["mode"]:
            assert f["mode"] in world.failure_modes[world.pns[f["part"]].family]
    assert fields(x, "HE B3 02 swashplate bite fail")["mode"] is None     # not a drivetrain mode


def test_gold_set_no_silent_errors(x):
    right = silent = total = 0
    for text, exp in GOLD:
        d = x.extract(text).as_dict()["fields"]
        for k, v in exp.items():
            got, src = d[k]["value"], d[k]["source"]
            open_ = got is None or src in ("ambiguous", "missing")
            total += 1
            if (v is None and open_) or got == v:
                right += 1
            elif not open_:
                silent += 1
    assert silent == 0
    assert right / total >= 0.95


def test_synthetic_benchmark(world):
    r = score(world, generate(world, n=300, seed=3))
    assert r["any_silent_error"] == 0.0
    assert r["complete_and_correct"] >= 0.95
    assert set(r["by_language"]) == {"en", "hinglish", "hi"}


# ---------------------------------------------------------------- desk (checks + ledger)


@pytest.fixture()
def desk_factory(world, history, frames, model, family_of, tmp_path):
    frailty = serial_frailty(model, frames["spells"], family_of)
    rogues = set(int(s) for s in frailty[(frailty["p_rogue"] >= 0.5) & (frailty["n_fail"] >= 2)]["serial"])
    signals = [{"family": "hydraulics", "env": "humid_ne", "mode": "corrosion", "signal": True, "candidate": True,
                "rate_ratio": 2.5}]
    path = tmp_path / "ledger.jsonl"

    def make():
        return SaarthiDesk(world, history.snapshot, frailty, rogues, signals, Ledger(path), Signer.generate("t"))
    return make


def _fitted(desk, pn):
    for tail, slots in desk.installed.items():
        for (p, k), sid in slots.items():
            if p == pn:
                return tail, k + 1, sid
    raise AssertionError(pn)


def test_checks_wrong_serial_and_signal(desk_factory):
    desk = desk_factory()
    tail, pos, sid = _fitted(desk, "HU-HP-04")
    other_tail, other_pos, other_sid = next((t, k + 1, s) for t, sl in desk.installed.items()
                                            for (p, k), s in sl.items() if p == "HU-HP-04" and s != sid)
    r = desk.check({"tail": tail, "part": "HU-HP-04", "position": pos, "mode": "leak", "action": "reported",
                    "serial": other_sid})
    serial = next(c for c in r["checks"] if c["id"] == "serial")
    assert serial["status"] == "critical" and other_tail in serial["title"]
    assert not r["ready"]
    r = desk.check({"tail": "HE-B4-01", "part": "HU-HP-04", "position": 1, "mode": "corrosion", "action": "inspected"})
    assert any(c["id"] == "signal" for c in r["checks"]) and r["ready"]


def test_part_must_fit_the_aircraft(desk_factory):
    r = desk_factory().check({"tail": "HE-B4-01", "part": "FH-RD-05", "mode": "bite_fail"})
    assert any(c["id"] == "part" and c["status"] == "critical" for c in r["checks"])
    assert not r["ready"]


def test_position_inferred_from_serial(desk_factory):
    desk = desk_factory()
    tail, pos, sid = _fitted(desk, "FH-FP-01")
    r = desk.check({"tail": tail, "part": "FH-FP-01", "mode": "leak", "serial": sid})
    assert r["fields"]["position"] == pos and "position" in r["inferred"]


def test_rogue_unit_flagged(desk_factory):
    desk = desk_factory()
    hit = next(((t, p, k + 1, s) for t, sl in desk.installed.items() for (p, k), s in sl.items() if s in desk.rogues), None)
    if hit is None:
        pytest.skip("no rogue fitted in this history")
    tail, pn, pos, sid = hit
    mode = next(iter(desk.w.failure_modes[desk.w.pns[pn].family]))
    r = desk.check({"tail": tail, "part": pn, "position": pos, "mode": mode})
    assert any(c["id"] == "rogue" and c["status"] == "warning" for c in r["checks"])


def test_confirm_signs_updates_state_and_replays(desk_factory):
    desk = desk_factory()
    (base, pn), spares = next(((k, v) for k, v in desk.stock.items() if v))
    tail = next(t["id"] for t in desk.w.tails if t["base"] == base and t["fleet"] == desk.w.pns[pn].fleet)
    old = desk.installed[tail][(pn, 0)]
    mode = next(iter(desk.w.failure_modes[desk.w.pns[pn].family]))
    n_spares = len(spares)
    e = desk.confirm({"fields": {"tail": tail, "part": pn, "position": 1, "mode": mode, "action": "replaced"},
                      "transcript": "test", "input": "voice", "entry_seconds": 11.5})
    assert e["removed_serial"] == old and e["installed_serial"] is not None
    assert desk.installed[tail][(pn, 0)] == e["installed_serial"]
    assert len(desk.stock[(base, pn)]) == n_spares - 1
    assert desk.ledger.entries[-1]["kind"] == "snag_entry" and desk.ledger.verify_all() == []
    # duplicate warning, then a fresh desk replays the ledger to the same state
    r = desk.check({"tail": tail, "part": pn, "position": 1, "mode": mode})
    assert any(c["id"] == "duplicate" for c in r["checks"])
    again = desk_factory()
    assert again.installed[tail][(pn, 0)] == e["installed_serial"]
    assert again.stats()["entries"] == 1 and again.stats()["voice"] == 1


def test_confirm_refuses_incomplete(desk_factory):
    with pytest.raises(ValueError):
        desk_factory().confirm({"fields": {"tail": "FI-B1-07", "part": "FH-HP-03"}})
    with pytest.raises(ValueError):
        desk_factory().check(["not", "a", "dict"])
