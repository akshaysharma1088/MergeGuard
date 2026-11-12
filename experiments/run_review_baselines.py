"""Post-hoc baselines requested in review (not pre-registered; scenarios E to L are development data by now).

A. Abstention: is MergeGuard safer than COMA only because it approves fewer mappings?
   COMA variants: trust all; same identifier-review rule; top-k by score at MergeGuard's coverage;
   COMA pairs screened by MergeGuard's detectors. Plus the largest coverage at which COMA is as safe.
B. Record diff: does a plain same-record comparison on the trial-load output catch what the verifier catches?
   strict = values equal as text; tolerant = numbers within a cent, booleans and whitespace normalised.

    python experiments/run_review_baselines.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mergeguard.baselines import valentine_predictions
from mergeguard.bench.generate import generate
from mergeguard.bench.round3 import SPECS
from mergeguard.bench.round4 import SPEC_L
from mergeguard.bench.spec import generate_spec
from mergeguard.evaluate import evaluate
from mergeguard.match import detect_conflicts, match_sides, score_pair
from mergeguard.verify import FAIL_RATE, Verifier, _bool

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402

SEEDS = {"E": 303, "F": 404, "G": 571, "H": 572, "I": 573, "J": 574, "K": 575, "L": 612}


def build(root: Path) -> dict:
    out = {}
    for k, seed in SEEDS.items():
        d = root / k
        if not (d / "ground_truth.json").exists():
            if k == "E":
                generate(d, seed=seed, scenario="practitioner")
            elif k == "F":
                generate(d, seed=seed, scenario="practitioner2")
            else:
                generate_spec(SPEC_L if k == "L" else SPECS[k], d, seed=seed)
        out[k] = d
    return out


def abstention(src, tgt, gt_path) -> dict:
    gt = {g["source"]: g for g in json.loads(Path(gt_path).read_text())["attributes"]}
    mg = match_sides(src, tgt)
    r_mg = evaluate(mg, gt_path)
    coma = valentine_predictions(src, tgt, "coma")
    is_id = lambda m: src.card(m.source).is_identifier or (m.target and tgt.card(m.target).is_identifier)
    cand = [m for m in coma if m.target is not None]
    no_id = [m for m in cand if not is_id(m)]
    ranked = sorted(no_id, key=lambda m: -m.score)

    def harmful(accepted) -> int:
        acc = {m.source for m in accepted}
        return evaluate(coma, gt_path, auto_accept=lambda m: m.source in acc)["harmful_auto_accepts"]

    k = r_mg["auto_accepted"]
    screened = [m for m in no_id
                if not detect_conflicts(score_pair(src.card(m.source), tgt.card(m.target)))]
    curve = [harmful(ranked[:i]) for i in range(len(ranked) + 1)]
    safe = max(i for i, h in enumerate(curve) if h <= r_mg["harmful_auto_accepts"])
    return {"columns": len(gt), "risky": r_mg["risky_attributes"],
            "mergeguard": {"accepted": k, "harmful": r_mg["harmful_auto_accepts"]},
            "coma_trust_all": {"accepted": len(cand), "harmful": harmful(cand)},
            "coma_id_rule": {"accepted": len(no_id), "harmful": harmful(no_id)},
            "coma_matched_coverage": {"accepted": min(k, len(ranked)), "harmful": harmful(ranked[:k])},
            "coma_plus_detectors": {"accepted": len(screened), "harmful": harmful(screened)},
            "coma_coverage_at_mergeguard_safety": safe, "coma_curve": curve}


def _norm(s: pd.Series) -> pd.Series:
    b = s.map(_bool)
    if s.notna().any() and b[s.notna()].notna().all():
        return b.astype(object)
    return s.map(lambda v: None if pd.isna(v) else str(v).strip())


def diff_rates(df: pd.DataFrame) -> tuple[float, float]:
    a, b = df.sv.astype(object), df.tv.astype(object)
    sa = a.map(lambda v: None if pd.isna(v) else str(v))
    sb = b.map(lambda v: None if pd.isna(v) else str(v))
    strict = ~((sa == sb) | (sa.isna() & sb.isna()))
    na, nb = _norm(a), _norm(b)
    num = lambda x: pd.to_numeric(x.map(lambda v: None if isinstance(v, (bool, np.bool_)) else v), errors="coerce").astype(float)
    close = ((num(a) - num(b)).abs() <= 0.011).fillna(False)
    tolerant = ~((na == nb) | (na.isna() & nb.isna()) | close)
    return float(strict.mean()), float(tolerant.mean())


def record_diff(src, tgt, d: Path) -> dict:
    meta = json.loads((d / "scenario.json").read_text())
    loaded = set(meta.get("loaded", []))
    gt = {g["source"]: g for g in json.loads((d / "ground_truth.json").read_text())["attributes"]}
    res = match_sides(src, tgt)
    ver = Verifier(src, tgt, d / "parallel")
    checks = {c.source: c for c in ver.run(res)}
    groups = {"computed_traps": [], "stored_traps": [], "clean_exact": [], "clean_transform": []}
    rows = []
    for m in res:
        g = gt[m.source]
        if not m.target or "+" in m.target or m.target != g["target"] or m.target.split(".")[0] not in ver.available:
            continue
        if m.source.split(".")[1] == src.schema[m.source.split(".")[0]]["key"]:
            continue
        risky = bool(g["conflicts"] or g["false_friend_of"])
        grp = (("stored_traps" if m.target in loaded else "computed_traps") if risky
               else "clean_exact" if g["match_type"] == "exact" else "clean_transform" if g["match_type"] == "transform" else None)
        if grp is None:
            continue
        df = ver.pairs(m.source, m.target)
        if df.empty:
            continue
        strict, tol = diff_rates(df)
        c = checks[m.source]
        row = {"source": m.source, "group": grp, "truth": g["conflicts"], "strict_rate": strict, "tolerant_rate": tol,
               "strict_fail": strict > FAIL_RATE, "tolerant_fail": tol > FAIL_RATE, "verifier_fail": c.status == "FAIL",
               "verifier_flags": c.flags, "type_correct": bool(set(c.flags) & set(g["conflicts"])),
               "diagnosis": c.diagnosis}
        rows.append(row)
        groups[grp].append(row)
    summ = {grp: {"n": len(v), "strict": sum(r["strict_fail"] for r in v), "tolerant": sum(r["tolerant_fail"] for r in v),
                  "verifier": sum(r["verifier_fail"] for r in v)} for grp, v in groups.items()}
    traps = groups["computed_traps"] + groups["stored_traps"]
    summ["verifier_type_correct_of_failed"] = [sum(r["type_correct"] for r in traps if r["verifier_fail"]),
                                               sum(r["verifier_fail"] for r in traps)]
    summ["verifier_only"] = [r["source"] for r in traps if r["verifier_fail"] and not r["tolerant_fail"]]
    summ["diff_only"] = [r["source"] for r in traps if r["tolerant_fail"] and not r["verifier_fail"]]
    return {"summary": summ, "rows": rows}


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dirs = build(out / "scenarios")
    result = {"abstention": {}, "record_diff": {}}
    for k, d in dirs.items():
        src, tgt, gt, _ = load(d)
        a = abstention(src, tgt, gt)
        result["abstention"][k] = a
        print(f"{k} abstain: cols {a['columns']} | MG {a['mergeguard']} | all {a['coma_trust_all']} | id {a['coma_id_rule']} "
              f"| matched {a['coma_matched_coverage']} | +det {a['coma_plus_detectors']} | COMA safe coverage "
              f"{a['coma_coverage_at_mergeguard_safety']}", flush=True)
        if (d / "parallel").exists():
            src, tgt, gt, _ = load(d)
            r = record_diff(src, tgt, d)
            result["record_diff"][k] = r
            print(f"{k} diff: {json.dumps(r['summary'])}", flush=True)
    (out / "results.json").write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
