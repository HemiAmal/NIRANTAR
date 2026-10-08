"""SAARTHI on real logbook English (MaintNet entries) and catalogue (IPC) linking."""
import pytest

from nirantar.saarthi import logbook as LB
from nirantar.saarthi.logbook_eval import evaluate


@pytest.fixture(scope="module")
def vocab():
    return LB.Vocabulary.from_ipc()


@pytest.mark.parametrize("problem,action,part,prob,cyl,eng,act", [
    ("#2 & 3 ROCKER COVER GASKETS LEAKING, R/H ENG.", "REMOVED & REPLACED ROCKER COVER GASKETS.",
     "ROCKER COVER GASKET", "leak", [2, 3], "R", "replace"),
    ("L/H ENG #2, 3 & 4 INTAKE TUBE GASKETS LEAKING.", "INSTALLED NEW GASKETS.",
     "INTAKE TUBE GASKET", "leak", [2, 3, 4], "L", "replace"),
    ("CYL #4 AFT BAFFLE CRACKED.", "STOP DRILLED CRACK.", "BAFFLE", "crack", [4], None, "repair"),
    ("ROCKER BOX COVER SCREWS LOOSE (ALL CYLS).", "RETORQUED SCREWS.", "ROCKER BOX COVER SCREW", "loose",
     [1, 2, 3, 4], None, "tighten"),
    ("#3 INTAKE GASKET LEAKIN", "R&R GASKET", "INTAKE GASKET", "leak", [3], None, "replace"),   # truncated, shorthand
])
def test_fields(vocab, problem, action, part, prob, cyl, eng, act):
    e = LB.extract(problem, action, vocab)
    assert (e.part, e.problem, e.cylinders, e.engine, e.action) == (part, prob, cyl, eng, act)


def test_catalogue_links_and_abstains(vocab):
    assert LB.extract("#3 ROCKER COVER GASKET LEAKING.", "", vocab).ipc[0]["pn"] == "75906"
    assert LB.extract("PUSH ROD TUBE BENT.", "", vocab).ipc[0]["type"].startswith("SHROUD TUBE")   # synonym
    assert LB.extract("ADEL CLAMP LOOSE.", "", vocab).ipc == []          # a bare clamp: ask which one
    assert LB.extract("ENGINE RAN ROUGH.", "", vocab).ipc == []          # the engine is not a catalogue line


def test_held_out_agreement_with_the_reference():
    r = evaluate(split="test")
    assert r["test_entries"] > 4000
    assert r["part_same_head_noun"]["agree"] > 0.85 and r["problem"]["agree"] > 0.95
    assert r["cylinders"]["agree"] > 0.9 and r["engine_side"]["agree"] > 0.95 and r["action"]["agree"] > 0.9
