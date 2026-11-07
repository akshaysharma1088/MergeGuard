"""Upload the reviewed workbook and migrate.

    gate      every row is checked before anything moves: decisions, sign-offs on risky fields,
              open stress-test answers, transforms that parse and reference real columns
    plan      one SELECT per target table, built only from approved rows
    rehearse  the plan runs locally in DuckDB on the source data; outputs land in a folder
    reconcile row counts, key integrity, key collisions with the acquirer's live data, orphans,
              cast failures, unmapped codes, nulls introduced, conformance to target values
    emit      migration.sql in the warehouse dialect (Snowflake by default), one comment per
              column naming the workbook row and approvers
    audit     audit.json with SHA-256 of the workbook, inputs, SQL and outputs

Nothing is loaded into a real target unless the gate and the reconciliation both pass.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import sqlglot
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from . import __version__
from .cards import Side, type_family
from .report import STRESS

SIGNOFFS = ["source_ops_signoff", "target_ops_signoff", "finance_risk_signoff", "data_profiling_signoff"]
MIGRATE = {"accept", "change"}
AS_IS = {"as is", "as-is", "none", "no transform", "identity"}
FAIL_RATE, REVIEW_RATE = 0.01, 0.0


@dataclass
class Row:
    row_no: int
    source: str
    target: str | None
    decision: str
    match_type: str
    flags: list
    false_friend: bool
    transform: str
    suggested: str
    crosswalk: str
    stress: dict
    signoffs: dict
    high_risk: bool = False
    trap: str = "NO"


@dataclass
class Issue:
    row_no: int | None
    source: str
    severity: str           # BLOCK or WARN
    message: str


@dataclass
class ColumnPlan:
    target_col: str
    expr: str               # pre-cast expression over source columns
    cast_type: str
    row: Row
    crosswalk: dict = field(default_factory=dict)
    base: str | None = None  # expression the crosswalk applies to


@dataclass
class TablePlan:
    target_table: str
    source_table: str
    columns: list


@dataclass
class Result:
    table: str
    check: str
    status: str
    detail: str
    column: str = ""


# ------------------------------------------------------------------ read
def _clean(v) -> str:
    return "" if v is None else str(v).strip()


def read_workbook(path: str | Path) -> list[Row]:
    wb = load_workbook(path, data_only=False)
    ws = wb["Mapping"]
    head = {_clean(c.value): i for i, c in enumerate(ws[1])}
    need = {"source_attribute", "decision", "target_attribute", "transform"}
    if not need <= set(head):
        raise ValueError(f"{path} is not a MergeGuard review workbook (missing {sorted(need - set(head))})")
    rows = []
    for r_no, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        g = lambda k: _clean(r[head[k]]) if k in head and head[k] < len(r) else ""
        if not g("source_attribute"):
            continue
        tgt = g("target_attribute")
        stress = {k: g(k) for k, _ in STRESS}
        row = Row(r_no, g("source_attribute"), None if tgt in ("", "(none)") else tgt, g("decision").lower(),
                  g("match_type"), [f.strip() for f in g("flags").split(",") if f.strip()],
                  bool(g("false_friend")), g("transform"), g("suggested_transform"), g("value_crosswalk"),
                  stress, {k: g(k) for k in SIGNOFFS})
        vals = list(stress.values())
        row.trap = "YES" if "Differs" in vals else "OPEN" if "" in vals else "NO"
        row.high_risk = row.match_type == "conflict" or row.false_friend or row.trap == "YES"
        rows.append(row)
    return rows


# ------------------------------------------------------------------ transforms
def _cast_type(sql_type: str) -> str:
    fam = type_family(sql_type)
    if fam == "int":
        return "BIGINT"
    if fam == "decimal":
        m = re.search(r"\((\d+)\s*,\s*(\d+)\)", sql_type)
        return f"DECIMAL({min(int(m.group(1)), 38)},{m.group(2)})" if m else "DOUBLE"
    return {"date": "DATE", "timestamp": "TIMESTAMP", "bool": "BOOLEAN"}.get(fam, "VARCHAR")


def parse_crosswalk(text: str) -> dict:
    text = re.sub(r"^\s*crosswalk\s*", "", text, flags=re.I)
    out = {}
    for part in re.split(r"[,\n;]", text):
        m = re.match(r"\s*'?([^'=>-]+?)'?\s*(?:->|=>|=|→)\s*'?([^']*?)'?\s*$", part)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _parse_expr(expr: str, table: str, columns: set) -> str | None:
    """Returns an error message, or None if the expression is a safe single expression over real columns."""
    try:
        tree = sqlglot.parse_one(f"SELECT {expr} FROM {table}", read="duckdb")
    except sqlglot.errors.ParseError as e:
        return f"transform does not parse: {str(e).splitlines()[0]}"
    if not isinstance(tree, sqlglot.exp.Select) or len(tree.expressions) != 1:
        return "transform must be one SQL expression"
    if tree.find(sqlglot.exp.Subquery) or list(tree.find_all(sqlglot.exp.Select))[1:]:
        return "transform may not contain a subquery"
    lower = {c.lower(): c for c in columns}
    unknown = sorted({c.name for c in tree.find_all(sqlglot.exp.Column) if c.name.lower() not in lower})
    return f"transform uses columns not in {table}: {', '.join(unknown)}" if unknown else None


def _segments(text: str) -> list[str]:
    return [s.strip() for s in re.split(r";(?=(?:[^']*'[^']*')*[^']*$)", text) if s.strip()]


def column_plans(row: Row, src: Side, tgt: Side) -> tuple[list[ColumnPlan], list[Issue]]:
    st, sc = row.source.split(".")
    s_cols = set(src.schema[st]["columns"])
    targets = row.target.split("+")
    tt = targets[0].split(".")[0]
    t_cols = tgt.schema[tt]["columns"]
    own = [t.split(".")[1] for t in targets]
    issues, assigns, plain, xw = [], {}, [], parse_crosswalk(row.crosswalk) if row.crosswalk else {}
    text = row.transform
    if text.lower() in AS_IS:
        text = ""
    for seg in _segments(text):
        if seg.lower().startswith("crosswalk"):
            xw.update(parse_crosswalk(seg))
            continue
        if "many-to-one crosswalk needed" in seg.lower():
            if not xw:
                issues.append(Issue(row.row_no, row.source, "BLOCK",
                                    "a many-to-one code crosswalk is needed; fill value_crosswalk"))
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.+)$", seg, re.S)
        if m and m.group(1) in t_cols:
            assigns[m.group(1)] = m.group(2).strip()
        else:
            plain.append(seg)
    if len(plain) > 1:
        issues.append(Issue(row.row_no, row.source, "BLOCK",
                            "transform has several expressions; write one, or 'column = expression' per target column"))
        return [], issues
    plans = []
    if len(own) > 1:                          # structural: one source feeds several target columns
        for c in own:
            if c not in assigns:
                issues.append(Issue(row.row_no, row.source, "BLOCK",
                                    f"source feeds {' + '.join(own)}; give 'column = expression' for {c}"))
        own = []
    else:
        assigns.setdefault(own[0], plain[0] if plain else f'"{sc}"')
    for col, expr in assigns.items():
        err = _parse_expr(expr, st, s_cols)
        if err:
            issues.append(Issue(row.row_no, row.source, "BLOCK", f"{col}: {err}"))
            continue
        cp = ColumnPlan(col, expr, _cast_type(t_cols[col]["type"]), row)
        if xw and col == row.target.split(".")[1]:
            cp.crosswalk, cp.base = xw, expr
            cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in xw.items())
            cp.expr = f"CASE CAST({expr} AS VARCHAR) {cases} ELSE NULL END"
        plans.append(cp)
    return plans, issues


# ------------------------------------------------------------------ gate + plan
def gate(rows: list[Row], src: Side, tgt: Side, allow_partial: bool = False) -> tuple[list[TablePlan], list[Issue]]:
    issues: list[Issue] = []
    by_table: dict[str, dict[str, list[ColumnPlan]]] = {}
    for r in rows:
        if not r.decision:
            issues.append(Issue(r.row_no, r.source, "WARN" if allow_partial else "BLOCK", "no decision yet"))
            continue
        if r.decision not in MIGRATE:
            continue
        if not r.target:
            issues.append(Issue(r.row_no, r.source, "WARN", "accepted with no target; nothing to load"))
            continue
        bad = [t for t in r.target.split("+") if t.count(".") != 1 or t.split(".")[0] not in tgt.schema
               or t.split(".")[1] not in tgt.schema[t.split(".")[0]]["columns"]]
        if bad:
            issues.append(Issue(r.row_no, r.source, "BLOCK", f"target not in the target schema: {', '.join(bad)}"))
            continue
        if r.high_risk:
            missing = [k.replace("_signoff", "").replace("_", " ") for k in SIGNOFFS if not r.signoffs[k]]
            if missing:
                why = "conflict" if r.match_type == "conflict" else "false friend" if r.false_friend else "trap identified"
                issues.append(Issue(r.row_no, r.source, "BLOCK", f"high-risk ({why}); missing sign-off: {', '.join(missing)}"))
            if r.trap == "OPEN":
                open_ = [k for k, v in r.stress.items() if not v]
                issues.append(Issue(r.row_no, r.source, "BLOCK", f"high-risk with open stress-test answers: {', '.join(open_)}"))
        known = set(r.flags) & {"unit", "scale", "sign", "format", "code_set"}
        if known and not r.transform and not r.crosswalk:
            issues.append(Issue(r.row_no, r.source, "BLOCK",
                                f"MergeGuard found a {', '.join(sorted(known))} difference but the transform is blank; "
                                "write the transform or 'as is'"))
            continue
        plans, errs = column_plans(r, src, tgt)
        issues += errs
        if errs:
            continue
        st = r.source.split(".")[0]
        for p in plans:
            tt = r.target.split(".")[0]
            by_table.setdefault(tt, {}).setdefault(st, []).append(p)
    tables = []
    for tt, srcs in by_table.items():
        if len(srcs) > 1:
            issues.append(Issue(None, tt, "BLOCK", f"target table {tt} draws from several source tables "
                                f"({', '.join(srcs)}); joins are not supported yet, split the load"))
            continue
        st, cols = next(iter(srcs.items()))
        seen = {}
        for p in cols:
            if p.target_col in seen:
                issues.append(Issue(p.row.row_no, p.row.source, "BLOCK",
                                    f"{tt}.{p.target_col} is also loaded from {seen[p.target_col]}"))
            seen[p.target_col] = p.row.source
        key = tgt.schema[tt]["key"]
        if key not in seen:
            issues.append(Issue(None, tt, "BLOCK", f"the key {tt}.{key} is not mapped; rows cannot be loaded"))
        tables.append(TablePlan(tt, st, cols))
    return tables, issues


# ------------------------------------------------------------------ rehearse + reconcile
def _status(rate: float, n_bad: int | None = None) -> str:
    """FAIL above 1%, but never on fewer than 3 records: one stray record in a small table is a REVIEW."""
    if rate > FAIL_RATE and (n_bad is None or n_bad >= 3):
        return "FAIL"
    return "REVIEW" if rate > REVIEW_RATE else "PASS"


def _select(tp: TablePlan, cast: bool = True) -> str:
    cols = [f'TRY_CAST({p.expr} AS {p.cast_type}) AS "{p.target_col}"' if cast else f'{p.expr} AS "{p.target_col}"'
            for p in tp.columns]
    return f'SELECT {", ".join(cols)} FROM "{tp.source_table}"'


def _parallel(con, ver, tp: TablePlan, p: ColumnPlan, src: Side, tgt: Side) -> list[Result]:
    """Compare a migrated column with the mock conversion and say, in plain words, how they differ."""
    tt, c = tp.target_table, p.target_col
    k = tgt.schema[tt]["key"]
    if tt not in ver.available or c == k or c not in tgt.schema[tt]["columns"]:
        return []
    df = con.execute(f'SELECT m."{k}" AS k, m."{c}" AS sv, q."{c}" AS tv FROM "mg_{tt}" m '
                     f'JOIN p_{tt} q ON CAST(q."{k}" AS VARCHAR) = CAST(m."{k}" AS VARCHAR)').df()
    if df.empty:
        return [Result(tt, "mock conversion", "REVIEW", f"row {p.row.row_no}: no records line up with the mock conversion", c)]
    t_card = tgt.card(f"{tt}.{c}")
    s_card = src.card(p.row.source) if "+" not in (p.row.target or "") else t_card
    from .verify import _bool

    def norm(s):
        b = s.map(_bool)
        if s.notna().any() and b[s.notna()].notna().all():
            return b.astype(object)
        return s.map(lambda v: None if pd.isna(v) else str(v).strip())

    a, b_ = norm(df.sv), norm(df.tv)
    same = (a == b_) | (a.isna() & b_.isna())
    num = lambda x: pd.to_numeric(x.map(lambda v: None if isinstance(v, (bool, np.bool_)) else v), errors="coerce").astype(float)
    na, nb = num(df.sv), num(df.tv)
    bad = ~(same | ((na - nb).abs() < 0.011).fillna(False))
    rate = float(bad.mean())
    if rate <= REVIEW_RATE:
        return [Result(tt, "mock conversion", "PASS", f"row {p.row.row_no}: matches on {len(df):,} records", c)]
    kind = t_card.profile.get("kind")
    try:
        if t_card.family in ("date", "timestamp"):
            _, flags, why = ver._dates(df)
        elif kind == "bool":
            _, flags, why = ver._flags(df)
        elif kind == "numeric" and not t_card.is_identifier:
            _, flags, why = ver._numeric(df, s_card, t_card)
        else:
            _, flags, why = ver._codes(df, t_card)
    except Exception:          # diagnosis is best effort; the mismatch itself is what matters
        flags, why = [], ""
    ex = ", ".join(f"{a}->{b} (mock)" for a, b in df.loc[bad, ["sv", "tv"]].head(2).itertuples(index=False))
    return [Result(tt, "mock conversion", _status(rate, int(bad.sum())),
                   f"row {p.row.row_no}: differs on {rate:.1%} of {len(df):,} records"
                   + (f"; {why}" if why else "") + (f"; e.g. {ex}" if ex else "")
                   + ". If the acquirer recomputes this field, load the inputs and let it recompute", c)]


def rehearse(tables: list[TablePlan], src: Side, tgt: Side, out_dir: Path, parallel: str | Path | None = None) -> list[Result]:
    con, res = src.con, []
    ver = None
    if parallel:
        from .verify import Verifier
        ver = Verifier(src, tgt, parallel)
    mig = out_dir / "migrated"
    mig.mkdir(parents=True, exist_ok=True)
    keys = {t: tgt.schema[t]["key"] for t in tgt.schema}
    schema = {}
    for tp in tables:
        tt, st = tp.target_table, tp.source_table
        for p in tp.columns:                          # run each column alone so errors point at a workbook row
            try:
                con.execute(f'SELECT TRY_CAST({p.expr} AS {p.cast_type}) FROM "{st}" LIMIT 1')
            except Exception as e:
                res.append(Result(tt, "runs", "FAIL", f"row {p.row.row_no}: {str(e).splitlines()[0]}", p.target_col))
        if any(r.table == tt and r.check == "runs" for r in res):
            continue
        con.execute(f'CREATE OR REPLACE TABLE "mg_{tt}" AS {_select(tp)}')
        con.execute(f"COPY \"mg_{tt}\" TO '{(mig / f'{tt}.parquet').as_posix()}' (FORMAT PARQUET)")
        schema[tt] = {"key": keys[tt], "columns": {p.target_col: tgt.schema[tt]["columns"][p.target_col] for p in tp.columns}}
        n_src = con.execute(f'SELECT COUNT(*) FROM "{st}"').fetchone()[0]
        n_mig = con.execute(f'SELECT COUNT(*) FROM "mg_{tt}"').fetchone()[0]
        res.append(Result(tt, "row count", "PASS" if n_src == n_mig else "FAIL", f"{n_src:,} source rows, {n_mig:,} migrated"))
        k = keys[tt]
        nulls, dups = con.execute(f'SELECT COUNT(*) - COUNT("{k}"), COUNT("{k}") - COUNT(DISTINCT "{k}") FROM "mg_{tt}"').fetchone()
        res.append(Result(tt, "key integrity", "PASS" if nulls == dups == 0 else "FAIL",
                          f"{nulls:,} null keys, {dups:,} duplicate keys", k))
        live = f'(SELECT CAST("{k}" AS VARCHAR) AS k FROM tgt_live."{tt}")'
        coll = _scalar(con, tgt, f'SELECT COUNT(*) FROM "mg_{tt}" m WHERE CAST(m."{k}" AS VARCHAR) IN {live}')
        if coll is not None:
            res.append(Result(tt, "key collision", "PASS" if coll == 0 else "FAIL",
                              f"{coll:,} migrated keys already exist in the acquirer's {tt}" + (
                                  "; re-key the acquired records (offset or new surrogate) before loading" if coll else ""), k))
        for p in tp.columns:
            c = p.target_col
            pre = f"({p.expr})"
            cast_bad, introduced = con.execute(
                f'SELECT COUNT(*) FILTER (WHERE {pre} IS NOT NULL AND TRY_CAST({pre} AS {p.cast_type}) IS NULL), '
                f'COUNT(*) FILTER (WHERE TRY_CAST({pre} AS {p.cast_type}) IS NULL) FROM "{st}"').fetchone()
            if cast_bad:
                res.append(Result(tt, "cast", _status(cast_bad / max(n_src, 1)),
                                  f"row {p.row.row_no}: {cast_bad:,} values do not fit {p.cast_type}", c))
            if p.crosswalk:
                keys_ = ", ".join(f"'{x}'" for x in p.crosswalk)
                miss = con.execute(f'SELECT CAST({p.base} AS VARCHAR) v, COUNT(*) n FROM "{st}" WHERE {p.base} IS NOT NULL '
                                   f'AND CAST({p.base} AS VARCHAR) NOT IN ({keys_}) GROUP BY 1 ORDER BY 2 DESC').fetchall()
                n_miss = sum(n for _, n in miss)
                res.append(Result(tt, "crosswalk", _status(n_miss / max(n_src, 1)) if n_miss else "PASS",
                                  f"row {p.row.row_no}: " + (f"{n_miss:,} rows have codes with no mapping: "
                                  + ", ".join(str(v) for v, _ in miss[:6]) if n_miss else "every source code mapped"), c))
            s_col = p.row.source.split(".")[1] if "+" not in (p.row.target or "") else None
            if s_col:
                src_nulls = con.execute(f'SELECT COUNT(*) - COUNT("{s_col}") FROM "{st}"').fetchone()[0]
                extra = introduced - src_nulls - cast_bad
                if extra > 0:
                    res.append(Result(tt, "nulls introduced", _status(extra / max(n_src, 1)),
                                      f"row {p.row.row_no}: transform turned {extra:,} values into NULL", c))
            res += _conformance(con, tgt, tt, c, p)
            if ver:
                res += _parallel(con, ver, tp, p, src, tgt)
    res += _orphans(con, tgt, tables)
    (mig / "schema.json").write_text(json.dumps(schema, indent=2))
    return res


def _scalar(con, tgt: Side, sql: str):
    """Run a query that reads the acquirer's live tables (attached as tgt_live)."""
    try:
        return con.execute(sql).fetchone()[0]
    except Exception:
        return None


