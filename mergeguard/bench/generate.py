"""Generate a MergeBench scenario.

Keystone Bank (acquirer, target schema) buys Riverbend Financial (acquired, source schema).
Riverbend's data is planted with conflicts from the MergeGuard taxonomy, and the ground
truth records the correct target and the conflict types for every source attribute.

Everything is synthetic. Layout written to ``out_dir``::

    acquirer/schema.json   acquirer/derivations.json   acquirer/<table>.parquet
    acquired/schema.json   acquired/derivations.json   acquired/<table>.parquet
    ground_truth.json
"""
from __future__ import annotations

import json
import string
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

AS_OF = date(2026, 10, 31)
FIRST = ["Ava", "Liam", "Noah", "Emma", "Mia", "Ethan", "Zoe", "Ravi", "Priya", "Omar",
         "Lena", "Mateo", "Chen", "Sara", "Ivan", "Nia", "Kai", "Aria", "Leo", "Maya"]
LAST = ["Patel", "Garcia", "Nguyen", "Smith", "Kim", "Okafor", "Rossi", "Haddad", "Silva",
        "Novak", "Cohen", "Ibrahim", "Larsen", "Mehta", "Brown", "Lopez", "Wong", "Ali"]


# ---------------------------------------------------------------- helpers
def _people(rng, n):
    first = rng.choice(FIRST, n)
    last = rng.choice(LAST, n)
    dob = [date(1950, 1, 1) + timedelta(days=int(d)) for d in rng.integers(0, 365 * 55, n)]
    opened = [date(2005, 1, 1) + timedelta(days=int(d)) for d in rng.integers(0, 365 * 21, n)]
    return first, last, dob, opened


def _email(rng, first, last, domain):
    tag = "".join(rng.choice(list(string.digits), 3))
    return f"{first.lower()}.{last.lower()}{tag}@{domain}"


def _business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _transfers(rng, account_ids, n):
    acct = rng.choice(account_ids, n)
    principal = np.round(rng.lognormal(5.4, 1.0, n), 2)          # dollars, ~$220 median
    fee = np.where(rng.random(n) < 0.3, np.round(rng.uniform(2.5, 25, n), 2), 0.0)
    outgoing = rng.random(n) < 0.55
    initiated = [AS_OF - timedelta(days=int(d), minutes=int(m))
                 for d, m in zip(rng.integers(0, 365, n), rng.integers(0, 1440, n))]
    initiated_ts = [pd.Timestamp(d) + pd.Timedelta(minutes=int(m))
                    for d, m in zip(initiated, rng.integers(0, 1440, n))]
    settled = [_business_day(d + timedelta(days=int(lag)))
               for d, lag in zip(initiated, rng.integers(0, 3, n))]
    channel = rng.choice(["WEB", "MOBILE", "BRANCH"], n, p=[0.45, 0.4, 0.15])
    return acct, principal, fee, outgoing, initiated, initiated_ts, settled, channel


def _write(con, df: pd.DataFrame, path: Path):
    con.register("df_tmp", df)
    con.execute(f"COPY df_tmp TO '{path.as_posix()}' (FORMAT PARQUET)")
    con.unregister("df_tmp")


