"""Trial-load verification: compare the same records on both sides and explain each difference.

Input: the acquired bank's tables (source) and a parallel run of the same accounts through the
acquirer's system (target schema, keyed by the source keys). For every mapped column pair,
MergeGuard joins source and parallel records on the key and classifies the disagreement:

    sign flip, constant factor (unit or scale), a missing or extra component (another source column
    explains the gap), one-sided gaps (netting, inclusion), constant or growing date lags, NULL vs
    placeholder dates, yes/no flips, code crosswalks, changed identifiers, larger or smaller counts.

Fields the target system only stores get a conformance check against the acquirer's existing data
instead: codes outside the target's code set, formats the target never uses, values out of range.

A check FAILS above 1% mismatched records (benign extract-timing noise sits well below that) and is
marked REVIEW between 0.1% and 1%. Nothing is ever passed to "Approved": PASS only means no evidence
of a problem in the trial load.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .cards import BOOL_VALUES, Side
from .match import Match

FAIL_RATE, REVIEW_RATE = 0.01, 0.001
FACTORS = {100.0: "scale", 0.01: "scale", 1000.0: "scale", 0.001: "scale", 12.0: "unit", 1 / 12: "unit", 2.0: "aggregation", 0.5: "aggregation"}


@dataclass
class Check:
    source: str
    target: str
    status: str                 # PASS / REVIEW / FAIL / SKIPPED
    mismatch_rate: float = 0.0
    records: int = 0
    flags: list = field(default_factory=list)
    diagnosis: str = ""
    edge_cases: list = field(default_factory=list)
    sql: str = ""


def _bool(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return BOOL_VALUES.get(str(v).upper())


def _shape(v) -> str:
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", str(v)))


class Verifier:
    def __init__(self, src: Side, tgt: Side, parallel_dir: str | Path):
        self.src, self.tgt = src, tgt
        self.con = src.con
        pdir = Path(parallel_dir)
        for t in tgt.schema:
            f = pdir / f"{t}.parquet"
            if f.exists():
                self.con.execute(f"CREATE OR REPLACE VIEW p_{t} AS SELECT * FROM '{f.as_posix()}'")
        self.available = {t for t in tgt.schema if (pdir / f"{t}.parquet").exists()}

    def pairs(self, s_q: str, t_q: str) -> pd.DataFrame:
        st, sc = s_q.split(".")
        tt, tc = t_q.split(".")
        sk, tk = self.src.schema[st]["key"], self.tgt.schema[tt]["key"]
        return self.con.execute(
            f'SELECT s."{sk}" AS k, s."{sc}" AS sv, p."{tc}" AS tv FROM "{st}" s JOIN p_{tt} p ON p."{tk}" = s."{sk}"').df()

    # ------------------------------------------------------------------ classifiers
    def _numeric(self, df, s_card, t_card) -> tuple[pd.Series, list, str]:
        sv = pd.to_numeric(df.sv, errors="coerce")
        tv = pd.to_numeric(df.tv, errors="coerce")
        both = sv.notna() & tv.notna()
        null_mismatch = sv.isna() != tv.isna()
        tol = np.maximum(0.011, 0.001 * tv.abs())
        bad = ((sv - tv).abs() > tol) & both | null_mismatch
        if bad.mean() <= FAIL_RATE:
            return bad, [], ""
        b = bad & both & (sv != 0)
        s_, t_ = sv[b], tv[b]
        if len(s_) and ((s_ + t_).abs() <= tol[b]).mean() > 0.9:
            return bad, ["sign"], "Target is the source with the sign flipped"
        if len(s_):
            ratio = (t_ / s_).replace([np.inf, -np.inf], np.nan).dropna()
            if len(ratio) and ratio.std() / max(abs(ratio.median()), 1e-9) < 0.02:
                r = float(ratio.median())
                for f, kind in FACTORS.items():
                    if abs(r / f - 1) < 0.02:
                        return bad, [kind], f"Target = source x {r:g} ({'units' if kind == 'unit' else kind})"
                return bad, ["scale"], f"Target = source x {r:.4g}"
        gap = (tv - sv)[bad & both]
        comp = self._component(df[bad & both], gap, s_card)
        if comp:
            return bad, ["inclusion"], comp
        if null_mismatch.mean() > FAIL_RATE and (bad & both).mean() <= FAIL_RATE:
            return bad, ["null_semantics"], "Missing values on one side where the other has values"
        ints = (sv.dropna() % 1 == 0).all() and (tv.dropna() % 1 == 0).all()
        if len(gap) and max((gap > 0).mean(), (gap < 0).mean()) >= 0.95:
            side = "larger" if (gap > 0).mean() >= 0.95 else "smaller"
            if ints:
                return bad, ["aggregation"], f"Target counts are always {side}: counted over a different scope"
            return bad, ["inclusion"], f"Target is always {side} than source: one side includes or nets components"
        return bad, ["definition"], "Values differ in both directions: different method or basis"

    def _component(self, rows, gap, s_card) -> str:
        """Another numeric column of the same source table equals the gap (holds, interest, fees)."""
        st, key = s_card.table, self.src.schema[s_card.table]["key"]
        cands = [c for c in self.src.cards if c.table == st and c.column != s_card.column
                 and c.profile.get("kind") == "numeric" and not c.is_identifier]
        if not cands or rows.empty:
            return ""
        keys = ",".join(str(int(k)) if isinstance(k, (int, np.integer, float)) else f"'{k}'" for k in rows.k.head(2000))
        other = self.con.execute(
            f'SELECT "{key}" AS k, {", ".join(f"""CAST("{c.column}" AS DOUBLE) AS "{c.column}" """ for c in cands)} '
            f'FROM "{st}" WHERE "{key}" IN ({keys})').df().set_index("k")
        g = pd.Series(gap.values, index=rows.k.values).head(2000)
        for c in cands:
            col = other[c.column].reindex(g.index).fillna(0)
            for sign, word in ((1, "excludes"), (-1, "includes")):
                if ((g - sign * col).abs() <= 0.011).mean() > 0.9:
                    return f"Source {word} {c.column}: target = source {'+' if sign > 0 else '-'} {c.column}"
        return ""

    def _dates(self, df) -> tuple[pd.Series, list, str]:
        sv = pd.to_datetime(df.sv, errors="coerce")
        tv = pd.to_datetime(df.tv, errors="coerce")
        s_sent = df.sv.astype(str).str.startswith(("2099", "9999", "1900-01-01"))
        t_sent = df.tv.astype(str).str.startswith(("2099", "9999", "1900-01-01"))
        lag = (sv.dt.normalize() - tv.dt.normalize()).dt.days
        bad = (lag.abs() > 0) | (sv.isna() != tv.isna()) | (s_sent != t_sent)
        if bad.mean() <= FAIL_RATE:
            return bad, [], ""
        if ((sv.isna() | s_sent) & tv.notna() & ~t_sent).mean() > FAIL_RATE:
            return bad, ["null_semantics"], "Source uses NULL or a placeholder date where the target has a real date"
        l = lag[bad & lag.notna()]
        if len(l):
            direction = "later" if (l > 0).mean() > 0.9 else "earlier" if (l < 0).mean() > 0.9 else "different"
            return bad, ["temporal"], (f"Source date is {direction} than target by {int(l.abs().median())} days "
                                       f"(median, range {int(l.min())} to {int(l.max())}): a different business event")
        return bad, ["temporal"], "Dates differ"

    def _flags(self, df) -> tuple[pd.Series, list, str]:
        tv = df.tv.map(_bool)
        sv = df.sv.map(_bool)
        if sv.isna().all():                                   # two-value code: best orientation
            vals = sorted(df.sv.dropna().astype(str).unique())
            a = df.sv.astype(str) == vals[0]
            sv = a if (a != tv).mean() <= (~a != tv).mean() else ~a
        bad = sv != tv
        if bad.mean() <= FAIL_RATE:
            return bad, [], ""
        more = "source marks more records" if (sv & ~tv.fillna(False)).sum() > (~sv.fillna(False) & tv).sum() else "target marks more records"
        return bad, ["population"], f"{bad.mean():.1%} of records flip ({more}): a different rule decides the flag"

    def _codes(self, df, t_card) -> tuple[pd.Series, list, str]:
        sv, tv = df.sv.astype(str), df.tv.astype(str)
        bad = sv != tv
        if bad.mean() <= FAIL_RATE:
            return bad, [], ""
        ct = pd.crosstab(sv, tv)
        purity = (ct.max(axis=1).sum() / ct.values.sum()) if ct.size else 0
        if purity >= 0.99:
            xw = {s: ct.loc[s].idxmax() for s in ct.index}
            return bad, ["code_set"], "Consistent crosswalk found: " + ", ".join(f"{k}->{v}" for k, v in list(xw.items())[:8])
        if t_card.is_identifier:
            return bad, ["identity"], "The same records carry different identifiers on each side"
        return bad, ["definition"], "Values differ with no consistent mapping: a different meaning"

    def _conformance(self, df, t_card) -> tuple[pd.Series, list, str]:
        """Loaded fields: do the loaded values look like anything the target system holds?"""
        tp = t_card.profile
        sv = df.sv
        kind = tp.get("kind")
        if kind == "categorical" and tp.get("freqs"):
            dom = set(map(str, tp["freqs"]))
            bad = sv.notna() & ~sv.astype(str).isin(dom)
            if bad.mean() > FAIL_RATE:
                return bad, ["code_set"], f"{bad.mean():.0%} of loaded values are not in the target code set ({', '.join(sorted(dom)[:6])})"
        if kind in ("text", "categorical"):
            t_shapes = self.tgt.con.execute(
                f'SELECT DISTINCT "{t_card.column}" FROM "{t_card.table}" LIMIT 500').df().iloc[:, 0].map(_shape)
            top = set(t_shapes.value_counts().head(5).index)
            bad = sv.notna() & ~sv.map(_shape).isin(top) if len(top) <= 3 else pd.Series(False, index=sv.index)
            if bad.mean() > FAIL_RATE:
                ex = next(iter(top))
                return bad, ["format"], f"Loaded values use a format the target never uses (target looks like {ex})"
        if kind == "numeric":
            v = pd.to_numeric(sv, errors="coerce")
            tv_ = tp["values"]
            if len(tv_):
                lo, hi = np.quantile(tv_, 0.001), np.quantile(tv_, 0.999)
                bad = v.notna() & ((v < lo - abs(lo) * 0.5) | (v > hi * 1.5))
                if bad.mean() > 0.05:
                    return bad, ["scale"], f"{bad.mean():.0%} of loaded values fall outside the target's range"
        return pd.Series(False, index=sv.index), [], ""

    # ------------------------------------------------------------------ run
    def check(self, m: Match) -> Check:
        if not m.target or "+" in m.target or m.target.split(".")[0] not in self.available:
            return Check(m.source, m.target or "", "SKIPPED", diagnosis="No trial-load data for this target")
        s_card, t_card = self.src.card(m.source), self.tgt.card(m.target)
        df = self.pairs(m.source, m.target)
        if df.empty:
            return Check(m.source, m.target, "SKIPPED", diagnosis="No matching records in the trial load")
        kind = t_card.profile.get("kind")
        if t_card.family in ("date", "timestamp"):
            bad, flags, why = self._dates(df)
        elif kind == "bool":
            bad, flags, why = self._flags(df)
        elif kind == "numeric" and not t_card.is_identifier:
            bad, flags, why = self._numeric(df, s_card, t_card)
        else:
            bad, flags, why = self._codes(df, t_card)
        if not flags and not (t_card.is_identifier or s_card.is_identifier):   # IDs are re-keyed, not range-checked
            cbad, cflags, cwhy = self._conformance(df, t_card)
            if cflags:
                bad, flags, why = cbad, cflags, cwhy
        rate = float(bad.mean())
        status = "FAIL" if flags and rate > FAIL_RATE else "REVIEW" if rate > REVIEW_RATE else "PASS"
        if status != "FAIL":
            flags, why = ([], why) if status == "PASS" else (flags, why or "A few records differ")
        return Check(m.source, m.target, status, round(rate, 4), len(df), flags, why,
                     [str(k) for k in df.k[bad].head(5)], _sql(m.source, m.target, self.src, self.tgt))

    def run(self, results: list[Match]) -> list[Check]:
        return [self.check(m) for m in results]


def _sql(s_q, t_q, src: Side, tgt: Side) -> str:
    st, sc = s_q.split(".")
    tt, tc = t_q.split(".")
    sk, tk = src.schema[st]["key"], tgt.schema[tt]["key"]
    return (f"SELECT COUNT(*) AS records_checked, SUM(CASE WHEN s.{sc} IS DISTINCT FROM t.{tc} THEN 1 ELSE 0 END) "
            f"AS mismatches FROM stg_src_{st.lower()} s JOIN stg_tgt_{tt.lower()} t ON t.{tk} = s.{sk}")


def scorecard_sql(checks: list[Check], prefix: str = "MG") -> str:
    """One UNION ALL scorecard, in the style of the practitioner profiling suite; Mapping_IDs match the workbook."""
    blocks = []
    for i, c in enumerate(checks, 1):
        if not c.sql:
            continue
        rule = c.diagnosis.replace("'", "''") or "Values must match on matched records"
        blocks.append(f"    SELECT '{prefix}-{i:04d}' AS mapping_id, '{c.source} -> {c.target}' AS field_pair,\n"
                      f"           '{rule}' AS diagnostic_rule, x.records_checked, x.mismatches\n"
                      f"    FROM ({c.sql}) x")
    return ("-- MergeGuard trial-load scorecard (generated). Replace stg_src_/stg_tgt_ with your staging tables.\n"
            "WITH checks AS (\n" + "\n    UNION ALL\n".join(blocks) + "\n)\n"
            "SELECT *, CASE WHEN mismatches * 1.0 / NULLIF(records_checked, 0) > 0.01\n"
            "            THEN 'FAIL - BLOCK MIGRATION' ELSE 'PASS - READY FOR SME SIGN-OFF' END AS verdict\n"
            "FROM checks ORDER BY mismatches DESC;\n")
