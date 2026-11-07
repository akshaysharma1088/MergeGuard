import json
import sys
import types

import duckdb
import pandas as pd
import sqlalchemy as sa

from mergeguard.bench.generate import generate
from mergeguard.cards import load_side
from mergeguard.connectors import _view_derivations, ingest, read_dictionary
from mergeguard.match import match_sides


def _bank():
    acct = pd.DataFrame({"ACCT_NO": [1, 2, 3, 4], "CUR_BAL": [10.5, 20.25, 0.0, 99.99],
                         "OPEN_DT": pd.to_datetime(["2020-01-01", "2021-05-03", "2019-07-09", "2022-02-02"]).date,
                         "STAT_CD": ["A", "A", "C", "I"]})
    ln = pd.DataFrame({"LN_NO": [10, 11], "ACCT_NO": [1, 2], "INT_RT": [5.25, 6.5]})
    dic = pd.DataFrame({"Table Name": ["ACCT", "ACCT", "ACCT", "LN"], "Field": ["ACCT_NO", "CUR_BAL", "STAT_CD", "INT_RT"],
                        "Data Type": ["NUMBER(10)", "NUMBER(15,2)", "CHAR(1)", "NUMBER(6,4)"],
                        "Business Definition": ["Account number", "Current balance incl. holds", "Status", "Rate in percent"],
                        "PK": ["Y", "", "", ""]})
    return acct, ln, dic


def test_dictionary_headers_are_flexible(tmp_path):
    _, _, dic = _bank()
    dic.to_csv(tmp_path / "d.csv", index=False)
    d = read_dictionary(tmp_path / "d.csv")
    assert list(d.columns[:6]) == ["table", "column", "type", "description", "key", "derivation"] or {"table", "column"} <= set(d.columns)
    assert d.loc[d.column == "CUR_BAL", "description"].iat[0] == "Current balance incl. holds"


def test_csv_with_excel_dictionary(tmp_path):
    acct, ln, dic = _bank()
    (tmp_path / "data").mkdir()
    acct.to_csv(tmp_path / "data" / "ACCT.csv", index=False)
    ln.to_csv(tmp_path / "data" / "LN.csv", index=False)
    dic.to_excel(tmp_path / "dict.xlsx", index=False)
    cfg = tmp_path / "bank.yml"
    cfg.write_text("connector: csv\npath: data\ndictionary: dict.xlsx\nkeys: {LN: LN_NO}\n")
    out = ingest(cfg, tmp_path / "out")
    schema = json.loads((out / "schema.json").read_text())
    assert schema["ACCT"]["key"] == "ACCT_NO" and schema["LN"]["key"] == "LN_NO"
    assert schema["ACCT"]["columns"]["CUR_BAL"] == {"type": "NUMBER(15,2)", "description": "Current balance incl. holds"}
    assert schema["ACCT"]["columns"]["OPEN_DT"]["type"].startswith("VARCHAR") or schema["ACCT"]["columns"]["OPEN_DT"]["type"] == "DATE"
    side = load_side(out, "bank")
    assert side.card("ACCT.CUR_BAL").family == "decimal"


def test_excel_workbook_with_dictionary_sheet(tmp_path):
    acct, ln, dic = _bank()
    with pd.ExcelWriter(tmp_path / "bank.xlsx") as w:
        acct.to_excel(w, sheet_name="ACCT", index=False)
        ln.to_excel(w, sheet_name="LN", index=False)
        dic.to_excel(w, sheet_name="Data Dictionary", index=False)
    out = ingest({"connector": "excel", "path": str(tmp_path / "bank.xlsx")}, tmp_path / "out")
    schema = json.loads((out / "schema.json").read_text())
    assert set(schema) == {"ACCT", "LN"}
    assert schema["LN"]["columns"]["INT_RT"]["description"] == "Rate in percent"


def test_sql_database_with_view(tmp_path):
    acct, ln, _ = _bank()
    url = f"sqlite:///{tmp_path / 'bank.db'}"
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE ACCT (ACCT_NO INTEGER PRIMARY KEY, CUR_BAL NUMERIC(15,2), OPEN_DT DATE, STAT_CD CHAR(1))")
        acct.to_sql("ACCT", c, if_exists="append", index=False)
        c.exec_driver_sql("CREATE VIEW ACCT_V AS SELECT ACCT_NO, CUR_BAL * 100 AS CUR_BAL_CENTS FROM ACCT")
    out = ingest({"connector": "sql", "url": url}, tmp_path / "out")
    schema = json.loads((out / "schema.json").read_text())
    der = json.loads((out / "derivations.json").read_text())
    assert schema["ACCT"]["key"] == "ACCT_NO"
    assert "ACCT_V.CUR_BAL_CENTS" in der and "ACCT_V.ACCT_NO" not in der


