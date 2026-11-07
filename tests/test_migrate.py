import hashlib
import json

import pandas as pd
import pytest
import sqlalchemy as sa
import sqlglot
from openpyxl import load_workbook

from mergeguard.bench.round4 import SPEC_L
from mergeguard.bench.spec import generate_spec
from mergeguard.cards import load_side
from mergeguard.connectors import write_folder
from mergeguard.match import match_sides
from mergeguard.migrate import apply
from mergeguard.report import STRESS, write_mapping

SIGN = ["source_ops_signoff", "target_ops_signoff", "finance_risk_signoff", "data_profiling_signoff"]


def _sides(tmp_path, live_ids=(900, 901)):
    src = {"acct": pd.DataFrame({"acct_no": [1, 2, 3, 4], "bal_cents": [1050, 2000, None, 99900],
                                 "stat_cd": ["A", "A", "C", "Z"], "full_nm": ["Ann Lee", "Bo Diaz", "Cy Wu", "Di Ng"]})}
    tgt = {"account": pd.DataFrame({"account_id": list(live_ids), "balance": [12.5, 30.0], "status": ["ACTIVE", "CLOSED"],
                                    "first_name": ["X", "Y"], "last_name": ["P", "Q"]})}
    s = write_folder(tmp_path / "src", src, {"acct": {"key": "acct_no", "columns": {
        "bal_cents": {"type": "NUMBER(12)", "description": "Balance in cents"}}}}, {})
    t = write_folder(tmp_path / "tgt", tgt, {"account": {"key": "account_id", "columns": {
        "balance": {"type": "NUMBER(12,2)", "description": "Balance in dollars"}}}}, {})
    return load_side(s, "s"), load_side(t, "t")


def _workbook(tmp_path, src, tgt, edits: dict):
    """Write the review workbook, then fill it like an analyst: edits[source] = {column: value}."""
    path = write_mapping(match_sides(src, tgt), src, tgt, tmp_path / "review.xlsx")
    wb = load_workbook(path)
    ws = wb["Mapping"]
    h = {c.value: i + 1 for i, c in enumerate(ws[1])}
    for r in range(2, ws.max_row + 1):
        for k, v in edits.get(ws.cell(r, h["source_attribute"]).value, {}).items():
            ws.cell(r, h[k]).value = v
    wb.save(path)
    return path


def _ok(target, transform=None, **kw):
    d = {"decision": "Accept", "target_attribute": target, "transform": transform, **{k: "Same" for k, _ in STRESS}}
    d.update(kw)
    return d


def _signed(target, transform=None, **kw):
    return _ok(target, transform, **{k: "J. Doe" for k in SIGN}, **kw)


def test_unreviewed_workbook_is_blocked(tmp_path):
    src, tgt = _sides(tmp_path)
    wb = _workbook(tmp_path, src, tgt, {})
    o = apply(wb, src, tgt, tmp_path / "run")
    assert o.status == "BLOCKED"
    assert not (tmp_path / "run" / "migration.sql").exists()
    assert any("no decision" in i.message for i in o.issues)
    assert json.loads((tmp_path / "run" / "audit.json").read_text())["status"] == "BLOCKED"


def test_gate_rules(tmp_path):
    src, tgt = _sides(tmp_path)
    wb = _workbook(tmp_path, src, tgt, {
        "acct.acct_no": _ok("account.account_id"),
        "acct.bal_cents": _ok("account.balance", "bal_cents / 100", sign_scale="Differs"),     # high risk, unsigned
        "acct.stat_cd": _ok("account.status", "UPPER(no_such_col)"),
        "acct.full_nm": _ok("account.first_name+account.last_name", "first_name = SPLIT_PART(full_nm, ' ', 1)"),
    })
    o = apply(wb, src, tgt, tmp_path / "run")
    msgs = " | ".join(i.message for i in o.issues if i.severity == "BLOCK")
    assert o.status == "BLOCKED"
    assert "missing sign-off" in msgs
    assert "no_such_col" in msgs
    assert "for last_name" in msgs


