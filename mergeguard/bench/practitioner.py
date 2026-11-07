"""Scenario E: Great Lakes National Bank (acquirer) buys Cedar Valley Savings (acquired).

Built from ten traps written by a practitioner co-author after MergeGuard v0.0.3 was frozen
(see PREREGISTRATION.md for the verbatim list). Each trap is tagged T1..T10 below.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .generate import AS_OF, FIRST, LAST, _business_day, _email, _people

BRANCHES = [f"BR{i:03d}" for i in range(1, 61)]


def _population(rng, n_cust, cust_start, acct_start, loan_start, txn_start, domain):
    first, last, dob, _ = _people(rng, n_cust)
    cust_ids = np.arange(cust_start, cust_start + n_cust)
    income = np.round(rng.lognormal(11.0, 0.5, n_cust), -2)
    cust = dict(id=cust_ids, name=[f"{f} {l}" for f, l in zip(first, last)], dob=dob,
                email=[_email(rng, f, l, domain) for f, l in zip(first, last)], income=income)

    n_acct = int(n_cust * 1.3)
    a_type = rng.choice(["CHECKING", "SAVINGS", "CREDIT_LINE"], n_acct, p=[0.5, 0.3, 0.2])
    a_status = rng.choice(["OPEN", "DORMANT", "CLOSED"], n_acct, p=[0.75, 0.13, 0.12])
    settled = np.round(rng.lognormal(7.4, 1.2, n_acct), 2)
    holds = np.where(rng.random(n_acct) < 0.3, np.round(rng.uniform(20, 800, n_acct), 2), 0.0)
    limit = np.where(a_type == "CREDIT_LINE", rng.choice([2500, 5000, 10000, 25000], n_acct).astype(float), np.nan)
    owed = np.where(a_type == "CREDIT_LINE", np.round(np.minimum(limit * rng.uniform(0, 1.05, n_acct), limit * 1.05), 2), np.nan)
    open_branch = rng.choice(BRANCHES, n_acct)
    moved = rng.random(n_acct) < 0.2
    current_branch = np.where(moved, rng.choice(BRANCHES, n_acct), open_branch)
    acct = dict(id=np.arange(acct_start, acct_start + n_acct), cust=rng.choice(cust_ids, n_acct), type=a_type,
                status=a_status, open=[AS_OF - timedelta(days=int(d)) for d in rng.integers(30, 365 * 15, n_acct)],
                settled=np.where(a_type == "CREDIT_LINE", owed, settled), holds=np.where(a_type == "CREDIT_LINE", 0.0, holds),
                limit=limit, owed=owed, open_branch=open_branch, current_branch=current_branch)

    n_loan = int(n_cust * 0.5)
    funding = [AS_OF - timedelta(days=int(d)) for d in rng.integers(60, 365 * 9, n_loan)]
    renewed = rng.random(n_loan) < 0.25
    renewal = [min(f + timedelta(days=int(k)), AS_OF - timedelta(days=5)) if r else None
               for f, r, k in zip(funding, renewed, rng.integers(365, 365 * 4, n_loan))]
    dpd = np.where(rng.random(n_loan) < 0.85, 0, rng.choice([5, 12, 20, 35, 48, 65, 95, 130], n_loan))
    joint = rng.random(n_loan) < 0.3
    b1 = rng.choice(np.arange(n_cust), n_loan)
    b2 = rng.choice(np.arange(n_cust), n_loan)
    by_income = np.where(joint & (income[b2] > income[b1]), b2, b1)           # highest earner
    first_signer = np.where(joint & (rng.random(n_loan) < 0.5), b2, b1)        # whoever signed first
    loan = dict(funding=funding, renewal=renewal, dpd=dpd, rate=np.round(rng.uniform(0.03, 0.12, n_loan), 4),
                principal=np.round(rng.lognormal(9.8, 0.8, n_loan), 2),
                maturity=[f + timedelta(days=int(t) * 30) for f, t in zip(funding, rng.choice([36, 60, 120, 360], n_loan))],
                owner_income=cust_ids[by_income], owner_signer=cust_ids[first_signer],
                modified=rng.random(n_loan) < 0.15, start=loan_start)

    n_tx = n_acct * 15
    debit = rng.random(n_tx) < 0.6
    posted = [_business_day(AS_OF - timedelta(days=int(d))) for d in rng.integers(0, 240, n_tx)]
    posted = [min(p, AS_OF) for p in posted]
    tx = dict(id=np.arange(txn_start, txn_start + n_tx), acct=rng.choice(acct["id"], n_tx),
              amount=np.round(rng.lognormal(4.2, 1.1, n_tx), 2), debit=debit, posted=posted)
    return cust, acct, loan, tx


def build_acquirer(rng, n=3000):
    C, A, L, T = _population(rng, n, 1, 100001, 200001, 1, "greatlakesmail.com")
    customer = pd.DataFrame({"customer_id": C["id"], "full_name": C["name"], "birth_date": C["dob"],
                             "email": C["email"], "annual_income": C["income"]})
    account = pd.DataFrame({
        "account_id": A["id"], "customer_id": A["cust"], "account_type": A["type"], "open_date": A["open"],
        "account_status": A["status"],
        "current_balance": A["settled"],                                                    # T1: settled only
        "branch_code": A["open_branch"],                                                    # T4: opening branch
        "credit_limit": A["limit"],
        "available_credit": np.where(np.isnan(A["limit"]), np.nan,
                                     np.round(np.maximum(A["limit"] - np.nan_to_num(A["owed"]), 0), 2)),  # T7: capped
    })
    n_loan = len(L["funding"])
    loan = pd.DataFrame({
        "loan_id": np.arange(L["start"], L["start"] + n_loan),                              # T6: stable ID
        "primary_owner_id": L["owner_income"],                                             # T9: highest earner
        "origination_date": L["funding"],                                                   # T2: initial funding
        "interest_rate": L["rate"],                                                         # T8: decimal
        "principal_balance": L["principal"],
        "days_past_due": L["dpd"],                                                          # T5: from due date
        "maturity_date": L["maturity"],
    })
    txn = pd.DataFrame({"transaction_id": T["id"], "account_id": T["acct"],
                        "amount": np.where(T["debit"], -T["amount"], T["amount"]),          # T10: signed
                        "post_date": T["posted"]})
    last = txn.groupby("account_id").post_date.max()
    account["is_active"] = account.account_id.map(last).apply(                              # T3: activity
        lambda d: bool(pd.notna(d) and d >= AS_OF - timedelta(days=90)))
    schema = {
        "customer": {"key": "customer_id", "columns": {
            "customer_id": ("NUMBER(38,0)", "Customer identifier"),
            "full_name": ("VARCHAR(120)", "Customer full name"),
            "birth_date": ("DATE", "Date of birth"),
            "email": ("VARCHAR(120)", "Primary email address"),
            "annual_income": ("NUMBER(12,2)", "Stated annual income in dollars"),
        }},
        "account": {"key": "account_id", "columns": {
            "account_id": ("NUMBER(38,0)", "Account identifier"),
            "customer_id": ("NUMBER(38,0)", "Owning customer"),
            "account_type": ("VARCHAR(12)", "CHECKING, SAVINGS or CREDIT_LINE"),
            "open_date": ("DATE", "Date the account was opened"),
            "account_status": ("VARCHAR(8)", "OPEN, DORMANT or CLOSED"),
            "current_balance": ("NUMBER(14,2)", "Settled balance in dollars; pending holds are not included"),
            "branch_code": ("VARCHAR(5)", "Branch where the account was originally opened"),
            "credit_limit": ("NUMBER(12,2)", "Credit limit for credit lines"),
            "available_credit": ("NUMBER(12,2)", "Credit limit minus balance owed, never above the credit limit"),
            "is_active": ("BOOLEAN", "Account had a posted transaction in the last 90 days"),
        }},
        "loan": {"key": "loan_id", "columns": {
            "loan_id": ("NUMBER(38,0)", "Loan identifier; unchanged by modifications"),
            "primary_owner_id": ("NUMBER(38,0)", "Primary owner: the co-borrower with the highest income"),
            "origination_date": ("DATE", "Initial funding date of the loan"),
            "interest_rate": ("NUMBER(6,4)", "Annual interest rate as a decimal, e.g. 0.0525"),
            "principal_balance": ("NUMBER(14,2)", "Outstanding principal in dollars"),
            "days_past_due": ("NUMBER(5,0)", "Days since the missed payment due date"),
            "maturity_date": ("DATE", "Scheduled maturity date"),
        }},
        "account_transaction": {"key": "transaction_id", "columns": {
            "transaction_id": ("NUMBER(38,0)", "Transaction identifier"),
            "account_id": ("NUMBER(38,0)", "Account"),
            "amount": ("NUMBER(14,2)", "Signed amount: debits negative, credits positive"),
            "post_date": ("DATE", "Posting date"),
        }},
    }
    derivations = {
        "account.is_active": (
            "SELECT a.account_id, MAX(t.post_date) >= DATE '2026-10-31' - INTERVAL 90 DAY AS is_active "
            "FROM account a JOIN account_transaction t ON t.account_id = a.account_id GROUP BY a.account_id"),
        "account.available_credit": (
            "SELECT a.account_id, GREATEST(a.credit_limit - a.current_balance, 0) AS available_credit FROM account a"),
        "loan.primary_owner_id": (
            "SELECT b.loan_id, b.customer_id AS primary_owner_id FROM loan_borrower b JOIN customer c "
            "ON c.customer_id = b.customer_id QUALIFY ROW_NUMBER() OVER (PARTITION BY b.loan_id "
            "ORDER BY c.annual_income DESC) = 1"),
    }
    return {"customer": customer, "account": account, "loan": loan, "account_transaction": txn}, schema, derivations


def build_acquired(rng, n=2000):
    C, A, L, T = _population(rng, n, 610001, 7200001, 4100001, 88000001, "cedarvalley.org")
    cust = pd.DataFrame({"CUST_NBR": C["id"], "CUST_NM": C["name"], "BIRTH_DT": C["dob"],
                         "EMAIL_ADDR": C["email"], "ANNL_INCM": C["income"]})
    shadow = np.where(np.isnan(A["limit"]), np.nan, A["limit"] * 0.10)
    acct = pd.DataFrame({
        "ACCT_NBR": A["id"], "CUST_NBR": A["cust"],
        "ACCT_TYP_CD": pd.Series(A["type"]).map({"CHECKING": "DDA", "SAVINGS": "SAV", "CREDIT_LINE": "LOC"}).to_numpy(),
        "OPEN_DT": A["open"],
        "ACCT_STAT_CD": pd.Series(A["status"]).map({"OPEN": "A", "DORMANT": "D", "CLOSED": "C"}).to_numpy(),
        "CUR_BAL": np.round(A["settled"] + A["holds"], 2),                                  # T1: includes holds
        "PEND_HOLD_AMT": A["holds"],
        "BRANCH_CD": A["current_branch"],                                                   # T4: current branch
        "CR_LMT": A["limit"],
        "AVAIL_CR": np.where(np.isnan(A["limit"]), np.nan,
                             np.round(A["limit"] + shadow - np.nan_to_num(A["owed"]), 2)),  # T7: shadow buffer
    })
    acct["ACTIVE_IND"] = np.where(acct.ACCT_STAT_CD != "C", "Y", "N")                       # T3: not closed
    n_loan = len(L["funding"])
    ids = np.arange(L["start"], L["start"] + n_loan)
    ids = np.where(L["modified"], ids + 800000, ids)                                        # T6: new ID after mod
    ln = pd.DataFrame({
        "LN_ID": ids, "PRIM_OWNR_ID": L["owner_signer"],                                    # T9: first signer
        "ORIG_DT": [r or f for f, r in zip(L["funding"], L["renewal"])],                    # T2: latest renewal
        "INT_RT": np.round(L["rate"] * 100, 2),                                             # T8: percent
        "PRIN_BAL": L["principal"],
        "DLQ_DAYS": np.maximum(L["dpd"] - 15, 0),                                           # T5: from grace end
        "MAT_DT": L["maturity"],
    })
    txn = pd.DataFrame({"TXN_ID": T["id"], "ACCT_NBR": T["acct"], "TXN_AMT": T["amount"],   # T10: unsigned + flag
                        "DR_CR_FLG": np.where(T["debit"], "D", "C"), "POST_DT": T["posted"]})
    schema = {
        "CUST": {"key": "CUST_NBR", "columns": {
            "CUST_NBR": ("INTEGER", "Customer number"),
            "CUST_NM": ("VARCHAR(100)", "Customer name"),
            "BIRTH_DT": ("DATE", "Birth date"),
            "EMAIL_ADDR": ("VARCHAR(100)", "Email"),
            "ANNL_INCM": ("DECIMAL(12,2)", "Annual income"),
        }},
        "ACCT": {"key": "ACCT_NBR", "columns": {
            "ACCT_NBR": ("INTEGER", "Account number"),
            "CUST_NBR": ("INTEGER", "Customer number"),
            "ACCT_TYP_CD": ("CHAR(3)", "Account type"),
            "OPEN_DT": ("DATE", "Open date"),
            "ACCT_STAT_CD": ("CHAR(1)", "Account status"),
            "CUR_BAL": ("DECIMAL(15,2)", "Current balance"),
            "PEND_HOLD_AMT": ("DECIMAL(15,2)", "Pending holds"),
            "BRANCH_CD": ("CHAR(5)", "Branch"),
            "CR_LMT": ("DECIMAL(12,2)", "Credit limit"),
            "AVAIL_CR": ("DECIMAL(12,2)", "Available credit"),
            "ACTIVE_IND": ("CHAR(1)", "Active indicator"),
        }},
        "LN": {"key": "LN_ID", "columns": {
            "LN_ID": ("INTEGER", "Loan identifier"),
            "PRIM_OWNR_ID": ("INTEGER", "Primary owner"),
            "ORIG_DT": ("DATE", "Origination date"),
            "INT_RT": ("DECIMAL(7,4)", "Interest rate"),
            "PRIN_BAL": ("DECIMAL(15,2)", "Principal balance"),
            "DLQ_DAYS": ("SMALLINT", "Days delinquent"),
            "MAT_DT": ("DATE", "Maturity date"),
        }},
        "TXN": {"key": "TXN_ID", "columns": {
            "TXN_ID": ("BIGINT", "Transaction id"),
            "ACCT_NBR": ("INTEGER", "Account number"),
            "TXN_AMT": ("DECIMAL(15,2)", "Transaction amount"),
            "DR_CR_FLG": ("CHAR(1)", "Debit/credit flag"),
            "POST_DT": ("DATE", "Post date"),
        }},
    }
    derivations = {
        "ACCT.CUR_BAL": ("SELECT r.ACCT_NBR, r.SETTLED_BAL + r.PEND_HOLD_AMT AS CUR_BAL FROM ACCT_RAW r"),
        "ACCT.AVAIL_CR": ("SELECT r.ACCT_NBR, r.CR_LMT + r.SHADOW_OVLMT_AMT - r.BAL_OWED AS AVAIL_CR FROM ACCT_RAW r"),
        "ACCT.ACTIVE_IND": (
            "SELECT a.ACCT_NBR, CASE WHEN a.ACCT_STAT_CD <> 'C' THEN 'Y' ELSE 'N' END AS ACTIVE_IND FROM ACCT a"),
        "LN.ORIG_DT": ("SELECT r.LN_ID, COALESCE(r.LAST_RENEWAL_DT, r.FUNDING_DT) AS ORIG_DT FROM LN_RAW r"),
        "LN.DLQ_DAYS": (
            "SELECT r.LN_ID, CASE WHEN CURRENT_DATE > r.GRACE_END_DT THEN CURRENT_DATE - r.GRACE_END_DT ELSE 0 END "
            "AS DLQ_DAYS FROM LN_RAW r"),
        "LN.PRIM_OWNR_ID": ("SELECT a.LN_ID, a.CUST_NBR AS PRIM_OWNR_ID FROM LN_APPLICANT a WHERE a.SIGN_SEQ = 1"),
    }
    return {"CUST": cust, "ACCT": acct, "LN": ln, "TXN": txn}, schema, derivations


GROUND_TRUTH = [
    ("CUST.CUST_NBR",      "customer.customer_id",            "exact",     [], None),
    ("CUST.CUST_NM",       "customer.full_name",              "exact",     [], None),
    ("CUST.BIRTH_DT",      "customer.birth_date",             "exact",     [], None),
    ("CUST.EMAIL_ADDR",    "customer.email",                  "exact",     [], None),
    ("CUST.ANNL_INCM",     "customer.annual_income",          "exact",     [], None),
    ("ACCT.ACCT_NBR",      "account.account_id",              "exact",     [], None),
    ("ACCT.CUST_NBR",      "account.customer_id",             "exact",     [], None),
    ("ACCT.ACCT_TYP_CD",   "account.account_type",            "transform", ["code_set"], None),
    ("ACCT.OPEN_DT",       "account.open_date",               "exact",     [], None),
    ("ACCT.ACCT_STAT_CD",  "account.account_status",          "transform", ["code_set"], None),
    ("ACCT.CUR_BAL",       "account.current_balance",         "conflict",  ["inclusion"], None),        # T1
    ("ACCT.PEND_HOLD_AMT", None,                              "unmatched", [], None),
    ("ACCT.BRANCH_CD",     "account.branch_code",             "conflict",  ["temporal"], None),         # T4
    ("ACCT.CR_LMT",        "account.credit_limit",            "exact",     [], None),
    ("ACCT.AVAIL_CR",      "account.available_credit",        "conflict",  ["inclusion"], None),        # T7
    ("ACCT.ACTIVE_IND",    "account.is_active",               "conflict",  ["population"], None),       # T3
    ("LN.LN_ID",           "loan.loan_id",                    "conflict",  ["identity"], None),         # T6
    ("LN.PRIM_OWNR_ID",    "loan.primary_owner_id",           "conflict",  ["role"], None),             # T9
    ("LN.ORIG_DT",         "loan.origination_date",           "conflict",  ["temporal"], None),         # T2
    ("LN.INT_RT",          "loan.interest_rate",              "transform", ["scale"], None),            # T8
    ("LN.PRIN_BAL",        "loan.principal_balance",          "exact",     [], None),
    ("LN.DLQ_DAYS",        "loan.days_past_due",              "conflict",  ["temporal"], None),         # T5
    ("LN.MAT_DT",          "loan.maturity_date",              "exact",     [], None),
    ("TXN.TXN_ID",         "account_transaction.transaction_id", "exact",  [], None),
    ("TXN.ACCT_NBR",       "account_transaction.account_id",  "exact",     [], None),
    ("TXN.TXN_AMT",        "account_transaction.amount",      "transform", ["sign"], None),             # T10
    ("TXN.DR_CR_FLG",      None,                              "unmatched", [], None),
    ("TXN.POST_DT",        "account_transaction.post_date",   "exact",     [], None),
]
SOURCE_DIALECT = "tsql"
TARGET_DIALECT = "snowflake"
NAMES = ("greatlakes_cedarvalley", "Great Lakes National Bank", "Cedar Valley Savings")