def test_snowflake_connector_reads_catalog(tmp_path, monkeypatch):
    class Cur:
        def __init__(self):
            self.description, self._rows = [], []

        def execute(self, sql, params=None):
            if "INFORMATION_SCHEMA.COLUMNS" in sql:
                self._rows = [("ACCT", "ACCT_NO", "NUMBER", 10, 0, None, "Account number"),
                              ("ACCT", "CUR_BAL", "NUMBER", 15, 2, None, "Current balance"),
                              ("ACCT", "STAT_CD", "TEXT", None, None, 1, None)]
            elif sql.startswith("SHOW PRIMARY KEYS"):
                self.description = [("created_on",), ("database_name",), ("schema_name",), ("table_name",),
                                    ("column_name",), ("key_sequence",)]
                self._rows = [(None, "CORE", "LENDING", "ACCT", "ACCT_NO", 1)]
            elif "INFORMATION_SCHEMA.VIEWS" in sql:
                self._rows = []
            elif "SAMPLE" in sql:
                from decimal import Decimal
                self.description = [("ACCT_NO",), ("CUR_BAL",), ("STAT_CD",)]
                self._rows = [(Decimal(1), Decimal("10.50"), "A"), (Decimal(2), Decimal("20.25"), "C")]
            return self

        def fetchall(self):
            return self._rows

        def close(self):
            pass

    class Con:
        def cursor(self):
            return Cur()

        def close(self):
            pass

    calls = {}
    fake = types.ModuleType("snowflake.connector")
    fake.connect = lambda **kw: calls.update(kw) or Con()
    monkeypatch.setitem(sys.modules, "snowflake.connector", fake)
    monkeypatch.setitem(sys.modules, "snowflake", types.ModuleType("snowflake"))
    sys.modules["snowflake"].connector = fake
    monkeypatch.setenv("SF_PW", "secret")
    out = ingest({"connector": "snowflake", "account": "acme", "user": "u", "password": "${SF_PW}",
                  "database": "CORE", "schema": "LENDING"}, tmp_path / "out")
    schema = json.loads((out / "schema.json").read_text())
    assert calls["password"] == "secret"
    assert schema["ACCT"]["key"] == "ACCT_NO"
    assert schema["ACCT"]["columns"]["CUR_BAL"] == {"type": "NUMBER(15,2)", "description": "Current balance"}
    card = load_side(out, "sf").card("ACCT.CUR_BAL")
    assert card.family == "decimal"


def test_view_derivation_parsing():
    der = _view_derivations("V", "CREATE VIEW V AS SELECT a.ID, a.X + a.Y AS TOTAL FROM A a", "snowflake")
    assert list(der) == ["V.TOTAL"]


def test_same_mapping_through_a_database(tmp_path):
    """A bank read from SQL (with its dictionary) maps exactly like the original files."""
    d = generate(tmp_path / "mb", seed=5, n_acquirer=600, n_acquired=400)
    folders = {}
    for side in ("acquired", "acquirer"):
        schema = json.loads((d / side / "schema.json").read_text())
        url = f"sqlite:///{tmp_path / (side + '.db')}"
        eng = sa.create_engine(url)
        rows = []
        with eng.begin() as c:
            for t, spec in schema.items():
                duckdb.sql(f"SELECT * FROM '{d / side / (t + '.parquet')}'").df().to_sql(t, c, index=False)
                for col, m in spec["columns"].items():
                    rows.append({"table": t, "column": col, "type": m["type"], "description": m["description"],
                                 "key": "Y" if col == spec["key"] else ""})
        pd.DataFrame(rows).to_csv(tmp_path / f"{side}_dict.csv", index=False)
        (tmp_path / f"{side}.yml").write_text(
            f"connector: sql\nurl: {url}\ndictionary: {side}_dict.csv\nderivations: {d / side / 'derivations.json'}\n")
        folders[side] = ingest(tmp_path / f"{side}.yml", tmp_path / f"in_{side}")
    direct = {m.source: m.target for m in match_sides(load_side(d / "acquired", "a", "oracle"), load_side(d / "acquirer", "t"))}
    via_db = {m.source: m.target for m in match_sides(load_side(folders["acquired"], "a", "oracle"), load_side(folders["acquirer"], "t"))}
    assert via_db == direct