def test_migrates_reconciles_and_audits(tmp_path):
    src, tgt = _sides(tmp_path)
    wb = _workbook(tmp_path, src, tgt, {
        "acct.acct_no": _ok("account.account_id", "acct_no + 1000"),                 # re-key away from live ids
        "acct.bal_cents": _signed("account.balance", "bal_cents / 100", sign_scale="Differs"),
        "acct.stat_cd": _ok("account.status", "as is", value_crosswalk="A->ACTIVE, C->CLOSED"),
        "acct.full_nm": _ok("account.first_name+account.last_name",
                            "first_name = SPLIT_PART(full_nm, ' ', 1); last_name = SPLIT_PART(full_nm, ' ', 2)"),
    })
    o = apply(wb, src, tgt, tmp_path / "run")
    out = tmp_path / "run"
    import duckdb
    df = duckdb.sql(f"SELECT * FROM '{out / 'migrated' / 'account.parquet'}' ORDER BY account_id").df()
    assert list(df.account_id) == [1001, 1002, 1003, 1004]
    assert df.balance.iloc[0] == pytest.approx(10.5) and pd.isna(df.balance.iloc[2])
    assert list(df.first_name) == ["Ann", "Bo", "Cy", "Di"]
    xw = next(r for r in o.results if r.check == "crosswalk")
    assert xw.status == "FAIL" and "Z" in xw.detail                                 # unmapped code caught
    assert any(r.check == "key collision" and r.status == "PASS" for r in o.results)
    sql = (out / "migration.sql").read_text()
    assert "workbook row" in sql and "signed off by J. Doe" in sql
    sqlglot.parse(sql, read="snowflake")
    audit = json.loads((out / "audit.json").read_text())
    assert (out / "audit.sha256").read_text().split()[0] == hashlib.sha256((out / "audit.json").read_bytes()).hexdigest()
    assert audit["workbook"]["sha256"] == hashlib.sha256(wb.read_bytes()).hexdigest()
    assert {x["target"] for x in audit["lineage"]} >= {"account.balance", "account.first_name"}


def test_key_collision_and_load_gating(tmp_path):
    src, tgt = _sides(tmp_path, live_ids=(3, 4))
    edits = {"acct.acct_no": _ok("account.account_id"),
             "acct.bal_cents": _signed("account.balance", "bal_cents / 100", sign_scale="Differs"),
             "acct.stat_cd": _ok("account.status", value_crosswalk="A->ACTIVE, C->CLOSED, Z->CLOSED"),
             "acct.full_nm": {"decision": "Skip"}}
    db = f"sqlite:///{tmp_path / 'core.db'}"
    eng = sa.create_engine(db)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE account (account_id INTEGER PRIMARY KEY, balance NUMERIC, status TEXT, "
                          "first_name TEXT, last_name TEXT)")
    target_cfg = {"connector": "sql", "url": db}
    o = apply(_workbook(tmp_path, src, tgt, edits), src, tgt, tmp_path / "run1", load_into=target_cfg)
    assert any(r.check == "key collision" and r.status == "FAIL" for r in o.results)
    assert o.status == "FAILED" and not o.loaded
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT COUNT(*) FROM account").scalar() == 0
    edits["acct.acct_no"] = _ok("account.account_id", "acct_no + 1000")
    o = apply(_workbook(tmp_path, src, tgt, edits), src, tgt, tmp_path / "run2", load_into=target_cfg)
    assert o.status == "PASSED" and o.loaded
    with eng.connect() as c:
        assert c.exec_driver_sql("SELECT COUNT(*), SUM(balance) FROM account").one() == (4, pytest.approx(1029.5))


def test_mock_conversion_catches_computed_traps(tmp_path):
    """Scenario L, analyst signs everything without reading: the mock-conversion comparison still stops it."""
    d = generate_spec(SPEC_L, tmp_path / "L", seed=11, n_acquirer=600, n_acquired=400)
    src, tgt = load_side(d / "acquired", "s", "oracle"), load_side(d / "acquirer", "t")
    gt = {a["source"]: a for a in json.loads((d / "ground_truth.json").read_text())["attributes"]}
    edits = {s: (_signed(a["target"]) if a["target"] else {"decision": "Skip"}) for s, a in gt.items()}
    o = apply(_workbook(tmp_path, src, tgt, edits), src, tgt, tmp_path / "run", parallel=d / "parallel")
    assert o.status == "FAILED"
    loaded = set(json.loads((d / "scenario.json").read_text())["loaded"])
    computed_traps = {a["target"] for a in gt.values() if a["target"] and a["conflicts"]} - loaded
    failed = {f"{r.table}.{r.column}" for r in o.results if r.status == "FAIL"}
    clean = {a["target"] for a in gt.values() if a["target"] and not a["conflicts"]}
    assert len(computed_traps & failed) >= len(computed_traps) - 1
    assert not (clean & failed - loaded)


def test_shared_key_name_is_not_an_orphan(tmp_path):
    src = {"a": pd.DataFrame({"loan_no": [1, 2], "amt": [5.0, 6.0]})}
    tgt = {"auto_loan": pd.DataFrame({"loan_id": [90], "amt": [1.0]}),
           "student_loan": pd.DataFrame({"loan_id": [91], "amt": [2.0]})}
    s = load_side(write_folder(tmp_path / "s", src, {"a": {"key": "loan_no"}}, {}), "s")
    t = load_side(write_folder(tmp_path / "t", tgt, {"auto_loan": {"key": "loan_id"}, "student_loan": {"key": "loan_id"}}, {}), "t")
    wb = _workbook(tmp_path, s, t, {"a.loan_no": _ok("auto_loan.loan_id"), "a.amt": _ok("auto_loan.amt", "as is")})
    o = apply(wb, s, t, tmp_path / "run")
    assert not any(r.check == "orphans" for r in o.results), o.results
