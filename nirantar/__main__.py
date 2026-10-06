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
    sv.add_argument("--db", default=None, help="plan from a SETU record store instead of the synthetic fleet")
    sv.add_argument("--auth", default=None, metavar="USERS_DB",
                    help="require logins (user accounts from `nirantar users`), e.g. experiments/results/users.db")
    sv.add_argument("--cert", default=None, help="TLS certificate (PEM) for HTTPS")
    sv.add_argument("--key", default=None, help="TLS private key (PEM)")
    sv.add_argument("--allow-insecure", action="store_true",
                    help="allow listening beyond this machine without logins and HTTPS (isolated test networks only)")
    us = sub.add_parser("users", help="manage console user accounts (roles, passphrases, disabling)")
    us.add_argument("action", choices=["add", "list", "roles", "disable", "enable", "reset-password", "audit"])
    us.add_argument("username", nargs="?")
    us.add_argument("--db", default="experiments/results/users.db")
    us.add_argument("--roles", default=None, help="comma-separated, e.g. 'CEngO,Logistics officer'")
    us.add_argument("--display", default=None, help="name shown in the console and ledger")
    mc = sub.add_parser("make-cert", help="create a self-signed TLS certificate for the console")
    mc.add_argument("--out", default="experiments/results/keys")
    mc.add_argument("--host", action="append", default=None, help="host name or IP the console is reached at")
    pl = sub.add_parser("plan", help="prepare today's decision-desk plan (signed into the ledger)")
    pl.add_argument("--results", default="experiments/results")
    pl.add_argument("--workers", type=int, default=None, help="processes for pricing (default: CPU count, max 8)")
    pl.add_argument("--db", default=None, help="plan from a SETU record store instead of the synthetic fleet")
    ex = sub.add_parser("export-synthetic", help="write the synthetic fleet's records as e-MMS/IMMOLS-style files")
    ex.add_argument("--out", default="data/exports/bharat-fleet")
    ex.add_argument("--days", type=int, default=1825)
    ex.add_argument("--defects", type=float, default=0.0, help="share of install rows to corrupt on purpose")
    im = sub.add_parser("import", help="import a folder of source exports into the record store")
    im.add_argument("folder")
    im.add_argument("--db", default="data/nirantar.db")
    im.add_argument("--mapping", default=None, help="mapping file (default: nirantar/setu/mappings/default.json)")
    im.add_argument("--results", default="experiments/results", help="whose ledger signs each accepted batch")
    bt = sub.add_parser("records-backtest", help="plan from exported records, score in the synthetic fleet's truth")
    bt.add_argument("--out", default="experiments/results")
    bt.add_argument("--workers", type=int, default=None)
    rf = sub.add_parser("refit", help="refit the reliability model on the record store, back-tested on the last year")
    rf.add_argument("--db", default="data/nirantar.db")
    rf.add_argument("--results", default="experiments/results", help="whose ledger signs the model card")
    rf.add_argument("--holdout-days", type=float, default=365.0)
    vp = sub.add_parser("validate-public", help="check DHANVANTARI on real public reliability data")
    vp.add_argument("--out", default="experiments/results")
    ev = sub.add_parser("saarthi-eval", help="score the SAARTHI snag extractor on synthetic utterances")
    ev.add_argument("--n", type=int, default=900)
    ev.add_argument("--seed", type=int, default=0)
    ev.add_argument("--out", default="experiments/results")
    args = ap.parse_args()
    if args.cmd == "plan":
        from nirantar.ui.server import Console
        console = Console(args.results, plan_kwargs={"workers": args.workers}, store=args.db)
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
        from pathlib import Path

        from nirantar.chitragupta.ledger import Ledger, Signer
        from nirantar.setu.ingest import Importer
        from nirantar.setu.schema import Store
        st = Store(args.db)
        res = Path(args.results)
        led, signer = Ledger(res / "ledger.jsonl"), Signer.load_or_create(res / "keys" / "setu.key", "setu")
        rep = Importer(st, mapping=args.mapping, ledger=led, signer=signer).import_folder(args.folder)
        for b in rep["batches"]:
            if b["skipped"]:
                continue
            print(f"{b['file']:28s} {b['rows']:6d} rows  {b['accepted']:6d} accepted  {b['quarantined']:4d} quarantined"
                  + (f"  {b['issues']}" if b["issues"] else ""))
        print("cross-record issues:", rep["data_issues"] or "none", "| store:", args.db)
        return
    if args.cmd == "records-backtest":
        import json
        from pathlib import Path

        from nirantar.bharat_fleet.world import make_world
        from nirantar.pipeline import clean_json
        from nirantar.setu.backtest import backtest
        r = backtest(make_world(seed=7), workers=args.workers)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "records_backtest.json").write_text(json.dumps(clean_json(r), indent=1), encoding="utf-8")
        print(json.dumps(r["summary"], indent=1))
        return
    if args.cmd == "users":
        from nirantar.rakshak.cli import users_command
        users_command(args)
        return
    if args.cmd == "make-cert":
        from nirantar.rakshak.tls import make_self_signed
        cert, key = make_self_signed(args.out, args.host or ["localhost", "127.0.0.1"])
        print(f"certificate {cert}\nprivate key {key}  (keep it on this machine; give users the certificate to trust)")
        return
    if args.cmd == "refit":
        from pathlib import Path

        from nirantar.chitragupta.ledger import Ledger, Signer
        from nirantar.setu.refit import refit
        from nirantar.setu.schema import Store
        res = Path(args.results)
        card = refit(Store(args.db), args.holdout_days, ledger=Ledger(res / "ledger.jsonl"),
                     signer=Signer.load_or_create(res / "keys" / "setu.key", "setu"))
        print(f"model v{card['version']} ({card['spec']}) as of {card['as_of']}, ledger #{card['ledger_seq']}; "
              f"drift: {card['drift'] or 'none'}")
        return
    if args.cmd == "validate-public":
        import json
        from pathlib import Path

        from nirantar.pipeline import clean_json
        from nirantar.pariksha.studies import run_all
        r = run_all()
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "public_validation.json").write_text(json.dumps(clean_json(r), indent=1), encoding="utf-8")
        print(f"-> {Path(args.out) / 'public_validation.json'}")
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
        serve(args.results, args.host, args.port, store=args.db, auth_db=args.auth, cert=args.cert, key=args.key,
              allow_insecure=args.allow_insecure)
        return
    cfg = Config(out_dir=args.out, quick=args.quick)
    if args.seeds:
        cfg.n_seeds = args.seeds
    run(cfg)


if __name__ == "__main__":
    main()
