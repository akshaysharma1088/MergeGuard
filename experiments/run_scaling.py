"""Post-hoc: run time and peak memory as rows and columns grow. One process per configuration.

Rows: scenario L (7 table pairs, 37 source columns) at increasing rows per table.
Columns: scenario L with every table copied k times under a new name (rows fixed), so columns grow by k
and the score matrix by k squared. The copies are only a load test; nothing is scored for accuracy.
The stage-three run uses a workbook in which every proposal is approved and signed (as in run_careless_e2e).

Scenario L's two target rules cannot be rewritten (inputs missing on the source side), so rule execution is timed
separately on the payroll pair from run_rule_rewrite_checks (one rule, correct inputs).
Stage-three time is only meaningful when apply_status is not BLOCKED.

    python experiments/run_scaling.py <out_dir>
"""
from __future__ import annotations

import json
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path


def widen(d: Path, k: int) -> None:
    for side in ("acquired", "acquirer"):
        schema = json.loads((d / side / "schema.json").read_text())
        der = json.loads((d / side / "derivations.json").read_text())
        names = list(schema)
        for i in range(1, k):
            suf = f"_{chr(97 + i)}{chr(97 + i)}"
            ren = lambda s: re.sub(r"\b(" + "|".join(map(re.escape, names)) + r")\b", lambda m: m.group(1) + suf, s)
            for t in names:
                shutil.copy(d / side / f"{t}.parquet", d / side / f"{t}{suf}.parquet")
                if side == "acquirer" and (d / "parallel" / f"{t}.parquet").exists():
                    shutil.copy(d / "parallel" / f"{t}.parquet", d / "parallel" / f"{t}{suf}.parquet")
                schema[t + suf] = schema[t]
            for q, sql in list(der.items()):
                t, c = q.split(".")
                if t in names:
                    der[f"{t}{suf}.{c}"] = ren(sql)
        (d / side / "schema.json").write_text(json.dumps(schema))
        (d / side / "derivations.json").write_text(json.dumps(der))


def one(d: str, rows: int, k: int) -> None:
    from openpyxl import load_workbook

    import mergeguard.match as M
    from mergeguard.bench.round4 import SPEC_L
    from mergeguard.bench.spec import generate_spec
    from mergeguard.cards import load_side
    from mergeguard.migrate import SIGNOFFS, apply
    from mergeguard.report import STRESS, write_mapping
    from mergeguard.verify import Verifier

    d = Path(d)
    generate_spec(SPEC_L, d, seed=612, n_acquirer=int(rows * 1.5), n_acquired=rows)
    if k > 1:
        widen(d, k)
    t = {}
    clock = time.perf_counter
    t0 = clock()
    fresh = lambda: (load_side(d / "acquired", "s", "oracle"), load_side(d / "acquirer", "t"))
    src, tgt = fresh()
    t["profile"] = clock() - t0
    inner = {}
    for name in ("align_tables", "_attach_ddr", "linear_sum_assignment"):
        f = getattr(M, name)
        def wrap(*a, _f=f, _n=name, **kw):
            s = clock()
            try:
                return _f(*a, **kw)
            finally:
                inner[_n] = inner.get(_n, 0) + clock() - s
        setattr(M, name, wrap)
    t0 = clock()
    res = M.match_sides(src, tgt)
    total = clock() - t0
    t["rule_rewrite"] = inner.get("_attach_ddr", 0)
    t["assignment"] = inner.get("linear_sum_assignment", 0)
    t["scoring"] = total - t["rule_rewrite"] - t["assignment"]
    t0 = clock()
    Verifier(src, tgt, d / "parallel").run(res)
    t["verify"] = clock() - t0
    wbp = write_mapping(res, src, tgt, d / "review.xlsx")
    wb = load_workbook(wbp)
    ws = wb["Mapping"]
    h = {c.value: i + 1 for i, c in enumerate(ws[1])}
    for r in range(2, ws.max_row + 1):
        tg = ws.cell(r, h["target_attribute"]).value
        ws.cell(r, h["decision"]).value = "Accept" if tg and tg != "(none)" else "Skip"
        if not ws.cell(r, h["transform"]).value:
            ws.cell(r, h["transform"]).value = ws.cell(r, h["suggested_transform"]).value or "as is"
        for key, _ in STRESS:
            ws.cell(r, h[key]).value = ws.cell(r, h[key]).value or "Same"
        for key in SIGNOFFS:
            ws.cell(r, h[key]).value = "J. Doe"
    wb.save(wbp)
    src, tgt = fresh()
    t0 = clock()
    o = apply(wbp, src, tgt, d / "run", parallel=d / "parallel")
    t["apply"] = clock() - t0
    print("RESULT " + json.dumps({"rows": rows, "copies": k, "source_columns": len(src.cards), "target_columns": len(tgt.cards),
                                  "seconds": {a: round(b, 2) for a, b in t.items()}, "total_s": round(sum(t.values()), 2),
                                  "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                                  "apply_status": o.status}), flush=True)


def rule_time(out: Path) -> list:
    sys.path.insert(0, str(Path(__file__).parent))
    import run_rule_rewrite_checks as R
    from mergeguard.match import Match, _attach_ddr, align_tables
    res = []
    for n in (10_000, 100_000, 1_000_000):
        src, tgt = R.build(out / f"rule_{n}", "same", n)
        align_tables(src, tgt)
        pairs = {"PAYROLL.EMP_NO": "pay.emp_id", "PAYROLL.NET_PAY": "pay.net_pay",
                 "PAYROLL.GROSS_PAY": "pay.gross_pay", "PAYROLL.TAX_AMT": "pay.tax"}
        ms = [Match(s, t, 1.0, "exact", [], {}, "", []) for s, t in pairs.items()]
        t0 = time.perf_counter()
        _attach_ddr(ms, src, tgt)
        res.append({"rows": n, "rule_seconds": round(time.perf_counter() - t0, 2), "ddr": ms[1].ddr and ms[1].ddr.get("rate")})
        shutil.rmtree(out / f"rule_{n}", ignore_errors=True)
        print(json.dumps(res[-1]), flush=True)
    return res


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if "--rule-only" in sys.argv:
        (out / "rule_time.json").write_text(json.dumps(rule_time(out), indent=1))
        return
    rows = []
    for n, k in [(1000, 1), (10000, 1), (100000, 1), (1000000, 1), (2000, 2), (2000, 4), (2000, 8)]:
        d = out / f"n{n}_k{k}"
        p = subprocess.run([sys.executable, __file__, "--one", str(d), str(n), str(k)], capture_output=True, text=True)
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
        shutil.rmtree(d, ignore_errors=True)
        if line is None:
            rows.append({"rows": n, "copies": k, "error": p.stderr[-400:]})
        else:
            rows.append(json.loads(line[7:]))
        print(json.dumps(rows[-1]), flush=True)
        (out / "results.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "--one":
        one(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        main(sys.argv[1])
