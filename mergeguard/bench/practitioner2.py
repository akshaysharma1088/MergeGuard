"""Scenario F: Northfield Bancorp (acquirer) buys Willow Creek Bank (acquired).

Built from ten traps written by the practitioner co-author after MergeGuard v0.0.4 was frozen
(see PREREGISTRATION.md). Each trap is tagged T1..T10 below.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .cards_portfolio import MCC
from .generate import AS_OF, _business_day, _email, _people

INTERNAL_CAT = {"GROCERY": "GROC", "TRAVEL": "TRVL", "DINING": "DINE", "FUEL": "FUEL", "OTHER": "RETL"}


def _population(rng, n_cust, starts, domain):
    c0, card0, tx0, d0, a0 = starts
    first, last, _, _ = _people(rng, n_cust)
    ids = np.arange(c0, c0 + n_cust)
    business = rng.random(n_cust) < 0.15
    gross = np.where(business, np.nan, np.round(rng.lognormal(11.0, 0.5, n_cust), -2))
    revenue = np.where(business, np.round(rng.lognormal(14.8, 1.2, n_cust), -3), np.nan)
    exposure = np.where(business, revenue * rng.lognormal(-1.6, 0.9, n_cust), np.nan)
    last_kyc = [AS_OF - timedelta(days=int(d)) for d in rng.integers(1, 730, n_cust)]
    next_kyc = [k + timedelta(days=int(365 * y)) for k, y in zip(last_kyc, rng.choice([1, 2, 3], n_cust))]
    cust = dict(id=ids, name=[f"{f} {l}" for f, l in zip(first, last)], business=business, gross=gross,
                revenue=revenue, exposure=exposure, last_kyc=last_kyc, next_kyc=next_kyc,
                email=[_email(rng, f, l, domain) for f, l in zip(first, last)])

    n_card = int(n_cust * 0.9)
    card = dict(id=np.arange(card0, card0 + n_card), cust=rng.choice(ids, n_card),
                number=rng.integers(4000000000000000, 4999999999999999, n_card, dtype=np.int64),
                status=rng.choice(["ACTIVE", "BLOCKED", "CLOSED"], n_card, p=[0.82, 0.06, 0.12]),
                open=[AS_OF - timedelta(days=int(d)) for d in rng.integers(30, 365 * 10, n_card)])

    n_tx = n_card * 20
    idx = rng.integers(0, n_card, n_tx)
    mcc = rng.choice(list(MCC), n_tx)
    fee = np.where(rng.random(n_tx) < 0.15, np.round(rng.choice([2.5, 3.0, 5.0, 29.0, 39.0], n_tx), 2), 0.0)
    refund = np.where((fee > 0) & (rng.random(n_tx) < 0.3), np.round(fee * rng.choice([0.5, 1.0], n_tx), 2), 0.0)
    tx = dict(id=np.arange(tx0, tx0 + n_tx), card_idx=idx, amount=np.round(rng.lognormal(3.7, 1.0, n_tx), 2),
              mcc=mcc, fee=fee, refund=refund)

    n_dep = int(n_cust * 0.4)
    opened = [AS_OF - timedelta(days=int(d)) for d in rng.integers(30, 365 * 6, n_dep)]
    term = rng.choice([6, 12, 24, 36, 60], n_dep)
    orig_mat = [o + timedelta(days=int(t) * 30) for o, t in zip(opened, term)]
    auto = rng.random(n_dep) < 0.8
    renewed = []
    for m, t, a in zip(orig_mat, term, auto):
        r = m
        while a and r <= AS_OF:
            r = r + timedelta(days=int(t) * 30)
        renewed.append(r)
    dep = dict(id=np.arange(d0, d0 + n_dep), cust=rng.choice(ids, n_dep),
               principal=np.round(rng.lognormal(9.6, 0.9, n_dep), 2), open=opened, orig_mat=orig_mat, renewed=renewed)

    n_acct = int(n_cust * 0.6)
    dpd = np.where(rng.random(n_acct) < 0.72, 0, rng.choice([3, 10, 25, 40, 70, 95, 130, 160, 200], n_acct))
    charged = dpd >= 130
    prin = np.round(rng.lognormal(8.3, 0.8, n_acct), 2)
    interest = np.round(prin * rng.uniform(0.03, 0.12, n_acct), 2)
    late = np.round(rng.choice([25, 50, 75, 105], n_acct).astype(float), 2)
    secured = rng.random(n_acct) < 0.4
    appraisal = np.where(secured, np.round(rng.lognormal(12.5, 0.4, n_acct), -3), np.nan)
    assigned = (dpd > 60) & (rng.random(n_acct) < 0.7)
    acct = dict(id=np.arange(a0, a0 + n_acct), cust=rng.choice(ids, n_acct), balance=prin, dpd=dpd,
                charged=charged, interest=interest, late=late, appraisal=appraisal,
                avm=np.round(appraisal * rng.uniform(1.0, 1.5, n_acct), -2), assigned=assigned)
    return cust, card, tx, dep, acct


def build_acquirer(rng, n=3000):
    C, K, T, D, A = _population(rng, n, (1, 1, 1, 50001, 70001), "northfieldmail.com")
    customer = pd.DataFrame({
        "customer_id": C["id"], "full_name": C["name"],
        "customer_type": np.where(C["business"], "BUSINESS", "PERSON"),
        "annual_income": C["gross"],                                                       # T4: annual gross
        "annual_revenue": C["revenue"],
        "is_small_business": np.where(C["business"], C["revenue"] < 5_000_000, False),     # T8: revenue
        "kyc_review_date": C["last_kyc"],                                                  # T10: last completed
        "email": C["email"],
    })
    card = pd.DataFrame({"card_id": K["id"], "customer_id": K["cust"], "card_status": K["status"],
                         "open_date": K["open"]})                                         # T1: stable card id
    txn = pd.DataFrame({"transaction_id": T["id"], "card_id": K["id"][T["card_idx"]], "amount": T["amount"],
                        "merchant_category_code": T["mcc"],                                # T6: network MCC
                        "fee_amount": T["fee"]})                                           # T2: gross fee
    deposit = pd.DataFrame({"deposit_id": D["id"], "customer_id": D["cust"], "principal_amount": D["principal"],
                            "open_date": D["open"], "maturity_date": D["orig_mat"]})       # T3: original term end
    acct = pd.DataFrame({
        "account_id": A["id"], "customer_id": A["cust"], "current_balance": A["balance"],
        "days_past_due": A["dpd"],
        "in_collections": A["dpd"] > 0,                                                    # T9: past due
        "charge_off_amount": np.where(A["charged"], A["balance"], np.nan),                # T5: principal only
        "collateral_value": A["appraisal"],                                               # T7: original appraisal
    })
    schema = {
        "customer": {"key": "customer_id", "columns": {
            "customer_id": ("NUMBER(38,0)", "Customer identifier"),
            "full_name": ("VARCHAR(120)", "Customer or business legal name"),
            "customer_type": ("VARCHAR(8)", "PERSON or BUSINESS"),
            "annual_income": ("NUMBER(12,2)", "Self-reported annual gross income in dollars"),
            "annual_revenue": ("NUMBER(16,2)", "Annual revenue of a business customer in dollars"),
            "is_small_business": ("BOOLEAN", "Business with annual revenue under 5 million dollars"),
            "kyc_review_date": ("DATE", "Date the most recent KYC review was completed"),
            "email": ("VARCHAR(120)", "Primary email"),
        }},
        "card": {"key": "card_id", "columns": {
            "card_id": ("NUMBER(38,0)", "Card identifier; unchanged when a card is reissued"),
            "customer_id": ("NUMBER(38,0)", "Cardholder"),
            "card_status": ("VARCHAR(8)", "ACTIVE, BLOCKED or CLOSED"),
            "open_date": ("DATE", "Card account open date"),
        }},
        "card_transaction": {"key": "transaction_id", "columns": {
            "transaction_id": ("NUMBER(38,0)", "Transaction identifier"),
            "card_id": ("NUMBER(38,0)", "Card"),
            "amount": ("NUMBER(12,2)", "Transaction amount in dollars"),
            "merchant_category_code": ("VARCHAR(4)", "Four digit merchant category code from the card network"),
            "fee_amount": ("NUMBER(10,2)", "Fee charged on the transaction, before any refund"),
        }},
        "deposit": {"key": "deposit_id", "columns": {
            "deposit_id": ("NUMBER(38,0)", "Certificate of deposit identifier"),
            "customer_id": ("NUMBER(38,0)", "Depositor"),
            "principal_amount": ("NUMBER(14,2)", "Deposit principal in dollars"),
            "open_date": ("DATE", "Date the CD was opened"),
            "maturity_date": ("DATE", "End of the original CD term"),
        }},
        "credit_account": {"key": "account_id", "columns": {
            "account_id": ("NUMBER(38,0)", "Credit account identifier"),
            "customer_id": ("NUMBER(38,0)", "Borrower"),
            "current_balance": ("NUMBER(14,2)", "Outstanding balance in dollars"),
            "days_past_due": ("NUMBER(5,0)", "Days past due"),
            "in_collections": ("BOOLEAN", "Account is in collections: any amount past due"),
            "charge_off_amount": ("NUMBER(14,2)", "Unpaid principal charged off"),
            "collateral_value": ("NUMBER(14,2)", "Appraised collateral value at origination"),
        }},
    }
    derivations = {
        "customer.is_small_business": (
            "SELECT c.customer_id, COALESCE(c.annual_revenue < 5000000, FALSE) AS is_small_business FROM customer c"),
        "credit_account.in_collections": (
            "SELECT a.account_id, a.days_past_due > 0 AS in_collections FROM credit_account a"),
    }
    return ({"customer": customer, "card": card, "card_transaction": txn, "deposit": deposit, "credit_account": acct},
            schema, derivations)


def build_acquired(rng, n=2000):
    C, K, T, D, A = _population(rng, n, (300001, 1, 900000001, 6100001, 8300001), "willowcreek.com")
    cust = pd.DataFrame({
        "cust_id": C["id"], "cust_full_nm": C["name"],
        "cust_typ_cd": np.where(C["business"], "B", "P"),
        "incm_amt": np.round(C["gross"] * 0.72 / 12, 2),                                   # T4: monthly net
        "ann_rev_amt": C["revenue"],
        "sb_flg": np.where(C["business"] & (C["exposure"] < 1_000_000), "Y", "N"),         # T8: exposure
        "kyc_rvw_dt": C["next_kyc"],                                                       # T10: next deadline
        "email_addr": C["email"],
    })
    card = pd.DataFrame({"card_id": K["number"], "cust_id": K["cust"],                     # T1: 16-digit number
                         "card_stat_cd": pd.Series(K["status"]).map({"ACTIVE": "A", "BLOCKED": "B", "CLOSED": "C"}).to_numpy(),
                         "open_dt": K["open"]})
    txn = pd.DataFrame({"txn_id": T["id"], "card_id": K["number"][T["card_idx"]], "txn_amt": T["amount"],
                        "mcc_cat": pd.Series(T["mcc"]).map(MCC).map(INTERNAL_CAT).to_numpy(),  # T6: internal list
                        "fee_amt": np.round(T["fee"] - T["refund"], 2)})                  # T2: net of refunds
    dep = pd.DataFrame({"dep_id": D["id"], "cust_id": D["cust"], "prin_amt": D["principal"], "open_dt": D["open"],
                        "mat_dt": D["renewed"]})                                           # T3: auto-renewed end
    acct = pd.DataFrame({
        "acct_id": A["id"], "cust_id": A["cust"], "cur_bal": A["balance"], "days_pd": A["dpd"],
        "coll_stat_ind": np.where(A["assigned"], "Y", "N"),                                # T9: agent assigned
        "co_amt": np.where(A["charged"], np.round(A["balance"] + A["interest"] + A["late"], 2), np.nan),  # T5
        "coll_val_amt": A["avm"],                                                          # T7: monthly AVM
    })
    schema = {
        "cust_mstr": {"key": "cust_id", "columns": {
            "cust_id": ("NUMBER(10)", "Customer id"),
            "cust_full_nm": ("VARCHAR2(120)", "Customer name"),
            "cust_typ_cd": ("CHAR(1)", "Customer type"),
            "incm_amt": ("NUMBER(12,2)", "Income"),
            "ann_rev_amt": ("NUMBER(16,2)", "Annual revenue"),
            "sb_flg": ("CHAR(1)", "Small business flag"),
            "kyc_rvw_dt": ("DATE", "KYC review date"),
            "email_addr": ("VARCHAR2(120)", "Email"),
        }},
        "card_mstr": {"key": "card_id", "columns": {
            "card_id": ("NUMBER(16)", "Card id"),
            "cust_id": ("NUMBER(10)", "Customer id"),
            "card_stat_cd": ("CHAR(1)", "Card status"),
            "open_dt": ("DATE", "Open date"),
        }},
        "card_txn": {"key": "txn_id", "columns": {
            "txn_id": ("NUMBER(12)", "Transaction id"),
            "card_id": ("NUMBER(16)", "Card id"),
            "txn_amt": ("NUMBER(12,2)", "Transaction amount"),
            "mcc_cat": ("VARCHAR2(4)", "Merchant category"),
            "fee_amt": ("NUMBER(10,2)", "Fee amount"),
        }},
        "dep_acct": {"key": "dep_id", "columns": {
            "dep_id": ("NUMBER(10)", "Deposit id"),
            "cust_id": ("NUMBER(10)", "Customer id"),
            "prin_amt": ("NUMBER(14,2)", "Principal"),
            "open_dt": ("DATE", "Open date"),
            "mat_dt": ("DATE", "Maturity date"),
        }},
        "cr_acct": {"key": "acct_id", "columns": {
            "acct_id": ("NUMBER(10)", "Account id"),
            "cust_id": ("NUMBER(10)", "Customer id"),
            "cur_bal": ("NUMBER(14,2)", "Current balance"),
            "days_pd": ("NUMBER(5)", "Days past due"),
            "coll_stat_ind": ("CHAR(1)", "Collections status"),
            "co_amt": ("NUMBER(14,2)", "Charge-off amount"),
            "coll_val_amt": ("NUMBER(14,2)", "Collateral value"),
        }},
    }
    derivations = {
        "card_txn.fee_amt": ("SELECT r.txn_id, r.fee_chrg_amt - r.fee_rfnd_amt AS fee_amt FROM card_txn_raw r"),
        "cust_mstr.incm_amt": ("SELECT v.cust_id, v.verified_net_annual / 12 AS incm_amt FROM income_verification v"),
        "cust_mstr.sb_flg": (
            "SELECT e.cust_id, CASE WHEN SUM(e.exposure_amt) < 1000000 THEN 'Y' ELSE 'N' END AS sb_flg "
            "FROM credit_exposure e GROUP BY e.cust_id"),
        "cust_mstr.kyc_rvw_dt": ("SELECT k.cust_id, k.next_review_due_dt AS kyc_rvw_dt FROM kyc_schedule k"),
        "dep_acct.mat_dt": ("SELECT r.dep_id, COALESCE(r.renewed_mat_dt, r.orig_mat_dt) AS mat_dt FROM dep_raw r"),
        "cr_acct.co_amt": ("SELECT r.acct_id, r.co_prin_amt + r.co_int_amt + r.co_fee_amt AS co_amt FROM cr_raw r"),
        "cr_acct.coll_stat_ind": (
            "SELECT a.acct_id, CASE WHEN a.agency_assign_dt IS NOT NULL THEN 'Y' ELSE 'N' END AS coll_stat_ind "
            "FROM collections_assignment a"),
        "cr_acct.coll_val_amt": ("SELECT v.acct_id, v.avm_estimate_amt AS coll_val_amt FROM avm_monthly v"),
    }
    return ({"cust_mstr": cust, "card_mstr": card, "card_txn": txn, "dep_acct": dep, "cr_acct": acct},
            schema, derivations)


GROUND_TRUTH = [
    ("cust_mstr.cust_id",       "customer.customer_id",            "exact",     [], None),
    ("cust_mstr.cust_full_nm",  "customer.full_name",              "exact",     [], None),
    ("cust_mstr.cust_typ_cd",   "customer.customer_type",          "transform", ["code_set"], None),
    ("cust_mstr.incm_amt",      "customer.annual_income",          "conflict",  ["unit", "inclusion"], None),   # T4
    ("cust_mstr.ann_rev_amt",   "customer.annual_revenue",         "exact",     [], None),
    ("cust_mstr.sb_flg",        "customer.is_small_business",      "conflict",  ["population"], None),          # T8
    ("cust_mstr.kyc_rvw_dt",    "customer.kyc_review_date",        "conflict",  ["temporal"], None),            # T10
    ("cust_mstr.email_addr",    "customer.email",                  "exact",     [], None),
    ("card_mstr.card_id",       "card.card_id",                    "conflict",  ["identity"], None),            # T1
    ("card_mstr.cust_id",       "card.customer_id",                "exact",     [], None),
    ("card_mstr.card_stat_cd",  "card.card_status",                "transform", ["code_set"], None),
    ("card_mstr.open_dt",       "card.open_date",                  "exact",     [], None),
    ("card_txn.txn_id",         "card_transaction.transaction_id", "exact",     [], None),
    ("card_txn.card_id",        "card_transaction.card_id",        "conflict",  ["identity"], None),            # T1
    ("card_txn.txn_amt",        "card_transaction.amount",         "exact",     [], None),
    ("card_txn.mcc_cat",        "card_transaction.merchant_category_code", "conflict", ["code_set"], None),     # T6
    ("card_txn.fee_amt",        "card_transaction.fee_amount",     "conflict",  ["inclusion"], None),           # T2
    ("dep_acct.dep_id",         "deposit.deposit_id",              "exact",     [], None),
    ("dep_acct.cust_id",        "deposit.customer_id",             "exact",     [], None),
    ("dep_acct.prin_amt",       "deposit.principal_amount",        "exact",     [], None),
    ("dep_acct.open_dt",        "deposit.open_date",               "exact",     [], None),
    ("dep_acct.mat_dt",         "deposit.maturity_date",           "conflict",  ["temporal"], None),            # T3
    ("cr_acct.acct_id",         "credit_account.account_id",       "exact",     [], None),
    ("cr_acct.cust_id",         "credit_account.customer_id",      "exact",     [], None),
    ("cr_acct.cur_bal",         "credit_account.current_balance",  "exact",     [], None),
    ("cr_acct.days_pd",         "credit_account.days_past_due",    "exact",     [], None),
    ("cr_acct.coll_stat_ind",   "credit_account.in_collections",   "conflict",  ["population"], None),          # T9
    ("cr_acct.co_amt",          "credit_account.charge_off_amount", "conflict", ["inclusion"], None),           # T5
    ("cr_acct.coll_val_amt",    "credit_account.collateral_value", "conflict",  ["temporal"], None),            # T7
]
SOURCE_DIALECT = "oracle"
TARGET_DIALECT = "snowflake"
NAMES = ("northfield_willowcreek", "Northfield Bancorp", "Willow Creek Bank")
