"""Run every method on the dev scenario and the two held-out scenarios.

    python experiments/run_heldout.py <dev_dir> <lending_dir> <cards_dir> <out_dir>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from mergeguard.baselines import VALENTINE_METHODS, valentine_predictions
from mergeguard.cards import load_side
from mergeguard.evaluate import evaluate, name_only_baseline
from mergeguard.match import match_sides


def load(d: Path):
    meta = json.loads((d / "scenario.json").read_text()) if (d / "scenario.json").exists() else {}
    src = load_side(d / "acquired", "acquired", meta.get("source_dialect", "oracle"))
    tgt = load_side(d / "acquirer", "acquirer", meta.get("target_dialect", "duckdb"))
    return src, tgt, d / "ground_truth.json"


def main(dev, lending, cards, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    scenarios = {"keystone (dev)": Path(dev), "lending (held-out)": Path(lending), "cards (held-out)": Path(cards)}
    table, details = [], {}
    for label, d in scenarios.items():
        src, tgt, gt = load(d)
        methods = {"name_only": lambda: name_only_baseline(src, tgt)}
        for m in VALENTINE_METHODS:
            methods[f"valentine_{m}"] = (lambda m=m: valentine_predictions(src, tgt, m))
        methods["mergeguard"] = lambda: match_sides(src, tgt)
        for name, fn in methods.items():
            t = time.time()
            res = fn()
            secs = time.time() - t
            acc = None if name == "mergeguard" else (lambda x: x.target is not None)
            r = evaluate(res, gt, auto_accept=acc)
            table.append({"scenario": label, "method": name, "target_accuracy": r["target_accuracy"],
                          "conflict_recall": r["conflict_recall"], "harmful_auto_accepts": r["harmful_auto_accepts"],
                          "attributes": r["attributes"], "seconds": round(secs, 1),
                          "recall_by_type": r["conflict_recall_by_type"]})
            if name == "mergeguard":
                details[label] = r["rows"]
            print(f"{label:20} {name:32} acc {r['target_accuracy']:.0%}  recall {r['conflict_recall']:.0%}  "
                  f"harmful {r['harmful_auto_accepts']}  ({secs:.0f}s)", flush=True)
    (out / "results.json").write_text(json.dumps({"table": table, "mergeguard_rows": details}, indent=2, default=str))
    lines = ["| Scenario | Method | Target accuracy | Conflict recall | Harmful auto-accepts |",
             "| --- | --- | --- | --- | --- |"]
    for r in table:
        lines.append(f"| {r['scenario']} | {r['method']} | {r['target_accuracy']:.0%} | {r['conflict_recall']:.0%} "
                     f"| {r['harmful_auto_accepts']} |")
    (out / "results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:5])