def _attach_live(src: Side, tgt: Side) -> None:
    src.con.execute("CREATE SCHEMA IF NOT EXISTS tgt_live")
    for t in tgt.schema:
        f = (tgt.path / f"{t}.parquet").as_posix()
        src.con.execute(f"CREATE OR REPLACE VIEW tgt_live.\"{t}\" AS SELECT * FROM '{f}'")


def _conformance(con, tgt: Side, tt: str, c: str, p: ColumnPlan) -> list[Result]:
    """Do the migrated values look like what the acquirer's system already holds?"""
    card = tgt.card(f"{tt}.{c}")
    if card.is_identifier:
        return []
    prof = card.profile
    if prof.get("kind") == "categorical" and prof.get("freqs"):
        dom = ", ".join("'" + str(x).replace("'", "''") + "'" for x in prof["freqs"])
        bad, n = con.execute(f'SELECT COUNT(*) FILTER (WHERE "{c}" IS NOT NULL AND CAST("{c}" AS VARCHAR) NOT IN ({dom})), '
                             f'COUNT(*) FROM "mg_{tt}"').fetchone()
        if bad:
            return [Result(tt, "target code set", _status(bad / max(n, 1)),
                           f"row {p.row.row_no}: {bad:,} values are not codes the acquirer uses "
                           f"({', '.join(map(str, list(prof['freqs'])[:6]))})", c)]
    if prof.get("kind") == "bool":
        live = con.execute(f'SELECT AVG(CASE WHEN CAST("{c}" AS VARCHAR) IN (\'true\',\'Y\',\'1\') THEN 1.0 ELSE 0 END) '
                           f'FROM tgt_live."{tt}"').fetchone()[0]
        mig = con.execute(f'SELECT AVG(CASE WHEN CAST("{c}" AS VARCHAR) IN (\'true\',\'Y\',\'1\') THEN 1.0 ELSE 0 END) '
                          f'FROM "mg_{tt}"').fetchone()[0]
        n_live = con.execute(f'SELECT COUNT("{c}") FROM tgt_live."{tt}"').fetchone()[0]
        if n_live >= 50 and live is not None and mig is not None and abs(live - mig) > 0.08 and max(live, mig) / max(min(live, mig), 1e-9) > 1.5:
            return [Result(tt, "flag rate", "REVIEW", f"row {p.row.row_no}: {mig:.0%} of migrated records are flagged vs "
                           f"{live:.0%} in the acquirer's book; confirm both banks set the flag on the same event", c)]
    if prof.get("kind") == "numeric" and len(prof.get("values", [])) >= 50:
        lo, hi = np.quantile(prof["values"], 0.001), np.quantile(prof["values"], 0.999)
        bad, n = con.execute(f'SELECT COUNT(*) FILTER (WHERE "{c}" < {lo - abs(lo) * 0.5} OR "{c}" > {hi * 1.5}), '
                             f'COUNT("{c}") FROM "mg_{tt}"').fetchone()
        if n and bad / n > 0.05:
            return [Result(tt, "target range", "FAIL", f"row {p.row.row_no}: {bad / n:.0%} of values fall outside the "
                           f"acquirer's range ({lo:,.4g} to {hi:,.4g}); check units and scale", c)]
    return []


