"""Held-out scenario C: Meridian Card Services (acquirer) buys Pinecrest Bank's card portfolio.

Mainframe-style UPPER_SNAKE source names with abbreviations MergeGuard's dictionary does
not know (TRAN, LMT, OPN, REF, CHG, FLG, IND, MCC). Conflicts in new forms: sign carried by a
separate debit/credit indicator, transaction vs posting date, revolver over 1 vs 3 cycles,
interest that silently includes fees, many-to-one merchant codes, a lifetime vs per-transaction
cashback grain clash, and NULL credit limit meaning "no preset limit".
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .generate import AS_OF, _business_day, _people

MCC = {"5411": "GROCERY", "5422": "GROCERY", "5499": "GROCERY", "3000": "TRAVEL", "4511": "TRAVEL",
       "7011": "TRAVEL", "4111": "TRAVEL", "5812": "DINING", "5813": "DINING", "5814": "DINING",
       "5541": "FUEL", "5542": "FUEL", "5999": "OTHER", "5311": "OTHER", "5732": "OTHER", "4900": "OTHER"}


def _book(rng, n_acct, id_start, txn_start, stmt_start):
    first, last, _, opened = _people(rng, n_acct)
    acct = np.arange(id_start, id_start + n_acct)
    tier = rng.choice(["CLASSIC", "GOLD", "PLATINUM"], n_acct, p=[0.6, 0.3, 0.1])
    limit = np.where(tier == "PLATINUM", rng.choice([15000, 25000], n_acct),
                     rng.choice([2000, 5000, 8000, 12000], n_acct)).astype(float)
    revolving = rng.random(n_acct) < 0.45
    # statements: 6 monthly cycles per account
    rows = []
    sid = stmt_start
    for i, a in enumerate(acct):
        for k in range(6):
            sdate = AS_OF - timedelta(days=30 * k + int(rng.integers(0, 5)))
            spend = round(float(rng.lognormal(6.5, 0.8)), 2)
            carry = revolving[i] and rng.random() < (0.9 if k < 3 else 0.6)
            last_cycle_only = k == 0 and rng.random() < 0.15        # some pay off only the latest cycle
            interest = round(float(rng.uniform(15, 180)), 2) if (carry and not last_cycle_only) else 0.0
            fee = round(float(rng.choice([0, 0, 0, 35, 39])), 2)
            bal = round(spend * rng.uniform(1, 3) + interest + fee, 2)
            rows.append((sid, a, sdate, bal, round(max(25, bal * 0.02), 2), interest, fee, spend))
            sid += 1
    stmt = pd.DataFrame(rows, columns=["sid", "acct", "sdate", "bal", "min_due", "interest", "fee", "spend"])
    n_tx = n_acct * 25
    tx_acct = rng.choice(acct, n_tx)
    mcc = rng.choice(list(MCC), n_tx)
    credit = rng.random(n_tx) < 0.12
    amt = np.round(rng.lognormal(3.6, 1.0, n_tx), 2)
    purch = [AS_OF - timedelta(days=int(d)) for d in rng.integers(0, 180, n_tx)]
    post = [_business_day(d + timedelta(days=int(l))) for d, l in zip(purch, rng.integers(1, 3, n_tx))]
    cash = np.where(credit, 0.0, np.round(amt * 0.015, 2))
    tx = pd.DataFrame({"tid": np.arange(txn_start, txn_start + n_tx), "acct": tx_acct, "amt": amt,
                       "credit": credit, "purch": purch, "post": post, "mcc": mcc, "cash": cash})
    util = []
    last_bal = stmt.sort_values("sdate").groupby("acct").bal.last()
    for a, lim in zip(acct, limit):
        util.append(min(last_bal.get(a, 0) / lim, 1.5))
    return dict(acct=acct, name=[f"{f} {l}" for f, l in zip(first, last)], opened=opened, tier=tier,
                limit=limit, util=np.array(util), autopay=rng.random(n_acct) < 0.35), stmt, tx


def build_acquirer(rng, n=3000):
    A, S, T = _book(rng, n, 1, 1, 1)
    lim = A["limit"].copy()
    lim[rng.random(n) < 0.02] = np.nan                                  # NULL = unknown
    acct = pd.DataFrame({"account_id": A["acct"], "holder_name": A["name"], "credit_limit": lim,
                         "utilization_ratio": np.round(A["util"], 4), "open_date": A["opened"],
                         "product_tier": A["tier"], "autopay_enabled": A["autopay"]})
    recent = S[S.sdate >= AS_OF - timedelta(days=90)]
    rev = recent.groupby("acct").interest.max().gt(0)
    acct["is_revolver"] = acct.account_id.map(rev).fillna(False).astype(bool)
    stmt = pd.DataFrame({"statement_id": S.sid, "account_id": S.acct, "statement_date": S.sdate,
                         "new_balance": S.bal, "minimum_due": S.min_due, "interest_charged": S.interest,
                         "fees_charged": S.fee, "cycle_spend": S.spend})
    tx = pd.DataFrame({"transaction_id": T.tid, "account_id": T.acct,
                       "amount": np.where(T.credit, -T.amt, T.amt), "transaction_date": T.purch,
                       "post_date": T.post, "merchant_category": T.mcc.map(MCC),
                       "cashback_earned": np.round(T.cash * 100).astype("int64")})
    schema = {
        "card_account": {"key": "account_id", "columns": {
            "account_id": ("NUMBER(38,0)", "Card account identifier"),
            "holder_name": ("VARCHAR(100)", "Primary cardholder full name"),
            "credit_limit": ("NUMBER(10,2)", "Credit limit in dollars; NULL when not yet assigned"),
            "utilization_ratio": ("NUMBER(6,4)", "Latest statement balance divided by credit limit"),
            "open_date": ("DATE", "Account open date"),
            "product_tier": ("VARCHAR(10)", "CLASSIC, GOLD or PLATINUM"),
            "autopay_enabled": ("BOOLEAN", "Autopay is set up"),
            "is_revolver": ("BOOLEAN", "Charged interest in any statement of the last 90 days"),
        }},
        "statement": {"key": "statement_id", "columns": {
            "statement_id": ("NUMBER(38,0)", "Statement identifier"),
            "account_id": ("NUMBER(38,0)", "Card account"),
            "statement_date": ("DATE", "Statement closing date"),
            "new_balance": ("NUMBER(12,2)", "Statement balance including interest and fees"),
            "minimum_due": ("NUMBER(10,2)", "Minimum payment due"),
            "interest_charged": ("NUMBER(10,2)", "Interest charged in the cycle, excluding fees"),
            "fees_charged": ("NUMBER(10,2)", "Fees charged in the cycle"),
            "cycle_spend": ("NUMBER(12,2)", "Purchases in the cycle"),
        }},
        "card_transaction": {"key": "transaction_id", "columns": {
            "transaction_id": ("NUMBER(38,0)", "Transaction identifier"),
            "account_id": ("NUMBER(38,0)", "Card account"),
            "amount": ("NUMBER(12,2)", "Signed amount in dollars: purchases positive, credits negative"),
            "transaction_date": ("DATE", "Date of purchase at the merchant"),
            "post_date": ("DATE", "Date the transaction posted to the account"),
            "merchant_category": ("VARCHAR(10)", "GROCERY, TRAVEL, DINING, FUEL or OTHER"),
            "cashback_earned": ("NUMBER(10,0)", "Cashback earned on the transaction in cents"),
        }},
    }
    derivations = {
        "card_account.is_revolver": (
            "SELECT a.account_id, MAX(s.interest_charged) > 0 AS is_revolver FROM card_account a "
            "JOIN statement s ON s.account_id = a.account_id "
            "WHERE s.statement_date >= DATE '2026-10-31' - INTERVAL 90 DAY GROUP BY a.account_id"),
        "statement.interest_charged": ("SELECT r.statement_id, r.interest_amt AS interest_charged FROM stmt_raw r"),
        "card_transaction.amount": (
            "SELECT r.transaction_id, CASE WHEN r.dr_cr = 'C' THEN -r.amt ELSE r.amt END AS amount FROM txn_raw r"),
    }
    return {"card_account": acct, "statement": stmt, "card_transaction": tx}, schema, derivations


def build_acquired(rng, n=2000):
    A, S, T = _book(rng, n, 4400001, 61000001, 3300001)
    lim = A["limit"].copy()
    lim[rng.random(n) < 0.12] = np.nan                                  # NULL = no preset limit
    acct = pd.DataFrame({"CRD_ACCT_REF": A["acct"], "CARDHOLDER_NAME": A["name"], "CR_LMT": lim,
                         "UTIL_PCT": np.round(A["util"] * 100, 1), "ACCT_OPN_DT": A["opened"],
                         "PROD_CD": pd.Series(A["tier"]).map({"CLASSIC": "C", "GOLD": "G", "PLATINUM": "P"}).to_numpy(),
                         "AUTOPAY_IND": np.where(A["autopay"], "Y", "N")})
    last = S[S.sdate >= AS_OF - timedelta(days=30)]
    rev1 = (last.interest + last.fee).groupby(last.acct).max().gt(0)      # POPULATION: 1 cycle, fees count
    acct["REVOLVER_FLG"] = np.where(acct.CRD_ACCT_REF.map(rev1).fillna(False).astype(bool), "Y", "N")
    acct["CASHBACK_EARNED"] = acct.CRD_ACCT_REF.map(T.groupby("acct").cash.sum()).fillna(0).round(2)  # GRAIN
    stmt = pd.DataFrame({"STMT_REF": S.sid, "CRD_ACCT_REF": S.acct, "STMT_DT": S.sdate, "NEW_BAL": S.bal,
                         "MIN_PMT_DUE": S.min_due, "INT_CHG": np.round(S.interest + S.fee, 2),  # INCLUSION
                         "FEE_CHG": S.fee, "CYCLE_SPEND": S.spend})
    tx = pd.DataFrame({"TRAN_REF": T.tid, "CRD_ACCT_REF": T.acct, "AMOUNT": T.amt,       # SIGN via DR_CR_IND
                       "DR_CR_IND": np.where(T.credit, "C", "D"), "TRAN_DT": T.post,     # FALSE FRIEND: posting
                       "PURCH_DT": T.purch, "MCC_CD": T.mcc, "CASHBACK_AMT": T.cash})
    schema = {
        "CRD_ACCT": {"key": "CRD_ACCT_REF", "columns": {
            "CRD_ACCT_REF": ("PIC 9(10)", "CARD ACCOUNT REFERENCE"),
            "CARDHOLDER_NAME": ("PIC X(60)", "CARDHOLDER NAME"),
            "CR_LMT": ("PIC 9(8)V99", "CREDIT LIMIT, BLANK FOR NO PRESET LIMIT"),
            "UTIL_PCT": ("PIC 9(3)V9", "UTILIZATION PCT"),
            "ACCT_OPN_DT": ("DATE", "ACCOUNT OPEN DATE"),
            "PROD_CD": ("PIC X(1)", "PRODUCT CODE"),
            "AUTOPAY_IND": ("PIC X(1)", "AUTOPAY INDICATOR"),
            "REVOLVER_FLG": ("PIC X(1)", "REVOLVER FLAG"),
            "CASHBACK_EARNED": ("PIC 9(8)V99", "CASHBACK EARNED"),
        }},
        "STMT": {"key": "STMT_REF", "columns": {
            "STMT_REF": ("PIC 9(10)", "STATEMENT REFERENCE"),
            "CRD_ACCT_REF": ("PIC 9(10)", "CARD ACCOUNT REFERENCE"),
            "STMT_DT": ("DATE", "STATEMENT DATE"),
            "NEW_BAL": ("PIC S9(10)V99", "NEW BALANCE"),
            "MIN_PMT_DUE": ("PIC 9(8)V99", "MINIMUM PAYMENT DUE"),
            "INT_CHG": ("PIC 9(8)V99", "INTEREST CHARGED"),
            "FEE_CHG": ("PIC 9(8)V99", "FEES CHARGED"),
            "CYCLE_SPEND": ("PIC 9(10)V99", "CYCLE SPEND"),
        }},
        "TRAN": {"key": "TRAN_REF", "columns": {
            "TRAN_REF": ("PIC 9(12)", "TRANSACTION REFERENCE"),
            "CRD_ACCT_REF": ("PIC 9(10)", "CARD ACCOUNT REFERENCE"),
            "AMOUNT": ("PIC 9(10)V99", "TRANSACTION AMOUNT"),
            "DR_CR_IND": ("PIC X(1)", "DEBIT CREDIT INDICATOR"),
            "TRAN_DT": ("DATE", "TRANSACTION DATE"),
            "PURCH_DT": ("DATE", "PURCHASE DATE"),
            "MCC_CD": ("PIC X(4)", "MERCHANT CATEGORY CODE"),
            "CASHBACK_AMT": ("PIC 9(6)V99", "CASHBACK AMOUNT"),
        }},
    }
    derivations = {
        "CRD_ACCT.REVOLVER_FLG": (
            "SELECT s.CRD_ACCT_REF, CASE WHEN MAX(s.INT_CHG) > 0 THEN 'Y' ELSE 'N' END AS REVOLVER_FLG "
            "FROM STMT s WHERE s.STMT_DT >= ADD_MONTHS(SYSDATE, -1) GROUP BY s.CRD_ACCT_REF"),
        "CRD_ACCT.CASHBACK_EARNED": (
            "SELECT t.CRD_ACCT_REF, SUM(t.CASHBACK_AMT) AS CASHBACK_EARNED FROM TRAN t GROUP BY t.CRD_ACCT_REF"),
        "STMT.INT_CHG": ("SELECT r.STMT_REF, r.INT_AMT + r.FEE_AMT AS INT_CHG FROM STMT_RAW r"),
        "TRAN.TRAN_DT": ("SELECT r.TRAN_REF, r.POST_DATE AS TRAN_DT FROM TRAN_RAW r"),
    }
    return {"CRD_ACCT": acct, "STMT": stmt, "TRAN": tx}, schema, derivations


GROUND_TRUTH = [
    ("CRD_ACCT.CRD_ACCT_REF",    "card_account.account_id",         "exact",     [], None),
    ("CRD_ACCT.CARDHOLDER_NAME", "card_account.holder_name",        "exact",     [], None),
    ("CRD_ACCT.CR_LMT",          "card_account.credit_limit",       "conflict",  ["null_semantics"], None),
    ("CRD_ACCT.UTIL_PCT",        "card_account.utilization_ratio",  "transform", ["scale"], None),
    ("CRD_ACCT.ACCT_OPN_DT",     "card_account.open_date",          "exact",     [], None),
    ("CRD_ACCT.PROD_CD",         "card_account.product_tier",       "transform", ["code_set"], None),
    ("CRD_ACCT.AUTOPAY_IND",     "card_account.autopay_enabled",    "exact",     [], None),
    ("CRD_ACCT.REVOLVER_FLG",    "card_account.is_revolver",        "conflict",  ["population"], None),
    ("CRD_ACCT.CASHBACK_EARNED", None,                              "conflict",  ["grain", "unit"], "card_transaction.cashback_earned"),
    ("STMT.STMT_REF",            "statement.statement_id",          "exact",     [], None),
    ("STMT.CRD_ACCT_REF",        "statement.account_id",            "exact",     [], None),
    ("STMT.STMT_DT",             "statement.statement_date",        "exact",     [], None),
    ("STMT.NEW_BAL",             "statement.new_balance",           "exact",     [], None),
    ("STMT.MIN_PMT_DUE",         "statement.minimum_due",           "exact",     [], None),
    ("STMT.INT_CHG",             "statement.interest_charged",      "conflict",  ["inclusion"], None),
    ("STMT.FEE_CHG",             "statement.fees_charged",          "exact",     [], None),
    ("STMT.CYCLE_SPEND",         "statement.cycle_spend",           "exact",     [], None),
    ("TRAN.TRAN_REF",            "card_transaction.transaction_id", "exact",     [], None),
    ("TRAN.CRD_ACCT_REF",        "card_transaction.account_id",     "exact",     [], None),
    ("TRAN.AMOUNT",              "card_transaction.amount",         "transform", ["sign"], None),
    ("TRAN.DR_CR_IND",           None,                              "unmatched", [], None),
    ("TRAN.TRAN_DT",             "card_transaction.post_date",      "conflict",  ["temporal"], "card_transaction.transaction_date"),
    ("TRAN.PURCH_DT",            "card_transaction.transaction_date", "exact",   [], None),
    ("TRAN.MCC_CD",              "card_transaction.merchant_category", "transform", ["code_set"], None),
    ("TRAN.CASHBACK_AMT",        "card_transaction.cashback_earned", "transform", ["unit"], None),
]
SOURCE_DIALECT = "oracle"
TARGET_DIALECT = "snowflake"
NAMES = ("meridian_pinecrest", "Meridian Card Services", "Pinecrest Bank")
