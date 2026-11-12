"""Build a real public pair for MergeGuard's profiling stage: Freddie Mac vs Fannie Mae loan-level disclosures.

    python experiments/real_pair/build_gse_pair.py <freddie_orig.txt> <freddie_perf.txt> <fannie.csv> <out_dir> [loans]

Source ("acquired"): Freddie Mac Single-Family Loan-Level Dataset, one quarter (origination + monthly performance).
Target ("acquirer"): Fannie Mae Single-Family Loan Performance Data, the same quarter (one file, static and
monthly fields on every row; split here into a loan table and a loan-month table).

The data files are NOT redistributed (both publishers' terms forbid it). Register and download them yourself:
  https://freddiemac.com/research/datasets/sf-loanlevel-dataset
  https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data

Column names are the publishers' attribute names in snake case. Descriptions are one-line paraphrases of the
published glossaries (Freddie Mac General User Guide, Release 47, July 2026; Fannie Mae Glossary and File Layout,
May 2025). Columns with no values in the quarter are dropped. Fannie positions 111 to 114 are newer than the
layout used here and are dropped.

Ground truth was written from the two glossaries BEFORE any matcher was run on this pair. A conflict is labeled
only where the glossaries state different conventions (a code list, a placeholder for "not available", a date
format, the event a counter starts from). Whether a stated difference occurs in this quarter's rows was not checked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

# (position, name, sql type, cast, description)
FREDDIE_LOAN = [
    (1, "classic_fico", "NUMBER(4)", "INT", "Borrower Classic FICO score at origination. 9999 = not available."),
    (2, "first_payment_date", "CHAR(6)", "VARCHAR", "Month of the first scheduled payment, YYYYMM."),
    (3, "first_time_homebuyer_indicator", "CHAR(1)", "VARCHAR", "Y = yes, N = no, 9 = not available or not applicable."),
    (4, "maturity_date", "CHAR(6)", "VARCHAR", "Month of the final scheduled payment per the note, YYYYMM."),
    (5, "msa", "CHAR(5)", "VARCHAR", "MSA or Metropolitan Division code. Null if neither applies or unknown."),
    (6, "mi_percentage", "NUMBER(3)", "INT", "Primary mortgage insurance coverage percent at origination. 0 = no MI, 999 = not available."),
    (7, "number_of_units", "NUMBER(2)", "INT", "Dwelling units, 1 to 4. 99 = not available."),
    (8, "occupancy_status", "CHAR(1)", "VARCHAR", "P = primary residence, I = investment, S = second home, 9 = not available."),
    (9, "original_cltv", "NUMBER(3)", "INT", "Combined loan-to-value percent at origination. 999 = not available."),
    (10, "original_dti", "NUMBER(3)", "INT", "Monthly debt over monthly income at origination, percent. 999 = not available."),
    (11, "original_upb", "NUMBER(12)", "DOUBLE", "Loan amount on the note, rounded to the nearest 1,000 dollars."),
    (12, "original_ltv", "NUMBER(3)", "INT", "Loan amount over property value at origination, percent. 999 = not available."),
    (13, "original_interest_rate", "NUMBER(6,3)", "DOUBLE", "Note interest rate at origination."),
    (14, "channel", "CHAR(1)", "VARCHAR", "R = retail, B = broker, C = correspondent, T = third party not specified, 9 = not available."),
    (15, "prepayment_penalty_indicator", "CHAR(1)", "VARCHAR", "Y = penalty applies, N = no penalty."),
    (16, "amortization_type", "CHAR(3)", "VARCHAR", "FRM = fixed rate, ARM = adjustable rate."),
    (17, "property_state", "CHAR(2)", "VARCHAR", "State or territory of the property."),
    (18, "property_type", "CHAR(2)", "VARCHAR", "CP = co-op, CO = condo, PU = planned unit development, SF = single-family, MH = manufactured, 99 = not available."),
    (19, "postal_code", "CHAR(3)", "VARCHAR", "First three digits of the property postal code. 000 = unknown."),
    (20, "loan_identifier", "CHAR(12)", "VARCHAR", "Unique loan ID: product letter, origination year and quarter, sequence."),
    (21, "loan_purpose", "CHAR(1)", "VARCHAR", "P = purchase, C = cash-out refinance, N = no cash-out refinance, R = refinance not specified, 9 = not available."),
    (22, "original_loan_term", "NUMBER(3)", "INT", "Months of scheduled payments."),
    (23, "number_of_borrowers", "NUMBER(2)", "INT", "Borrowers obligated to repay. 99 = not available."),
    (24, "seller_name", "VARCHAR(60)", "VARCHAR", "Seller if at least 1 percent of the quarter's volume, otherwise OTHER."),
    (25, "super_conforming_flag", "CHAR(1)", "VARCHAR", "Y = loan amount exceeds the conforming limit."),
    (27, "special_eligibility_program", "CHAR(1)", "VARCHAR", "H = Home Possible, F = HFA Advantage, R = Refi Possible, null = not applicable."),
    (28, "harp_indicator", "CHAR(1)", "VARCHAR", "Y = Relief Refinance loan, N = not."),
    (29, "property_valuation_method", "CHAR(1)", "VARCHAR", "1 = appraisal waiver, 2 = appraisal, 3 = other, 4 = waiver plus property data report, 7 = not available."),
    (30, "interest_only_indicator", "CHAR(1)", "VARCHAR", "Y = interest-only period applies, N = no."),
    (31, "vantagescore_4", "NUMBER(4)", "INT", "VantageScore 4.0 at origination. 9999 = not available."),
]
FREDDIE_MONTH = [
    (1, "loan_identifier", "CHAR(12)", "VARCHAR", "Loan ID, as in the origination file."),
    (2, "period", "CHAR(6)", "VARCHAR", "As-of month for the record, YYYYMM."),
    (3, "current_actual_upb", "NUMBER(12,2)", "DOUBLE", "Ending balance for the period, including any deferred balance."),
    (4, "current_loan_delinquency_status", "CHAR(2)", "VARCHAR", "00 = current or under 30 days, 01 = 30 to 59 days, 02 = 60 to 89, and so on; RA = REO acquisition; XX = not available."),
    (5, "loan_age", "NUMBER(3)", "INT", "Scheduled payments from origination through the period; reset after a modification."),
    (6, "remaining_months_to_legal_maturity", "NUMBER(3)", "INT", "Scheduled payments remaining; uses the modified maturity if modified."),
    (9, "zero_balance_code", "CHAR(2)", "VARCHAR", "01 = prepaid or matured, 02 = third-party sale, 03 = short sale or charge-off, 09 = REO disposition, 15 = whole loan sale, 16 = reperforming securitization, 96 = defect before credit event."),
    (10, "zero_balance_effective_date", "CHAR(6)", "VARCHAR", "Period of the termination event, YYYYMM."),
    (11, "current_interest_rate", "NUMBER(6,3)", "DOUBLE", "Rate in effect this period; the modified rate when modified."),
    (12, "current_non_interest_bearing_upb", "NUMBER(12,2)", "DOUBLE", "Non-interest-bearing (deferred) portion of the balance."),
    (23, "cumulative_modification_costs", "NUMBER(12,2)", "DOUBLE", "Running total of modification costs."),
    (26, "estimated_ltv", "NUMBER(3)", "INT", "Balance over model-estimated property value, percent. 999 = not available."),
    (27, "zero_balance_removal_upb", "NUMBER(12,2)", "DOUBLE", "Balance just before the zero balance code was applied."),
    (32, "current_interest_bearing_upb", "NUMBER(12,2)", "DOUBLE", "Interest-bearing portion of the balance."),
    (33, "mi_cancellation_indicator", "CHAR(1)", "VARCHAR", "Y = MI cancelled, N = not cancelled, 7 = not applicable or not available."),
    (34, "servicer_name", "VARCHAR(60)", "VARCHAR", "Servicer if at least 1 percent of volume, otherwise OTHER."),
    (35, "bankruptcy_cramdown_costs", "NUMBER(12,2)", "DOUBLE", "Court-ordered cramdown costs, in the zero balance period."),
]
FANNIE_LOAN = [
    (2, "loan_identifier", "CHAR(12)", "VARCHAR", "Unique loan identifier; does not match other Fannie Mae identifiers."),
    (4, "channel", "CHAR(1)", "VARCHAR", "R = retail, C = correspondent, B = broker."),
    (5, "seller_name", "VARCHAR(50)", "VARCHAR", "Entity that delivered the loan; Other below 1 percent of volume."),
    (8, "original_interest_rate", "NUMBER(5,3)", "DOUBLE", "Interest rate stated in the original note."),
    (10, "original_upb", "NUMBER(12,2)", "DOUBLE", "Loan amount on the note at origination; values are rounded."),
    (13, "original_loan_term", "NUMBER(3)", "INT", "Months of scheduled payments due at origination."),
    (14, "origination_date", "CHAR(6)", "VARCHAR", "Date of the note, MMYYYY."),
    (15, "first_payment_date", "CHAR(6)", "VARCHAR", "Date of the first scheduled borrower payment, MMYYYY."),
    (19, "maturity_date", "CHAR(6)", "VARCHAR", "Month the loan is scheduled to be paid in full, MMYYYY; updated for modifications."),
    (20, "original_loan_to_value_ratio", "NUMBER(3)", "INT", "Loan amount over property value at origination, percent. Null if above 97 or unknown."),
    (21, "original_combined_loan_to_value_ratio", "NUMBER(3)", "INT", "All known loan balances over property value at origination, percent."),
    (22, "number_of_borrowers", "NUMBER(2)", "INT", "Individuals obligated to repay the loan."),
    (23, "debt_to_income", "NUMBER(2)", "INT", "Monthly debt over monthly income at origination. Blank if out of range or unknown."),
    (26, "first_time_home_buyer_indicator", "CHAR(1)", "VARCHAR", "Y = yes, N = no, null = unknown."),
    (27, "loan_purpose", "CHAR(1)", "VARCHAR", "C = cash-out refinance, R = refinance, P = purchase, U = refinance not specified."),
    (28, "property_type", "CHAR(2)", "VARCHAR", "CO = condo, CP = co-op, PU = planned urban development, MH = manufactured, SF = single-family."),
    (29, "number_of_units", "NUMBER(1)", "INT", "Units in the mortgaged property, 1 to 4."),
    (30, "occupancy_status", "CHAR(1)", "VARCHAR", "P = principal, S = second, I = investor, U = unknown."),
    (31, "property_state", "CHAR(2)", "VARCHAR", "State or territory of the property."),
    (32, "metropolitan_statistical_area", "CHAR(5)", "VARCHAR", "MSA code of the property. 00000 if not in a designated MSA."),
    (33, "zip_code_short", "CHAR(3)", "VARCHAR", "First three digits of the property ZIP code."),
    (34, "mortgage_insurance_percentage", "NUMBER(5,2)", "DOUBLE", "Original mortgage insurance coverage percent."),
    (35, "amortization_type", "CHAR(3)", "VARCHAR", "ARM = adjustable rate, FRM = fixed rate."),
    (36, "prepayment_penalty_indicator", "CHAR(1)", "VARCHAR", "Y = early payment penalty applies, N = no."),
    (37, "interest_only_loan_indicator", "CHAR(1)", "VARCHAR", "Y = interest-only payments for a set period, N = no."),
    (73, "mortgage_insurance_type", "CHAR(1)", "VARCHAR", "1 = borrower paid, 2 = lender paid, 3 = enterprise paid, null = no MI."),
    (79, "special_eligibility_program", "CHAR(1)", "VARCHAR", "F = HFA Preferred, H = HomeReady, R = RefiNow, O = other, 7 = not applicable, 9 = not available."),
    (81, "relocation_mortgage_indicator", "CHAR(1)", "VARCHAR", "Y = relocation mortgage, N = no."),
    (86, "property_valuation_method", "CHAR(1)", "VARCHAR", "A = appraisal, C = waiver plus data collection (condition), P = waiver plus data collection (value), R = targeted refinance, W = appraisal waiver, O = other."),
    (87, "high_balance_loan_indicator", "CHAR(1)", "VARCHAR", "Y = original balance above the conforming limit but within the high-cost limit."),
    (103, "high_ltv_refinance_option_indicator", "CHAR(1)", "VARCHAR", "Y = refinanced under the high LTV refinance option, N = no."),
]
FANNIE_MONTH = [
    (2, "loan_identifier", "CHAR(12)", "VARCHAR", "Loan identifier."),
    (3, "monthly_reporting_period", "CHAR(6)", "VARCHAR", "Servicer cut-off month for the record, MMYYYY."),
    (6, "servicer_name", "VARCHAR(50)", "VARCHAR", "Primary servicer; Other below 1 percent."),
    (9, "current_interest_rate", "NUMBER(5,3)", "DOUBLE", "Rate in effect for the current installment; updated for modifications."),
    (12, "current_actual_upb", "NUMBER(12,2)", "DOUBLE", "Outstanding principal reflecting payments received; zero when removed; masked for the first six months."),
    (16, "loan_age", "NUMBER(3)", "INT", "Calendar months since origination, from the first full month of interest accrual."),
    (17, "remaining_months_to_legal_maturity", "NUMBER(3)", "INT", "Calendar months until the loan is due in full under the mortgage documents."),
    (18, "remaining_months_to_maturity", "NUMBER(3)", "INT", "Months until the balance amortizes to zero, counting prepayments; blank for modified loans."),
    (40, "current_loan_delinquency_status", "CHAR(2)", "VARCHAR", "Months delinquent; blank after removal; XX = unknown; 99 = 99 or more."),
    (41, "loan_payment_history", "CHAR(48)", "VARCHAR", "Coded 24-month payment history, most recent month rightmost."),
    (42, "modification_flag", "CHAR(1)", "VARCHAR", "Y = loan has been modified, N = no."),
    (44, "zero_balance_code", "CHAR(3)", "VARCHAR", "01 = prepaid or matured, 02 = third party sale, 03 = short sale, 06 = repurchased, 09 = deed-in-lieu or REO disposition, 15 = non-performing note sale, 16 = reperforming note sale, 96 = removal, 97 = delinquency, 98 = other credit event."),
    (45, "zero_balance_effective_date", "CHAR(6)", "VARCHAR", "Date the balance was reduced to zero, MMYYYY."),
    (46, "upb_at_the_time_of_removal", "NUMBER(12,2)", "DOUBLE", "Balance when the loan was removed or liquidated."),
    (49, "total_principal_current", "NUMBER(12,2)", "DOUBLE", "Change in current actual UPB from the prior period."),
    (74, "servicing_activity_indicator", "CHAR(1)", "VARCHAR", "Y = servicer changed during the period, N = no."),
    (102, "borrower_assistance_plan", "CHAR(1)", "VARCHAR", "F = forbearance, R = repayment, T = trial period, O = other workout, N = no plan, 7 = not applicable, 9 = not available."),
    (106, "alternative_delinquency_resolution", "CHAR(1)", "VARCHAR", "P = payment deferral, C = COVID-19 deferral, D = disaster deferral, 7 = not applicable, 9 = not available."),
    (109, "payment_deferral_modification_event_indicator", "CHAR(1)", "VARCHAR", "Y = a payment deferral contributes to a modification event, N = no, 7 = not applicable."),
]

# source, target, match type, conflicts stated by the glossaries, false friend
L, M = "loan", "loan_month"
TRUTH = [
    (f"{L}.classic_fico", None, "unmatched", [], None),                       # Fannie's score fields are empty this quarter
    (f"{L}.first_payment_date", f"{L}.first_payment_date", "transform", ["format"], None),
    (f"{L}.first_time_homebuyer_indicator", f"{L}.first_time_home_buyer_indicator", "exact", ["null_semantics"], None),
    (f"{L}.maturity_date", f"{L}.maturity_date", "transform", ["format"], None),
    (f"{L}.msa", f"{L}.metropolitan_statistical_area", "exact", ["null_semantics"], None),
    (f"{L}.mi_percentage", f"{L}.mortgage_insurance_percentage", "exact", ["null_semantics"], None),
    (f"{L}.number_of_units", f"{L}.number_of_units", "exact", ["null_semantics"], None),
    (f"{L}.occupancy_status", f"{L}.occupancy_status", "exact", ["code_set"], None),
    (f"{L}.original_cltv", f"{L}.original_combined_loan_to_value_ratio", "exact", ["null_semantics"], None),
    (f"{L}.original_dti", f"{L}.debt_to_income", "exact", ["null_semantics"], None),
    (f"{L}.original_upb", f"{L}.original_upb", "exact", [], None),
    (f"{L}.original_ltv", f"{L}.original_loan_to_value_ratio", "exact", ["null_semantics"], None),
    (f"{L}.original_interest_rate", f"{L}.original_interest_rate", "exact", [], None),
    (f"{L}.channel", f"{L}.channel", "exact", ["code_set"], None),
    (f"{L}.prepayment_penalty_indicator", f"{L}.prepayment_penalty_indicator", "exact", [], None),
    (f"{L}.amortization_type", f"{L}.amortization_type", "exact", [], None),
    (f"{L}.property_state", f"{L}.property_state", "exact", [], None),
    (f"{L}.property_type", f"{L}.property_type", "exact", ["null_semantics"], None),
    (f"{L}.postal_code", f"{L}.zip_code_short", "exact", ["null_semantics"], None),
    (f"{L}.loan_identifier", f"{L}.loan_identifier", "exact", ["identity"], None),
    (f"{L}.loan_purpose", f"{L}.loan_purpose", "exact", ["code_set"], None),      # R means different things
    (f"{L}.original_loan_term", f"{L}.original_loan_term", "exact", [], None),
    (f"{L}.number_of_borrowers", f"{L}.number_of_borrowers", "exact", ["null_semantics"], None),
    (f"{L}.seller_name", f"{L}.seller_name", "exact", [], None),
    (f"{L}.super_conforming_flag", f"{L}.high_balance_loan_indicator", "exact", [], None),
    (f"{L}.special_eligibility_program", f"{L}.special_eligibility_program", "exact", ["code_set", "null_semantics"], None),
    (f"{L}.harp_indicator", None, "unmatched", [], None),
    (f"{L}.property_valuation_method", f"{L}.property_valuation_method", "exact", ["code_set"], None),
    (f"{L}.interest_only_indicator", f"{L}.interest_only_loan_indicator", "exact", [], None),
    (f"{L}.vantagescore_4", None, "unmatched", [], None),
    (f"{M}.loan_identifier", f"{M}.loan_identifier", "exact", ["identity"], None),
    (f"{M}.period", f"{M}.monthly_reporting_period", "transform", ["format"], None),
    (f"{M}.current_actual_upb", f"{M}.current_actual_upb", "exact", [], None),
    (f"{M}.current_loan_delinquency_status", f"{M}.current_loan_delinquency_status", "exact", ["code_set"], None),
    (f"{M}.loan_age", f"{M}.loan_age", "exact", ["temporal"], None),             # counted from different starting points
    (f"{M}.remaining_months_to_legal_maturity", f"{M}.remaining_months_to_legal_maturity", "exact", [], None),
    (f"{M}.zero_balance_code", f"{M}.zero_balance_code", "exact", ["code_set"], None),
    (f"{M}.zero_balance_effective_date", f"{M}.zero_balance_effective_date", "transform", ["format"], None),
    (f"{M}.current_interest_rate", f"{M}.current_interest_rate", "exact", [], None),
    (f"{M}.current_non_interest_bearing_upb", None, "unmatched", [], None),     # Fannie's counterpart is empty this quarter
    (f"{M}.cumulative_modification_costs", None, "unmatched", [], None),
    (f"{M}.estimated_ltv", None, "unmatched", [], None),
    (f"{M}.zero_balance_removal_upb", f"{M}.upb_at_the_time_of_removal", "exact", [], None),
    (f"{M}.current_interest_bearing_upb", None, "unmatched", [], None),
    (f"{M}.mi_cancellation_indicator", None, "unmatched", [], None),
    (f"{M}.servicer_name", f"{M}.servicer_name", "exact", [], None),
    (f"{M}.bankruptcy_cramdown_costs", None, "unmatched", [], None),
]


def _select(cols, offset: int) -> str:
    """Freddie files number columns from column00 (two digits); Fannie from column000 (three digits)."""
    width = 2 if offset == 0 else 3
    out = []
    for pos, name, _, cast, _ in cols:
        src = f"column{pos - 1:0{width}d}"
        out.append(f'TRY_CAST({src} AS {cast}) AS "{name}"' if cast != "VARCHAR" else f'{src} AS "{name}"')
    return ", ".join(out)


def _schema(cols, key):
    return {"key": key, "columns": {name: {"type": t, "description": d} for _, name, t, _, d in cols}}


def main(freddie_orig, freddie_perf, fannie, out_dir, loans="20000"):
    out, n = Path(out_dir), int(loans)
    con = duckdb.connect()
    rd = lambda f: f"read_csv('{f}', delim='|', header=false, all_varchar=true)"
    con.execute(f"CREATE VIEW fo AS SELECT * FROM {rd(freddie_orig)}")
    con.execute(f"CREATE VIEW fp AS SELECT * FROM {rd(freddie_perf)}")
    con.execute(f"CREATE VIEW fn AS SELECT * FROM {rd(fannie)}")
    con.execute(f"CREATE TABLE fo_ids AS SELECT column19 AS id FROM fo ORDER BY hash(column19) LIMIT {n}")
    con.execute(f"CREATE TABLE fn_ids AS SELECT id FROM (SELECT DISTINCT column001 AS id FROM fn) ORDER BY hash(id) LIMIT {n}")
    rid = lambda a, b: f"{a} || '_' || {b} AS row_id, "
    builds = {
        ("acquired", "loan"): f"SELECT {_select(FREDDIE_LOAN, 0)} FROM fo WHERE column19 IN (SELECT id FROM fo_ids)",
        ("acquired", "loan_month"): f"SELECT {rid('column00', 'column01')}{_select(FREDDIE_MONTH, 0)} FROM fp "
                                    f"WHERE column00 IN (SELECT id FROM fo_ids)",
        ("acquirer", "loan"): f"SELECT {_select(FANNIE_LOAN, 1)} FROM fn WHERE column001 IN (SELECT id FROM fn_ids) "
                              f"QUALIFY ROW_NUMBER() OVER (PARTITION BY column001 ORDER BY RIGHT(column002, 4) || LEFT(column002, 2)) = 1",
        ("acquirer", "loan_month"): f"SELECT {rid('column001', 'column002')}{_select(FANNIE_MONTH, 1)} FROM fn "
                                    f"WHERE column001 IN (SELECT id FROM fn_ids)",
    }
    row_id = (0, "row_id", "VARCHAR(20)", "VARCHAR", "Loan identifier and period joined; one row per loan per month.")
    schemas = {"acquired": {"loan": _schema(FREDDIE_LOAN, "loan_identifier"), "loan_month": _schema([row_id] + FREDDIE_MONTH, "row_id")},
               "acquirer": {"loan": _schema(FANNIE_LOAN, "loan_identifier"), "loan_month": _schema([row_id] + FANNIE_MONTH, "row_id")}}
    for (side, table), sql in builds.items():
        d = out / side
        d.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY ({sql}) TO '{(d / (table + '.parquet')).as_posix()}' (FORMAT PARQUET)")
        rows = con.execute(f"SELECT COUNT(*) FROM '{(d / (table + '.parquet')).as_posix()}'").fetchone()[0]
        print(f"{side}.{table}: {rows:,} rows")
    for side, sch in schemas.items():
        (out / side / "schema.json").write_text(json.dumps(sch, indent=2))
        (out / side / "derivations.json").write_text("{}")
    gt = [{"source": s, "target": t, "match_type": m, "conflicts": c, "false_friend_of": f} for s, t, m, c, f in TRUTH]
    (out / "ground_truth.json").write_text(json.dumps(
        {"scenario": "gse_real_pair", "acquirer": "Fannie Mae SF Loan Performance", "acquired": "Freddie Mac SFLLD",
         "attributes": gt}, indent=2))
    (out / "scenario.json").write_text(json.dumps({"scenario": "R real pair (Freddie Mac to Fannie Mae)",
                                                   "source_dialect": "duckdb", "target_dialect": "duckdb"}, indent=2))
    print(f"{len(gt)} source attributes, {sum(bool(g['conflicts']) for g in gt)} with a stated difference")


if __name__ == "__main__":
    main(*sys.argv[1:6])