def _orphans(con, tgt: Side, tables: list[TablePlan]) -> list[Result]:
    """Foreign keys: a migrated column named like another table's key must point at a row that exists."""
    res, loaded = [], {tp.target_table for tp in tables}
    owners: dict[str, list] = {}
    for t in tgt.schema:
        owners.setdefault(tgt.schema[t]["key"], []).append(t)
    for tp in tables:
        for p in tp.columns:
            parents = owners.get(p.target_col, [])
            if p.target_col == tgt.schema[tp.target_table]["key"] or len(parents) != 1:
                continue                     # its own key, or a key name several tables share: not a clear FK
            parent = parents[0]
            pool = [f'SELECT CAST("{p.target_col}" AS VARCHAR) k FROM tgt_live."{parent}"']
            if parent in loaded:
                pool.append(f'SELECT CAST("{p.target_col}" AS VARCHAR) k FROM "mg_{parent}"')
            n = _scalar(con, tgt, f'SELECT COUNT(*) FROM "mg_{tp.target_table}" WHERE "{p.target_col}" IS NOT NULL AND '
                                  f'CAST("{p.target_col}" AS VARCHAR) NOT IN ({" UNION ALL ".join(pool)})')
            if n is not None:
                res.append(Result(tp.target_table, "orphans", "PASS" if n == 0 else "FAIL",
                                  f"{n:,} rows point at a {parent} that does not exist", p.target_col))
    return res


