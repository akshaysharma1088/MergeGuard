"""Held-out scenario D: Lakeshore Mutual (acquirer) buys Prairie Insurance Group (acquired).

Written and frozen before MergeGuard v0.0.2 existed. New domain (property and casualty
insurance), Hungarian-notation SQL Server source (nPolicyNo, curPremium, dtLoss, sName),
numbers stored as text, and conflicts in forms not used in scenarios A to C:
a monthly vs annual premium (factor 12), deductibles in thousands, a sentinel end date vs NULL,
"Last, First" names, ZIP codes stored as integers, reported vs loss date, indemnity vs
indemnity plus adjustment expense, in-force by dates vs a status code, and holder-level vs
policy-level premium.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .generate import AS_OF, _people

LINES = {"AUTO": "AU", "HOME": "HO", "UMBRELLA": "UM", "RENTERS": "RE"}
LINE_P = [0.5, 0.3, 0.08, 0.12]
OPEN_END = date(9999, 12, 31)


def _policies(rng, holders, n):
    line = rng.choice(list(LINES), n, p=LINE_P)
    annual = np.round(np.where(line == "HOME", rng.lognormal(7.3, 0.3, n),
                               np.where(line == "AUTO", rng.lognormal(7.0, 0.35, n), rng.lognormal(5.6, 0.4, n))), 2)
    ded = rng.choice([250, 500, 1000, 2500, 5000], n, p=[0.1, 0.35, 0.35, 0.15, 0.05]).astype(float)
    eff = [AS_OF - timedelta(days=int(d)) for d in rng.integers(0, 365 * 6, n)]
    cancelled = rng.random(n) < 0.22
    cancel = [e + timedelta(days=int(k)) if c else None for e, c, k in zip(eff, cancelled, rng.integers(30, 900, n))]
    cancel = [c if (c is None or c <= AS_OF) else None for c in cancel]
    return dict(holder=rng.choice(holders, n), line=line, annual=annual, ded=ded, eff=eff, cancel=cancel)


def _claims(rng, policy_ids, eff_dates, n):
    idx = rng.integers(0, len(policy_ids), n)
    loss = [max(eff_dates[i], AS_OF - timedelta(days=int(d))) for i, d in zip(idx, rng.integers(0, 900, n))]
    reported = [l + timedelta(days=int(k)) for l, k in zip(loss, rng.geometric(0.15, n))]
    reported = [min(r, AS_OF) for r in reported]
    indemnity = np.round(rng.lognormal(8.2, 1.1, n), 2)
    lae = np.round(indemnity * rng.uniform(0.05, 0.25, n), 2)
    status = rng.choice(["OPEN", "CLOSED", "REOPENED"], n, p=[0.3, 0.62, 0.08])
    return dict(policy=np.asarray(policy_ids)[idx], loss=loss, reported=reported, indemnity=indemnity, lae=lae,
                status=status)


def build_acquirer(rng, n=3000):
    first, last, dob, since = _people(rng, n)
    ids = np.arange(1, n + 1)
    holder = pd.DataFrame({
        "policyholder_id": ids, "first_name": first, "last_name": last, "date_of_birth": dob,
        "postal_code": [f"{z:05d}" for z in rng.integers(601, 99950, n)],
        "customer_since": since,
    })
    P = _policies(rng, ids, int(n * 1.6))
    policy = pd.DataFrame({
        "policy_id": np.arange(100001, 100001 + len(P["holder"])), "policyholder_id": P["holder"],
        "line_of_business": P["line"], "annual_premium": P["annual"], "deductible": P["ded"],
        "effective_date": P["eff"], "expiration_date": [c or OPEN_END for c in P["cancel"]],
    })
    policy["is_in_force"] = [(e <= AS_OF) and (x > AS_OF) for e, x in zip(policy.effective_date, policy.expiration_date)]
    C = _claims(rng, policy.policy_id.to_numpy(), list(policy.effective_date), len(policy) // 2)
    claim = pd.DataFrame({
        "claim_id": np.arange(1, len(C["policy"]) + 1), "policy_id": C["policy"], "loss_date": C["loss"],
        "reported_date": C["reported"], "indemnity_amount": C["indemnity"], "expense_amount": C["lae"],
        "claim_status": C["status"],
    })
    schema = {
        "policyholder": {"key": "policyholder_id", "columns": {
            "policyholder_id": ("NUMBER(38,0)", "Policyholder identifier"),
            "first_name": ("VARCHAR(40)", "Given name"),
            "last_name": ("VARCHAR(60)", "Family name"),
            "date_of_birth": ("DATE", "Date of birth"),
            "postal_code": ("VARCHAR(5)", "Five digit ZIP code with leading zeros"),
            "customer_since": ("DATE", "Date the first policy started"),
        }},
        "policy": {"key": "policy_id", "columns": {
            "policy_id": ("NUMBER(38,0)", "Policy identifier"),
            "policyholder_id": ("NUMBER(38,0)", "Insured policyholder"),
            "line_of_business": ("VARCHAR(10)", "AUTO, HOME, UMBRELLA or RENTERS"),
            "annual_premium": ("NUMBER(10,2)", "Written premium for twelve months in dollars"),
            "deductible": ("NUMBER(10,2)", "Per claim deductible in dollars"),
            "effective_date": ("DATE", "Policy start date"),
            "expiration_date": ("DATE", "End of coverage; 9999-12-31 while the policy is open"),
            "is_in_force": ("BOOLEAN", "Coverage active today: effective date passed and expiration date not reached"),
        }},
        "claim": {"key": "claim_id", "columns": {
            "claim_id": ("NUMBER(38,0)", "Claim identifier"),
            "policy_id": ("NUMBER(38,0)", "Policy the claim is filed under"),
            "loss_date": ("DATE", "Date the loss occurred"),
            "reported_date": ("DATE", "Date the loss was reported to the insurer"),
            "indemnity_amount": ("NUMBER(12,2)", "Amount paid to the claimant, excluding adjustment expense"),
            "expense_amount": ("NUMBER(12,2)", "Loss adjustment expense"),
            "claim_status": ("VARCHAR(8)", "OPEN, CLOSED or REOPENED"),
        }},
    }
    derivations = {
        "policy.is_in_force": (
            "SELECT p.policy_id, p.effective_date <= DATE '2026-10-31' AND p.expiration_date > DATE '2026-10-31' "
            "AS is_in_force FROM policy p"),
        "claim.indemnity_amount": ("SELECT r.claim_id, r.indemnity_paid AS indemnity_amount FROM claim_raw r"),
    }
    return {"policyholder": holder, "policy": policy, "claim": claim}, schema, derivations


def build_acquired(rng, n=2000):
    first, last, dob, since = _people(rng, n)
    ids = np.arange(70001, 70001 + n)
    holder = pd.DataFrame({
        "nInsuredNo": ids, "sName": [f"{l}, {f}" for f, l in zip(first, last)], "dtBirth": dob,
        "nZip": rng.integers(601, 99950, n), "dtFirstPolicy": since,
        "sAgentCode": rng.choice([f"AG{i:03d}" for i in range(1, 61)], n),
    })
    P = _policies(rng, ids, int(n * 1.6))
    pol = pd.DataFrame({
        "nPolicyNo": np.arange(3000001, 3000001 + len(P["holder"])), "nInsuredNo": P["holder"],
        "sLineCd": pd.Series(P["line"]).map(LINES).to_numpy(),
        "curPremium": np.round(P["annual"] / 12, 2),                       # UNIT: monthly
        "sDeductibleK": [f"{d / 1000:.2f}" for d in P["ded"]],            # SCALE: thousands, stored as text
        "dtEffective": P["eff"], "dtCancel": P["cancel"],                  # NULL = still open
    })
    in_force = [(e <= AS_OF) and (c is None) for e, c in zip(pol.dtEffective, pol.dtCancel)]
    status = np.where(in_force, "A", "X")
    flip = rng.random(len(pol)) < 0.1                                      # status lags reality
    pol["sStatus"] = np.where(flip, np.where(status == "A", "X", "A"), status)
    holder["curTotalPremium"] = holder.nInsuredNo.map(pol.groupby("nInsuredNo").curPremium.sum() * 12).fillna(0).round(2)
    C = _claims(rng, pol.nPolicyNo.to_numpy(), list(pol.dtEffective), len(pol) // 2)
    clm = pd.DataFrame({
        "nClaimNo": np.arange(9100001, 9100001 + len(C["policy"])), "nPolicyNo": C["policy"],
        "dtClaim": C["reported"],                                          # FALSE FRIEND for loss date: reported
        "dtOccurred": C["loss"],                                           # hidden match for loss_date
        "curClaimAmt": np.round(C["indemnity"] + C["lae"], 2),             # INCLUSION: indemnity + expense
        "curIndemnity": C["indemnity"],
        "curLAE": C["lae"],
        "nStatus": pd.Series(C["status"]).map({"OPEN": 1, "CLOSED": 2, "REOPENED": 3}).to_numpy(),
    })
    schema = {
        "tblInsured": {"key": "nInsuredNo", "columns": {
            "nInsuredNo": ("int", "Insured number"),
            "sName": ("nvarchar(100)", "Insured name"),
            "dtBirth": ("datetime", "Birth date"),
            "nZip": ("int", "Zip"),
            "dtFirstPolicy": ("datetime", "First policy date"),
            "sAgentCode": ("nvarchar(5)", "Agent"),
            "curTotalPremium": ("money", "Total premium"),
        }},
        "tblPolicy": {"key": "nPolicyNo", "columns": {
            "nPolicyNo": ("int", "Policy number"),
            "nInsuredNo": ("int", "Insured number"),
            "sLineCd": ("nvarchar(2)", "Line"),
            "curPremium": ("money", "Premium"),
            "sDeductibleK": ("nvarchar(10)", "Deductible (K)"),
            "dtEffective": ("datetime", "Effective"),
            "dtCancel": ("datetime", "Cancel date"),
            "sStatus": ("nchar(1)", "Status"),
        }},
        "tblClaim": {"key": "nClaimNo", "columns": {
            "nClaimNo": ("int", "Claim number"),
            "nPolicyNo": ("int", "Policy number"),
            "dtClaim": ("datetime", "Claim date"),
            "dtOccurred": ("datetime", "Occurrence date"),
            "curClaimAmt": ("money", "Claim amount"),
            "curIndemnity": ("money", "Indemnity"),
            "curLAE": ("money", "LAE"),
            "nStatus": ("tinyint", "Status"),
        }},
    }
    derivations = {
        "tblInsured.curTotalPremium": (
            "SELECT p.nInsuredNo, SUM(p.curPremium) * 12 AS curTotalPremium FROM tblPolicy p GROUP BY p.nInsuredNo"),
        "tblPolicy.sStatus": (
            "SELECT p.nPolicyNo, CASE WHEN p.sStatusRaw IN ('A', 'R') THEN 'A' ELSE 'X' END AS sStatus FROM tblPolicyRaw p"),
        "tblClaim.curClaimAmt": ("SELECT r.nClaimNo, r.curIndemnity + r.curLAE AS curClaimAmt FROM tblClaimRaw r"),
        "tblClaim.dtClaim": ("SELECT r.nClaimNo, r.dtReported AS dtClaim FROM tblClaimRaw r"),
    }
    return {"tblInsured": holder, "tblPolicy": pol, "tblClaim": clm}, schema, derivations


GROUND_TRUTH = [
    ("tblInsured.nInsuredNo",      "policyholder.policyholder_id",   "exact",      [], None),
    ("tblInsured.sName",           "policyholder.first_name+policyholder.last_name", "structural", [], None),
    ("tblInsured.dtBirth",         "policyholder.date_of_birth",     "exact",      [], None),
    ("tblInsured.nZip",            "policyholder.postal_code",       "transform",  ["format"], None),
    ("tblInsured.dtFirstPolicy",   "policyholder.customer_since",    "exact",      [], None),
    ("tblInsured.sAgentCode",      None,                             "unmatched",  [], None),
    ("tblInsured.curTotalPremium", None,                             "conflict",   ["grain"], "policy.annual_premium"),
    ("tblPolicy.nPolicyNo",        "policy.policy_id",               "exact",      [], None),
    ("tblPolicy.nInsuredNo",       "policy.policyholder_id",         "exact",      [], None),
    ("tblPolicy.sLineCd",          "policy.line_of_business",        "transform",  ["code_set"], None),
    ("tblPolicy.curPremium",       "policy.annual_premium",          "transform",  ["unit"], None),
    ("tblPolicy.sDeductibleK",     "policy.deductible",              "transform",  ["scale"], None),
    ("tblPolicy.dtEffective",      "policy.effective_date",          "exact",      [], None),
    ("tblPolicy.dtCancel",         "policy.expiration_date",         "conflict",   ["null_semantics"], None),
    ("tblPolicy.sStatus",          "policy.is_in_force",             "conflict",   ["population"], None),
    ("tblClaim.nClaimNo",          "claim.claim_id",                 "exact",      [], None),
    ("tblClaim.nPolicyNo",         "claim.policy_id",                "exact",      [], None),
    ("tblClaim.dtClaim",           "claim.reported_date",            "conflict",   ["temporal"], "claim.loss_date"),
    ("tblClaim.dtOccurred",        "claim.loss_date",                "exact",      [], None),
    ("tblClaim.curClaimAmt",       None,                             "conflict",   ["inclusion"], "claim.indemnity_amount"),
    ("tblClaim.curIndemnity",      "claim.indemnity_amount",         "exact",      [], None),
    ("tblClaim.curLAE",            "claim.expense_amount",           "exact",      [], None),
    ("tblClaim.nStatus",           "claim.claim_status",             "transform",  ["code_set"], None),
]
SOURCE_DIALECT = "tsql"
TARGET_DIALECT = "snowflake"
NAMES = ("lakeshore_prairie", "Lakeshore Mutual", "Prairie Insurance Group")
