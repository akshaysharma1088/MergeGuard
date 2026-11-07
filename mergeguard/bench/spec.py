"""Declarative MergeBench scenarios from a shared latent world.

A scenario lists entities. Each entity has *latent* facts about the real world (the true first-lien
balance, the date funds really became available). Each bank exposes columns computed from those
facts under its own definition. Both banks get independent populations drawn from the same world
model, which is what two real banks look like: different customers, same kinds of facts.

Spec shape::

    SPEC = {
      "names": (scenario_id, acquirer, acquired), "dialects": (source, target),
      "entities": [
        {"name": "loan", "per_base": 1.0,
         "latent": {"first_lien": "money:240000", "owner": "fk:customer", ...},
         "target": {"table": "mortgage", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Loan identifier", "ID"), ...]},
         "source": {"table": "MTG", "key": "LN_NO", "columns": [...]},
        }, ...],
      "derivations": {"target": {...}, "source": {...}},
      "truth": [(source, target, match_type, conflicts, false_friend_of), ...],
    }

Column expressions are Python over the latent Series plus helpers (np, pd, days, bizday, ID, where,
sentinel). A string starting with "hint:" draws fresh values from the hint vocabulary instead.
"""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .generate import AS_OF, FIRST, LAST

AS_OF_TS = pd.Timestamp(AS_OF)
SAFE = {"int": int, "float": float, "str": str, "bool": bool, "abs": abs}
BANKS = ["First Meridian", "Atlas Trust", "Pacific Union", "Harbor National", "Summit Federal", "Crown Bank",
         "Northgate", "Lakeview Savings", "Ironwood", "Silverline", "Cobalt Capital", "Granite State"]


def _parse(hint: str, n: int, rng, ctx: dict) -> pd.Series:
    nulls = 0.0
    if ";null:" in hint:
        hint, p = hint.split(";null:")
        nulls = float(p)
    kind, _, arg = hint.partition(":")
    if kind == "money":
        parts = arg.split(",")
        med = float(parts[0])
        sigma = float(next((p.split("=")[1] for p in parts if p.startswith("sigma=")), 0.8))
        s = pd.Series(np.round(rng.lognormal(np.log(med), sigma, n), 2))
    elif kind == "int":
        a, b = map(int, arg.split("-"))
        s = pd.Series(rng.integers(a, b + 1, n))
    elif kind == "uniform":
        a, b = map(float, arg.split("~"))
        s = pd.Series(rng.uniform(a, b, n))
    elif kind == "normal":
        mu, sd = map(float, arg.split(","))
        s = pd.Series(rng.normal(mu, sd, n))
    elif kind in ("date", "timestamp"):
        start, end = arg.split(",")[0].split("..")
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        span = max((hi - lo).days, 1)
        s = pd.Series(lo + pd.to_timedelta(rng.integers(0, span + 1, n), unit="D"))
        if kind == "timestamp":
            s = s + pd.to_timedelta(rng.integers(0, 86400, n), unit="s")
        if ",business" in arg:
            s = bizday(s)
    elif kind == "code":
        vals, probs = zip(*[(v.split("=")[0], float(v.split("=")[1])) for v in arg.split("|")])
        p = np.array(probs) / sum(probs)
        s = pd.Series(rng.choice(vals, n, p=p))
    elif kind == "bool":
        s = pd.Series(rng.random(n) < float(arg))
    elif kind == "name":
        f, l = rng.choice(FIRST, n), rng.choice(LAST, n)
        s = pd.Series({"full": [f"{a} {b}" for a, b in zip(f, l)], "first": list(f), "last": list(l),
                       "last_first": [f"{b}, {a}" for a, b in zip(f, l)]}[arg])
    elif kind == "pattern":
        def one():
            return "".join(str(rng.integers(0, 10)) if ch == "#" else
                           rng.choice(list(string.ascii_uppercase)) if ch == "A" else ch for ch in arg)
        s = pd.Series([one() for _ in range(n)])
    elif kind == "bank":
        s = pd.Series(rng.choice(BANKS, n))
    elif kind == "fk":
        s = pd.Series(rng.choice(ctx["ids"][arg], n))
    else:
        raise ValueError(f"unknown hint {hint}")
    if nulls:
        s = s.where(rng.random(n) >= nulls)
    return s


def bizday(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s)
    wd = s.dt.weekday
    return s + pd.to_timedelta(np.where(wd == 5, 2, np.where(wd == 6, 1, 0)), unit="D")


def days(x) -> pd.Series:
    return pd.to_timedelta(np.asarray(x), unit="D")