# ------------------------------------------------------------------ emit
def migration_sql(tables: list[TablePlan], dialect: str = "snowflake", source_prefix: str = "",
                  target_prefix: str = "", header: str = "") -> str:
    out = [header] if header else []
    for tp in tables:
        lines = [f"-- {tp.source_table} -> {tp.target_table}"]
        for p in tp.columns:
            who = ", ".join(v for v in p.row.signoffs.values() if v)
            lines.append(f"--   {p.target_col}: workbook row {p.row.row_no} ({p.row.source}, {p.row.decision}"
                         + (f", signed off by {who}" if who else "") + ")")
        cols = ", ".join(f'"{p.target_col}"' for p in tp.columns)
        sel = _select(tp).replace(f'FROM "{tp.source_table}"', f"FROM {source_prefix}{tp.source_table}")
        sql = f"INSERT INTO {target_prefix}{tp.target_table} ({cols}) {sel}"
        sql = sqlglot.transpile(sql, read="duckdb", write=dialect, pretty=True)[0]
        out.append("\n".join(lines) + "\n" + sql + ";\n")
    return "\n".join(out)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_reconciliation(issues: list[Issue], results: list[Result], tables: list[TablePlan], path: Path) -> Path:
    wb = Workbook()
    fills = {"FAIL": "FDE2E1", "BLOCK": "FDE2E1", "REVIEW": "FEF3C7", "WARN": "FEF3C7", "PASS": "DCFCE7"}
    sheets = [
        ("Reconciliation", ["table", "column", "check", "status", "detail"],
         [[r.table, r.column, r.check, r.status, r.detail] for r in results]),
        ("Gate", ["workbook row", "attribute", "severity", "issue"],
         [[i.row_no, i.source, i.severity, i.message] for i in issues]),
        ("Lineage", ["target", "source", "workbook row", "decision", "expression", "cast", *SIGNOFFS],
         [[f"{tp.target_table}.{p.target_col}", p.row.source, p.row.row_no, p.row.decision, p.expr, p.cast_type,
           *[p.row.signoffs[k] for k in SIGNOFFS]] for tp in tables for p in tp.columns]),
    ]
    for i, (name, head, rows) in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet(name)
        ws.title = name
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F2A37")
        for r in rows:
            ws.append(r)
            st = r[3] if name == "Reconciliation" else r[2] if name == "Gate" else None
            if st in fills:
                ws.cell(ws.max_row, 4 if name == "Reconciliation" else 3).fill = PatternFill("solid", fgColor=fills[st])
        for col, w in zip("ABCDEFGHIJ", (22, 22, 18, 12, 90, 14, 16, 16, 16, 16)):
            ws.column_dimensions[col].width = w
    wb.save(path)
    return path


