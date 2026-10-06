"""Command line: python -m nirantar demo [--quick] [--out DIR] | serve [--port 8050] | plan | saarthi-eval"""
from __future__ import annotations

import argparse

from nirantar.pipeline import Config, run


def main() -> None:
    ap = argparse.ArgumentParser(prog="nirantar", description="NIRANTAR Milestone-1 engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the full pipeline on BHARAT-FLEET synthetic data")
    d.add_argument("--quick", action="store_true", help="fewer seeds and shorter history (about a minute)")
    d.add_argument("--out", default="experiments/results")
    d.add_argument("--seeds", type=int, default=None, help="ensemble seeds per policy arm")
    sv = sub.add_parser("serve", help="open the web console on the latest results")
    sv.add_argument("--results", default="experiments/results")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8050)
    pl = sub.add_parser("plan", help="prepare today's decision-desk plan (signed into the ledger)")
    pl.add_argument("--results", default="experiments/results")
    pl.add_argument("--workers", type=int, default=None, help="processes for pricing (default: CPU count, max 8)")
    ex = sub.add_parser("export-synthetic", help="write the synthetic fleet's records as e-MMS/IMMOLS-style files")
    ex.add_argument("--out", default="data/exports/bharat-fleet")
    ex.add_argument("--days", type=int, default=1825)
    ex.add_argument("--defects", type=float, default=0.0, help="share of install rows to corrupt on purpose")
    im = sub.add_parser("import", help="import a folder of source exports into the record store")
    im.add_argument("folder")
    im.add_argument("--db", default="data/nirantar.db")
    im.add_argument("--mapping", default=None, help="mapping file (default: nirantar/setu/mappings/default.json)")
    ev = sub.add_parser("saarthi-eval", help="score the SAARTHI snag extractor on synthetic utterances")
    ev.add_argument("--n", type=int, default=900)
    ev.add_argument("--seed", type=int, default=0)
    ev.add_argument("--out", default="experiments/results")
    args = ap.parse_args()
    if args.cmd == "plan":
        from nirantar.ui.server import Console
        console = Console(args.results, plan_kwargs={"workers": args.workers})
        desk = console.planner()
        plan = desk.build(log=print)
        j = plan["joint"] or {}
        print(f"{plan['plan_id']}: {len(plan['items'])} actions from {plan['n_candidates']} candidates, "
              f"cost {plan['cost_lakh']} lakh, value {j.get('mrv')} wAAD {j.get('ci95')} over "
              f"{plan['horizon_days']} days, {plan['runtime_s']} s -> {desk.path}")
        return
    if args.cmd == "export-synthetic":
        from nirantar.bharat_fleet.world import make_world
        from nirantar.sanjaya.ensemble import P0
        from nirantar.sanjaya.twin import Twin
        from nirantar.setu.export import export
        w = make_world(seed=7)
        h = Twin(w, P0, args.days, seed=99, record=True).run()
        m = export(w, h.records, h.snapshot, args.days, args.out, defect_rate=args.defects)
        print(f"{len(m['files'])} files as of {m['as_of']} -> {args.out}"
              + (f" ({len(m['planted_defects'])} planted defects)" if m["planted_defects"] else ""))
        return
    if args.cmd == "import":
        from nirantar.setu.ingest import Importer
        from nirantar.setu.schema import Store
        st = Store(args.db)
        rep = Importer(st, mapping=args.mapping).import_folder(args.folder)
        for b in rep["batches"]:
            if b["skipped"]:
                continue
            print(f"{b['file']:28s} {b['rows']:6d} rows  {b['accepted']:6d} accepted  {b['quarantined']:4d} quarantined"
                  + (f"  {b['issues']}" if b["issues"] else ""))
        print("cross-record issues:", rep["data_issues"] or "none", "| store:", args.db)
        return
    if args.cmd == "saarthi-eval":
        import json
        from pathlib import Path

        from nirantar.bharat_fleet.world import make_world
        from nirantar.saarthi.evaluate import generate, score
        w = make_world(seed=7)
        r = score(w, generate(w, n=args.n, seed=args.seed))
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "saarthi_eval.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{r['n']} utterances: complete and correct {r['complete_and_correct']:.1%}, "
              f"any silent error {r['any_silent_error']:.1%}, by language {r['by_language']}")
        return
    if args.cmd == "serve":
        from nirantar.ui.server import serve
        serve(args.results, args.host, args.port)
        return
    cfg = Config(out_dir=args.out, quick=args.quick)
    if args.seeds:
        cfg.n_seeds = args.seeds
    run(cfg)


if __name__ == "__main__":
    main()
