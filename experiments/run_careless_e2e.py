"""Post-hoc: stage three with the tool's OWN proposed mappings and a reviewer who approves everything.

The earlier careless-sign-off check filled the workbook with correct targets. Here the reviewer accepts whatever
target the tool proposed (wrong targets included), copies the suggested transform or writes "as is", answers "Same"
to every open stress question and signs all four columns. Rows the gate blocks are then skipped (as a reviewer
in a hurry would) and the run is repeated, so that the reconciliation runs on what is left.

For every column that would be loaded: is it wrong (wrong target, or a trap), and did any check FAIL or ask for REVIEW?

    python experiments/run_careless_e2e.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from mergeguard.bench import round3, round4
from mergeguard.bench.spec import generate_spec
from mergeguard.cards import load_side
from mergeguard.match import match_sides
from mergeguard.migrate import SIGNOFFS, apply
from mergeguard.report import STRESS, write_mapping

SPECS = {k: getattr(round3, f"SPEC_{k}") for k in "GHIJK"} | {"L": round4.SPEC_L}


def main(out_dir):
    out = Path(out_dir)
    total, per = Counter(), {}
    for name, spec in SPECS.items():
        d = Path(generate_spec(spec, out / "scenarios" / name, seed=21, n_acquirer=1500, n_acquired=1000))
        gt = {a["source"]: a for a in json.loads((d / "ground_truth.json").read_text())["attributes"]}
        fresh = lambda: (load_side(d / "acquired", "s", "oracle"), load_side(d / "acquirer", "t"))
        src, tgt = fresh()
        wbp = write_mapping(match_sides(src, tgt), src, tgt, d / "review.xlsx")
        wb = load_workbook(wbp)
        ws = wb["Mapping"]
        h = {c.value: i + 1 for i, c in enumerate(ws[1])}
        for r in range(2, ws.max_row + 1):
            t = ws.cell(r, h["target_attribute"]).value
            ws.cell(r, h["decision"]).value = "Accept" if t and t != "(none)" else "Skip"
            if not ws.cell(r, h["transform"]).value:
                ws.cell(r, h["transform"]).value = ws.cell(r, h["suggested_transform"]).value or "as is"
            for k, _ in STRESS:
                ws.cell(r, h[k]).value = ws.cell(r, h[k]).value or "Same"
            for k in SIGNOFFS:
                ws.cell(r, h[k]).value = "J. Doe"
        wb.save(wbp)
        blocks = []
        for attempt in range(4):
            src, tgt = fresh()
            o = apply(wbp, src, tgt, d / f"run{attempt}", parallel=d / "parallel")
            if o.status != "BLOCKED":
                break
            bl = [i for i in o.issues if i.severity == "BLOCK"]
            blocks += [(i.source, i.message) for i in bl]
            rows = {i.row_no for i in bl if i.row_no}
            if not rows:
                break
            for r in rows:
                ws.cell(r, h["decision"]).value = "Skip"
            wb.save(wbp)
        flagged = {(r.table, r.column) for r in o.results if r.status in ("FAIL", "REVIEW")}
        failed = {(r.table, r.column) for r in o.results if r.status == "FAIL"}
        res = Counter(status=o.status, gate_blocks=len(blocks))
        silent = []
        for tp in o.tables:
            for p in tp.columns:
                g = gt.get(p.row.source)
                if g is None or p.target_col == tgt.schema[tp.target_table]["key"]:
                    continue
                target = f"{tp.target_table}.{p.target_col}"
                wrong_target = g["target"] is None or target not in (g["target"] or "").split("+")
                trap = bool(g["conflicts"] or g["false_friend_of"])
                res["loaded_columns"] += 1
                if wrong_target or trap:
                    res["wrong"] += 1
                    res["wrong_target"] += wrong_target
                    res["wrong_failed"] += (tp.target_table, p.target_col) in failed
                    res["wrong_flagged"] += (tp.target_table, p.target_col) in flagged
                    if (tp.target_table, p.target_col) not in flagged:
                        silent.append(f"{p.row.source}->{target}" + (" (wrong target)" if wrong_target else f" {g['conflicts']}"))
                else:
                    res["clean"] += 1
                    res["clean_failed"] += (tp.target_table, p.target_col) in failed
        per[name] = {**res, "silent": silent, "blocks": [f"{s}: {m}" for s, m in blocks]}
        print(name, dict(res), "silent:", silent, "blocks:", [m[:70] for _, m in blocks][:4], flush=True)
        for k, v in res.items():
            if isinstance(v, int):
                total[k] += v
        total["runs_" + o.status] += 1
    print("TOTAL", dict(total))
    (out / "results.json").write_text(json.dumps({"per_scenario": per, "total": dict(total)}, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
