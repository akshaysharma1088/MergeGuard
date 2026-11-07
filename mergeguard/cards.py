"""Attribute cards: everything MergeGuard knows about one column.

A card holds six kinds of evidence: name, documented meaning, type, value profile,
derivation logic and context (entity and grain).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import sqlglot
from sqlglot import exp

ABBR = {
    "xfer": ["transfer"], "amt": ["amount"], "cust": ["customer"], "acct": ["account"],
    "dt": ["date"], "nm": ["name"], "cd": ["code"], "stat": ["status"], "seg": ["segment"],
    "no": ["id"], "num": ["id"], "nbr": ["id"], "pct": ["percent"], "dob": ["birth", "date"],
    "addr": ["address"], "txn": ["transaction"], "ts": ["timestamp"], "settle": ["settlement"],
    "od": ["overdraft"], "bal": ["balance"], "dir": ["direction"], "flg": ["flag"],
    "req": ["request"], "init": ["initiated"], "mob": ["mobile"], "opened": ["open"],
    "key": ["id"], "ref": ["id"], "pk": ["id"],
}
# words that mean the same event or concept in logic evidence
CONCEPT = {"request": "initiated", "posted": "settlement", "posting": "settlement",
           "principal": "net", "transaction": "transfer"}
STOP = {"the", "of", "a", "an", "in", "to", "for", "is", "if", "any", "see", "e", "g", "and",
        "or", "as", "by", "on", "at", "it", "its", "be", "when", "with", "us"}
ENTITY_WORDS = {"customer", "account", "transfer"}


HUNGARIAN = ("tbl", "str", "int", "dbl", "lng", "cur", "n", "s", "b", "i", "f")


def strip_type_prefix(name: str) -> str:
    """nInsuredNo -> InsuredNo, curPremium -> Premium. Only lowercase prefixes before an uppercase letter."""
    m = re.match(r"^([a-z]{1,3})([A-Z][a-zA-Z0-9]*)$", name)
    if m and m.group(1) in HUNGARIAN:
        return m.group(2)
    return name


def tokens(text: str) -> list[str]:
    out = []
    text = " ".join(strip_type_prefix(w) for w in re.split(r"(\s+)", text))
    for raw in re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", text).lower()):
        if raw and raw not in STOP:
            out.extend(ABBR.get(raw, [raw]))
    return out


def entity_of(table: str) -> str:
    toks = tokens(table)
    return toks[0] if toks else table


def type_family(t: str) -> str:
    t = t.upper().strip()
    if t.startswith("PIC"):
        if "X" in t or "A(" in t:
            return "string"
        return "decimal" if "V" in t else "int"
    if "MONEY" in t:
        return "decimal"
    if t == "BIT" or "BOOL" in t:
        return "bool"
    if "TIMESTAMP" in t:
        return "timestamp"
    if "DATE" in t:
        return "date"
    if "CHAR" in t or "TEXT" in t or "STRING" in t:
        return "string"
    m = re.search(r"\((\d+)\s*,\s*(\d+)\)", t)
    if ("NUMBER" in t or "DECIMAL" in t or "NUMERIC" in t) and m and int(m.group(2)) > 0:
        return "decimal"
    if any(k in t for k in ("INT", "NUMBER", "DECIMAL", "NUMERIC")):
        return "int"
    if any(k in t for k in ("FLOAT", "DOUBLE", "REAL")):
        return "decimal"
    return "string"


def infer_family(s: pd.Series, declared: str) -> tuple[str, pd.Series]:
    """Trust the data over the declared type: numbers stored as text become numbers.

    Zero-padded codes (ZIP, account codes) stay text, because the padding carries meaning.
    """
    if declared != "string":
        return declared, s
    nn = s.dropna().astype(str).str.strip()
    if nn.empty:
        return declared, s
    if (nn.str.len().gt(1) & nn.str.startswith("0") & ~nn.str.startswith("0.")).any():
        return declared, s
    num = pd.to_numeric(nn, errors="coerce")
    lengths = nn.str.len()
    if nn.str.fullmatch(r"\d+").all() and lengths.nunique() == 1 and lengths.iat[0] >= 5:
        return declared, s   # fixed-width digit codes (phones, ZIPs) are text
    if num.notna().mean() >= 0.95:
        conv = pd.to_numeric(s.astype(str).str.strip().where(s.notna()), errors="coerce")
        fam = "int" if (num.dropna() % 1 == 0).all() else "decimal"
        return fam, conv
    return declared, s


def digit_profile(s: pd.Series) -> dict | None:
    """Values that are digits once punctuation is removed (phones, ZIPs, codes)."""
    nn = s.dropna().astype(str)
    if nn.empty:
        return None
    if nn.str.match(r"^-?\d+\.\d+$").mean() > 0.5:   # real decimals are not digit codes
        return None
    stripped = nn.str.replace(r"[^0-9A-Za-z]", "", regex=True)
    if stripped.str.fullmatch(r"\d+").mean() < 0.95:
        return None
    shape = nn.str.replace(r"\d", "9", regex=True).str.replace(r"[A-Za-z]", "A", regex=True)
    return {"values": pd.to_numeric(stripped, errors="coerce").dropna().to_numpy(dtype=float),
            "length": float(stripped.str.len().mean()), "shape": shape.mode().iat[0],
            "punct": float(nn.str.contains(r"[^0-9]").mean())}


BOOL_VALUES = {"Y": True, "N": False, "T": True, "F": False, "TRUE": True, "FALSE": False,
               "1": True, "0": False}


def profile(s: pd.Series, family: str, sample: int = 20000, seed: int = 0) -> dict:
    n = len(s)
    nn = s.dropna()
    p = {"n": n, "null_rate": 1 - len(nn) / n if n else 0.0,
         "distinct": int(nn.nunique()), "uniq_ratio": nn.nunique() / max(len(nn), 1)}
    if len(nn) > sample:
        nn = nn.sample(sample, random_state=seed)
    dp = digit_profile(nn) if family in ("string", "int") else None
    if dp:
        p["digits"] = dp
    if family == "bool" or (family == "string" and p["distinct"] <= 2
                            and set(map(lambda v: str(v).upper(), nn.unique())) <= set(BOOL_VALUES)):
        vals = nn.map(lambda v: BOOL_VALUES.get(str(v).upper(), bool(v)) if not isinstance(v, (bool, np.bool_)) else bool(v))
        p.update(kind="bool", true_rate=float(vals.mean()))
    elif family in ("int", "decimal"):
        v = nn.astype(float).to_numpy()
        p.update(kind="numeric", values=v, neg_share=float((v < 0).mean()),
                 zero_share=float((v == 0).mean()), median=float(np.median(v)) if len(v) else 0.0)
        if s.isna().any():
            p["values_fill0"] = s.fillna(0).astype(float).to_numpy()[:sample]
        sparse = len(v) and (v.max() - v.min() + 1) > 2 * p["distinct"]
        if len(v) and (v % 1 == 0).all() and (p["distinct"] <= 10 or (p["distinct"] <= 50 and sparse)):
            # integer codes: 1/2/3 statuses, or sparse code lists like merchant category codes
            p["freqs"] = pd.Series(v.astype(int).astype(str)).value_counts(normalize=True).to_dict()
    elif family in ("date", "timestamp"):
        raw = nn.astype(str)
        sentinel = raw.str.startswith(("9999", "9998", "1900-01-01", "0001"))
        d = pd.to_datetime(nn[~sentinel], errors="coerce").dropna()
        p.update(kind="date", weekend_share=float((d.dt.weekday >= 5).mean()) if len(d) else 0.0,
                 min=d.min(), max=d.max(), has_time=bool((d.dt.hour + d.dt.minute > 0).any()),
                 sentinel_share=float(sentinel.mean()) * (1 - p["null_rate"]),
                 ordinals=(d.dt.normalize() - pd.Timestamp("1970-01-01")).dt.days.to_numpy(dtype=float))
    else:
        txt = nn.astype(str)
        p.update(kind="categorical" if p["distinct"] <= 50 else "text",
                 freqs=txt.value_counts(normalize=True).to_dict() if p["distinct"] <= 50 else {},
                 space_share=float(txt.str.contains(" ").mean()),
                 comma_share=float(txt.str.contains(",").mean()),
                 at_share=float(txt.str.contains("@").mean()),
                 avg_len=float(txt.str.len().mean()))
    return p


def _logic_features(sql: str, column: str, dialect: str, table_entity: str) -> tuple[set, dict]:
    """Semantic features of how a derived column is computed."""
    tree = sqlglot.parse_one(sql, read=dialect)
    proj = next((e for e in tree.expressions if e.alias_or_name == column), tree.expressions[-1])
    body = proj.this if isinstance(proj, exp.Alias) else proj
    feats: set[str] = set()
    refs = [c.name for c in body.find_all(exp.Column)]
    for r in refs:
        toks = [CONCEPT.get(t, t) for t in tokens(r)]
        if any(t in ("date", "timestamp") for t in toks):
            feats.update(f"event:{t}" for t in toks if t not in ("date", "timestamp", "id"))
        for t in toks:
            if t in ("net",):
                feats.add("fee:excluded")
            elif t not in ("fee", "gross", "cents", "direction", "status", "code", "id", "date", "timestamp"):
                feats.add(t)
    for node in body.find_all(exp.Add, exp.Sub):
        if any("fee" in tokens(c.name) for c in node.expression.find_all(exp.Column)) or \
           any("fee" in tokens(c.name) for c in node.this.find_all(exp.Column)):
            feats.discard("fee:excluded")
            feats.add("fee:included" if isinstance(node, exp.Add) else "fee:excluded")
    if list(body.find_all(exp.Neg)):
        feats.add("sign:signed")
    for agg in body.find_all(exp.AggFunc):
        feats.add(f"agg:{agg.key}")
    if list(body.find_all(exp.Count)) or isinstance(body, exp.Count):
        feats.add("agg:count")
    # what the rule is based on
    for cmp_ in list(body.find_all(exp.EQ, exp.GTE, exp.GT, exp.LT, exp.LTE)):
        cols = [tokens(c.name) for c in cmp_.find_all(exp.Column)]
        if any("status" in t or "code" in t for t in cols):
            feats.add("basis:status")
        if any("date" in t or "timestamp" in t for t in cols):
            feats.add("basis:recency")
    where = tree.args.get("where")
    if where is not None and any("date" in tokens(c.name) for c in where.find_all(exp.Column)):
        feats.add("basis:recency")
        for c in where.find_all(exp.Column):
            feats.update(f"event:{CONCEPT.get(t, t)}" for t in tokens(c.name) if t not in ("date", "timestamp"))
    terms = []
    top = body
    while isinstance(top, (exp.Neg, exp.Paren)):
        top = top.this
    if isinstance(top, exp.Case):
        top = top.args.get("default") or top
        while isinstance(top, (exp.Neg, exp.Paren)):
            top = top.this
    if isinstance(top, exp.Add):
        terms = [tuple(t for t in tokens(c.name) if t not in ("id", "raw")) for c in top.find_all(exp.Column)]
    group = tree.args.get("group")
    grain = table_entity
    if group is not None and group.expressions:
        grain = entity_of(group.expressions[0].sql().split(".")[-1].replace("_no", "_id"))
        gtoks = tokens(group.expressions[0].sql().split(".")[-1])
        grain = next((t for t in gtoks if t in ENTITY_WORDS), grain)
    feats.add(f"grain:{grain}")
    return feats, {"grain": grain, "refs": refs, "terms": terms}


def raw_logic(column: str, table_entity: str, family: str) -> set:
    toks = [CONCEPT.get(t, t) for t in tokens(column)]
    feats = {f"grain:{table_entity}"}
    if family in ("date", "timestamp"):
        feats.update(f"event:{t}" for t in toks if t not in ("date", "timestamp", "id"))
    else:
        feats.update(t for t in toks if t not in ("id", "code"))
        if "net" in toks:
            feats.add("fee:excluded")
    return feats


@dataclass
class Card:
    side: str
    table: str
    column: str
    sql_type: str
    family: str
    description: str
    entity: str
    is_key: bool
    is_identifier: bool
    name_tokens: list
    desc_tokens: list
    profile: dict
    logic: set
    derived: bool
    grain: str
    derivation: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def qname(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass
class Side:
    name: str
    path: Path
    schema: dict
    derivations: dict
    cards: list
    con: duckdb.DuckDBPyConnection

    def card(self, qname: str) -> Card:
        return next(c for c in self.cards if c.qname == qname)


def load_side(path: str | Path, name: str, dialect: str = "duckdb") -> Side:
    path = Path(path)
    schema = json.loads((path / "schema.json").read_text())
    der_file = path / "derivations.json"
    derivations = json.loads(der_file.read_text()) if der_file.exists() else {}
    con = duckdb.connect()
    cards = []
    for table, spec in schema.items():
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{(path / f'{table}.parquet').as_posix()}'")
        df = con.execute(f"SELECT * FROM {table}").df()
        ent = entity_of(table)
        for col, meta in spec["columns"].items():
            declared = type_family(meta["type"])
            fam, values = infer_family(df[col], declared)
            q = f"{table}.{col}"
            derived = q in derivations
            terms = []
            if derived:
                logic, info = _logic_features(derivations[q], col, dialect, ent)
                grain, terms = info["grain"], info["terms"]
            else:
                logic, grain = raw_logic(col, ent, fam), ent
            ntok = tokens(col)
            cards.append(Card(
                side=name, table=table, column=col, sql_type=meta["type"], family=fam,
                description=meta.get("description", ""), entity=ent,
                is_key=(col == spec.get("key")), is_identifier=(col == spec.get("key") or ("id" in ntok and (
                    fam in ("int", "decimal") or df[col].nunique() / max(df[col].notna().sum(), 1) >= 0.9))),
                name_tokens=ntok, desc_tokens=tokens(meta.get("description", "")),
                profile=profile(values, fam), logic=logic, derived=derived, grain=grain,
                derivation=derivations.get(q),
                extra={"declared_family": declared, "terms": terms or [tuple(ntok)]}))
    return Side(name, path, schema, derivations, cards, con)
