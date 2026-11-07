"""Profiling (before mapping) plus trial-load verification (before cutover), per MergeBench paired scenario.

    python experiments/run_verify.py <out_dir> <paired_scenario_dir> [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from mergeguard.bench.round3 import SPECS
from mergeguard.match import match_sides
from mergeguard.verify import Verifier

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402

MEANING = {"population", "grain", "null_semantics", "inclusion", "temporal", "definition", "sign", "unit", "scale",
           "code_set", "format", "aggregation", "identity"}


def main(argv):
    out = Path(argv[0]); out.mkdir(parents=True, exist_ok=True)
    loaded_all = {t for s in SPECS.values() for t in s.get("loaded", [])}
    summary, rows_out = [], []
    for d in map(Path, argv[1:]):
        src, tgt, gt_path, label = load(d)
        meta = json.loads((d / "scenario.json").read_text())
        loaded_here = set(meta.get("loaded", [])) or loaded_all
        gt = {g["source"]: g for g in json.loads(gt_path.read_text())["attributes"]}
        res = match_sides(src, tgt)
        checks = {c.source: c for c in Verifier(src, tgt, d / "parallel").run(res)}
        prof = {m.source: m for m in res}
        tot = dict(risky=0, prof_any=0, ver_any=0, both_any=0, ver_type=0, loaded=0, loaded_caught=0,
                   computed=0, computed_caught=0, clean=0, false_fail=0, conflicts=0)
        for s, g in gt.items():
            m, c = prof[s], checks[s]
            risky = bool(g["conflicts"] or g["false_friend_of"])
            p_any = bool(m.match_type == "conflict" or m.false_friend or set(m.flags) & MEANING)
            v_any = c.status == "FAIL"
            if not risky:
                if g["match_type"] in ("exact",):
                    tot["clean"] += 1
                    tot["false_fail"] += v_any
                continue
            tot["risky"] += 1
            tot["prof_any"] += p_any
            tot["ver_any"] += v_any
            tot["both_any"] += p_any or v_any
            tot["conflicts"] += len(g["conflicts"])
            tot["ver_type"] += len(set(g["conflicts"]) & set(c.flags))
            is_loaded = g["target"] in loaded_here
            tot["loaded" if is_loaded else "computed"] += 1
            tot["loaded_caught" if is_loaded else "computed_caught"] += p_any or v_any
            rows_out.append({"scenario": label, "source": s, "truth": g["conflicts"], "loaded": is_loaded,
                             "profile_flags": m.flags, "verify": c.status, "verify_flags": c.flags,
                             "diagnosis": c.diagnosis, "mismatch_rate": c.mismatch_rate, "edge_cases": c.edge_cases})
        summary.append({"scenario": label, **tot})
        print(f"{label:26} risky {tot['risky']:2}  profiling {tot['prof_any']:2}  trial-load {tot['ver_any']:2}  "
              f"combined {tot['both_any']:2}  type-correct {tot['ver_type']}/{tot['conflicts']}  "
              f"computed {tot['computed_caught']}/{tot['computed']}  loaded {tot['loaded_caught']}/{tot['loaded']}  "
              f"false FAIL {tot['false_fail']}/{tot['clean']}", flush=True)
    (out / "verify_results.json").write_text(json.dumps({"summary": summary, "rows": rows_out}, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
