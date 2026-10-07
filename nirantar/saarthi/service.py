"""SAARTHI desk: checks a draft snag against the fleet records, then signs it into the ledger.

The fleet state (what is fitted where, what is in stores) starts from the
records and is rolled forward by every confirmed entry, including entries
already in the ledger from earlier sessions, so the checks stay consistent
across restarts.
"""
from __future__ import annotations

import copy

import pandas as pd

from nirantar.bharat_fleet.world import World
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.saarthi import lexicon as L
from nirantar.saarthi.extract import Extractor, missing_fields

EXTRACTOR_VERSION = "saarthi-lexicon/1"
REMOVES_UNIT = ("replaced", "removed", "sent_for_repair")
ENV_LABELS = {"coastal_saline": "coastal saline", "desert_dust": "desert dust",
              "high_altitude": "high altitude", "humid_ne": "humid north-east"}


class SaarthiDesk:
    def __init__(self, world: World, snapshot: dict, frailty: pd.DataFrame, rogue_flags: set[int],
                 signal_table: list[dict], ledger: Ledger, signer: Signer, day: int = 0):
        self.w = world
        self.x = Extractor(world)
        self.installed = copy.deepcopy(snapshot["installed"])          # tail -> {(pn, slot): serial}
        self.stock = {k: list(v) for k, v in snapshot["stock"].items()}  # (base, pn) -> [serial]
        self.tails = {t["id"]: t for t in world.tails}
        self.ledger, self.signer = ledger, signer
        self.rogues = set(rogue_flags)
        fr = frailty.set_index("serial") if len(frailty) else frailty
        self.p_rogue = {int(s): (float(r["p_rogue"]), int(r["n_fail"])) for s, r in fr.iterrows()} if len(fr) else {}
        self.signals = {(r["family"], r["env"], r["mode"]): r for r in signal_table}
        self.day = day
        self.entries: list[dict] = []
        for e in ledger.entries:                     # roll today's state forward from earlier sessions
            if e["kind"] == "snag_entry" and e["payload"].get("day", 0) == day:
                self._apply(e["payload"])
                self.entries.append(self._summary(e))

    # ------------------------------------------------------------ lookups

    def _where(self, serial: int) -> str | None:
        for tail, slots in self.installed.items():
            for (pn, k), sid in slots.items():
                if sid == serial:
                    return f"fitted to {tail}, {pn} position {k + 1}"
        for (base, pn), sids in self.stock.items():
            if serial in sids:
                return f"in stores at {base} ({pn})"
        return None

    def options(self) -> dict:
        return {
            "tails": [{"id": t["id"], "fleet": t["fleet"], "base": t["base"]} for t in self.w.tails],
            "parts": [{"pn": p.pn, "name": p.name, "fleet": p.fleet, "family": p.family, "positions": p.positions}
                      for p in self.w.pns.values()],
            "modes": {fam: [{"id": m, "label": L.MODE_LABELS[m]} for m in modes]
                      for fam, modes in self.w.failure_modes.items()},
            "actions": [{"id": k, "label": v} for k, v in L.ACTION_LABELS.items()],
            "fleets": {f.id: f.role for f in self.w.fleets.values()},
        }

    # ------------------------------------------------------------ parse + check

    def parse(self, text: str) -> dict:
        text = str(text)[:500]
        draft = self.x.extract(text).as_dict()
        fields = {k: v["value"] for k, v in draft["fields"].items()}
        return {"draft": draft, **self.check(fields, draft["findings"])}

    def _clean_fields(self, fields: dict) -> dict:
        if not isinstance(fields, dict):
            raise ValueError("fields must be an object")
        out = {}
        tail = fields.get("tail")
        out["tail"] = tail if tail in self.tails else None
        pn = fields.get("part")
        out["part"] = pn if pn in self.w.pns else None
        try:
            out["position"] = int(fields["position"]) if fields.get("position") not in (None, "") else None
        except (TypeError, ValueError):
            out["position"] = None
        mode = fields.get("mode")
        out["mode"] = mode if mode in L.MODE_LABELS else None
        act = fields.get("action") or "reported"
        out["action"] = act if act in L.ACTION_LABELS else "reported"
        out["serial"] = self.w.serial_from_plate(fields.get("serial"))
        return out

    def check(self, fields: dict, findings: list[str] | None = None) -> dict:
        """Checks for the form; serial numbers go out as people know them."""
        res = self._check(fields, findings)
        res["fields"] = {**res["fields"], "serial": self._sn(res["fields"]["serial"])}
        res["serial_on_record"] = self._sn(res["serial_on_record"])
        return res

    def _sn(self, sid: int | None) -> str | None:
        return None if sid is None else self.w.sn(sid)

    def _check(self, fields: dict, findings: list[str] | None = None) -> dict:
        f = self._clean_fields(fields)
        checks: list[dict] = []

        def add(cid, status, title, detail=""):
            checks.append({"id": cid, "status": status, "title": title, "detail": detail})

        tail = self.tails.get(f["tail"]) if f["tail"] else None
        part = self.w.pns.get(f["part"]) if f["part"] else None
        if tail:
            env = self.w.base_env(tail["base"])
            add("aircraft", "good", f"{tail['id']} is on the register",
                f"{self.w.fleets[tail['fleet']].role}, base {tail['base']} ({ENV_LABELS.get(env, env)})")
        if part and tail and part.fleet != tail["fleet"]:
            add("part", "critical", f"{part.pn} is not fitted to {tail['fleet']}",
                "Choose a part from this aircraft type")
            part = None
            f["part"] = None
        elif part:
            add("part", "good", f"{part.pn} {part.name}", f"{part.positions} position(s) per aircraft")
        if part and f["position"] is not None and not 1 <= f["position"] <= part.positions:
            add("position", "critical", f"Position {f['position']} does not exist",
                f"{part.name} has {part.positions} position(s)")
            f["position"] = None
        inferred = []
        if part and part.positions == 1 and f["position"] is None:
            f["position"] = 1
        if tail and part and f["position"] is None and f["serial"] is not None:
            for (pn, k), sid in self.installed.get(tail["id"], {}).items():
                if pn == part.pn and sid == f["serial"]:
                    f["position"] = k + 1
                    inferred.append("position")
                    add("position", "info", f"Position {k + 1} taken from S/N {self.w.sn(sid)}", "The records place it there")
        if f["mode"] and part and f["mode"] not in self.w.failure_modes[part.family]:
            add("mode", "critical", f"'{L.MODE_LABELS[f['mode']]}' is not a recorded failure mode of a {part.family} part",
                "Pick one of the listed modes")
            f["mode"] = None

        on_record = None
        if tail and part and f["position"]:
            slot = (part.pn, f["position"] - 1)
            on_record = self.installed.get(tail["id"], {}).get(slot)
            spoken = f["serial"]
            if spoken is not None:
                if spoken == on_record:
                    add("serial", "good", f"S/N {self.w.sn(spoken)} matches the records")
                else:
                    where = self._where(spoken)
                    rec = f"records show S/N {self.w.sn(on_record)} here" if on_record is not None else "records show this position empty"
                    if where and where.startswith("fitted"):
                        add("serial", "critical", f"S/N {self.w.sn(spoken)} is already {where}",
                            f"One unit cannot be fitted twice; {rec}. Read the data plate again.")
                    else:
                        add("serial", "warning", f"S/N {self.w.sn(spoken)} differs from the records",
                            f"{rec}{'; S/N ' + self.w.sn(spoken) + ' is ' + where if where else ''}. "
                            "If the plate is right, the records need correcting (SATYA will raise it).")
            elif on_record is not None:
                add("serial", "info", f"S/N {self.w.sn(on_record)} taken from the records",
                    "Scan or read the data plate to confirm")
            else:
                add("serial", "warning", "Records show this position empty (awaiting a spare)")

            unit = spoken if spoken is not None else on_record
            if unit is not None:
                if unit in self.rogues:
                    p, n = self.p_rogue.get(unit, (1.0, 0))
                    add("rogue", "warning", f"S/N {self.w.sn(unit)} is on the rogue-unit watchlist",
                        f"{n} failures on record, rogue probability {p:.2f}. Route it to the agency with the best "
                        "repair quality and keep it out of the AOG pool.")
                elif self.p_rogue.get(unit, (0, 0))[0] >= 0.3:
                    p, n = self.p_rogue[unit]
                    add("rogue", "info", f"S/N {self.w.sn(unit)} is failing more often than its peers",
                        f"{n} failures on record, rogue probability {p:.2f}")

        if tail and part and f["mode"]:
            env = self.w.base_env(tail["base"])
            sig = self.signals.get((part.family, env, f["mode"]))
            if sig and sig.get("signal"):
                add("signal", "info", "Matches a confirmed fleet signal",
                    f"{part.family} {L.MODE_LABELS[f['mode']].lower()} in {ENV_LABELS.get(env, env)}: "
                    f"{sig['rate_ratio']:.1f}x the fleet rate per flight hour. This report adds evidence.")
            elif sig and sig.get("candidate"):
                add("signal", "info", "Matches a pattern under watch",
                    f"{part.family} {L.MODE_LABELS[f['mode']].lower()} in {ENV_LABELS.get(env, env)} is a candidate signal")

        if tail and part and f["action"] in REMOVES_UNIT:
            here = len(self.stock.get((tail["base"], part.pn), []))
            if f["action"] == "replaced" and here:
                add("spares", "good", f"{here} serviceable {part.name.lower()}(s) in stores at {tail['base']}",
                    "One will be issued and fitted")
            elif here:
                add("spares", "info", f"{here} serviceable in stores at {tail['base']}",
                    "Fit one to return the aircraft to service")
            else:
                other = sorted(((len(v), b) for (b, pn), v in self.stock.items() if pn == part.pn and v and b != tail["base"]),
                               reverse=True)
                where = ", ".join(f"{b} ({n})" for n, b in other[:3])
                add("spares", "warning", f"No serviceable {part.name.lower()} at {tail['base']}",
                    f"Lateral transfer possible from {where}" if where else
                    "None in any stores: the aircraft stays down until a repaired unit returns")

        if f["action"] == "deferred":
            add("deferral", "warning", "Deferral needs supervisor authorisation",
                "SAARTHI records the technician's entry only; it never relaxes a safety margin")

        if tail and part and f["mode"]:
            for e in self.entries[-50:]:
                if (e["tail"], e["pn"], e["position"], e["mode"]) == (tail["id"], part.pn, f["position"], f["mode"]):
                    add("duplicate", "warning", f"Possible duplicate of entry #{e['seq']}",
                        "Same aircraft, part, position and finding already logged")
                    break

        need = missing_fields({k: {"value": v} for k, v in f.items()})
        if need:
            add("missing", "critical", "Still needed: " + ", ".join(need))
        ready = not need and not any(c["status"] == "critical" for c in checks)
        return {"fields": f, "inferred": inferred, "serial_on_record": on_record, "checks": checks, "ready": ready,
                "readback": self.readback(f), "findings": findings or []}

    def readback(self, f: dict) -> dict:
        tail = f.get("tail") or "Aircraft not given"
        part = self.w.pns[f["part"]].name if f.get("part") else "Part not given"
        pos = f" position {f['position']}" if f.get("position") and f.get("part") and \
            self.w.pns[f["part"]].positions > 1 else ""
        mode = L.MODE_LABELS.get(f.get("mode"), "Finding not given")
        act = f.get("action") or "reported"
        en = f"{tail}. {part}{pos}. {mode}. {L.ACTION_LABELS[act]}. Confirm?"
        hing = f"{tail}, {part}{(' number ' + str(f['position'])) if pos else ''}, {mode.lower()}, " \
               f"{L.ACTION_HINGLISH[act]}. Sahi hai?"
        return {"en": en, "hinglish": hing}

    # ------------------------------------------------------------ confirm

    def _apply(self, p: dict) -> None:
        slot = (p["pn"], int(p["position"]) - 1)
        inst = self.installed.setdefault(p["tail"], {})
        # recorded serials are the durable identity; planning ids can change when records are re-imported
        removed = self.w.serial_from_plate(p["removed_sn"]) if p.get("removed_sn") else p.get("removed_serial")
        new = self.w.serial_from_plate(p["installed_sn"]) if p.get("installed_sn") else p.get("installed_serial")
        if removed is not None and inst.get(slot) == removed:
            inst.pop(slot, None)
        if new is not None:
            sids = self.stock.get((p["base"], p["pn"]), [])
            if new in sids:
                sids.remove(new)
            inst[slot] = new

    @staticmethod
    def _summary(e: dict) -> dict:
        p = e["payload"]
        return {"seq": e["seq"], "hash": e["entry_hash"][:16], "ts": e["ts"], "tail": p["tail"], "pn": p["pn"],
                "part": p["part"], "position": p["position"], "mode": p["mode"], "action": p["action"],
                "removed_serial": p.get("removed_sn", p.get("removed_serial")),
                "installed_serial": p.get("installed_sn", p.get("installed_serial")),
                "lang": p.get("lang"), "input": p.get("input"), "entry_seconds": p.get("entry_seconds"),
                "edited_fields": p.get("edited_fields", [])}

    def confirm(self, body: dict, signer: Signer | None = None) -> dict:
        """Sign the entry: with the logged-in user's key when given, else the desk's."""
        res = self._check(body.get("fields", {}), body.get("findings"))
        if not res["ready"]:
            raise ValueError("entry is not ready: " + "; ".join(c["title"] for c in res["checks"]
                                                                 if c["status"] == "critical"))
        f = res["fields"]
        tail = self.tails[f["tail"]]
        part = self.w.pns[f["part"]]
        on_record = res["serial_on_record"]
        unit = f["serial"] if f["serial"] is not None else on_record
        removed = installed = None
        if f["action"] in REMOVES_UNIT and unit is not None and unit == on_record:
            removed = unit
            if f["action"] == "replaced":
                sids = self.stock.get((tail["base"], part.pn), [])
                installed = sids[0] if sids else None
        try:
            secs = round(float(body.get("entry_seconds")), 1) if body.get("entry_seconds") is not None else None
        except (TypeError, ValueError):
            secs = None
        payload = {
            "tail": tail["id"], "fleet": tail["fleet"], "base": tail["base"], "env": self.w.base_env(tail["base"]),
            "pn": part.pn, "part": part.name, "position": f["position"], "mode": f["mode"], "action": f["action"],
            "serial_reported": self._sn(f["serial"]), "serial_on_record": self._sn(on_record),
            "removed_serial": removed, "installed_serial": installed,
            "removed_sn": self._sn(removed), "installed_sn": self._sn(installed),
            "findings": [str(x)[:120] for x in (body.get("findings") or [])][:8],
            "transcript": str(body.get("transcript", ""))[:500],
            "lang": str(body.get("lang", ""))[:12], "input": "voice" if body.get("input") == "voice" else "typed",
            "entry_seconds": secs,
            "edited_fields": [str(x)[:16] for x in (body.get("edited_fields") or [])][:8],
            "checks": [{"id": c["id"], "status": c["status"]} for c in res["checks"]],
            "extractor": EXTRACTOR_VERSION, "day": self.day,
        }
        e = self.ledger.append("snag_entry", payload, signer or self.signer)
        self._apply(payload)
        summary = self._summary(e)
        self.entries.append(summary)
        return summary

    def stats(self) -> dict:
        n = len(self.entries)
        secs = sorted(e["entry_seconds"] for e in self.entries if e.get("entry_seconds") is not None)
        edited = sum(1 for e in self.entries if e.get("edited_fields"))
        return {"entries": n, "median_seconds": secs[len(secs) // 2] if secs else None,
                "voice": sum(1 for e in self.entries if e.get("input") == "voice"),
                "hands_free": n - edited}
