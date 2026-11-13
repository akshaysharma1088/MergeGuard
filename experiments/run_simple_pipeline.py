"""Post-hoc: a complete simple pipeline against MergeGuard, end to end on trial-load scenarios G to L.

Simple pipeline (no MergeGuard matcher, detectors or verifier logic):
    COMA one-to-one mapping -> tolerant same-record diff on the trial-load output (>1% mismatch = flag)
    -> if the diff passes, three standard conformance checks of the source values against the acquirer's live
       column: domain (target has <= 50 distinct values; >1% of source values outside them), range (>5% of
       numeric values outside the live min..max), length (>1% of text values shorter or longer than any live value)
    -> everything flagged, every identifier and every unmapped column goes to the review queue
       (identifiers are not conformance-checked: they are re-keyed).
A second variant feeds MergeGuard's own mapping into the same diff and conformance checks.

MergeGuard: its matcher, profiling flags and verifier, with its own auto-accept rule.

Per column: flagged (reaches a reviewer with a warning) and approved (not flagged, not an identifier, mapped).

    python experiments/run_simple_pipeline.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mergeguard.baselines import valentine_predictions
from mergeguard.match import match_sides
from mergeguard.verify import FAIL_RATE, Verifier

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load  # noqa: E402
from run_review_baselines import SEEDS, build, diff_rates  # noqa: E402

LETTERS = ["G", "H", "I", "J", "K", "L"]
MEANING = {"population", "grain", "null_semantics", "inclusion", "temporal", "definition", "unit", "scale", "sign",
           "code_set", "format"}


def conformance(src, tgt, source: str, target: str) -> str:
    st, sc = source.split(".")
    tt, tc = target.split(".")
    s = src.con.execute(f'SELECT "{sc}" FROM "{st}" WHERE "{sc}" IS NOT NULL').df().iloc[:, 0]
    t = tgt.con.execute(f'SELECT "{tc}" FROM "{tt}" WHERE "{tc}" IS NOT NULL').df().iloc[:, 0]
    if s.empty or t.empty:
        return ""
    dom = set(t.astype(str).unique())
    if len(dom) <= 50 and (~s.astype(str).isin(dom)).mean() > FAIL_RATE:
        return "domain"
    sn, tn = pd.to_numeric(s, errors="coerce"), pd.to_numeric(t, errors="coerce")
    if tn.notna().mean() > 0.99 and sn.notna().mean() > 0.99:
        return "range" if ((sn < tn.min()) | (sn > tn.max())).mean() > 0.05 else ""
    ls, lt = s.astype(str).str.len(), t.astype(str).str.len()
    return "length" if ((ls < lt.min()) | (ls > lt.max())).mean() > FAIL_RATE else ""


def simple(src, tgt, ver, mapping: dict) -> dict:
    """mapping: source -> target or None. Returns source -> (flagged, reason)."""
    out = {}
    for s, t in mapping.items():
        if not t or "+" in t:
            out[s] = (False, "unmapped" if not t else "split")
            continue
        if t.split(".")[0] in ver.available:
            df = ver.pairs(s, t)
            if not df.empty and diff_rates(df)[1] > FAIL_RATE:
                out[s] = (True, "diff")
                continue
        if src.card(s).is_identifier or tgt.card(t).is_identifier:   # identifiers are re-keyed; they go to review anyway
            out[s] = (False, "identifier")
            continue
        c = conformance(src, tgt, s, t)
        out[s] = (bool(c), c)
    return out


def score(gt, mapping, flagged, approved) -> dict:
    r = dict(columns=0, traps=0, clean=0, correct=0, traps_flagged=0, clean_flagged=0, approved=0, wrong=0)
    for g in gt:
        s, t = g["source"], mapping.get(g["source"])
        risky = bool(g["conflicts"] or g["false_friend_of"])
        ok = t == g["target"]
        clean = (not risky) and g["target"] is not None
        r["columns"] += 1
        r["traps"] += risky
        r["clean"] += clean
        r["correct"] += ok
        r["traps_flagged"] += risky and flagged[s]
        r["clean_flagged"] += clean and ok and flagged[s]
        r["approved"] += approved[s]
        r["wrong"] += approved[s] and (risky or not ok)
    return {k: int(v) for k, v in r.items()}


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dirs = build(out / "scenarios")
    total, per = {}, {}
    for k in LETTERS:
        d = dirs[k]
        src, tgt, gt_path, _ = load(d)
        gt = json.loads(Path(gt_path).read_text())["attributes"]
        ver = Verifier(src, tgt, d / "parallel")
        is_id = lambda s, t: src.card(s).is_identifier or bool(t and "+" not in t and tgt.card(t).is_identifier)

        mg = match_sides(src, tgt)
        checks = {c.source: c for c in ver.run(mg)}
        mg_map = {m.source: m.target for m in mg}
        mg_flag = {m.source: bool(m.match_type == "conflict" or m.false_friend or set(m.flags) & MEANING
                                  or checks[m.source].status == "FAIL") for m in mg}
        mg_appr = {m.source: bool(m.auto_accept and checks[m.source].status != "FAIL") for m in mg}

        coma_map = {m.source: m.target for m in valentine_predictions(src, tgt, "coma")}
        variants = {"mergeguard": (mg_map, mg_flag, mg_appr)}
        for name, mp in (("simple_coma", coma_map), ("simple_mergeguard_mapping", mg_map)):
            res = simple(src, tgt, ver, mp)
            flag = {s: res[s][0] for s in mp}
            appr = {s: bool(mp[s] and "+" not in mp[s] and not flag[s] and not is_id(s, mp[s])) for s in mp}
            variants[name] = (mp, flag, appr)
        per[k] = {}
        for name, (mp, flag, appr) in variants.items():
            r = score(gt, mp, flag, appr)
            per[k][name] = r
            for key, v in r.items():
                total.setdefault(name, {}).setdefault(key, 0)
                total[name][key] += v
            print(k, name, r, flush=True)
    print("TOTAL", json.dumps(total, indent=1))
    (out / "results.json").write_text(json.dumps({"seeds": {k: SEEDS[k] for k in LETTERS}, "per_scenario": per,
                                                  "total": total}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