# ---------------------------------------------------------------- acquirer (target)
def build_acquirer(rng, n_cust=3000):
    first, last, dob, opened = _people(rng, n_cust)
    cust_ids = np.arange(1, n_cust + 1)
    customer = pd.DataFrame({
        "customer_id": cust_ids,
        "first_name": first,
        "last_name": last,
        "email": [_email(rng, f, l, "keystonemail.com") for f, l in zip(first, last)],
        "birth_date": dob,
        "customer_segment": rng.choice(["RETAIL", "PREMIER", "PRIVATE"], n_cust, p=[0.7, 0.25, 0.05]),
        "opened_date": opened,
        "kyc_risk_rating": rng.choice(["LOW", "MEDIUM", "HIGH"], n_cust, p=[0.8, 0.17, 0.03]),
    })

    n_acct = int(n_cust * 1.4)
    acct_ids = np.arange(100001, 100001 + n_acct)
    od = np.where(rng.random(n_acct) < 0.4, rng.choice([500, 1000, 2500], n_acct).astype(float), 0.0)
    od[rng.random(n_acct) < 0.03] = np.nan                       # NULL = unknown
    account = pd.DataFrame({
        "account_id": acct_ids,
        "customer_id": rng.choice(cust_ids, n_acct),
        "account_status": rng.choice(["OPEN", "DORMANT", "CLOSED", "CHARGED_OFF"], n_acct,
                                     p=[0.72, 0.15, 0.1, 0.03]),
        "current_balance": np.round(rng.lognormal(7.5, 1.3, n_acct), 2),
        "apr": np.round(rng.uniform(0.0999, 0.2999, n_acct), 4),
        "overdraft_limit": od,
    })

    n_tx = n_acct * 12
    acct, principal, fee, out, init, init_ts, settled, channel = _transfers(rng, acct_ids, n_tx)
    transfer = pd.DataFrame({
        "transfer_id": np.arange(1, n_tx + 1),
        "account_id": acct,
        "transfer_amount": np.round(principal * 100).astype("int64"),   # cents, net, unsigned
        "direction": np.where(out, "OUT", "IN"),
        "fee_amount": np.round(fee * 100).astype("int64"),            # cents
        "posted_date": settled,
        "initiated_ts": init_ts,
        "channel": np.where(channel == "WEB", "ONLINE", channel),
    })
    cnt = transfer[transfer.posted_date >= AS_OF - timedelta(days=30)].groupby("account_id").size()
    account["monthly_txn_count"] = account.account_id.map(cnt).fillna(0).astype(int)
    last_tx = (transfer.merge(account[["account_id", "customer_id"]], on="account_id")
               .groupby("customer_id").posted_date.max())
    customer["is_active"] = customer.customer_id.map(last_tx).apply(
        lambda d: bool(pd.notna(d) and d >= AS_OF - timedelta(days=90)))

    schema = {
        "customer": {"key": "customer_id", "columns": {
            "customer_id": ("BIGINT", "Unique customer identifier"),
            "first_name": ("VARCHAR(50)", "Customer given name"),
            "last_name": ("VARCHAR(50)", "Customer family name"),
            "email": ("VARCHAR(120)", "Primary email address of the customer"),
            "birth_date": ("DATE", "Customer date of birth"),
            "customer_segment": ("VARCHAR(10)", "Relationship segment: RETAIL, PREMIER or PRIVATE"),
            "opened_date": ("DATE", "Date the customer relationship began"),
            "kyc_risk_rating": ("VARCHAR(6)", "Know-your-customer risk rating"),
            "is_active": ("BOOLEAN", "Customer is active if any transfer posted in the last 90 days"),
        }},
        "account": {"key": "account_id", "columns": {
            "account_id": ("BIGINT", "Unique account identifier"),
            "customer_id": ("BIGINT", "Owning customer identifier"),
            "account_status": ("VARCHAR(12)", "Lifecycle status: OPEN, DORMANT, CLOSED, CHARGED_OFF"),
            "current_balance": ("DECIMAL(18,2)", "Current ledger balance in US dollars"),
            "apr": ("DECIMAL(6,4)", "Annual percentage rate as a fraction, e.g. 0.1999"),
            "overdraft_limit": ("DECIMAL(12,2)", "Approved overdraft limit in dollars; 0 if none, NULL if not yet reviewed"),
            "monthly_txn_count": ("INTEGER", "Number of transfers posted to the account in the last 30 days"),
        }},
        "transfer": {"key": "transfer_id", "columns": {
            "transfer_id": ("BIGINT", "Unique transfer identifier"),
            "account_id": ("BIGINT", "Account the transfer belongs to"),
            "transfer_amount": ("BIGINT", "Amount transferred in cents, excluding fees; always positive, see direction"),
            "direction": ("VARCHAR(3)", "IN for credits to the account, OUT for debits"),
            "fee_amount": ("BIGINT", "Fee charged on the transfer in cents"),
            "posted_date": ("DATE", "Date the transfer posted to the ledger"),
            "initiated_ts": ("TIMESTAMP", "Timestamp the customer initiated the transfer"),
            "channel": ("VARCHAR(8)", "Origination channel: ONLINE, MOBILE or BRANCH"),
        }},
    }
    derivations = {
        "customer.is_active": (
            "SELECT c.customer_id, MAX(t.posted_date) >= DATE '2026-10-31' - INTERVAL 90 DAY AS is_active "
            "FROM customer c JOIN account a ON a.customer_id = c.customer_id "
            "JOIN transfer t ON t.account_id = a.account_id GROUP BY c.customer_id"),
        "account.monthly_txn_count": (
            "SELECT t.account_id, COUNT(*) AS monthly_txn_count FROM transfer t "
            "WHERE t.posted_date >= DATE '2026-10-31' - INTERVAL 30 DAY GROUP BY t.account_id"),
        "transfer.transfer_amount": (
            "SELECT r.transfer_id, r.gross_amount_cents - r.fee_cents AS transfer_amount FROM transfer_raw r"),
        "transfer.posted_date": (
            "SELECT p.transfer_id, p.settlement_date AS posted_date FROM ledger_postings p"),
    }
    return {"customer": customer, "account": account, "transfer": transfer}, schema, derivations


