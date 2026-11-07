"""Connectors: read a bank's tables and data dictionary from where they live, write a MergeGuard folder.

Every connector produces the same folder (schema.json, one Parquet sample per table, derivations.json),
so profiling, verification and the workbook never change. Configure a source in YAML:

    name: acquired
    connector: snowflake            # snowflake | sql | excel | csv | parquet
    sample_rows: 20000
    account: ${SNOWFLAKE_ACCOUNT}    # ${VAR} reads an environment variable; keep secrets out of the file
    user: ${SNOWFLAKE_USER}
    password: ${SNOWFLAKE_PASSWORD}  # or authenticator: externalbrowser
    warehouse: ANALYTICS_WH
    database: CORE
    schema: LENDING
    tables: [ACCT, LN_MSTR]          # optional, default every table and view in the schema
    dictionary: dictionary.xlsx      # optional, any connector: types, descriptions, keys, derivations
    keys: {ACCT: ACCT_NO}            # optional key overrides

Only a sample of rows is read, and it stays on the machine running MergeGuard.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd

# ---------------------------------------------------------------- config


def _expand(v):
    if isinstance(v, str):
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: os.environ.get(m.group(1), ""), v)
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


def load_config(path: str | Path) -> dict:
    import yaml
    path = Path(path)
    cfg = _expand(yaml.safe_load(path.read_text()) or {})
    cfg["_base"] = path.parent
    return cfg


def _path(cfg: dict, key: str) -> Path | None:
    v = cfg.get(key)
    if not v:
        return None
    p = Path(v)
    return p if p.is_absolute() else Path(cfg.get("_base", ".")) / p


# ---------------------------------------------------------------- data dictionary

HEADERS = {
    "table": ("table", "table_name", "entity", "tablename", "source_table"),
    "column": ("column", "column_name", "field", "field_name", "attribute", "columnname", "element"),
    "type": ("type", "data_type", "datatype", "sql_type", "format"),
    "description": ("description", "definition", "business_definition", "business_rule", "meaning", "comment", "comments"),
    "key": ("key", "pk", "primary_key", "is_key", "is_pk"),
    "derivation": ("derivation", "derivation_sql", "logic", "transformation", "sql", "rule_sql"),
}


def _norm(h) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def read_dictionary(path: str | Path, sheet: str | None = None) -> pd.DataFrame:
    """A data dictionary in Excel or CSV, with any common header names, as table/column/type/description/key/derivation."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None if sheet is None else sheet)
        df = sheets if isinstance(sheets, pd.DataFrame) else next(
            (s for s in sheets.values() if {"table", "column"} <= set(_dictionary_roles(s))), None)
        if df is None:
            raise ValueError(f"No sheet in {path} has table and column headers")
    else:
        df = pd.read_csv(path)
    roles = _dictionary_roles(df)
    out = pd.DataFrame({role: df[col] for role, col in roles.items()})
    for role in HEADERS:
        if role not in out:
            out[role] = None
    out = out.dropna(subset=["table", "column"])
    out["table"] = out["table"].astype(str).str.strip()
    out["column"] = out["column"].astype(str).str.strip()
    return out


def _dictionary_roles(df: pd.DataFrame) -> dict:
    roles = {}
    for col in df.columns:
        n = _norm(col)
        for role, names in HEADERS.items():
            if role not in roles and (n in names or (role == "column" and n.endswith("column_name"))):
                roles[role] = col
    return roles


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("y", "yes", "true", "1", "pk", "x")


# ---------------------------------------------------------------- type inference


def infer_sql_type(s: pd.Series) -> str:
    nn = s.dropna()
    if pd.api.types.is_bool_dtype(s):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(s):
        return "BIGINT"
    if pd.api.types.is_float_dtype(s):
        return "DECIMAL(18,4)" if (nn % 1 != 0).any() else "BIGINT"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "TIMESTAMP" if (nn.dt.hour + nn.dt.minute + nn.dt.second > 0).any() else "DATE"
    if len(nn) and all(hasattr(v, "year") and not hasattr(v, "hour") for v in nn.head(200)):
        return "DATE"
    width = int(nn.astype(str).str.len().max()) if len(nn) else 1
    return f"VARCHAR({max(width, 1)})"


