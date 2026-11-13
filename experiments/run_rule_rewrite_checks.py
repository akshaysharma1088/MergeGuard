"""Post-hoc: how far can the rule-rewriting check be trusted when the mapping of a rule's INPUTS is wrong?

One target rule: net_pay = gross_pay - tax. The output pair under test is always NET_PAY -> pay.net_pay.
Each case fixes the input mapping by hand and calls the same code path the matcher uses (_attach_ddr).

Also reports what a proposed guard would do: mark the rule "unverified" when any input pair is itself flagged
or not an exact match, instead of trusting the result. The guard is NOT in the matcher; it is computed here.

    python experiments/run_rule_rewrite_checks.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mergeguard.cards import load_side
from mergeguard.connectors import write_folder
from mergeguard.match import Match, _attach_ddr, align_tables, detect_conflicts, score_pair

RULE = "SELECT p.emp_id, p.gross_pay - p.tax AS net_pay FROM pay p"


def build(root: Path, source_net: str, n: int = 2000):
    rng = np.random.default_rng(5)
    gross = rng.normal(5000, 1200, n).clip(1500).round(2)
    tax = (gross * rng.uniform(0.15, 0.3, n)).round(2)
    fee = rng.uniform(20, 60, n).round(2)
    s = pd.DataFrame({"EMP_NO": np.arange(1, n + 1), "GROSS_PAY": gross, "TAX_AMT": tax,
                      "TAX_CENTS": (tax * 100).round(0), "UNION_FEE": fee, "GROSS_YTD": (gross * rng.uniform(3, 9, n)).round(2),
                      "GROSS_AFTER_FEE": (gross - fee).round(2)})
    s["NET_PAY"] = {"same": gross - tax, "less_fee": gross - tax - fee}[source_net].round(2)
    g2 = rng.normal(5200, 1300, n).clip(1500).round(2)
    t2 = (g2 * rng.uniform(0.15, 0.3, n)).round(2)
    t = pd.DataFrame({"emp_id": np.arange(1, n + 1), "gross_pay": g2, "tax": t2, "net_pay": (g2 - t2).round(2)})
    sd = write_folder(root / "src", {"PAYROLL": s}, {"PAYROLL": {"key": "EMP_NO"}}, {})
    td = write_folder(root / "tgt", {"pay": t}, {"pay": {"key": "emp_id"}}, {"pay.net_pay": RULE})
    return load_side(sd, "s"), load_side(td, "t")


def run(root: Path, name: str, source_net: str, inputs: dict, truth: str) -> dict:
    src, tgt = build(root / name, source_net)
    align_tables(src, tgt)   # the matcher does this first; without it every pair looks like a grain conflict
    pairs = {"PAYROLL.EMP_NO": "pay.emp_id", "PAYROLL.NET_PAY": "pay.net_pay", **inputs}
    results, flagged_inputs = [], []
    for s, t in pairs.items():
        p = score_pair(src.card(s), tgt.card(t))
        flags = [f for f in detect_conflicts(p) if f != "cast"]
        results.append(Match(s, t, p.score, "exact" if not flags else "transform", list(flags), p.signals, "", []))
        if s in inputs and flags:
            flagged_inputs.append(f"{s} {flags}")
    _attach_ddr(results, src, tgt)
    m = next(r for r in results if r.source == "PAYROLL.NET_PAY")
    ddr = m.ddr or {}
    if m.ddr is None:
        raise SystemExit(f"{name}: rule was skipped, flags={m.flags}")
    outcome = ("not runnable: missing " + ", ".join(ddr.get("missing", [])) if ddr.get("available") is False
               else f"disagreement {ddr.get('rate', 0):.1%}; " + ("FLAGGED " + str([f for f in m.flags]) if m.match_type == "conflict" else "no flag"))
    flagged = m.match_type == "conflict"
    verdict = {("same", False): "correct (clean, not flagged)", ("same", True): "FALSE ALARM on a clean column",
               ("trap", True): "correct (trap flagged)", ("trap", False): "MISSED trap"}[(truth, flagged)]
    if ddr.get("available") is False:
        verdict = "correct (reported as not runnable)"
    guard = "unverified: " + "; ".join(flagged_inputs) if flagged_inputs else "would still trust the result"
    row = {"case": name, "inputs": inputs, "truth": truth, "outcome": outcome, "verdict": verdict, "proposed_guard": guard}
    print(json.dumps(row), flush=True)
    return row


def main(out_dir):
    root = Path(out_dir)
    good = {"PAYROLL.GROSS_PAY": "pay.gross_pay", "PAYROLL.TAX_AMT": "pay.tax"}
    rows = [
        run(root, "1_correct_inputs", "same", good, "same"),
        run(root, "2_wrong_input_column", "same", {"PAYROLL.GROSS_YTD": "pay.gross_pay", "PAYROLL.TAX_AMT": "pay.tax"}, "same"),
        run(root, "3_input_in_cents", "same", {"PAYROLL.GROSS_PAY": "pay.gross_pay", "PAYROLL.TAX_CENTS": "pay.tax"}, "same"),
        run(root, "4_missing_input", "same", {"PAYROLL.GROSS_PAY": "pay.gross_pay"}, "same"),
        run(root, "5_real_trap_correct_inputs", "less_fee", good, "trap"),
        run(root, "6_real_trap_masked_by_wrong_input", "less_fee",
            {"PAYROLL.GROSS_AFTER_FEE": "pay.gross_pay", "PAYROLL.TAX_AMT": "pay.tax"}, "trap"),
    ]
    (root / "results.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