# ---------------------------------------------------------------- acquired (source)
def build_acquired(rng, n_cust=2000):
    first, last, dob, opened = _people(rng, n_cust)
    cust_ids = np.arange(500001, 500001 + n_cust)
    cust = pd.DataFrame({
        "cust_no": cust_ids,
        "full_nm": [f"{f} {l}" for f, l in zip(first, last)],
        "email_addr": [_email(rng, f, l, "riverbend.net") for f, l in zip(first, last)],
        "dob": dob,
        "seg_cd": rng.choice(["R", "P", "W"], n_cust, p=[0.7, 0.25, 0.05]),
        "open_dt": opened,
        "branch_code": rng.choice([f"BR{i:03d}" for i in range(1, 41)], n_cust),
    })

    n_acct = int(n_cust * 1.4)
    acct_ids = np.arange(9000001, 9000001 + n_acct)
    od = np.where(rng.random(n_acct) < 0.4, rng.choice([500, 1000, 2500], n_acct).astype(float), np.nan)
    acct = pd.DataFrame({
        "acct_no": acct_ids,
        "cust_no": rng.choice(cust_ids, n_acct),
        "acct_stat": rng.choice(["A", "I", "C", "W"], n_acct, p=[0.72, 0.15, 0.1, 0.03]),
        "balance": np.round(rng.lognormal(7.5, 1.3, n_acct), 2),
        "apr_pct": np.round(rng.uniform(9.99, 29.99, n_acct), 2),                  # SCALE: percent
        "overdraft_limit": od,                                                    # NULL = no facility
    })

    n_tx = n_acct * 12
    a, principal, fee, out, init, init_ts, settled, channel = _transfers(rng, acct_ids, n_tx)
    sign = np.where(out, -1.0, 1.0)
    xfer = pd.DataFrame({
        "xfer_id": np.arange(70000001, 70000001 + n_tx),
        "acct_no": a,
        "transfer_amount": np.round(sign * (principal + fee), 2),   # FALSE FRIEND: dollars, gross, signed
        "xfer_amt_net": np.round(sign * principal, 2),             # hidden match for target transfer_amount
        "fee_amt": fee,                                            # UNIT: dollars vs cents
        "posted_date": init,                                       # FALSE FRIEND: actually request date
        "settle_dt": settled,                                      # hidden match for target posted_date
        "channel_cd": np.where(channel == "WEB", "WEB", np.where(channel == "MOBILE", "MOB", "BR")),
    })

    # active_flag comes from a status code, not from activity (POPULATION conflict)
    last_tx = xfer.merge(acct[["acct_no", "cust_no"]], on="acct_no").groupby("cust_no").settle_dt.max()
    recent = cust.cust_no.map(last_tx).apply(lambda d: bool(pd.notna(d) and d >= AS_OF - timedelta(days=90)))
    flip = rng.random(n_cust) < 0.18
    cust["active_flag"] = np.where(recent ^ flip, "Y", "N")

    # monthly_txn_count is per customer here, per account at the acquirer (GRAIN conflict)
    recent_tx = xfer[xfer.settle_dt >= AS_OF - timedelta(days=30)].merge(acct[["acct_no", "cust_no"]], on="acct_no")
    cust["monthly_txn_count"] = cust.cust_no.map(recent_tx.groupby("cust_no").size()).fillna(0).astype(int)

    schema = {
        "cust": {"key": "cust_no", "columns": {
            "cust_no": ("NUMBER(10)", "Customer number"),
            "full_nm": ("VARCHAR2(100)", "Customer full name"),
            "email_addr": ("VARCHAR2(120)", "Email address"),
            "dob": ("DATE", "Date of birth"),
            "seg_cd": ("CHAR(1)", "Segment code"),
            "open_dt": ("DATE", "Customer open date"),
            "branch_code": ("CHAR(5)", "Home branch"),
            "active_flag": ("CHAR(1)", "Active customer flag"),
            "monthly_txn_count": ("NUMBER(6)", "Monthly transaction count"),
        }},
        "acct": {"key": "acct_no", "columns": {
            "acct_no": ("NUMBER(10)", "Account number"),
            "cust_no": ("NUMBER(10)", "Customer number"),
            "acct_stat": ("CHAR(1)", "Account status"),
            "balance": ("NUMBER(18,2)", "Account balance"),
            "apr_pct": ("NUMBER(5,2)", "APR"),
            "overdraft_limit": ("NUMBER(12,2)", "Overdraft limit, NULL when no overdraft facility"),
        }},
        "xfer": {"key": "xfer_id", "columns": {
            "xfer_id": ("NUMBER(12)", "Transfer id"),
            "acct_no": ("NUMBER(10)", "Account number"),
            "transfer_amount": ("NUMBER(14,2)", "Transfer amount"),
            "xfer_amt_net": ("NUMBER(14,2)", "Net xfer amt"),
            "fee_amt": ("NUMBER(8,2)", "Fee amount"),
            "posted_date": ("DATE", "Posting date of transaction"),       # legacy doc is wrong
            "settle_dt": ("DATE", "Settlement date"),
            "channel_cd": ("VARCHAR2(6)", "Channel code"),
        }},
    }
    derivations = {
        "cust.active_flag": (
            "SELECT m.cust_no, CASE WHEN m.status_cd = 'A' THEN 'Y' ELSE 'N' END AS active_flag FROM cust_master m"),
        "cust.monthly_txn_count": (
            "SELECT a.cust_no, COUNT(*) AS monthly_txn_count FROM xfer x JOIN acct a ON a.acct_no = x.acct_no "
            "WHERE x.settle_dt >= ADD_MONTHS(SYSDATE, -1) GROUP BY a.cust_no"),
        "xfer.transfer_amount": (
            "SELECT r.xfer_id, CASE WHEN r.dir = 'D' THEN -(r.principal_amt + r.fee_amt) "
            "ELSE r.principal_amt + r.fee_amt END AS transfer_amount FROM xfer_raw r"),
        "xfer.xfer_amt_net": (
            "SELECT r.xfer_id, CASE WHEN r.dir = 'D' THEN -r.principal_amt ELSE r.principal_amt END "
            "AS xfer_amt_net FROM xfer_raw r"),
        "xfer.posted_date": (
            "SELECT r.xfer_id, TRUNC(r.request_ts) AS posted_date FROM xfer_raw r"),
    }
    return {"cust": cust, "acct": acct, "xfer": xfer}, schema, derivations