def _side(spec: dict, side: str, rng, n_base: int, id_base: int, parallel: bool = False, prng=None):
    """Build one bank. With parallel=True (source side only) also run the acquirer's definitions over the
    same accounts, as a parallel run would: system-computed target fields are recomputed, fields the target
    only stores (spec["loaded"]) receive the naively mapped source value."""
    ctx = {"ids": {}}
    tables, schema, ptables = {}, {}, {}
    loaded = set(spec.get("loaded", []))
    t2s = {t: s_ for s_, t, *_ in spec["truth"] if t and "+" not in t}
    for k, ent in enumerate(spec["entities"]):
        n = max(int(n_base * ent.get("per_base", 1.0)), 50)
        lat = {name: _parse(h, n, rng, ctx) for name, h in ent["latent"].items()}
        start = id_base * (k + 1) + (0 if side == "target" else 500000 * (k + 1))
        ids = pd.Series(np.arange(start, start + n))
        ctx["ids"][ent["name"]] = ids.to_numpy()
        ns = {**lat, "np": np, "pd": pd, "days": days, "bizday": bizday, "ID": ids, "where": np.where,
              "AS_OF": AS_OF_TS, "rng": rng, "n": n,
              "sentinel": lambda d, m: pd.Series(pd.Timestamp(d), index=m.index).where(m)}
        t = ent[side]
        cols = {}
        for col, sqlt, desc, expr in t["columns"]:
            if expr.startswith("hint:"):
                v = _parse(expr[5:], n, rng, ctx)
            else:
                v = eval(expr, {"__builtins__": SAFE}, ns)   # noqa: S307 (spec is trusted, written in this repo)
            v = pd.Series(v).reset_index(drop=True)
            if pd.api.types.is_datetime64_any_dtype(v) and "TIMESTAMP" not in sqlt.upper() and "DATETIME" not in sqlt.upper():
                v = v.dt.date
            cols[col] = v
            ns[f"col_{col}"] = v
        tables[t["table"]] = pd.DataFrame(cols)
        schema[t["table"]] = {"key": t["key"], "columns": {c: {"type": ty, "description": d}
                                                            for c, ty, d, _ in t["columns"]}}
        if parallel:
            tt = ent["target"]
            pns = {**ns}
            pcols = {}
            for col, sqlt, desc, expr in tt["columns"]:
                q = f"{tt['table']}.{col}"
                if q in loaded:
                    src_q = t2s.get(q)
                    v = cols[src_q.split(".")[1]] if src_q and src_q.split(".")[0] == t["table"] else pd.Series([None] * n)
                else:
                    v = pd.Series(eval(expr, {"__builtins__": SAFE}, pns)).reset_index(drop=True)
                    v = _noise(v, prng, col == tt["key"])
                if pd.api.types.is_datetime64_any_dtype(v) and "TIMESTAMP" not in sqlt.upper():
                    v = v.dt.date
                pcols[col] = pd.Series(v).reset_index(drop=True)
                pns[f"col_{col}"] = pcols[col]
            ptables[tt["table"]] = pd.DataFrame(pcols)
    return tables, schema, ptables


def _noise(v: pd.Series, rng, is_key: bool) -> pd.Series:
    """Benign parallel-run noise: a few records move between extracts (0.3%)."""
    if is_key or len(v) == 0:
        return v
    hit = rng.random(len(v)) < 0.003
    if pd.api.types.is_float_dtype(v):
        return v.where(~hit, (v * (1 + rng.normal(0, 0.02, len(v)))).round(2))
    if pd.api.types.is_datetime64_any_dtype(v):
        return v.where(~hit, v + pd.to_timedelta(rng.choice([-1, 1], len(v)), unit="D"))
    return v


def generate_spec(spec: dict, out_dir, seed: int, n_acquirer: int = 3000, n_acquired: int = 2000,
                  parallel: bool = True) -> Path:
    out = Path(out_dir)
    con = duckdb.connect()
    rng = np.random.default_rng(seed)
    for side, folder, n, base in (("target", "acquirer", n_acquirer, 100000), ("source", "acquired", n_acquired, 1000000)):
        tables, schema, ptables = _side(spec, side, rng, n, base, parallel=parallel and side == "source",
                                        prng=np.random.default_rng(seed + 99991))
        d = out / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            con.register("df_tmp", df)
            con.execute(f"COPY df_tmp TO '{(d / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)")
            con.unregister("df_tmp")
        (d / "schema.json").write_text(json.dumps(schema, indent=2))
        (d / "derivations.json").write_text(json.dumps(spec.get("derivations", {}).get(side, {}), indent=2))
        if ptables:
            pd_ = out / "parallel"
            pd_.mkdir(parents=True, exist_ok=True)
            for name, df in ptables.items():
                con.register("df_tmp", df)
                con.execute(f"COPY df_tmp TO '{(pd_ / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)")
                con.unregister("df_tmp")
    sid, acq, src = spec["names"]
    gt = [{"source": s, "target": t, "match_type": m, "conflicts": c, "false_friend_of": f}
          for s, t, m, c, f in spec["truth"]]
    (out / "ground_truth.json").write_text(json.dumps({"scenario": sid, "acquirer": acq, "acquired": src,
                                                       "seed": seed, "as_of": AS_OF.isoformat(), "attributes": gt}, indent=2))
    (out / "scenario.json").write_text(json.dumps({"scenario": sid, "source_dialect": spec["dialects"][0],
                                                   "target_dialect": spec["dialects"][1],
                                                   "loaded": spec.get("loaded", [])}, indent=2))
    return out


def check(out_dir) -> list[str]:
    """Ground truth names every source column once and points at real target columns."""
    out = Path(out_dir)
    gt = json.loads((out / "ground_truth.json").read_text())["attributes"]
    src = json.loads((out / "acquired" / "schema.json").read_text())
    tgt = json.loads((out / "acquirer" / "schema.json").read_text())
    scols = {f"{t}.{c}" for t, s in src.items() for c in s["columns"]}
    tcols = {f"{t}.{c}" for t, s in tgt.items() for c in s["columns"]}
    problems = [f"missing truth for {c}" for c in scols - {g['source'] for g in gt}]
    problems += [f"unknown source {g['source']}" for g in gt if g["source"] not in scols]
    problems += [f"unknown target {x}" for g in gt if g["target"] for x in g["target"].split("+") if x not in tcols]
    return problems
