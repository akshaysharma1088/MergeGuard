"""Run every method on any number of MergeBench scenarios.

    python experiments/run_eval.py <out_dir> <scenario_dir> [<scenario_dir> ...] [--mergeguard-only]
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
    return src, tgt, d / "ground_truth.json", meta.get("scenario", d.name)


def main(argv):
    only = "--mergeguard-only" in argv
    argv = [a for a in argv if a != "--mergeguard-only"]
    out, dirs = Path(argv[0]), [Path(d) for d in argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    table, details = [], {}
    for d in dirs:
        src, tgt, gt, label = load(d)
        methods = {} if only else {"name_only": lambda: name_only_baseline(src, tgt)}
        if not only:
            for m in VALENTINE_METHODS:
                methods[f"valentine_{m}"] = (lambda m=m: valentine_predictions(src, tgt, m))
        methods["mergeguard"] = lambda: match_sides(src, tgt)
        for name, fn in methods.items():
            t = time.time()
            res = fn()
            r = evaluate(res, gt, auto_accept=None if name == "mergeguard" else (lambda x: x.target is not None))
            table.append({"scenario": label, "method": name, "target_accuracy": r["target_accuracy"],
                          "conflict_recall": r["conflict_recall"], "harmful_auto_accepts": r["harmful_auto_accepts"],
                          "recall_by_type": r["conflict_recall_by_type"], "seconds": round(time.time() - t, 1)})
            if name == "mergeguard":
                details[label] = r["rows"]
            print(f"{label:22} {name:30} acc {r['target_accuracy']:.0%}  recall {r['conflict_recall']:.0%}  "
                  f"harmful {r['harmful_auto_accepts']}  auto {r['auto_accepted']}  false alarms {r['false_alarms']}/{r['clean_attributes']}  surfaced {r['surfaced']}/{r['risky_attributes']}", flush=True)
    (out / "results.json").write_text(json.dumps({"table": table, "mergeguard_rows": details}, indent=2, default=str))
    lines = ["| Scenario | Method | Target accuracy | Conflict recall | Harmful auto-accepts |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['scenario']} | {r['method']} | {r['target_accuracy']:.0%} | {r['conflict_recall']:.0%} | {r['harmful_auto_accepts']} |"
              for r in table]
    (out / "results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