GROUND_TRUTH = [
    # source attribute,        correct target,               match type,   conflicts,                       false friend of
    ("cust.cust_no",           "customer.customer_id",       "exact",      [], None),
    ("cust.full_nm",           "customer.first_name+customer.last_name", "structural", [], None),
    ("cust.email_addr",        "customer.email",             "exact",      [], None),
    ("cust.dob",               "customer.birth_date",        "exact",      [], None),
    ("cust.seg_cd",            "customer.customer_segment",  "transform",  ["code_set"], None),
    ("cust.open_dt",           "customer.opened_date",       "exact",      [], None),
    ("cust.branch_code",       None,                         "unmatched",  [], None),
    ("cust.active_flag",       "customer.is_active",         "conflict",   ["population"], None),
    ("cust.monthly_txn_count", None,                         "conflict",   ["grain"], "account.monthly_txn_count"),
    ("acct.acct_no",           "account.account_id",         "exact",      [], None),
    ("acct.cust_no",           "account.customer_id",        "exact",      [], None),
    ("acct.acct_stat",         "account.account_status",     "transform",  ["code_set"], None),
    ("acct.balance",           "account.current_balance",    "exact",      [], None),
    ("acct.apr_pct",           "account.apr",                "transform",  ["scale"], None),
    ("acct.overdraft_limit",   "account.overdraft_limit",    "conflict",   ["null_semantics"], None),
    ("xfer.xfer_id",           "transfer.transfer_id",       "exact",      [], None),
    ("xfer.acct_no",           "transfer.account_id",        "exact",      [], None),
    ("xfer.transfer_amount",   None,                         "conflict",   ["unit", "inclusion", "sign"], "transfer.transfer_amount"),
    ("xfer.xfer_amt_net",      "transfer.transfer_amount",   "transform",  ["unit", "sign"], None),
    ("xfer.fee_amt",           "transfer.fee_amount",        "transform",  ["unit"], None),
    ("xfer.posted_date",       "transfer.initiated_ts",      "conflict",   ["temporal"], "transfer.posted_date"),
    ("xfer.settle_dt",         "transfer.posted_date",       "exact",      [], None),
    ("xfer.channel_cd",        "transfer.channel",           "transform",  ["code_set"], None),
]


