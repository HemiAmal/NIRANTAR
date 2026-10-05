"""Synthetic utterance benchmark for the SAARTHI extractor.

Generates snag reports with known ground truth in English, Hinglish (Roman)
and Hindi (Devanagari), in the styles a speech recogniser produces: spelled
tail letters, number words, fillers, missing punctuation, clauses in any
order. Scores each field and, most importantly, the *silent error* rate:
a field filled with a wrong value and not flagged for the technician.

Limitation: the generator draws part and failure-mode wording from the same
lexicon the extractor uses, so this measures robustness of parsing (numbers,
order, script, fillers, ambiguity handling), not vocabulary coverage. The
hand-written gold set in ``tests/test_saarthi.py`` covers phrasing that is not
generated here; real flight-line speech remains to be tested.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nirantar.bharat_fleet.world import World
from nirantar.saarthi import lexicon as L
from nirantar.saarthi.extract import Extractor, _DEVANAGARI

FIELDS = ("tail", "part", "position", "mode", "action")
EN_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
HI_DIGITS = ("shunya", "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau")
DEV_DIGITS = ("शून्य", "एक", "दो", "तीन", "चार", "पांच", "छह", "सात", "आठ", "नौ")
DEV_EN_DIGITS = ("जीरो", "वन", "टू", "थ्री", "फोर", "फाइव", "सिक्स", "सेवन", "एट", "नाइन")
ACTIONS = ("reported", "inspected", "rectified_in_situ", "removed", "replaced", "sent_for_repair")


@dataclass
class Case:
    text: str
    lang: str
    truth: dict


def _pick(rng, seq):
    return seq[int(rng.integers(len(seq)))]


def _script(phrases, lang):
    dev = [p for p in phrases if _DEVANAGARI.search(p)]
    rom = [p for p in phrases if not _DEVANAGARI.search(p)]
    return dev if lang == "hi" and dev else rom


def _number(rng, n: int, lang: str, two_digit: bool = False) -> str:
    s = f"{n:02d}" if two_digit else str(n)
    style = rng.integers(3)
    if style == 0:
        return s if two_digit or rng.random() < 0.5 else str(n)
    digits = {"en": EN_DIGITS, "hinglish": HI_DIGITS, "hi": DEV_DIGITS}[lang]
    if lang == "hi" and rng.random() < 0.5:
        digits = DEV_EN_DIGITS
    if two_digit and n < 10 and rng.random() < 0.5:
        return " ".join(digits[int(c)] for c in s)
    if n <= 9:
        return digits[n]
    return str(n)


def _tail_text(rng, tail: dict, lang: str) -> str:
    fleet, base, num = tail["fleet"], tail["base"], int(tail["id"].split("-")[-1])
    b = int(base[1])
    pre = tail["id"][:2]
    if lang == "hi":
        letters = {"FI": "एफ आई", "HE": "एच ई"}[pre]
        word = _pick(rng, L.FLEET_WORDS[fleet][-3:] if fleet == "HeloU" else ("फाइटर",))
        return _pick(rng, [
            f"{letters} बी {_number(rng, b, lang)} {_number(rng, num, lang, True)}",
            f"{word} बी {_number(rng, b, lang)} नंबर {_number(rng, num, lang)}",
            f"बेस {_number(rng, b, lang)} का {_number(rng, num, lang)} नंबर {word}",
        ])
    word = _pick(rng, ("fighter", "jet") if fleet == "FighterH" else ("helicopter", "heli", "chopper"))
    if lang == "hinglish":
        return _pick(rng, [
            f"{word} B{b} ka {_number(rng, num, lang)} number",
            f"B{b} ka {_number(rng, num, lang)} number {word}",
            f"{pre} B{b} {num:02d}",
        ])
    return _pick(rng, [
        f"{pre}-B{b}-{num:02d}", f"{pre} B{b} {num:02d}", f"{pre.lower()} b {_number(rng, b, lang)} {_number(rng, num, lang, True)}",
        f"{word} B{b} number {_number(rng, num, lang)}", f"{word} base {_number(rng, b, lang)} tail {num}",
    ])


def _position_text(rng, pos: int, npos: int, lang: str) -> str:
    if lang == "hi":
        opts = [f"नंबर {_number(rng, pos, lang)}", f"पोजीशन {_number(rng, pos, lang)}"]
        if pos in L.ORDINALS:
            opts.append(_pick(rng, [w for w in L.ORDINALS[pos] if _DEVANAGARI.search(w)]))
        if npos == 2:
            opts.append(_pick(rng, [w for w in L.SIDES[pos] if _DEVANAGARI.search(w)]))
        return _pick(rng, opts)
    if lang == "hinglish":
        opts = [f"{_number(rng, pos, lang)} number", f"position {pos}"]
        if pos in L.ORDINALS:
            opts.append(_pick(rng, L.ORDINALS[pos][2:4]))
        if npos == 2:
            opts.append(_pick(rng, L.SIDES[pos][1:3]) + " side")
        return _pick(rng, opts)
    opts = [f"number {_number(rng, pos, lang)}", f"position {_number(rng, pos, lang)}", f"no {pos}"]
    if pos in L.ORDINALS:
        opts.append(L.ORDINALS[pos][0])
    if npos == 2:
        opts.append(L.SIDES[pos][0])
    return _pick(rng, opts)


def generate(world: World, n: int = 600, seed: int = 0) -> list[Case]:
    rng = np.random.default_rng(seed)
    langs = ("en", "hinglish", "hi")
    cases = []
    for i in range(n):
        lang = langs[i % 3]
        tail = world.tails[int(rng.integers(len(world.tails)))]
        pns = [p for p in world.pns.values() if p.fleet == tail["fleet"]]
        part = pns[int(rng.integers(len(pns)))]
        pos = int(rng.integers(1, part.positions + 1))
        mode = _pick(rng, list(world.failure_modes[part.family]))
        action = _pick(rng, ACTIONS)
        # avoid a phrase that also names another part of this fleet
        fleet_phrases = {p.pn: set(L.PART_PHRASES[p.pn]) for p in pns}
        own = [ph for ph in _script(L.PART_PHRASES[part.pn], lang)
               if not any(ph in v for k, v in fleet_phrases.items() if k != part.pn)]
        modes_here = world.failure_modes[part.family]
        mode_ph = [ph for ph in _script(L.MODE_PHRASES[mode], lang)
                   if not any(ph in L.MODE_PHRASES[m] for m in modes_here if m != mode)]
        clauses = [_tail_text(rng, tail, lang)]
        part_txt = _pick(rng, own)
        if part.positions > 1:
            ptxt = _position_text(rng, pos, part.positions, lang)
            part_txt = f"{ptxt} {part_txt}" if rng.random() < 0.6 else f"{part_txt} {ptxt}"
        clauses.append(part_txt)
        clauses.append(_pick(rng, mode_ph))
        if action != "reported":
            clauses.append(_pick(rng, _script(L.ACTION_PHRASES[action], lang)))
        if rng.random() < 0.3:          # clause order varies
            clauses[1:] = [clauses[1], *rng.permutation(clauses[2:]).tolist()]
        if rng.random() < 0.3:
            clauses.insert(int(rng.integers(len(clauses) + 1)), _pick(rng, L.FILLERS[:6] if lang != "hi" else L.FILLERS[-2:]))
        sep = _pick(rng, (", ", " ", " , "))
        cases.append(Case(sep.join(clauses), lang, {"tail": tail["id"], "part": part.pn, "position": pos,
                                                     "mode": mode, "action": action}))
    return cases


def score(world: World, cases: list[Case]) -> dict:
    x = Extractor(world)
    per = {f: {"right": 0, "flagged": 0, "silent_wrong": 0} for f in FIELDS}
    exact = silent_any = 0
    by_lang: dict[str, list[int]] = {}
    failures = []
    for c in cases:
        d = x.extract(c.text).as_dict()["fields"]
        ok_all, silent = True, False
        for f in FIELDS:
            v = d[f]["value"]
            if v == c.truth[f]:
                per[f]["right"] += 1
            elif v is None or d[f]["source"] in ("ambiguous", "missing"):
                per[f]["flagged"] += 1
                ok_all = False
            else:
                per[f]["silent_wrong"] += 1
                ok_all, silent = False, True
        exact += ok_all
        silent_any += silent
        by_lang.setdefault(c.lang, []).append(int(ok_all))
        if not ok_all and len(failures) < 15:
            failures.append({"text": c.text, "truth": c.truth, "got": {f: d[f]["value"] for f in FIELDS}})
    n = len(cases)
    return {
        "n": n,
        "complete_and_correct": round(exact / n, 4),
        "any_silent_error": round(silent_any / n, 4),
        "by_language": {k: round(sum(v) / len(v), 4) for k, v in by_lang.items()},
        "fields": {f: {k: round(v / n, 4) for k, v in d.items()} for f, d in per.items()},
        "examples_of_failures": failures,
    }
