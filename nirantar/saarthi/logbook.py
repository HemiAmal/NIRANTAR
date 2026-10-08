"""SAARTHI for real logbook English: shorthand in, structured defect out, linked to the parts catalogue.

Technicians write (and say) things like ``#2 & 3 ROCKER COVER GASKETS LEAKING, R/H ENG.``
and ``REMOVED & REPLACED #2 INTAKE GASKET.``. This module turns a problem and
action pair into:

* **part**: the part named, as a normalised phrase (``ROCKER COVER GASKET``), and
  its candidate entries in the illustrated parts catalogue (IPC), with part numbers;
* **problem**: one category (leak, crack, loose, missing, broken, worn, ...);
* **cylinders** and **engine side** (left or right engine on a twin);
* **action**: one category (replace, tighten, repair, clean, inspect, ...).

It is rules plus vocabulary, so it runs offline, is explainable field by field,
and adapts to a fleet by loading that fleet's IPC (``Vocabulary.from_ipc``)
rather than by retraining.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).parent / "data" / "lycoming"

# shorthand seen in maintenance writing generally (not mined from the test data)
ABBREV = {
    "CYL": "CYLINDER", "CYLS": "CYLINDERS", "ENG": "ENGINE", "ENGS": "ENGINES", "ASSY": "ASSEMBLY",
    "FWD": "FORWARD", "MAG": "MAGNETO", "MAGS": "MAGNETOS", "IGN": "IGNITION", "CARB": "CARBURETOR",
    "ALT": "ALTERNATOR", "INSP": "INSPECTED", "INSPD": "INSPECTED", "CK": "CHECK", "CKD": "CHECKED",
    "CHK": "CHECK", "A/C": "AIRCRAFT", "W/": "WITH", "W/O": "WITHOUT", "@": "AT", "&": "AND", "+": "AND",
    "REPL": "REPLACED", "REPLAED": "REPLACED", "REPLCED": "REPLACED", "REPALCED": "REPLACED", "REPACED": "REPLACED",
    "INSTL": "INSTALLED", "INST": "INSTALLED", "R&R": "REMOVED AND REPLACED", "R/R": "REMOVED AND REPLACED",
    "QTY": "QUANTITY", "PRESS": "PRESSURE", "TEMP": "TEMPERATURE", "LWR": "LOWER", "UPR": "UPPER",
    "BTM": "BOTTOM", "INOP": "INOPERATIVE", "MX": "MAINTENANCE", "OVHL": "OVERHAUL", "O/H": "OVERHAUL",
    "EXH": "EXHAUST", "INT": "INTAKE", "TRANS": "TRANSMISSION", "BRKT": "BRACKET", "ACCY": "ACCESSORY",
}
SIDES = {"L/H": "L", "LH": "L", "LEFT": "L", "R/H": "R", "RH": "R", "RIGHT": "R"}
NUMBER_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}

PROBLEMS = {   # category -> words (stem forms); first match in the problem text wins
    "leak": ("LEAK", "LEAKING", "LEAKS", "LEAKED", "SEEP", "SEEPING", "SEEPS", "WEEPING", "DRIPPING", "DRIP"),
    "crack": ("CRACK", "CRACKED", "CRACKS", "CRACKING"),
    "loose": ("LOOSE", "LOOSENED", "UNSECURED"),
    "missing": ("MISSING", "LOST"),
    "broken": ("BROKEN", "BROKE", "SHEARED", "SNAPPED", "FAILED", "FAILURE"),
    "worn": ("WORN", "CHAFING", "CHAFED", "FRAYED", "TORN", "DETERIORATED", "WEAR"),
    "compression": ("COMPRESSION", "COMPRESSIONS"),
    "rough": ("ROUGH", "ROUGHNESS", "VIBRATION", "VIBRATIONS", "VIBRATING"),
    "damaged": ("DAMAGED", "DAMAGE", "BENT", "DENTED", "BURNT", "BURNED"),
    "needs work": ("NEED", "NEEDS", "REQUIRES", "REQUIRED", "DUE"),
    "dirty": ("DIRTY", "CONTAMINATED", "OILY"),
    "overspeed": ("OVERSPEED",),
    "inoperative": ("INOPERATIVE", "INOP", "DEAD", "WOULD NOT START", "WILL NOT START", "WONT START"),
}
PROBLEM_OF = {w: c for c, ws in PROBLEMS.items() for w in ws}

ACTIONS = {    # category -> phrases, longest first within the action text
    "replace": ("REMOVED AND REPLACED", "REPLACED", "INSTALLED NEW", "INSTALLED A NEW", "CHANGED", "SWAPPED"),
    "tighten": ("TIGHTENED", "RESECURED", "SECURED", "RETORQUED", "TORQUED", "STAKED", "SAFETIED"),
    "repair": ("STOP DRILLED", "REPAIRED", "FABRICATED", "PATCHED", "WELDED", "SEALED", "APPLIED", "REAMED",
               "GROUND", "LAPPED", "REWORKED"),
    "install": ("REINSTALLED", "INSTALLED"),
    "remove": ("REMOVED",),
    "clean": ("CLEANED", "FLUSHED", "WASHED"),
    "adjust": ("ADJUSTED", "SET", "RESET", "REPOSITIONED", "ALIGNED", "TIMED"),
    "inspect": ("INSPECTED", "LEAK CHECK", "CHECKED", "RAN UP", "RAN", "PERFORMED", "TESTED", "VERIFIED",
                "FOUND", "STARTED", "COMPLETED", "CONTINUED", "TROUBLESHOT"),
}
ACTION_ORDER = [(p, c) for c, ps in ACTIONS.items() for p in ps]
ACTION_ORDER.sort(key=lambda x: -len(x[0]))
ACTION_RANK = {c: i for i, c in enumerate(("replace", "repair", "tighten", "install", "remove", "clean", "adjust",
                                           "inspect"))}            # the main corrective action when several appear

# a small general glossary of airframe/engine part words (heads) and qualifiers; the IPC adds the rest
GLOSSARY_HEADS = """GASKET GASKETS SEAL SEALS PLUG PLUGS SCREW SCREWS BOLT BOLTS NUT NUTS STUD STUDS WASHER WASHERS CLAMP
CLAMPS HOSE HOSES LINE LINES TUBE TUBES PIPE VALVE VALVES SPRING BRACKET BRACKETS BAFFLE BAFFLES BAFFLING COVER COVERS
CYLINDER CYLINDERS ENGINE MAGNETO MAGNETOS ALTERNATOR STARTER PROPELLER SPINNER COWLING COWL FILTER PUMP SERVO
CARBURETOR MUFFLER LEAD LEADS HARNESS WIRE WIRES CABLE CABLES BELT ROD RODS RIVET RIVETS SHROUD SHROUDS COOLER
INTAKE INTAKES EXHAUST DIPSTICK GAUGE SENSOR PROBE CAP FITTING FITTINGS GUIDE RING RINGS BEARING BUSHING LACING
MATERIAL PATCH PATCHES STACK MOUNT MOUNTS SCAT TUBING BOX""".split()
GLOSSARY_QUALIFIERS = """ROCKER INDUCTION INTAKE EXHAUST OIL FUEL PUSH TIE ANCHOR SPARK IGNITION FORWARD AFT REAR FRONT UPPER
LOWER SIDE CENTER INNER OUTER ENGINE BAFFLE COOLER BOX COVER TUBE VALVE CYLINDER DRAIN BREATHER PRESSURE
TEMPERATURE PRIMER MIXTURE THROTTLE CONTROL HEAT SCREEN STANDBY SUPPORT""".split()
SKIP = {"THE", "A", "AN", "OF", "ON", "IN", "TO", "FROM", "AT", "AND", "IS", "ARE", "WAS", "HAS", "HAVE", "BY", "FOR",
        "WITH", "ALL", "BOTH", "NEW", "#", ","}


def singular(w: str) -> str:
    if len(w) > 3 and w.endswith("ES") and w[:-2].endswith(("SH", "CH", "SS", "X")):
        return w[:-2]
    if len(w) > 3 and w.endswith("S") and not w.endswith("SS"):
        return w[:-1]
    return w


def normalise_part(phrase: str | None) -> str:
    if not phrase or phrase != phrase:
        return ""
    words = [ABBREV.get(w, w) for w in re.findall(r"[A-Z0-9/&#]+", str(phrase).upper())]
    words = [singular(w) for w in " ".join(words).split() if w not in SKIP and not w.startswith("#")]
    words = ["BAFFLE" if w == "BAFFLING" else w for w in words]
    return " ".join(words)


def tokens(text: str) -> list[str]:
    t = str(text or "").upper().replace("R & R", "R&R").replace("R/&R", "R&R")
    t = re.sub(r"#\s+(\d)", r"#\1", t)
    raw = re.findall(r"R&R|R/R|[LR]/H|A/C|W/O|W/|O/H|#\d+|\d+(?:\.\d+)?|[A-Z][A-Z'\-]*|&|@|\+|,", t)
    out = []
    for w in raw:
        out.extend(ABBREV.get(w, w).split())
    return out


# what technicians say -> what the catalogue calls it (per fleet; extend with the fleet's own usage)
SYNONYMS = {"PUSH ROD TUBE": "SHROUD TUBE", "ROCKER BOX COVER": "ROCKER COVER", "VALVE COVER": "ROCKER COVER",
            "INTAKE": "INTAKE PIPE", "INTAKE TUBE": "INTAKE PIPE", "INDUCTION TUBE": "INTAKE PIPE", "MAG": "MAGNETO",
            "SPARK PLUG LEAD": "IGNITION CABLE", "PLUG LEAD": "IGNITION CABLE"}


def _type_words(typ: str) -> list[str]:
    w = typ.split()
    while len(w) > 1 and w[-1] in ("ASSEMBLY", "ASSY"):
        w = w[:-1]
    return w


@dataclass
class Vocabulary:
    heads: set[str]
    qualifiers: set[str]
    ipc: list[dict] = field(default_factory=list)
    synonyms: dict[str, str] = field(default_factory=lambda: dict(SYNONYMS))

    @classmethod
    def from_ipc(cls, path: str | Path = DATA / "ipc.csv", extra_parts: list[str] | None = None) -> "Vocabulary":
        """Part words from the fleet's illustrated parts catalogue, a small general glossary, and optionally
        part names from labelled examples (``extra_parts``)."""
        heads, quals = set(GLOSSARY_HEADS), set(GLOSSARY_QUALIFIERS)
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                typ = normalise_part(r.get("Type", ""))
                words = _type_words(typ)
                if words and not any(ch.isdigit() for ch in typ):
                    heads.add(words[-1])
                    quals.update(words[:-1])
                fig = normalise_part(r.get("Figure", ""))
                quals.update(w for w in fig.split() if w.isalpha() and len(w) > 2)
                rows.append({"pn": r.get("Part Number", "").strip(), "type": typ, "figure": r.get("Figure", "").strip(),
                             "section": r.get("Section", "").strip(), "specifics": (r.get("Specifics") or "").strip(),
                             "words": set(fig.split()) | set(normalise_part(r.get("Specifics", "")).split())
                             | set(normalise_part(r.get("Section", "")).split())})
        for p in extra_parts or []:
            ws = normalise_part(p).split()
            if ws:
                heads.add(ws[-1])
                quals.update(ws[:-1])
        heads |= {h + "S" for h in list(heads)}
        return cls(heads, quals - SKIP, rows)

    def link(self, part: str, k: int = 3) -> list[dict]:
        """Candidate IPC entries for a part phrase: the same part type (if the catalogue has it), ranked by
        assembly and description words shared; only candidates close to the best are offered."""
        for said, cat in sorted(self.synonyms.items(), key=lambda x: -len(x[0])):
            if f" {said} " in f" {part} ":
                part = f" {part} ".replace(f" {said} ", f" {cat} ").strip()
                break
        words = part.split()
        if not words or not self.ipc or words == ["ENGINE"]:
            return []                                   # the whole engine is not a catalogue line
        head = words[-1]
        quals = set(words[:-1]) - GENERIC - POSITION    # too common to tell catalogue lines apart
        same_type = [r for r in self.ipc if _type_words(r["type"])[-1:] == [head]]
        pool = same_type or self.ipc
        scored = []
        for r in pool:
            tw = _type_words(r["type"])
            shared = len(quals & (r["words"] | set(tw)))
            score = (3.0 if same_type else 0.0) + shared
            # same type: needs a shared qualifier when the phrase has one (a 'baffle screw' is not any screw);
            # a different type only on strong evidence; otherwise no guess
            if (same_type and (shared >= 1 or not quals)) or (not same_type and shared >= 2):
                scored.append((score, r))
        if not scored:
            return []
        if not quals and len({r["figure"] for _, r in scored}) > 1:
            return []                                   # a bare 'clamp' or 'valve': ask which one, do not guess
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        return [{"pn": r["pn"], "type": r["type"], "assembly": r["figure"], "specifics": r["specifics"],
                 "score": sc} for sc, r in scored[:k] if sc >= best - 0.5]


CYL_ANCHORS = {"CYLINDER", "CYLINDERS", "INTAKE", "INTAKES"}


def _cylinders(tok: list[str]) -> list[int]:
    """Cylinder numbers: '#2, 3 & 4', 'CYL #2', 'INTAKES 2 & 4', 'ALL 4 ...', 'ALL CYLS'."""
    cyl: set[int] = set()
    n = len(tok)
    i = 0
    while i < n:
        t = tok[i]
        start = None
        if t.startswith("#") and t[1:].isdigit():
            start = i
        elif t in CYL_ANCHORS and i + 1 < n and tok[i + 1].lstrip("#").isdigit():
            start = i + 1
        if start is not None:
            j, got = start, []
            while j < n:
                v = tok[j].lstrip("#")
                if v.isdigit():
                    if not 1 <= int(v) <= 6 or (j + 1 < n and tok[j + 1] in ("PSI",)):
                        break
                    got.append(int(v))
                    j += 1
                elif tok[j] in (",", "AND") and j + 1 < n and tok[j + 1].lstrip("#").isdigit():
                    j += 1
                else:
                    break
            cyl.update(got)
            i = max(j, i + 1)
            continue
        if t == "ALL" and i + 1 < n and (tok[i + 1] in ("4", "FOUR", "CYLINDERS", "CYLINDER")):
            cyl.update(range(1, 5))
        i += 1
    return sorted(cyl)


def _side(tok: list[str], loose: bool = False) -> str | None:
    """Left or right engine: 'R/H ENG', 'ENGINE R/H', 'RIGHT ENGINE'; with ``loose``, any L/H or R/H (on a twin
    the hand nearly always names the engine)."""
    for i, t in enumerate(tok):
        if t in SIDES and ("ENGINE" in tok[i + 1:i + 3] or "ENGINES" in tok[i + 1:i + 3]):
            return SIDES[t]
        if t == "ENGINE" and i + 1 < len(tok) and tok[i + 1] in ("L/H", "R/H", "LH", "RH"):
            return SIDES[tok[i + 1]]
    if loose:
        for t in tok:
            if t in ("L/H", "R/H", "LH", "RH"):
                return SIDES[t]
    return None


def _problem(tok: list[str]) -> str | None:
    text = " " + " ".join(tok) + " "
    for c, ws in PROBLEMS.items():
        for w in ws:
            if " " in w and f" {w} " in text:
                return c
    for i, t in enumerate(tok):
        c = PROBLEM_OF.get(t)
        if c is None and i == len(tok) - 1 and len(t) >= 5:      # the source truncates entries mid-word
            c = next((PROBLEM_OF[w] for w in PROBLEM_OF if w.startswith(t)), None)
        if c:
            return c
        if t == "OIL" and i + 1 < len(tok) and tok[i + 1] in ("ON", "AROUND", "COMING", "SPRAY"):
            return "leak"
    return None


def _action(text: str) -> str | None:
    t = " " + " ".join(tokens(text)) + " "
    found = [c for p, c in ACTION_ORDER if f" {p} " in t]
    return min(found, key=lambda c: ACTION_RANK[c]) if found else None


GENERIC = {"ENGINE", "ENGINES", "CYLINDER", "CYLINDERS"}
POSITION = {"AFT", "FORWARD", "REAR", "FRONT", "UPPER", "LOWER", "SIDE", "CENTER", "INNER", "OUTER", "TOP", "BOTTOM",
            "LEFT", "RIGHT"}


def _part(tok: list[str], vocab: Vocabulary) -> str:
    runs, cur = [], []
    for t in tok + ["."]:
        if t in vocab.heads or t in vocab.qualifiers:
            cur.append(t)
        else:
            if cur:
                runs.append(cur)
            cur = []
    cands = []
    for r in runs:
        while r and r[-1] not in vocab.heads:                       # end on a part noun
            r = r[:-1]
        while len(r) > 1 and r[-1] in GENERIC and any(w in vocab.heads for w in r[:-1] if w not in GENERIC):
            r = r[:-1]                                              # 'INTAKE GASKET CYL' -> 'INTAKE GASKET'
            while r and r[-1] not in vocab.heads:
                r = r[:-1]
        while len(r) > 1 and (r[0] in POSITION or (r[0] in ("CYLINDER", "CYLINDERS") and r[1] not in GENERIC)):
            r = r[1:]                                               # 'CYL AFT BAFFLE' -> 'BAFFLE'
        if r:
            cands.append(r)
    specific = [r for r in cands if not set(r) <= GENERIC]
    best = (specific or cands or [None])[0]
    return normalise_part(" ".join(best)) if best else ""


@dataclass
class LogEntry:
    part: str
    problem: str | None
    cylinders: list[int]
    engine: str | None
    action: str | None
    ipc: list[dict]
    action_part: str


def extract(problem: str, action: str, vocab: Vocabulary) -> LogEntry:
    ptok = tokens(problem)
    atok = tokens(action)
    part = _part(ptok, vocab)
    apart = _part(atok, vocab)
    return LogEntry(part=part, problem=_problem(ptok), cylinders=_cylinders(ptok),
                    engine=_side(ptok) or _side(atok) or _side(ptok, loose=True), action=_action(action),
                    ipc=vocab.link(part or apart), action_part=apart)


def problem_category(word) -> str | None:
    if not word or word != word:
        return None
    for w in tokens(word):
        if w in PROBLEM_OF:
            return PROBLEM_OF[w]
    return None


def action_category(label, text: str) -> str | None:
    """The reference labels name the first verb only ('REMOVED' for 'REMOVED & REPLACED'); read it in its text."""
    if not label or label != label:
        return None
    lab = " ".join(tokens(label))
    if lab == "REMOVED" and "REPLACED" in " ".join(tokens(text)):
        return "replace"
    if lab == "INSTALLED" and "NEW" in " ".join(tokens(text)).split():
        return "replace"
    for p, c in ACTION_ORDER:
        if f" {p} " in f" {lab} ":
            return c
    return None


def counts(entries) -> Counter:
    return Counter(e.problem for e in entries)