SCENARIOS = ("keystone", "lending", "cards", "insurance", "practitioner", "practitioner2")


def _scenario(name: str):
    if name == "keystone":
        return (build_acquirer, build_acquired, GROUND_TRUTH, "oracle", "duckdb",
                ("keystone_riverbend", "Keystone Bank", "Riverbend Financial"))
    import importlib
    mod = importlib.import_module({"lending": ".lending", "cards": ".cards_portfolio", "insurance": ".insurance", "practitioner": ".practitioner", "practitioner2": ".practitioner2"}[name], __package__)
    return (mod.build_acquirer, mod.build_acquired, mod.GROUND_TRUTH, mod.SOURCE_DIALECT, mod.TARGET_DIALECT,
            mod.NAMES)


def generate(out_dir: str | Path, seed: int = 7, n_acquirer: int = 3000, n_acquired: int = 2000,
             scenario: str = "keystone") -> Path:
    out = Path(out_dir)
    b_acq, b_src, truth, src_dialect, tgt_dialect, names = _scenario(scenario)
    rng = np.random.default_rng(seed)
    con = duckdb.connect()
    for side, builder, n in (("acquirer", b_acq, n_acquirer), ("acquired", b_src, n_acquired)):
        tables, schema, derivations = builder(rng, n)
        d = out / side
        d.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            _write(con, df, d / f"{name}.parquet")
        (d / "schema.json").write_text(json.dumps(
            {t: {"key": s["key"], "columns": {c: {"type": ty, "description": de} for c, (ty, de) in s["columns"].items()}}
             for t, s in schema.items()}, indent=2))
        (d / "derivations.json").write_text(json.dumps(derivations, indent=2))
    gt = [{"source": s, "target": t, "match_type": m, "conflicts": c, "false_friend_of": f}
          for s, t, m, c, f in truth]
    (out / "ground_truth.json").write_text(json.dumps({"scenario": names[0], "acquirer": names[1], "acquired": names[2],
                                                       "seed": seed, "as_of": AS_OF.isoformat(), "attributes": gt}, indent=2))
    (out / "scenario.json").write_text(json.dumps({"scenario": names[0], "source_dialect": src_dialect,
                                                   "target_dialect": tgt_dialect}, indent=2))
    return out


if __name__ == "__main__":
    import sys
    print(generate(sys.argv[1] if len(sys.argv) > 1 else "mergebench_out"))