# ------------------------------------------------------------------ orchestrate
@dataclass
class Outcome:
    status: str             # BLOCKED, FAILED, REVIEW, PASSED
    issues: list
    results: list
    tables: list
    out_dir: Path
    loaded: bool = False

    def summary(self) -> str:
        b = sum(i.severity == "BLOCK" for i in self.issues)
        n = {s: sum(r.status == s for r in self.results) for s in ("FAIL", "REVIEW", "PASS")}
        cols = sum(len(t.columns) for t in self.tables)
        return (f"{self.status}: {b} gate blocks, {cols} columns in {len(self.tables)} tables; reconciliation "
                f"{n['FAIL']} FAIL, {n['REVIEW']} REVIEW, {n['PASS']} PASS" + ("; loaded into target" if self.loaded else ""))


def apply(workbook: str | Path, src: Side, tgt: Side, out_dir: str | Path, dialect: str = "snowflake",
          source_prefix: str = "", target_prefix: str = "", allow_partial: bool = False,
          load_into: str | Path | dict | None = None, force: bool = False,
          parallel: str | Path | None = None) -> Outcome:
    meta = src.path / "_ingest.json"
    if load_into is not None and meta.exists() and json.loads(meta.read_text()).get("sampled"):
        raise ValueError("the source was ingested as a row sample; do not load a sample into the target. "
                         "Run migration.sql inside the warehouse, or ingest with a larger sample_rows")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    workbook = Path(workbook)
    rows = read_workbook(workbook)
    tables, issues = gate(rows, src, tgt, allow_partial)
    results: list[Result] = []
    if any(i.severity == "BLOCK" for i in issues):
        status = "BLOCKED"
    else:
        _attach_live(src, tgt)
        results = rehearse(tables, src, tgt, out, parallel)
        status = ("FAILED" if any(r.status == "FAIL" for r in results)
                  else "REVIEW" if any(r.status == "REVIEW" for r in results) else "PASSED")
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    header = (f"-- MergeGuard {__version__} migration, generated {stamp}\n"
              f"-- workbook {workbook.name} sha256 {_sha(workbook)}\n-- status {status}\n")
    sql_path = out / "migration.sql"
    if status != "BLOCKED":
        sql_path.write_text(migration_sql(tables, dialect, source_prefix, target_prefix, header))
    write_reconciliation(issues, results, tables, out / "reconciliation.xlsx")
    outcome = Outcome(status, issues, results, tables, out)
    if load_into is not None:
        if status in ("PASSED", "REVIEW") or (force and status == "FAILED"):
            from .connectors import load_tables
            load_tables(load_into, {tp.target_table: out / "migrated" / f"{tp.target_table}.parquet" for tp in tables})
            outcome.loaded = True
    files = {}
    for p in [workbook, *sorted(src.path.glob("*.parquet")), src.path / "schema.json", tgt.path / "schema.json",
              *sorted(out.rglob("*.parquet")), sql_path, out / "reconciliation.xlsx"]:
        if p.exists():
            files[str(p)] = _sha(p)
    audit = {"tool": f"mergeguard {__version__}", "generated_utc": stamp, "status": status, "loaded": outcome.loaded,
             "forced": bool(force and outcome.loaded and status == "FAILED"),
             "workbook": {"path": str(workbook), "sha256": _sha(workbook)}, "files_sha256": files,
             "gate": [asdict(i) for i in issues], "reconciliation": [asdict(r) for r in results],
             "lineage": [{"target": f"{tp.target_table}.{p.target_col}", "source": p.row.source, "row": p.row.row_no,
                          "decision": p.row.decision, "expression": p.expr, "cast": p.cast_type,
                          "high_risk": p.row.high_risk, "signoffs": p.row.signoffs} for tp in tables for p in tp.columns]}
    body = json.dumps(audit, indent=2, default=str)
    (out / "audit.json").write_text(body)
    (out / "audit.sha256").write_text(hashlib.sha256(body.encode()).hexdigest() + "  audit.json\n")
    return outcome