def guess_key(df: pd.DataFrame) -> str | None:
    unique = [c for c in df.columns if df[c].notna().all() and df[c].is_unique]
    idish = [c for c in unique if re.search(r"(^|_)(id|no|nbr|num|key|ref)$", str(c).lower()) or str(c).lower().endswith(("id", "key"))]
    return (idish or unique or [None])[0]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Database drivers return Decimals and mixed objects; turn them into plain numbers and dates."""
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            nn = df[c].dropna()
            if len(nn) and all(isinstance(v, Decimal) for v in nn.head(500)):
                num = pd.to_numeric(df[c].astype(object).where(df[c].notna()), errors="coerce").astype(float)
                df[c] = num.astype("Int64") if (num.dropna() % 1 == 0).all() else num
    return df


# ---------------------------------------------------------------- writing a MergeGuard folder


def write_folder(out_dir: str | Path, tables: dict, meta: dict, derivations: dict) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    schema = {}
    for t, df in tables.items():
        df = _clean(df)
        con.register("df_tmp", df)
        con.execute(f"COPY df_tmp TO '{(out / f'{t}.parquet').as_posix()}' (FORMAT PARQUET)")
        con.unregister("df_tmp")
        m = meta.get(t, {})
        cols = {}
        for c in df.columns:
            cm = m.get("columns", {}).get(c, {})
            cols[c] = {"type": cm.get("type") or infer_sql_type(df[c]), "description": cm.get("description") or ""}
        key = m.get("key") if m.get("key") in df.columns else guess_key(df)
        schema[t] = {"key": key or list(df.columns)[0], "columns": cols}
    (out / "schema.json").write_text(json.dumps(schema, indent=2))
    (out / "derivations.json").write_text(json.dumps(derivations, indent=2))
    return out


def _apply_dictionary(cfg: dict, tables: dict, meta: dict, derivations: dict) -> None:
    dpath = _path(cfg, "dictionary")
    if dpath:
        d = read_dictionary(dpath, cfg.get("dictionary_sheet"))
        lookup = {t.lower(): t for t in tables}
        for _, r in d.iterrows():
            t = lookup.get(r["table"].lower())
            if not t:
                continue
            cols = {c.lower(): c for c in tables[t].columns}
            c = cols.get(r["column"].lower())
            if not c:
                continue
            cm = meta.setdefault(t, {}).setdefault("columns", {}).setdefault(c, {})
            if pd.notna(r["type"]) and str(r["type"]).strip():
                cm["type"] = str(r["type"]).strip()
            if pd.notna(r["description"]) and str(r["description"]).strip():
                cm["description"] = str(r["description"]).strip()
            if pd.notna(r["key"]) and _truthy(r["key"]):
                meta[t]["key"] = c
            if pd.notna(r["derivation"]) and str(r["derivation"]).strip():
                derivations[f"{t}.{c}"] = str(r["derivation"]).strip()
    for t, k in (cfg.get("keys") or {}).items():
        if t in tables:
            meta.setdefault(t, {})["key"] = k
    dfile = _path(cfg, "derivations")
    if dfile:
        derivations.update(json.loads(dfile.read_text()) if dfile.suffix == ".json" else _yaml(dfile))


def _yaml(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text()) or {}


# ---------------------------------------------------------------- connectors


def _file_tables(cfg: dict, pattern: str, reader) -> dict:
    root = _path(cfg, "path")
    files = sorted(root.glob(pattern)) if root.is_dir() else [root]
    wanted = set(cfg.get("tables") or [])
    n = int(cfg.get("sample_rows", 20000))
    out = {}
    for f in files:
        if wanted and f.stem not in wanted:
            continue
        df = reader(f)
        out[f.stem] = df.sample(n, random_state=0) if len(df) > n else df
    return out


def read_csv_source(cfg: dict):
    tables = _file_tables(cfg, "*.csv", lambda f: pd.read_csv(f, sep=cfg.get("delimiter", ","),
                                                            parse_dates=cfg.get("parse_dates") or False))
    return tables, {}, {}


def read_parquet_source(cfg: dict):
    return _file_tables(cfg, "*.parquet", lambda f: duckdb.connect().execute(f"SELECT * FROM '{f.as_posix()}'").df()), {}, {}


def read_excel_source(cfg: dict):
    """Each sheet is a table; a sheet with table and column headers is read as the data dictionary."""
    path = _path(cfg, "path")
    sheets = pd.read_excel(path, sheet_name=None)
    n = int(cfg.get("sample_rows", 20000))
    wanted = set(cfg.get("tables") or [])
    tables, meta, derivations = {}, {}, {}
    dict_sheet = cfg.get("dictionary_sheet")
    for name, df in sheets.items():
        if df.empty:
            continue
        if name == dict_sheet or (dict_sheet is None and {"table", "column"} <= set(_dictionary_roles(df))):
            if not cfg.get("dictionary"):
                cfg = {**cfg, "dictionary": str(path.resolve()), "dictionary_sheet": name}
            continue
        if wanted and name not in wanted:
            continue
        tables[re.sub(r"\W+", "_", name).strip("_")] = df.sample(n, random_state=0) if len(df) > n else df
    _apply_dictionary(cfg, tables, meta, derivations)
    return tables, meta, derivations


def read_sql_source(cfg: dict):
    """Oracle, SQL Server, Postgres, MySQL, SQLite or anything with a SQLAlchemy URL."""
    import sqlalchemy as sa
    engine = sa.create_engine(cfg["url"])
    schema = cfg.get("schema")
    insp = sa.inspect(engine)
    names = list(cfg.get("tables") or (insp.get_table_names(schema=schema) + insp.get_view_names(schema=schema)))
    views = set(insp.get_view_names(schema=schema))
    n = int(cfg.get("sample_rows", 20000))
    tables, meta, derivations = {}, {}, {}
    md = sa.MetaData()
    for t in names:
        tbl = sa.Table(t, md, autoload_with=engine, schema=schema)
        with engine.connect() as c:
            tables[t] = pd.read_sql(sa.select(tbl).limit(n), c)
        cols = {col["name"]: {"type": str(col["type"]), "description": col.get("comment") or ""}
                for col in insp.get_columns(t, schema=schema)}
        pk = (insp.get_pk_constraint(t, schema=schema) or {}).get("constrained_columns") or []
        meta[t] = {"columns": cols, "key": pk[0] if pk else None}
        if t in views:
            ddl = insp.get_view_definition(t, schema=schema) or ""
            derivations.update(_view_derivations(t, ddl, cfg.get("dialect")))
    _apply_dictionary(cfg, tables, meta, derivations)
    return tables, meta, derivations


def read_snowflake_source(cfg: dict):
    """Snowflake: types, comments, primary keys and view SQL from the catalog, plus a row sample per table."""
    import snowflake.connector
    params = {k: cfg[k] for k in ("account", "user", "password", "authenticator", "role", "warehouse",
                                   "database", "schema", "private_key_file", "token") if cfg.get(k)}
    con = snowflake.connector.connect(**params)
    db, schema = cfg["database"], cfg["schema"]
    n = int(cfg.get("sample_rows", 20000))
    cur = con.cursor()
    try:
        rows = cur.execute(
            f'SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH, '
            f'COMMENT FROM "{db}".INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, ORDINAL_POSITION',
            (schema,)).fetchall()
        wanted = set(cfg.get("tables") or [])
        meta: dict = {}
        for t, c, dt, prec, scale, length, comment in rows:
            if wanted and t not in wanted:
                continue
            meta.setdefault(t, {"columns": {}, "key": None})["columns"][c] = {
                "type": _sf_type(dt, prec, scale, length), "description": comment or ""}
        cur.execute(f'SHOW PRIMARY KEYS IN SCHEMA "{db}"."{schema}"')
        names = [d[0] for d in cur.description]
        for r in cur.fetchall():
            rec = dict(zip(names, r))
            t, c, seq = rec.get("table_name"), rec.get("column_name"), rec.get("key_sequence", 1)
            if t in meta and (meta[t]["key"] is None or seq == 1):
                meta[t]["key"] = c
        derivations = {}
        for t, ddl in cur.execute(
                f'SELECT TABLE_NAME, VIEW_DEFINITION FROM "{db}".INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = %s',
                (schema,)).fetchall():
            if t in meta and ddl:
                derivations.update(_view_derivations(t, ddl, "snowflake"))
        tables = {}
        for t in meta:
            cur.execute(f'SELECT * FROM "{db}"."{schema}"."{t}" SAMPLE ({n} ROWS)')
            tables[t] = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    finally:
        cur.close()
        con.close()
    _apply_dictionary(cfg, tables, meta, derivations)
    return tables, meta, derivations


def _sf_type(dt, prec, scale, length) -> str:
    dt = (dt or "").upper()
    if dt in ("NUMBER", "DECIMAL", "NUMERIC") and prec is not None:
        return f"NUMBER({prec},{scale or 0})"
    if dt in ("TEXT", "VARCHAR", "STRING") and length:
        return f"VARCHAR({length})"
    return dt or "VARCHAR"


def _view_derivations(view: str, ddl: str, dialect: str | None) -> dict:
    """Computed columns of a view become derivations; plain pass-through columns are left alone."""
    import sqlglot
    from sqlglot import exp
    m = re.search(r"\bselect\b", ddl, flags=re.I)
    if not m:
        return {}
    sql = ddl[m.start():].rstrip().rstrip(";")
    try:
        tree = sqlglot.parse_one(sql, read=dialect or None)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(tree, exp.Select):
        return {}
    out = {}
    for proj in tree.expressions:
        body = proj.this if isinstance(proj, exp.Alias) else proj
        if isinstance(body, exp.Column):
            continue
        out[f"{view}.{proj.alias_or_name}"] = sql
    return out


CONNECTORS = {"snowflake": read_snowflake_source, "sql": read_sql_source, "excel": read_excel_source,
              "csv": read_csv_source, "parquet": read_parquet_source}


def ingest(config: str | Path | dict, out_dir: str | Path) -> Path:
    cfg = load_config(config) if not isinstance(config, dict) else {"_base": Path("."), **_expand(config)}
    kind = cfg.get("connector")
    if kind not in CONNECTORS:
        raise ValueError(f"connector must be one of {sorted(CONNECTORS)}, got {kind!r}")
    tables, meta, derivations = CONNECTORS[kind](cfg)
    if kind in ("csv", "parquet"):
        _apply_dictionary(cfg, tables, meta, derivations)
    if not tables:
        raise ValueError("No tables were read; check the path, schema or tables list")
    out = write_folder(out_dir, tables, meta, derivations)
    n = int(cfg.get("sample_rows", 20000))
    sampled = kind in ("sql", "snowflake") and any(len(df) >= n for df in tables.values())
    (out / "_ingest.json").write_text(json.dumps({"connector": kind, "sample_rows": n, "sampled": sampled}))
    return out


def load_tables(config: str | Path | dict, files: dict) -> None:
    """Append rehearsed, reconciled tables into the target system (sql or snowflake connector).

    Each table loads in one transaction; a failure rolls that table back.
    """
    cfg = load_config(config) if not isinstance(config, dict) else {"_base": Path("."), **_expand(config)}
    frames = {t: duckdb.sql(f"SELECT * FROM '{Path(f).as_posix()}'").df() for t, f in files.items()}
    prefix = cfg.get("table_prefix", "")
    if cfg.get("connector") == "sql":
        import sqlalchemy as sa
        engine = sa.create_engine(cfg["url"])
        for t, df in frames.items():
            with engine.begin() as c:
                df.to_sql(prefix + t, c, schema=cfg.get("schema"), if_exists="append", index=False)
        return
    if cfg.get("connector") == "snowflake":
        import snowflake.connector
        params = {k: cfg[k] for k in ("account", "user", "password", "authenticator", "role", "warehouse",
                                       "database", "schema", "private_key_file", "token") if cfg.get(k)}
        con = snowflake.connector.connect(**params)
        try:
            cur = con.cursor()
            for t, df in frames.items():
                cols = ", ".join(f'"{c}"' for c in df.columns)
                marks = ", ".join(["%s"] * len(df.columns))
                rows = [tuple(None if pd.isna(v) else v for v in r) for r in df.itertuples(index=False)]
                cur.execute("BEGIN")
                try:
                    cur.executemany(f'INSERT INTO {prefix}{t} ({cols}) VALUES ({marks})', rows)
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
        finally:
            con.close()
        return
    raise ValueError("load_into needs a 'sql' or 'snowflake' connector config")
