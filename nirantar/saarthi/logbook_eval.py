"""Score the logbook extractor on real entries against the GPT-4o silver reference (held-out split)."""
from __future__ import annotations

import ast
import hashlib
import random
from collections import Counter

import pandas as pd

from nirantar.saarthi import logbook as LB

SEEN_DURING_DESIGN = 60          # entries read while writing the rules (random_state=1 sample); kept out of the test


def _split(ident: int) -> str:
    return "dev" if int(hashlib.sha256(str(ident).encode()).hexdigest(), 16) % 10 < 3 else "test"


def _side(v) -> str | None:
    v = str(v).upper().strip() if v == v and v is not None else ""
    if v in ("R", "R/H", "RH", "RIGHT", "RIGHT ENGINE"):
        return "R"
    if v in ("L", "L/H", "LH", "LEFT", "LEFT ENGINE"):
        return "L"
    return None if v == "" else "other"


def _cyl(v) -> list[int]:
    if v != v or v is None or str(v).strip() == "":
        return []
    try:
        x = ast.literal_eval(str(v))
        return sorted(int(i) for i in (x if isinstance(x, (list, tuple)) else [x]))
    except (ValueError, SyntaxError):
        return []


def load():
    d = LB.DATA
    log = pd.read_csv(d / "logbook.csv", encoding="utf-8-sig")
    rp = pd.read_csv(d / "reference_problems_gpt4o.csv").drop_duplicates("id").set_index("id")
    ra = pd.read_csv(d / "reference_actions_gpt4o.csv").drop_duplicates("id").set_index("id")
    log["split"] = log["IDENT"].map(_split)
    seen = set(log.sample(SEEN_DURING_DESIGN, random_state=1)["IDENT"])
    log.loc[log["IDENT"].isin(seen), "split"] = "seen"
    return log, rp, ra


def evaluate(samples: int = 0, seed: int = 0, split: str = "test") -> dict:
    """Agreement with the silver reference on the held-out ``test`` split (``dev`` for development)."""
    log, rp, ra = load()
    dev_ids = set(log[log["split"] == "dev"]["IDENT"])
    dev_parts = [p for i, p in rp["part"].dropna().items() if i in dev_ids]
    common = [p for p, n in Counter(LB.normalise_part(p) for p in dev_parts).items() if n >= 2 and p]
    vocab = LB.Vocabulary.from_ipc(extra_parts=common)
    vocab_ipc_only = LB.Vocabulary.from_ipc()
    rows = []
    for r in log[log["split"] == split].itertuples():
        e = LB.extract(r.PROBLEM, r.ACTION, vocab)
        e0 = LB.extract(r.PROBLEM, r.ACTION, vocab_ipc_only)
        p = rp.loc[r.IDENT] if r.IDENT in rp.index else None
        a = ra.loc[r.IDENT] if r.IDENT in ra.index else None
        ref_part = LB.normalise_part(p["part"]) if p is not None else ""
        rows.append({
            "id": r.IDENT, "problem_text": r.PROBLEM, "action_text": r.ACTION,
            "part": e.part, "part_ipc_only": e0.part, "ref_part": ref_part,
            "problem": e.problem, "ref_problem": LB.problem_category(p["problem"]) if p is not None else None,
            "cyl": e.cylinders, "ref_cyl": _cyl(p["cylinders"]) if p is not None else [],
            "engine": e.engine, "ref_engine": _side(p["engine"]) if p is not None else None,
            "action": e.action, "ref_action": LB.action_category(a["action"], r.ACTION) if a is not None else None,
            "ipc_top": e.ipc[0]["pn"] if e.ipc else None, "has_ref": p is not None,
        })
    df = pd.DataFrame(rows)
    ref = df[df["has_ref"]]

    def rate(mask, ok) -> dict:
        m = ref[mask]
        return {"n": int(len(m)), "agree": round(float(pd.Series(ok(m)).mean()), 3) if len(m) else None}

    head = lambda s: s.split()[-1] if s else ""
    jac = lambda a, b: len(set(a.split()) & set(b.split())) / max(len(set(a.split()) | set(b.split())), 1)
    out = {
        "test_entries": int(len(df)), "with_reference": int(len(ref)), "dev_entries": int((log["split"] == "dev").sum()),
        "vocabulary": {"heads": len(vocab.heads), "qualifiers": len(vocab.qualifiers),
                       "part_names_from_dev": len(common), "ipc_rows": len(vocab.ipc)},
        "part_exact": rate(ref["ref_part"] != "", lambda m: m["part"] == m["ref_part"]),
        "part_same_head_noun": rate(ref["ref_part"] != "", lambda m: m["part"].map(head) == m["ref_part"].map(head)),
        "part_overlap_half": rate(ref["ref_part"] != "", lambda m: [jac(a, b) >= 0.5 for a, b in zip(m["part"], m["ref_part"])]),
        "part_exact_ipc_vocabulary_only": rate(ref["ref_part"] != "", lambda m: m["part_ipc_only"] == m["ref_part"]),
        "problem": rate(ref["ref_problem"].notna(), lambda m: m["problem"] == m["ref_problem"]),
        "cylinders": rate(ref["ref_engine"] != "other", lambda m: m["cyl"].map(tuple) == m["ref_cyl"].map(tuple)),
        "engine_side": rate(ref["ref_engine"] != "other", lambda m: m["engine"].fillna("-") == m["ref_engine"].fillna("-")),
        "action": rate(ref["ref_action"].notna(), lambda m: m["action"] == m["ref_action"]),
        "linked_to_ipc": round(float(df["ipc_top"].notna().mean()), 3),
        "coverage": {"part": round(float((df["part"] != "").mean()), 3), "problem": round(float(df["problem"].notna().mean()), 3),
                     "action": round(float(df["action"].notna().mean()), 3)},
    }
    if samples:
        rng = random.Random(seed)
        dis = {}
        for f, (a, b) in {"part": ("part", "ref_part"), "problem": ("problem", "ref_problem"), "cyl": ("cyl", "ref_cyl"),
                          "engine": ("engine", "ref_engine"), "action": ("action", "ref_action")}.items():
            m = ref[[str(x) != str(y) for x, y in zip(ref[a], ref[b])]]
            idx = list(m.index)
            rng.shuffle(idx)
            dis[f] = m.loc[idx[:samples], ["id", "problem_text", "action_text", a, b]].to_dict("records")
        out["disagreements"] = dis
    return out
