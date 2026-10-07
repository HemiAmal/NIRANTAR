"""SAARTHI-lite: schema-constrained snag extraction from Hindi / Hinglish / English text.

Input is what a technician said (from speech recognition) or typed. Output is a
draft snag record whose every field is either a value from the fleet schema
(an existing tail, a part number fitted to that fleet, a failure mode of that
part's family, a position the part actually has) or explicitly missing. The
extractor never invents a value: when it is unsure it asks.

Each field carries its provenance:

* ``heard``     - stated in the utterance
* ``inferred``  - deduced from the schema (fleet from base, single-position part, ...)
* ``ambiguous`` - several schema values fit; ``options`` lists them
* ``missing``   - not stated and not deducible

It is deterministic, offline and has no model weights, so it runs on a
flight-line tablet. A production build would put an offline speech recogniser
(e.g. IndicConformer) in front of it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from nirantar.bharat_fleet.world import World
from nirantar.saarthi import lexicon as L

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SPLIT = re.compile(r"[\s,.;:!?()\[\]{}\"'`।॥|/\\\-_+*=<>]+")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def normalise(text: str) -> str:
    """Lower-case, unify Devanagari spelling variants and digits."""
    s = unicodedata.normalize("NFC", text).lower().translate(DEVANAGARI_DIGITS)
    s = s.replace("़", "")                  # nukta: ज़ -> ज
    s = s.replace("ँ", "ं")            # chandrabindu -> anusvara
    s = s.replace("ऑ", "ओ").replace("ॉ", "ो")   # ऑ/ॉ -> ओ/ो
    s = s.replace("s/n", " sn ").replace("s / n", " sn ")
    return s


# spoken letters (NATO alphabet and letter names) -> letters, as speech recognisers write them
SPOKEN_LETTERS = {
    "alpha": "a", "alfa": "a", "bravo": "b", "charlie": "c", "delta": "d", "echo": "e", "foxtrot": "f", "golf": "g",
    "hotel": "h", "india": "i", "juliet": "j", "juliett": "j", "kilo": "k", "lima": "l", "mike": "m",
    "november": "n", "oscar": "o", "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
    "uniform": "u", "victor": "v", "whiskey": "w", "whisky": "w", "xray": "x", "x-ray": "x", "yankee": "y",
    "zulu": "z", "eff": "f", "ef": "f", "eye": "i", "aitch": "h", "ech": "h",
}


def spoken_letters(s: str) -> str:
    """'foxtrot india bravo one oh seven' -> 'f i b one zero seven' ('oh' only between number words)."""
    words = s.split(" ")
    nums = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "oh"} | set("0123456789")
    out = []
    for i, w in enumerate(words):
        if w == "oh" and ((i and words[i - 1] in nums) or (i + 1 < len(words) and words[i + 1] in nums and
                                                         i and words[i - 1] in SPOKEN_LETTERS.values())):
            out.append("zero")
        else:
            out.append(SPOKEN_LETTERS.get(w, w))
    return " ".join(out)


def tokens_of(text: str) -> list[str]:
    s = spoken_letters(normalise(text))
    # split letter/digit runs written together ("b1" is kept; "2nd" is kept; "pump2" -> "pump 2")
    s = re.sub(r"(?<=[a-z]{3})(?=\d)|(?<=\d)(?=[a-z]{3})", " ", s)
    return [t for t in _SPLIT.split(s) if t]


def _phrase_table(entries: dict[str, tuple[str, ...]]) -> list[tuple[tuple[str, ...], str]]:
    out = []
    for value, phrases in entries.items():
        for p in phrases:
            toks = tuple(tokens_of(p))
            if toks:
                out.append((toks, value))
    out.sort(key=lambda x: -len(x[0]))           # longest phrase wins
    return out


def _word_set(words) -> frozenset[str]:
    return frozenset(t for w in words for t in [" ".join(tokens_of(w))] if t)


NUMBER_WORDS = {" ".join(tokens_of(k)): v for k, v in L.NUMBER_WORDS.items()}
ORDINALS = {w: n for n, ws in L.ORDINALS.items() for w in _word_set(ws)}
SIDES = {w: n for n, ws in L.SIDES.items() for w in _word_set(ws)}
BASE_WORDS = _word_set(L.BASE_WORDS)
FLEET_WORDS = {w: f for f, ws in L.FLEET_WORDS.items() for w in _word_set(ws)}
TAIL_PREFIX = {tuple(tokens_of(w)): f for f, ws in L.TAIL_PREFIX.items() for w in ws}
TAIL_WORDS = _word_set(L.TAIL_WORDS)
NUMBER_MARKERS = _word_set(L.NUMBER_MARKERS)
CONNECTORS = _word_set(L.CONNECTORS)
POSITION_WORDS = _word_set(L.POSITION_WORDS)
ENGINE_WORDS = _word_set(L.ENGINE_WORDS)
SERIAL_WORDS = _word_set(L.SERIAL_WORDS)
NEG_BEFORE = _word_set(L.NEGATION_BEFORE)
NEG_AFTER = _word_set(L.NEGATION_AFTER)
SAMPLE_WORDS = _word_set(("sample", "samples", "सैंपल", "सेंपल", "namoona", "namuna", "नमूना"))
HINGLISH = _word_set(L.HINGLISH_MARKERS)
PART_TABLE = _phrase_table(L.PART_PHRASES)
PART_HEADS = _phrase_table(L.PART_HEADS)
MODE_TABLE = _phrase_table(L.MODE_PHRASES)
ACTION_TABLE = _phrase_table(L.ACTION_PHRASES)
ACTION_PRIORITY = ("replaced", "sent_for_repair", "removed", "rectified_in_situ", "deferred", "inspected")


@dataclass
class Field:
    value: object = None
    source: str = "missing"            # heard | inferred | ambiguous | missing
    heard: str = ""                    # the words that produced it
    options: list = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {"value": self.value, "source": self.source, "heard": self.heard,
                "options": self.options, "error": self.error}


@dataclass
class Draft:
    text: str
    lang: str
    tokens: list[str]
    fields: dict[str, Field]
    findings: list[str]
    also_mentioned: list[str]

    def as_dict(self) -> dict:
        return {"text": self.text, "lang": self.lang, "tokens": self.tokens,
                "fields": {k: v.as_dict() for k, v in self.fields.items()},
                "findings": self.findings, "also_mentioned": self.also_mentioned}


class _Cursor:
    """Tokens plus a mask of tokens already explained by some field."""

    def __init__(self, toks: list[str]):
        self.t = toks
        self.used = [False] * len(toks)

    def __len__(self) -> int:
        return len(self.t)

    def free(self, i: int) -> bool:
        return 0 <= i < len(self.t) and not self.used[i]

    def take(self, i: int, j: int) -> str:
        for k in range(i, j):
            self.used[k] = True
        return " ".join(self.t[i:j])

    def number(self, i: int, max_digits: int = 2, allow_words_above_9: bool = True) -> tuple[int | None, str, int]:
        """Read a number at i: '07', 'seven', 'zero seven', 'saat'. Returns (value, digits, end)."""
        if not self.free(i):
            return None, "", i
        tok = self.t[i]
        if tok.isdigit():
            if len(tok) > max_digits:
                return None, "", i
            return int(tok), tok, i + 1
        v = NUMBER_WORDS.get(tok)
        if v is None:
            return None, "", i
        if v > 9:
            return (v, str(v), i + 1) if allow_words_above_9 else (None, "", i)
        digits, j = str(v), i + 1
        while len(digits) < max_digits and self.free(j):
            nxt = self.t[j]
            if nxt.isdigit() and len(digits) + len(nxt) <= max_digits:
                digits, j = digits + nxt, j + 1
            elif NUMBER_WORDS.get(nxt, 99) <= 9:
                digits, j = digits + str(NUMBER_WORDS[nxt]), j + 1
            else:
                break
        return int(digits), digits, j

    def find(self, table, allowed=None) -> list[tuple[int, int, str]]:
        """Greedy longest-first phrase matches over free tokens: (start, end, value)."""
        hits, i = [], 0
        while i < len(self.t):
            match = None
            if self.free(i):
                for toks, value in table:
                    n = len(toks)
                    if (allowed is None or value in allowed) and tuple(self.t[i:i + n]) == toks \
                            and all(self.free(k) for k in range(i, i + n)):
                        match = (i, i + n, value)
                        break
            if match:
                hits.append(match)
                i = match[1]
            else:
                i += 1
        return hits


def detect_language(text: str, toks: list[str]) -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    marks = sum(t in HINGLISH for t in toks)
    return "hinglish" if marks >= 1 and marks / max(len(toks), 1) >= 0.06 else "en"


class Extractor:
    def __init__(self, world: World):
        self.w = world
        self.tail_ids = {t["id"] for t in world.tails}
        self.fleet_of_tail = {t["id"]: t["fleet"] for t in world.tails}
        self.base_fleets = {b.id: b.fleets for b in world.bases.values()}
        self.prefix = {f: f[:2].upper() for f in world.fleets}

    # ------------------------------------------------------------ fields

    def _tail(self, c: _Cursor) -> tuple[str | None, int | None, int | None]:
        """Find base + tail number (+ fleet prefix). Returns (fleet heard, base, tail number)."""
        fleet = base = num = None
        for i in range(len(c)):
            if not c.free(i):
                continue
            tok = c.t[i]
            m = re.fullmatch(r"b([1-4])(\d{1,2})?", tok)
            j = None
            if m:
                base, j = int(m.group(1)), i + 1
                if m.group(2):
                    num, j = int(m.group(2)), None
                c.take(i, i + 1)
            elif tok in BASE_WORDS:
                v, _, e = c.number(i + 1, max_digits=1, allow_words_above_9=False)
                if v is not None and 1 <= v <= 4:
                    base, j = v, e
                    c.take(i, e)
            if base is None:
                continue
            # fleet prefix spoken right before the base ("FI B1", "एफ आई बी")
            for ptoks, pf in TAIL_PREFIX.items():
                n = len(ptoks)
                if i - n >= 0 and tuple(c.t[i - n:i]) == ptoks and all(c.free(k) for k in range(i - n, i)):
                    fleet = pf
                    c.take(i - n, i)
                    break
            if j is not None:
                k = j
                while k < len(c) and k - j < 3 and c.free(k) and (c.t[k] in CONNECTORS or c.t[k] in NUMBER_MARKERS
                                                                    or c.t[k] in TAIL_WORDS):
                    k += 1
                v, _, e = c.number(k, max_digits=2)
                if v is not None:
                    num = v
                    c.take(j, e)
                    if c.free(e) and c.t[e] in NUMBER_MARKERS and c.number(e + 1)[0] is None:   # "saat number"
                        c.take(e, e + 1)
            break
        if num is None:     # "tail 7", "aircraft number 07" elsewhere in the sentence
            for i in range(len(c)):
                if c.free(i) and c.t[i] in TAIL_WORDS:
                    k = i + 1
                    while c.free(k) and c.t[k] in NUMBER_MARKERS:
                        k += 1
                    v, _, e = c.number(k, max_digits=2)
                    if v is not None:
                        num = v
                        c.take(i, e)
                        break
        if fleet is None:
            for i in range(len(c)):
                if c.free(i) and c.t[i] in FLEET_WORDS:
                    fleet = FLEET_WORDS[c.t[i]]
                    c.take(i, i + 1)
                    break
        return fleet, base, num

    def _part(self, c: _Cursor, fleet: str | None) -> tuple[list[str], str, list[str]]:
        """Part candidates (best phrase), the words heard, and other parts mentioned."""
        fleets = [fleet] if fleet else list(self.w.fleets)
        allowed = {p for p, v in self.w.pns.items() if v.fleet in fleets}
        # explicit part number ("FH HP 03")
        joined = " ".join(c.t)
        m = re.search(r"\b(fh|hu)\s*([a-z]{2})\s*0?(\d)\b", joined)
        if m:
            pn = f"{m.group(1).upper()}-{m.group(2).upper()}-0{m.group(3)}"
            if pn in allowed:
                for i, t in enumerate(c.t):
                    if t in (m.group(1), m.group(2)) and c.free(i):
                        c.take(i, i + 1)
                return [pn], m.group(0), []
        hits = c.find(PART_TABLE, allowed)
        if hits:
            s, e, _ = hits[0]
            self._part_end = e
            words = tuple(c.t[s:e])
            cands = sorted({v for toks, v in PART_TABLE if toks == words and v in allowed})
            others = [v for _, _, v in hits[1:] if v not in cands]
            return cands, c.take(s, e), sorted(set(others))
        heads = c.find(PART_HEADS)
        if heads:
            s, e, head = heads[0]
            self._part_end = e
            cands = sorted(p for p in allowed if head in self.w.pns[p].name.lower())
            return cands, c.take(s, e), []
        return [], "", []

    def _position(self, c: _Cursor, positions: int) -> tuple[int | None, str]:
        n = len(c)
        for i in range(n):                              # "position 2", "engine 2"
            if c.free(i) and (c.t[i] in POSITION_WORDS or c.t[i] in ENGINE_WORDS):
                k = i + 1
                while c.free(k) and c.t[k] in NUMBER_MARKERS:
                    k += 1
                v, _, e = c.number(k, max_digits=1)
                if v is not None:
                    return v, c.take(i, e)
        for i in range(n):                              # "number two (engine)", "no 2"
            if c.free(i) and c.t[i] in NUMBER_MARKERS:
                v, _, e = c.number(i + 1, max_digits=1)
                if v is not None:
                    if c.free(e) and c.t[e] in ENGINE_WORDS:
                        e += 1
                    return v, c.take(i, e)
        for i in range(n):                              # "do number", "two engine"
            v, _, e = c.number(i, max_digits=1)
            if v is not None and c.free(e) and ((c.t[e] in NUMBER_MARKERS and c.t[e] != "no") or c.t[e] in ENGINE_WORDS):
                return v, c.take(i, e + 1)
        for i in range(n):                              # "second", "doosra"
            if c.free(i) and c.t[i] in ORDINALS:
                return ORDINALS[c.t[i]], c.take(i, i + 1)
        end = getattr(self, "_part_end", None)          # "fuel pump 1", "hydraulic pump do"
        if end is not None:
            v, _, e = c.number(end, max_digits=1)
            if v is not None and 1 <= v <= 9:
                return v, c.take(end, e)
        if positions == 2:
            for i in range(n):                          # "left", "baayan"
                if c.free(i) and c.t[i] in SIDES:
                    return SIDES[c.t[i]], c.take(i, i + 1)
        return None, ""

    def _serial(self, c: _Cursor) -> tuple[int | None, str]:
        for i in range(len(c)):
            if c.free(i) and c.t[i] in SERIAL_WORDS:
                k = i + 1
                while c.free(k) and c.t[k] in NUMBER_MARKERS:
                    k += 1
                digits, j = "", k
                while c.free(j) and len(digits) < 6:
                    tok = c.t[j]
                    if tok.isdigit():
                        digits += tok
                    elif NUMBER_WORDS.get(tok, 99) <= 9:
                        digits += str(NUMBER_WORDS[tok])
                    else:
                        break
                    j += 1
                if digits:
                    return int(digits), c.take(i, j)
        return None, ""

    def _modes(self, c: _Cursor, family: str | None) -> tuple[list[tuple[str, str]], list[str]]:
        allowed = set(self.w.failure_modes[family]) if family else None
        found, negated = [], []
        for s, e, mode in c.find(MODE_TABLE, allowed):
            before = c.t[s - 1] if c.free(s - 1) else ""
            after = [c.t[k] for k in range(e, e + 2) if c.free(k)]
            words = c.take(s, e)
            neg_after = next((a for a in after if a in NEG_AFTER), None)
            if before in NEG_BEFORE or neg_after:
                said = f"{before} {words}" if before in NEG_BEFORE else f"{words} {neg_after}"
                negated.append(f"{L.MODE_LABELS[mode]}: negative ('{said}')")
            else:
                found.append((mode, words))
        return found, negated

    def _action(self, c: _Cursor) -> tuple[str | None, str, list[str]]:
        findings = []
        hits = []
        for s, e, act in c.find(ACTION_TABLE):
            window = c.t[max(0, s - 3):s]
            if act == "sent_for_repair" and any(w in SAMPLE_WORDS for w in window):
                findings.append("Sample sent for analysis")
                c.take(s, e)
                continue
            hits.append((act, c.take(s, e)))
        if not hits:
            return None, "", findings
        best = min(hits, key=lambda h: ACTION_PRIORITY.index(h[0]))
        return best[0], best[1], findings

    # ------------------------------------------------------------ main

    def extract(self, text: str) -> Draft:
        self._part_end = None
        toks = tokens_of(text)
        c = _Cursor(toks)
        fields: dict[str, Field] = {}
        lang = detect_language(text, toks)

        serial, serial_words = self._serial(c)
        used_before = list(c.used)
        fleet_heard, base, num = self._tail(c)
        tail_words = " ".join(t for t, u, b in zip(toks, c.used, used_before) if u and not b)

        # part (needs the fleet to disambiguate; may also tell us the fleet)
        cands, part_words, others = self._part(c, fleet_heard)
        fleet, fleet_src = fleet_heard, "heard" if fleet_heard else None
        if fleet is None and base is not None:
            fl = self.base_fleets.get(f"B{base}", ())
            if len(fl) == 1:
                fleet, fleet_src = fl[0], "inferred"
        if fleet is None and cands:
            fl = {self.w.pns[p].fleet for p in cands}
            if len(fl) == 1:
                fleet, fleet_src = fl.pop(), "inferred"
        if fleet is not None:
            cands = [p for p in cands if self.w.pns[p].fleet == fleet]

        # tail
        tf = Field(heard=tail_words)
        if base is not None and num is not None:
            fleets = [fleet] if fleet else [fl for fl in self.base_fleets.get(f"B{base}", ())]
            ids = [f"{self.prefix[fl]}-B{base}-{num:02d}" for fl in fleets]
            real = [i for i in ids if i in self.tail_ids]
            if len(real) == 1:
                tf.value, tf.source = real[0], "heard" if fleet_src == "heard" or len(fleets) == 1 else "inferred"
                fleet = self.fleet_of_tail[real[0]]
            elif len(real) > 1:
                tf.source, tf.options = "ambiguous", real
            else:
                tf.source, tf.error = "missing", f"No aircraft {ids[0] if ids else f'B{base}-{num:02d}'} in the fleet register"
        elif base is not None or num is not None:
            tf.error = "Heard part of the aircraft number; say base and number, e.g. 'FI B1 07'"
        fields["tail"] = tf

        # part
        pf = Field(heard=part_words)
        if len(cands) == 1:
            pf.value, pf.source = cands[0], "heard"
        elif len(cands) > 1:
            pf.source, pf.options = "ambiguous", cands
        fields["part"] = pf
        pn = pf.value

        # position
        pos_f = Field()
        if pn:
            npos = self.w.pns[pn].positions
            v, words = self._position(c, npos)
            if v is not None:
                pos_f.value, pos_f.source, pos_f.heard = v, "heard", words
                if not 1 <= v <= npos:
                    pos_f.error = f"{self.w.pns[pn].name} has {npos} position{'s' if npos > 1 else ''}"
                    pos_f.source = "missing"
                    pos_f.value = None
            elif npos == 1:
                pos_f.value, pos_f.source = 1, "inferred"
            pos_f.options = list(range(1, npos + 1))
        else:
            v, words = self._position(c, 2)
            if v is not None:
                pos_f.value, pos_f.source, pos_f.heard = v, "heard", words
        fields["position"] = pos_f

        # action first, so "theek kiya" (fixed it) is not read as "theek" (OK) negating a finding
        act, act_words, act_findings = self._action(c)

        # failure mode
        family = self.w.pns[pn].family if pn else None
        modes, negated = self._modes(c, family)
        mf = Field()
        if modes:
            mf.value, mf.source, mf.heard = modes[0][0], "heard", modes[0][1]
        if family:
            mf.options = list(self.w.failure_modes[family])
        fields["mode"] = mf

        af = Field(value=act or "reported", source="heard" if act else "inferred", heard=act_words,
                   options=list(L.ACTION_LABELS))
        fields["action"] = af

        sf = Field(value=serial, source="heard" if serial is not None else "missing", heard=serial_words)
        fields["serial"] = sf

        findings = negated + [f"Also reported: {L.MODE_LABELS[m]}" for m, _ in modes[1:]] + act_findings
        also = [f"{p} {self.w.pns[p].name}" for p in others]
        return Draft(text=text, lang=lang, tokens=toks, fields=fields, findings=findings, also_mentioned=also)


REQUIRED = ("tail", "part", "position", "mode", "action")


def missing_fields(fields: dict) -> list[str]:
    return [k for k in REQUIRED if fields.get(k, {}).get("value") in (None, "")]
