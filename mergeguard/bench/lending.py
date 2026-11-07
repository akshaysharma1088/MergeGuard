"""Held-out scenario B: Harborline Credit Union (acquirer) buys Summit Lending (acquired).

Different domain (consumer lending), different naming style (CamelCase legacy source),
and different forms of each conflict than the Keystone scenario:
inclusion via escrow and accrued interest (not fees), population via a 60 vs 30
days-past-due threshold, temporal via received vs effective date, scale via percent rates,
code sets with full names vs codes, and a borrower-level vs loan-level grain clash.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .generate import AS_OF, _business_day, _people

STATES = {"IL": "Illinois", "IN": "Indiana", "WI": "Wisconsin", "MI": "Michigan", "OH": "Ohio",
          "IA": "Iowa", "MN": "Minnesota", "MO": "Missouri"}
STATE_P = [0.35, 0.15, 0.12, 0.12, 0.1, 0.06, 0.05, 0.05]


def _phone(rng, n, style):
    a, b, c = rng.integers(200, 999, n), rng.integers(200, 999, n), rng.integers(0, 9999, n)
    if style == "digits":
        return [f"{x}{y}{z:04d}" for x, y, z in zip(a, b, c)]
    return [f"({x}) {y}-{z:04d}" for x, y, z in zip(a, b, c)]


def _loans(rng, owner_ids, n):
    typ = rng.choice(["AUTO", "MORTGAGE", "PERSONAL", "HELOC"], n, p=[0.45, 0.25, 0.2, 0.1])
    principal = np.round(np.where(typ == "MORTGAGE", rng.lognormal(12.2, 0.4, n), rng.lognormal(9.6, 0.6, n)), 2)
    rate = np.round(np.where(typ == "MORTGAGE", rng.uniform(0.055, 0.075, n), rng.uniform(0.06, 0.18, n)), 4)
    orig = [AS_OF - timedelta(days=int(d)) for d in rng.integers(30, 365 * 8, n)]
    term = np.where(typ == "MORTGAGE", 360, rng.choice([36, 60, 72], n))
    mat = [o + timedelta(days=int(t) * 30) for o, t in zip(orig, term)]
    dpd = np.where(rng.random(n) < 0.86, 0, rng.choice([5, 15, 35, 45, 65, 95, 125], n))
    escrow = np.where(typ == "MORTGAGE", np.round(rng.uniform(800, 6000, n), 2), np.nan)
    return dict(owner=rng.choice(owner_ids, n), typ=typ, principal=principal, rate=rate, orig=orig,
                mat=mat, dpd=dpd, escrow=escrow)


def _payments(rng, loan_ids, loan_typ, n):
    idx = rng.integers(0, len(loan_ids), n)
    pi = np.round(rng.lognormal(6.2, 0.6, n), 2)
    escrow_pd = np.where(loan_typ[idx] == "MORTGAGE", np.round(rng.uniform(150, 600, n), 2), 0.0)
    received = [AS_OF - timedelta(days=int(d)) for d in rng.integers(0, 365, n)]
    received_ts = [pd.Timestamp(d) + pd.Timedelta(minutes=int(m)) for d, m in zip(received, rng.integers(0, 1440, n))]
    effective = [_business_day(d + timedelta(days=int(k))) for d, k in zip(received, rng.integers(1, 4, n))]
    method = rng.choice(["ACH", "CHECK", "CARD", "CASH"], n, p=[0.6, 0.2, 0.15, 0.05])
    return dict(loan=np.asarray(loan_ids)[idx], pi=pi, escrow=escrow_pd, received=received,
                received_ts=received_ts, effective=effective, method=method)


def build_acquirer(rng, n=3000):
    first, last, _, since = _people(rng, n)
    ids = np.arange(10001, 10001 + n)
    member = pd.DataFrame({
        "member_id": ids, "given_name": first, "surname": last,
        "phone_number": _phone(rng, n, "digits"), "member_since": since,
        "state_code": rng.choice(list(STATES), n, p=STATE_P),
        "credit_score": rng.normal(705, 60, n).clip(300, 850).round().astype(int),
    })
    L = _loans(rng, ids, int(n * 1.3))
    loan = pd.DataFrame({
        "loan_id": np.arange(1, len(L["owner"]) + 1), "member_id": L["owner"],
        "loan_type": L["typ"], "principal_balance": L["principal"], "interest_rate": L["rate"],
        "origination_date": L["orig"], "maturity_date": L["mat"], "days_past_due": L["dpd"],
        "escrow_balance": np.where(np.isnan(L["escrow"]), np.where(rng.random(len(L["owner"])) < 0.03, np.nan, 0.0),
                                   L["escrow"]),
    })
    P = _payments(rng, loan.loan_id.to_numpy(), loan.loan_type.to_numpy(), len(loan) * 10)
    payment = pd.DataFrame({
        "payment_id": np.arange(1, len(P["loan"]) + 1), "loan_id": P["loan"],
        "payment_amount": P["pi"], "payment_date": P["effective"], "received_ts": P["received_ts"],
        "payment_method": P["method"],
    })
    worst = loan.groupby("member_id").days_past_due.max()
    member["is_delinquent"] = member.member_id.map(worst).fillna(0).ge(30)
    schema = {
        "member": {"key": "member_id", "columns": {
            "member_id": ("NUMBER(38,0)", "Unique member identifier"),
            "given_name": ("VARCHAR(40)", "Member first name"),
            "surname": ("VARCHAR(60)", "Member last name"),
            "phone_number": ("VARCHAR(10)", "Primary phone, ten digits, no punctuation"),
            "member_since": ("DATE", "Date the membership started"),
            "state_code": ("VARCHAR(2)", "Two letter USPS state code of residence"),
            "credit_score": ("NUMBER(3,0)", "Most recent FICO credit score"),
            "is_delinquent": ("BOOLEAN", "True when any loan of the member is 30 or more days past due"),
        }},
        "loan": {"key": "loan_id", "columns": {
            "loan_id": ("NUMBER(38,0)", "Unique loan identifier"),
            "member_id": ("NUMBER(38,0)", "Borrowing member"),
            "loan_type": ("VARCHAR(10)", "AUTO, MORTGAGE, PERSONAL or HELOC"),
            "principal_balance": ("NUMBER(14,2)", "Outstanding principal in dollars, excluding accrued interest"),
            "interest_rate": ("NUMBER(6,4)", "Annual interest rate as a decimal fraction"),
            "origination_date": ("DATE", "Date the loan was funded"),
            "maturity_date": ("DATE", "Scheduled final payment date"),
            "days_past_due": ("NUMBER(5,0)", "Days the loan is past due as of the snapshot"),
            "escrow_balance": ("NUMBER(12,2)", "Escrow balance; 0 when the loan has no escrow, NULL when unknown"),
        }},
        "payment": {"key": "payment_id", "columns": {
            "payment_id": ("NUMBER(38,0)", "Unique payment identifier"),
            "loan_id": ("NUMBER(38,0)", "Loan the payment applies to"),
            "payment_amount": ("NUMBER(12,2)", "Principal and interest paid, excluding escrow"),
            "payment_date": ("DATE", "Effective date the payment was applied to the loan"),
            "received_ts": ("TIMESTAMP_NTZ", "When the payment was received"),
            "payment_method": ("VARCHAR(5)", "ACH, CHECK, CARD or CASH"),
        }},
    }
    derivations = {
        "member.is_delinquent": (
            "SELECT m.member_id, MAX(l.days_past_due) >= 30 AS is_delinquent "
            "FROM member m JOIN loan l ON l.member_id = m.member_id GROUP BY m.member_id"),
        "payment.payment_amount": (
            "SELECT r.payment_id, r.principal_paid + r.interest_paid AS payment_amount FROM payment_raw r"),
        "payment.payment_date": (
            "SELECT r.payment_id, r.effective_date AS payment_date FROM payment_raw r"),
    }
    return {"member": member, "loan": loan, "payment": payment}, schema, derivations


def build_acquired(rng, n=2000):
    first, last, _, since = _people(rng, n)
    ids = np.arange(800001, 800001 + n)
    borrower = pd.DataFrame({
        "BorrowerKey": ids, "BorrowerName": [f"{f} {l}" for f, l in zip(first, last)],
        "PhoneNbr": _phone(rng, n, "pretty"), "CustSinceDt": since,
        "StateNm": [STATES[s] for s in rng.choice(list(STATES), n, p=STATE_P)],
        "FicoScore": rng.normal(705, 60, n).clip(300, 850).round().astype(int),
        "LoanOfficerId": rng.choice([f"LO{i:02d}" for i in range(1, 31)], n),
    })
    L = _loans(rng, ids, int(n * 1.3))
    accrued = np.round(L["principal"] * L["rate"] / 12 * rng.uniform(0.2, 1.0, len(L["owner"])), 2)
    loan = pd.DataFrame({
        "LoanKey": np.arange(5000001, 5000001 + len(L["owner"])), "BorrowerKey": L["owner"],
        "LoanTypCd": pd.Series(L["typ"]).map({"AUTO": "A", "MORTGAGE": "M", "PERSONAL": "P", "HELOC": "H"}).to_numpy(),
        "CurrBal": np.round(L["principal"] + accrued, 2),            # INCLUSION: principal + accrued interest
        "PrinBal": L["principal"],                                  # hidden match for principal_balance
        "IntRate": np.round(L["rate"] * 100, 2),                    # SCALE: percent
        "OrigDt": L["orig"], "MatDt": L["mat"],
        "DaysDelinquent": L["dpd"],                                 # hidden match for days_past_due
        "EscrowBal": L["escrow"],                                   # NULL = no escrow
    })
    P = _payments(rng, loan.LoanKey.to_numpy(), pd.Series(L["typ"]).to_numpy(), len(loan) * 10)
    pmt = pd.DataFrame({
        "PmtKey": np.arange(90000001, 90000001 + len(P["loan"])), "LoanKey": P["loan"],
        "PaymentAmount": np.round(P["pi"] + P["escrow"], 2),        # FALSE FRIEND: includes escrow
        "PmtPI": P["pi"],                                           # hidden match for payment_amount
        "PaymentDate": P["received"],                               # FALSE FRIEND: received, not effective
        "EffDt": P["effective"],                                    # hidden match for payment_date
        "PmtMethCd": pd.Series(P["method"]).map({"ACH": "E", "CHECK": "K", "CARD": "C", "CASH": "X"}).to_numpy(),
    })
    worst = loan.groupby("BorrowerKey").DaysDelinquent.max()
    borrower["DelinqInd"] = np.where(borrower.BorrowerKey.map(worst).fillna(0) >= 60, "Y", "N")  # POPULATION: 60 dpd
    borrower["DaysPastDue"] = borrower.BorrowerKey.map(worst).fillna(0).astype(int)              # GRAIN: per borrower
    schema = {
        "Borrower": {"key": "BorrowerKey", "columns": {
            "BorrowerKey": ("INTEGER", "Borrower key"),
            "BorrowerName": ("VARCHAR(100)", "Borrower name"),
            "PhoneNbr": ("VARCHAR(14)", "Phone"),
            "CustSinceDt": ("DATE", "Customer since"),
            "StateNm": ("VARCHAR(20)", "State"),
            "FicoScore": ("SMALLINT", "FICO"),
            "LoanOfficerId": ("VARCHAR(4)", "Assigned loan officer"),
            "DelinqInd": ("CHAR(1)", "Delinquent indicator"),
            "DaysPastDue": ("INTEGER", "Days past due"),
        }},
        "Loan": {"key": "LoanKey", "columns": {
            "LoanKey": ("INTEGER", "Loan key"),
            "BorrowerKey": ("INTEGER", "Borrower key"),
            "LoanTypCd": ("CHAR(1)", "Loan type code"),
            "CurrBal": ("MONEY", "Current balance"),
            "PrinBal": ("MONEY", "Principal"),
            "IntRate": ("DECIMAL(5,2)", "Interest rate"),
            "OrigDt": ("DATE", "Origination"),
            "MatDt": ("DATE", "Maturity"),
            "DaysDelinquent": ("INTEGER", "Days delinquent"),
            "EscrowBal": ("MONEY", "Escrow balance"),
        }},
        "Pmt": {"key": "PmtKey", "columns": {
            "PmtKey": ("INTEGER", "Payment key"),
            "LoanKey": ("INTEGER", "Loan key"),
            "PaymentAmount": ("MONEY", "Payment amount"),
            "PmtPI": ("MONEY", "P and I"),
            "PaymentDate": ("DATE", "Payment date"),
            "EffDt": ("DATE", "Effective date"),
            "PmtMethCd": ("CHAR(1)", "Method"),
        }},
    }
    derivations = {
        "Borrower.DelinqInd": (
            "SELECT b.BorrowerKey, CASE WHEN MAX(l.DaysDelinquent) >= 60 THEN 'Y' ELSE 'N' END AS DelinqInd "
            "FROM Borrower b JOIN Loan l ON l.BorrowerKey = b.BorrowerKey GROUP BY b.BorrowerKey"),
        "Borrower.DaysPastDue": (
            "SELECT l.BorrowerKey, MAX(l.DaysDelinquent) AS DaysPastDue FROM Loan l GROUP BY l.BorrowerKey"),
        "Loan.CurrBal": ("SELECT r.LoanKey, r.PrinBal + r.AccruedInt AS CurrBal FROM LoanRaw r"),
        "Pmt.PaymentAmount": ("SELECT r.PmtKey, r.PrinPd + r.IntPd + r.EscrowPd AS PaymentAmount FROM PmtRaw r"),
        "Pmt.PmtPI": ("SELECT r.PmtKey, r.PrinPd + r.IntPd AS PmtPI FROM PmtRaw r"),
        "Pmt.PaymentDate": ("SELECT r.PmtKey, CAST(r.ReceivedTs AS DATE) AS PaymentDate FROM PmtRaw r"),
    }
    return {"Borrower": borrower, "Loan": loan, "Pmt": pmt}, schema, derivations


GROUND_TRUTH = [
    ("Borrower.BorrowerKey",   "member.member_id",          "exact",      [], None),
    ("Borrower.BorrowerName",  "member.given_name+member.surname", "structural", [], None),
    ("Borrower.PhoneNbr",      "member.phone_number",       "transform",  ["format"], None),
    ("Borrower.CustSinceDt",   "member.member_since",       "exact",      [], None),
    ("Borrower.StateNm",       "member.state_code",         "transform",  ["code_set"], None),
    ("Borrower.FicoScore",     "member.credit_score",       "exact",      [], None),
    ("Borrower.LoanOfficerId", None,                        "unmatched",  [], None),
    ("Borrower.DelinqInd",     "member.is_delinquent",      "conflict",   ["population"], None),
    ("Borrower.DaysPastDue",   None,                        "conflict",   ["grain"], "loan.days_past_due"),
    ("Loan.LoanKey",           "loan.loan_id",              "exact",      [], None),
    ("Loan.BorrowerKey",       "loan.member_id",            "exact",      [], None),
    ("Loan.LoanTypCd",         "loan.loan_type",            "transform",  ["code_set"], None),
    ("Loan.CurrBal",           None,                        "conflict",   ["inclusion"], "loan.principal_balance"),
    ("Loan.PrinBal",           "loan.principal_balance",    "exact",      [], None),
    ("Loan.IntRate",           "loan.interest_rate",        "transform",  ["scale"], None),
    ("Loan.OrigDt",            "loan.origination_date",     "exact",      [], None),
    ("Loan.MatDt",             "loan.maturity_date",        "exact",      [], None),
    ("Loan.DaysDelinquent",    "loan.days_past_due",        "exact",      [], None),
    ("Loan.EscrowBal",         "loan.escrow_balance",       "conflict",   ["null_semantics"], None),
    ("Pmt.PmtKey",             "payment.payment_id",        "exact",      [], None),
    ("Pmt.LoanKey",            "payment.loan_id",           "exact",      [], None),
    ("Pmt.PaymentAmount",      None,                        "conflict",   ["inclusion"], "payment.payment_amount"),
    ("Pmt.PmtPI",              "payment.payment_amount",    "exact",      [], None),
    ("Pmt.PaymentDate",        "payment.received_ts",       "conflict",   ["temporal"], "payment.payment_date"),
    ("Pmt.EffDt",              "payment.payment_date",      "exact",      [], None),
    ("Pmt.PmtMethCd",          "payment.payment_method",    "transform",  ["code_set"], None),
]
SOURCE_DIALECT = "tsql"
TARGET_DIALECT = "snowflake"
NAMES = ("harborline_summit", "Harborline Credit Union", "Summit Lending")
