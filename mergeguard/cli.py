"""mergeguard command line.

    mergeguard bench <out_dir> [--seed N]          generate a MergeBench scenario
    mergeguard match <source_dir> <target_dir> -o report.xlsx
    mergeguard eval  <scenario_dir>                 matcher vs name-only baseline
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bench.generate import generate
from .cards import load_side
from .evaluate import evaluate, name_only_baseline
from .match import match_sides
from .report import write_json, write_mapping


def _print_eval(label: str, r: dict) -> None:
    print(f"\n{label}")
    print(f"  target accuracy        {r['target_accuracy']:.0%}  ({r['attributes']} attributes)")
    print(f"  conflict recall        {r['conflict_recall']:.0%}")
    for k, v in r["conflict_recall_by_type"].items():
        print(f"      {k:15} {v:.0%}")
    print(f"  harmful auto-accepts   {r['harmful_auto_accepts']}  (wrong or conflict-hiding mappings accepted without review)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mergeguard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("out_dir")
    b.add_argument("--seed", type=int, default=7)
    m = sub.add_parser("match")
    m.add_argument("source_dir")
    m.add_argument("target_dir")
    m.add_argument("-o", "--output", default="mapping.xlsx")
    m.add_argument("--source-dialect", default="oracle")
    m.add_argument("--target-dialect", default="duckdb")
    m.add_argument("--sme-workbook", help="also fill the Banking Semantic Data Mapping & SME Sign-Off workbook")
    v = sub.add_parser("verify", help="trial-load verification on a parallel run of the acquired accounts")
    v.add_argument("source_dir")
    v.add_argument("target_dir")
    v.add_argument("--parallel", required=True, help="folder with the acquirer-schema tables for the acquired accounts")
    v.add_argument("--sme-workbook", default="signoff.xlsx")
    v.add_argument("--scorecard-sql", default="trial_load_scorecard.sql")
    v.add_argument("--source-dialect", default="oracle")
    v.add_argument("--target-dialect", default="duckdb")
    e = sub.add_parser("eval")
    e.add_argument("scenario_dir")
    a = ap.parse_args(argv)

    if a.cmd == "bench":
        print(f"MergeBench scenario written to {generate(a.out_dir, seed=a.seed)}")
        return 0
    if a.cmd == "match":
        src = load_side(a.source_dir, "source", a.source_dialect)
        tgt = load_side(a.target_dir, "target", a.target_dialect)
        res = match_sides(src, tgt)
        out = write_mapping(res, src, tgt, a.output)
        write_json(res, Path(a.output).with_suffix(".json"))
        if a.sme_workbook:
            from .sme_export import export_sme
            print(f"SME sign-off workbook: {export_sme(res, src, tgt, a.sme_workbook)}")
        ff = sum(1 for x in res if x.false_friend)
        conf = sum(1 for x in res if x.match_type == "conflict")
        print(f"{len(res)} attributes matched: {conf} conflicts, {ff} false friends. Report: {out}")
        return 0
    if a.cmd == "verify":
        from .sme_export import export_sme
        from .verify import Verifier
        src = load_side(a.source_dir, "source", a.source_dialect)
        tgt = load_side(a.target_dir, "target", a.target_dialect)
        res = match_sides(src, tgt)
        checks = {c.source: c for c in Verifier(src, tgt, a.parallel).run(res)}
        export_sme(res, src, tgt, a.sme_workbook, checks=checks, scorecard_path=a.scorecard_sql)
        n = {s: sum(1 for c in checks.values() if c.status == s) for s in ("FAIL", "REVIEW", "PASS", "SKIPPED")}
        print(f"Trial load: {n['FAIL']} FAIL, {n['REVIEW']} REVIEW, {n['PASS']} PASS, {n['SKIPPED']} skipped. "
              f"Workbook: {a.sme_workbook}  Scorecard SQL: {a.scorecard_sql}")
        return 0
    if a.cmd == "eval":
        d = Path(a.scenario_dir)
        src = load_side(d / "acquired", "acquired", "oracle")
        tgt = load_side(d / "acquirer", "acquirer", "duckdb")
        gt = d / "ground_truth.json"
        base = name_only_baseline(src, tgt)
        _print_eval("Name-only baseline (accepts best-named match)",
                    evaluate(base, gt, auto_accept=lambda x: x.target is not None))
        _print_eval("MergeGuard", evaluate(match_sides(src, tgt), gt))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
