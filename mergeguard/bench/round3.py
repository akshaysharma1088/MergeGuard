"""Scenarios G to K from the third practitioner trap list (experiments/practitioner_inputs/traps_round3.txt).

Written after MergeGuard v0.0.5 was frozen. Each trap is tagged G1..K10 in the order of the list.
Conflict labels beyond the original taxonomy: identity, role, currency, methodology, aggregation.
"""
from __future__ import annotations

FX = "ccy.map({'USD': 1.0, 'EUR': 1.08, 'GBP': 1.27, 'CAD': 0.73})"

SPEC_G = {
    "loaded": ['customer.marketing_opt_out', 'payment.counterparty_name', 'payment.payment_type', 'trust_account.tax_id', 'beneficiary.share_pct'],  # stored as loaded by the target system, not recomputed
    "names": ("harborpoint_bluestem", "Harbor Point Bank", "Bluestem Financial"),
    "dialects": ("oracle", "snowflake"),
    "entities": [
        {"name": "customer", "per_base": 1.0,
         "latent": {"nm": "name:full", "u": "uniform:0~1"},
         "target": {"table": "customer", "key": "customer_id", "columns": [
             ("customer_id", "NUMBER(38,0)", "Customer identifier", "ID"),
             ("full_name", "VARCHAR(120)", "Customer full name", "nm"),
             ("marketing_opt_out", "BOOLEAN", "Customer blocked all promotional messages: email, text and phone", "u < 0.12"),  # G8
         ]},
         "source": {"table": "CUSTOMER", "key": "CUST_NO", "columns": [
             ("CUST_NO", "NUMBER(10)", "Customer number", "ID"),
             ("CUST_NAME", "VARCHAR2(120)", "Customer name", "nm"),
             ("MKTG_OPT_OUT", "CHAR(1)", "Marketing opt out", "where(u < 0.30, 'Y', 'N')"),                     # G8
         ]}},
        {"name": "payment", "per_base": 6.0,
         "latent": {"cust": "fk:customer", "kind": "code:ACH=0.8|WIRE=0.2", "file_dt": "date:2026-05-01..2026-10-29,business",
                    "lag": "int:0-2", "amt": "money:900,sigma=1.0", "ccy": "code:USD=0.82|EUR=0.07|GBP=0.05|CAD=0.06",
                    "benef": "name:full", "inter": "bank:"},
         "target": {"table": "payment", "key": "payment_id", "columns": [
             ("payment_id", "NUMBER(38,0)", "Payment identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Originating customer", "cust"),
             ("payment_type", "VARCHAR(4)", "ACH or WIRE", "kind"),
             ("ach_settlement_date", "DATE", "Settlement date on the ACH clearinghouse file header", "file_dt"),       # G1
             ("counterparty_name", "VARCHAR(120)", "Ultimate beneficiary of the payment", "benef"),                    # G2
             ("currency_code", "VARCHAR(3)", "ISO currency of the transacted account", "ccy"),
             ("fx_amount", "NUMBER(14,2)", "Amount in the local currency of the transacted account", "amt"),           # G5
         ]},
         "source": {"table": "PMT", "key": "PMT_ID", "columns": [
             ("PMT_ID", "NUMBER(12)", "Payment id", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "cust"),
             ("PMT_TYP_CD", "CHAR(1)", "Payment type", "kind.map({'ACH': 'A', 'WIRE': 'W'})"),
             ("SETTLE_DT", "DATE", "Settlement date", "bizday(file_dt + days(lag))"),                                 # G1
             ("CPTY_NM", "VARCHAR2(120)", "Counterparty name", "where(kind == 'WIRE', inter, benef)"),                 # G2
             ("CCY_CD", "CHAR(3)", "Currency", "ccy"),
             ("AMT_USD", "NUMBER(14,2)", "Transaction amount", f"(amt * {FX}).round(2)"),                              # G5
         ]}},
        {"name": "mortgage", "per_base": 0.5,
         "latent": {"cust": "fk:customer", "lien1": "money:240000,sigma=0.5", "ltv": "uniform:0.4~0.95",
                    "heloc": "money:60000,sigma=0.5;null:0.6", "escrow": "normal:0,700",
                    "approve": "date:2025-01-01..2026-09-30", "close_lag": "int:15-45",
                    "loss": "uniform:0.005~0.03", "draw": "uniform:0.1~0.5"},
         "target": {"table": "mortgage_loan", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Mortgage identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Borrower", "cust"),
             ("first_lien_balance", "NUMBER(14,2)", "First lien principal balance", "lien1"),
             ("ltv_ratio", "NUMBER(6,4)", "First lien balance divided by appraised value", "ltv.round(4)"),            # G4
             ("escrow_balance", "NUMBER(12,2)", "Escrow balance; positive is a customer surplus", "escrow.round(2)"),   # G3
             ("hmda_action_date", "DATE", "HMDA action taken date: underwriting approval", "approve"),                 # G6
             ("cecl_reserve", "NUMBER(12,2)", "CECL allowance on the funded balance", "(lien1 * loss).round(2)"),     # G7
         ]},
         "source": {"table": "MTG_LN", "key": "LN_NO", "columns": [
             ("LN_NO", "NUMBER(10)", "Loan number", "ID"),
             ("CUST_NO", "NUMBER(10)", "Customer number", "cust"),
             ("PRIN_BAL", "NUMBER(14,2)", "Principal balance", "lien1"),
             ("LTV_RTO", "NUMBER(6,4)", "LTV", "((lien1 + heloc.fillna(0)) / (lien1 / ltv)).round(4)"),               # G4
             ("ESCROW_BAL", "NUMBER(12,2)", "Escrow balance", "(-escrow).round(2)"),                                   # G3
             ("HMDA_ACTN_DT", "DATE", "HMDA action date", "approve + days(close_lag)"),                                # G6
             ("CECL_RSRV", "NUMBER(12,2)", "CECL reserve", "((lien1 + heloc.fillna(0) * draw) * loss).round(2)"),     # G7
         ]}},
        {"name": "trust", "per_base": 0.15,
         "latent": {"ein": "pattern:##-#######", "ssn": "pattern:###-##-####", "opened": "date:2005-01-01..2026-06-30"},
         "target": {"table": "trust_account", "key": "trust_id", "columns": [
             ("trust_id", "NUMBER(38,0)", "Trust account identifier", "ID"),
             ("tax_id", "VARCHAR(11)", "Taxpayer ID of the trust (EIN)", "ein"),                                       # G9
             ("open_date", "DATE", "Trust account open date", "opened"),
         ]},
         "source": {"table": "TRUST_ACCT", "key": "TRUST_NO", "columns": [
             ("TRUST_NO", "NUMBER(10)", "Trust number", "ID"),
             ("TAX_ID", "VARCHAR2(11)", "Tax id", "ssn"),                                                              # G9
             ("OPEN_DT", "DATE", "Open date", "opened"),
         ]}},
        {"name": "beneficiary", "per_base": 0.4,
         "latent": {"trust": "fk:trust", "tier": "code:P=0.65|C=0.35", "k": "int:1-3", "nm": "name:full"},
         "target": {"table": "beneficiary", "key": "beneficiary_id", "columns": [
             ("beneficiary_id", "NUMBER(38,0)", "Beneficiary identifier", "ID"),
             ("trust_id", "NUMBER(38,0)", "Trust account", "trust"),
             ("beneficiary_name", "VARCHAR(120)", "Beneficiary name", "nm"),
             ("share_pct", "NUMBER(5,2)", "Share of the total account in percent", "(100 / k).round(2)"),              # G10
         ]},
         "source": {"table": "BENE", "key": "BENE_NO", "columns": [
             ("BENE_NO", "NUMBER(10)", "Beneficiary number", "ID"),
             ("TRUST_NO", "NUMBER(10)", "Trust number", "trust"),
             ("BENE_NM", "VARCHAR2(120)", "Beneficiary name", "nm"),
             ("BENE_SHR", "CHAR(1)", "Beneficiary share", "tier"),                                                     # G10
         ]}},
    ],
    "derivations": {
        "target": {
            "mortgage_loan.ltv_ratio": "SELECT m.loan_id, m.first_lien_balance / v.appraised_value AS ltv_ratio FROM mortgage_loan m JOIN valuation v ON v.loan_id = m.loan_id",
            "mortgage_loan.cecl_reserve": "SELECT m.loan_id, m.first_lien_balance * m.loss_rate AS cecl_reserve FROM mortgage_loan m",
        },
        "source": {
            "MTG_LN.LTV_RTO": "SELECT l.LN_NO, (l.PRIN_BAL + NVL(h.HELOC_LMT, 0)) / v.APPR_VAL AS LTV_RTO FROM MTG_LN l LEFT JOIN HELOC h ON h.LN_NO = l.LN_NO JOIN VALN v ON v.LN_NO = l.LN_NO",
            "MTG_LN.CECL_RSRV": "SELECT l.LN_NO, (l.PRIN_BAL + l.UNFUNDED_AMT * l.DRAW_RT) * l.LOSS_RT AS CECL_RSRV FROM MTG_LN l",
            "PMT.SETTLE_DT": "SELECT p.PMT_ID, p.FUNDS_AVAIL_DT AS SETTLE_DT FROM PMT_RAW p",
            "PMT.AMT_USD": "SELECT p.PMT_ID, p.LOCAL_AMT * r.SPOT_RATE AS AMT_USD FROM PMT_RAW p JOIN FX_EOD r ON r.CCY_CD = p.CCY_CD",
        },
    },
    "truth": [
        ("CUSTOMER.CUST_NO", "customer.customer_id", "exact", [], None),
        ("CUSTOMER.CUST_NAME", "customer.full_name", "exact", [], None),
        ("CUSTOMER.MKTG_OPT_OUT", "customer.marketing_opt_out", "conflict", ["population"], None),
        ("PMT.PMT_ID", "payment.payment_id", "exact", [], None),
        ("PMT.CUST_NO", "payment.customer_id", "exact", [], None),
        ("PMT.PMT_TYP_CD", "payment.payment_type", "transform", ["code_set"], None),
        ("PMT.SETTLE_DT", "payment.ach_settlement_date", "conflict", ["temporal"], None),
        ("PMT.CPTY_NM", "payment.counterparty_name", "conflict", ["role"], None),
        ("PMT.CCY_CD", "payment.currency_code", "exact", [], None),
        ("PMT.AMT_USD", "payment.fx_amount", "conflict", ["currency"], None),
        ("MTG_LN.LN_NO", "mortgage_loan.loan_id", "exact", [], None),
        ("MTG_LN.CUST_NO", "mortgage_loan.customer_id", "exact", [], None),
        ("MTG_LN.PRIN_BAL", "mortgage_loan.first_lien_balance", "exact", [], None),
        ("MTG_LN.LTV_RTO", "mortgage_loan.ltv_ratio", "conflict", ["inclusion"], None),
        ("MTG_LN.ESCROW_BAL", "mortgage_loan.escrow_balance", "conflict", ["sign"], None),
        ("MTG_LN.HMDA_ACTN_DT", "mortgage_loan.hmda_action_date", "conflict", ["temporal"], None),
        ("MTG_LN.CECL_RSRV", "mortgage_loan.cecl_reserve", "conflict", ["inclusion"], None),
        ("TRUST_ACCT.TRUST_NO", "trust_account.trust_id", "exact", [], None),
        ("TRUST_ACCT.TAX_ID", "trust_account.tax_id", "conflict", ["identity"], None),
        ("TRUST_ACCT.OPEN_DT", "trust_account.open_date", "exact", [], None),
        ("BENE.BENE_NO", "beneficiary.beneficiary_id", "exact", [], None),
        ("BENE.TRUST_NO", "beneficiary.trust_id", "exact", [], None),
        ("BENE.BENE_NM", "beneficiary.beneficiary_name", "exact", [], None),
        ("BENE.BENE_SHR", "beneficiary.share_pct", "conflict", ["code_set"], None),
    ],
}

SPEC_H = {
    "loaded": ['portfolio.cost_basis', 'letter_of_credit.expiry_date'],  # stored as loaded by the target system, not recomputed
    "names": ("ridgeview_copperleaf", "Ridgeview Bank", "Copperleaf Trust"),
    "dialects": ("tsql", "snowflake"),
    "entities": [
        {"name": "client", "per_base": 1.0, "latent": {"nm": "name:full"},
         "target": {"table": "client", "key": "client_id", "columns": [
             ("client_id", "NUMBER(38,0)", "Client identifier", "ID"),
             ("client_name", "VARCHAR(120)", "Client name", "nm")]},
         "source": {"table": "CLNT", "key": "CLNT_ID", "columns": [
             ("CLNT_ID", "INT", "Client id", "ID"),
             ("CLNT_NM", "NVARCHAR(120)", "Client name", "nm")]}},
        {"name": "portfolio", "per_base": 1.0,
         "latent": {"owner": "fk:client", "disc": "money:250000,sigma=1.2", "selfdir": "money:40000,sigma=1.3",
                    "cash": "money:8000,sigma=1.0", "shares": "int:50-5000", "px": "uniform:20~300", "lot": "uniform:0.85~1.15"},
         "target": {"table": "portfolio", "key": "portfolio_id", "columns": [
             ("portfolio_id", "NUMBER(38,0)", "Portfolio identifier", "ID"),
             ("client_id", "NUMBER(38,0)", "Client", "owner"),
             ("aum", "NUMBER(16,2)", "Assets under management: discretionary managed portfolios only", "disc"),        # H1
             ("cost_basis", "NUMBER(16,2)", "Cost basis from FIFO tax lots", "(shares * px * lot).round(2)"),           # H3
             ("share_qty", "NUMBER(12,0)", "Shares held", "shares")]},
         "source": {"table": "PORTF", "key": "PORTF_ID", "columns": [
             ("PORTF_ID", "INT", "Portfolio id", "ID"),
             ("CLNT_ID", "INT", "Client id", "owner"),
             ("AUM_AMT", "MONEY", "AUM", "(disc + selfdir + cash).round(2)"),                                            # H1
             ("COST_BASIS", "MONEY", "Cost basis", "(shares * px).round(2)"),                                             # H3
             ("SHR_QTY", "INT", "Share quantity", "shares")]}},
        {"name": "trade", "per_base": 4.0,
         "latent": {"pf": "fk:portfolio", "exec": "date:2026-06-01..2026-10-28,business", "lag": "code:1=0.7|2=0.3",
                    "qty": "int:10-1000"},
         "target": {"table": "trade_position", "key": "trade_id", "columns": [
             ("trade_id", "NUMBER(38,0)", "Trade identifier", "ID"),
             ("portfolio_id", "NUMBER(38,0)", "Portfolio", "pf"),
             ("position_date", "DATE", "Holding date: trade execution date", "exec"),                                     # H2
             ("quantity", "NUMBER(12,0)", "Quantity", "qty")]},
         "source": {"table": "TRD", "key": "TRD_ID", "columns": [
             ("TRD_ID", "INT", "Trade id", "ID"),
             ("PORTF_ID", "INT", "Portfolio id", "pf"),
             ("POSN_DT", "DATE", "Position date", "bizday(exec + days(lag.astype(int)))"),                                # H2
             ("QTY", "INT", "Quantity", "qty")]}},
        {"name": "lc", "per_base": 0.2,
         "latent": {"face": "money:400000,sigma=0.8", "drawn": "uniform:0~0.9", "ship_by": "date:2026-11-15..2027-06-30",
                    "doc_days": "int:15-21", "issued": "date:2026-01-01..2026-10-30"},
         "target": {"table": "letter_of_credit", "key": "lc_id", "columns": [
             ("lc_id", "NUMBER(38,0)", "Letter of credit identifier", "ID"),
             ("issue_date", "DATE", "Issue date", "issued"),
             ("lc_balance", "NUMBER(16,2)", "Original face value of the guarantee", "face"),                              # H4
             ("expiry_date", "DATE", "Latest date to load goods for shipment", "ship_by")]},                              # H5
         "source": {"table": "LC", "key": "LC_NO", "columns": [
             ("LC_NO", "INT", "LC number", "ID"),
             ("ISSUE_DT", "DATE", "Issue date", "issued"),
             ("LC_BAL", "MONEY", "LC balance", "(face * (1 - drawn)).round(2)"),                                          # H4
             ("EXPRY_DT", "DATE", "Expiry date", "ship_by + days(doc_days)")]}},                                          # H5
        {"name": "fraud", "per_base": 0.3,
         "latent": {"cl": "fk:client", "loss": "money:900,sigma=1.0", "recov": "uniform:0~0.8", "disputed": "bool:0.85",
                    "verified": "bool:0.6", "alert": "timestamp:2026-07-01..2026-10-30", "q_min": "int:5-600"},
         "target": {"table": "fraud_case", "key": "case_id", "columns": [
             ("case_id", "NUMBER(38,0)", "Fraud case identifier", "ID"),
             ("client_id", "NUMBER(38,0)", "Client", "cl"),
             ("fraud_loss_amount", "NUMBER(12,2)", "Initial unauthorized transaction total", "loss"),                      # H6
             ("is_confirmed_fraud", "BOOLEAN", "Confirmed fraud: customer disputed the charge", "disputed"),              # H7
             ("alert_ts", "TIMESTAMP_NTZ", "When the real-time scoring engine flagged the transaction", "alert")]},      # H8
         "source": {"table": "FRD_CASE", "key": "CASE_NO", "columns": [
             ("CASE_NO", "INT", "Case number", "ID"),
             ("CLNT_ID", "INT", "Client id", "cl"),
             ("FRD_LOSS_AMT", "MONEY", "Fraud loss", "(loss * (1 - recov)).round(2)"),                                    # H6
             ("CONF_FRD_IND", "NCHAR(1)", "Confirmed fraud", "where(disputed & verified, 'Y', 'N')"),                      # H7
             ("ALRT_TS", "DATETIME2", "Alert timestamp", "alert + pd.to_timedelta(q_min, unit='m')")]}},                  # H8
        {"name": "gl", "per_base": 3.0,
         "latent": {"eff": "date:2026-08-01..2026-10-28,business", "batch_lag": "int:0-3", "amt": "normal:0,5000"},
         "target": {"table": "gl_entry", "key": "entry_id", "columns": [
             ("entry_id", "NUMBER(38,0)", "Journal entry identifier", "ID"),
             ("post_date", "DATE", "Calendar day the nightly posting batch completed", "eff + days(batch_lag)"),           # H9
             ("amount", "NUMBER(16,2)", "Entry amount", "amt.round(2)")]},
         "source": {"table": "GL_TXN", "key": "ENTRY_NO", "columns": [
             ("ENTRY_NO", "INT", "Entry number", "ID"),
             ("POST_DT", "DATE", "Post date", "eff"),                                                                     # H9
             ("AMT", "MONEY", "Amount", "amt.round(2)")]}},
        {"name": "suspense", "per_base": 0.05,
         "latent": {"deb": "money:20000,sigma=0.8", "cred": "money:18000,sigma=0.8"},
         "target": {"table": "suspense_account", "key": "suspense_id", "columns": [
             ("suspense_id", "NUMBER(38,0)", "Suspense account", "ID"),
             ("suspense_balance", "NUMBER(16,2)", "Net of unapplied debits and credits", "(deb - cred).round(2)")]},      # H10
         "source": {"table": "SUSP", "key": "SUSP_ACCT_NO", "columns": [
             ("SUSP_ACCT_NO", "INT", "Suspense account", "ID"),
             ("SUSP_BAL", "MONEY", "Suspense balance", "deb.round(2)")]}},                                               # H10
    ],
    "derivations": {
        "target": {"suspense_account.suspense_balance": "SELECT s.suspense_id, s.open_debits - s.open_credits AS suspense_balance FROM suspense_items s"},
        "source": {
            "PORTF.AUM_AMT": "SELECT p.PORTF_ID, p.DISC_MV + p.SELF_DIR_MV + p.SWEEP_CASH AS AUM_AMT FROM PORTF_RAW p",
            "FRD_CASE.FRD_LOSS_AMT": "SELECT c.CASE_NO, c.UNAUTH_AMT - c.CHARGEBACK_RECOV - c.INS_RECOV AS FRD_LOSS_AMT FROM FRD_RAW c",
            "TRD.POSN_DT": "SELECT t.TRD_ID, t.SETTLE_DT AS POSN_DT FROM TRD_RAW t",
            "LC.LC_BAL": "SELECT l.LC_NO, l.FACE_AMT - l.DRAWN_AMT AS LC_BAL FROM LC_RAW l",
        },
    },
    "truth": [
        ("CLNT.CLNT_ID", "client.client_id", "exact", [], None),
        ("CLNT.CLNT_NM", "client.client_name", "exact", [], None),
        ("PORTF.PORTF_ID", "portfolio.portfolio_id", "exact", [], None),
        ("PORTF.CLNT_ID", "portfolio.client_id", "exact", [], None),
        ("PORTF.AUM_AMT", "portfolio.aum", "conflict", ["inclusion"], None),
        ("PORTF.COST_BASIS", "portfolio.cost_basis", "conflict", ["methodology"], None),
        ("PORTF.SHR_QTY", "portfolio.share_qty", "exact", [], None),
        ("TRD.TRD_ID", "trade_position.trade_id", "exact", [], None),
        ("TRD.PORTF_ID", "trade_position.portfolio_id", "exact", [], None),
        ("TRD.POSN_DT", "trade_position.position_date", "conflict", ["temporal"], None),
        ("TRD.QTY", "trade_position.quantity", "exact", [], None),
        ("LC.LC_NO", "letter_of_credit.lc_id", "exact", [], None),
        ("LC.ISSUE_DT", "letter_of_credit.issue_date", "exact", [], None),
        ("LC.LC_BAL", "letter_of_credit.lc_balance", "conflict", ["inclusion"], None),
        ("LC.EXPRY_DT", "letter_of_credit.expiry_date", "conflict", ["temporal"], None),
        ("FRD_CASE.CASE_NO", "fraud_case.case_id", "exact", [], None),
        ("FRD_CASE.CLNT_ID", "fraud_case.client_id", "exact", [], None),
        ("FRD_CASE.FRD_LOSS_AMT", "fraud_case.fraud_loss_amount", "conflict", ["inclusion"], None),
        ("FRD_CASE.CONF_FRD_IND", "fraud_case.is_confirmed_fraud", "conflict", ["population"], None),
        ("FRD_CASE.ALRT_TS", "fraud_case.alert_ts", "conflict", ["temporal"], None),
        ("GL_TXN.ENTRY_NO", "gl_entry.entry_id", "exact", [], None),
        ("GL_TXN.POST_DT", "gl_entry.post_date", "conflict", ["temporal"], None),
        ("GL_TXN.AMT", "gl_entry.amount", "exact", [], None),
        ("SUSP.SUSP_ACCT_NO", "suspense_account.suspense_id", "exact", [], None),
        ("SUSP.SUSP_BAL", "suspense_account.suspense_balance", "conflict", ["inclusion"], None),
    ],
}

SPEC_I = {
    "loaded": ['auto_loan.vehicle_value', 'equipment_lease.residual_value', 'syndicated_loan.commitment_amount', 'syndicated_loan.borrower_id'],  # stored as loaded by the target system, not recomputed
    "names": ("prairiegate_elmhurst", "Prairie Gate Bank", "Elmhurst Credit"),
    "dialects": ("oracle", "snowflake"),
    "entities": [
        {"name": "auto", "per_base": 1.0,
         "latent": {"retail": "money:34000,sigma=0.35", "whl": "uniform:0.7~0.85", "addons": "money:1800,sigma=0.5",
                    "dispatch": "date:2026-01-01..2026-10-20;null:0.9", "cure": "int:10-30", "rsv": "money:900,sigma=0.4",
                    "term": "code:60=0.5|72=0.5", "orig": "date:2021-01-01..2026-10-01"},
         "target": {"table": "auto_loan", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Auto loan identifier", "ID"),
             ("origination_date", "DATE", "Origination date", "orig"),
             ("term_months", "NUMBER(3,0)", "Term in months", "term.astype(int)"),
             ("vehicle_value", "NUMBER(12,2)", "Retail sticker price including dealer add-ons", "(retail + addons).round(2)"),  # I1
             ("is_repossessed", "BOOLEAN", "Repossession started: tow truck dispatched", "dispatch.notna()"),             # I2
             ("dealer_reserve_fee", "NUMBER(10,2)", "Dealer reserve booked upfront at origination", "rsv")]},             # I3
         "source": {"table": "AUTO_LN", "key": "LN_NO", "columns": [
             ("LN_NO", "NUMBER(10)", "Loan number", "ID"),
             ("ORIG_DT", "DATE", "Origination date", "orig"),
             ("TERM_MO", "NUMBER(3)", "Term", "term.astype(int)"),
             ("VEH_VAL", "NUMBER(12,2)", "Vehicle value", "(retail * whl).round(2)"),                                     # I1
             ("REPO_IND", "CHAR(1)", "Repossession", "where(dispatch.notna() & (dispatch + days(cure) <= AS_OF), 'Y', 'N')"),  # I2
             ("DLR_RSV_AMT", "NUMBER(10,2)", "Dealer reserve", "(rsv / term.astype(int)).round(2)")]}},                    # I3
        {"name": "student", "per_base": 0.6,
         "latent": {"nm": "name:full", "grad": "date:2026-05-01..2028-06-30", "annual": "money:12000,sigma=0.3", "u": "uniform:0~1"},
         "target": {"table": "student_loan", "key": "loan_id", "columns": [
             ("loan_id", "NUMBER(38,0)", "Student loan identifier", "ID"),
             ("borrower_name", "VARCHAR(120)", "Borrower name", "nm"),
             ("repayment_start_date", "DATE", "Projected graduation date", "grad"),                                       # I4
             ("disbursement_amount", "NUMBER(12,2)", "Academic-year loan amount approved", "annual"),                     # I5
             ("cosigner_release_flag", "BOOLEAN", "Borrower meets the criteria to apply for co-signer release", "u < 0.25")]},  # I6
         "source": {"table": "STU_LN", "key": "LN_NO", "columns": [
             ("LN_NO", "NUMBER(10)", "Loan number", "ID"),
             ("BRWR_NM", "VARCHAR2(120)", "Borrower", "nm"),
             ("RPMT_START_DT", "DATE", "Repayment start", "grad + days(183)"),                                             # I4
             ("DISB_AMT", "NUMBER(12,2)", "Disbursement", "(annual / 2).round(2)"),                                        # I5
             ("COSGN_REL_IND", "CHAR(1)", "Co-signer release", "where(u < 0.10, 'Y', 'N')")]}},                            # I6
        {"name": "lease", "per_base": 0.4,
         "latent": {"cost": "money:85000,sigma=0.6", "mkt": "uniform:0.15~0.35", "floor": "uniform:0.08~0.15",
                    "nrem": "int:6-48", "pmt": "money:1800,sigma=0.5", "r": "uniform:0.004~0.008",
                    "opt": "code:250=0.5|500=0.5", "start": "date:2022-01-01..2026-09-30"},
         "target": {"table": "equipment_lease", "key": "lease_id", "columns": [
             ("lease_id", "NUMBER(38,0)", "Lease identifier", "ID"),
             ("start_date", "DATE", "Lease start", "start"),
             ("residual_value", "NUMBER(12,2)", "Unguaranteed open-market residual estimate", "(cost * mkt).round(2)"),    # I7
             ("buyout_price", "NUMBER(14,2)", "Present value of remaining rent plus residual",
              "(pmt * (1 - (1 + r) ** (-nrem)) / r + cost * mkt / (1 + r) ** nrem).round(2)")]},                           # I8
         "source": {"table": "LEASE", "key": "LEASE_NO", "columns": [
             ("LEASE_NO", "NUMBER(10)", "Lease number", "ID"),
             ("START_DT", "DATE", "Start date", "start"),
             ("RESID_VAL", "NUMBER(12,2)", "Residual value", "(cost * floor).round(2)"),                                   # I7
             ("BUYOUT_AMT", "NUMBER(14,2)", "Buyout price", "(pmt * nrem + opt.astype(int)).round(2)")]}},                 # I8
        {"name": "synd", "per_base": 0.05,
         "latent": {"fac": "money:500000000,sigma=0.6", "share": "uniform:0.03~0.08", "parent": "int:9000-9300",
                    "spv": "int:20000-29999", "agent": "bank:"},
         "target": {"table": "syndicated_loan", "key": "deal_id", "columns": [
             ("deal_id", "NUMBER(38,0)", "Syndicated deal identifier", "ID"),
             ("agent_bank", "VARCHAR(60)", "Administrative agent", "agent"),
             ("commitment_amount", "NUMBER(18,2)", "Total facility commitment across all lenders", "fac"),                # I9
             ("borrower_id", "NUMBER(38,0)", "Ultimate parent company of the borrower", "parent")]},                       # I10
         "source": {"table": "SYND_LN", "key": "DEAL_NO", "columns": [
             ("DEAL_NO", "NUMBER(10)", "Deal number", "ID"),
             ("AGENT_BANK", "VARCHAR2(60)", "Agent", "agent"),
             ("CMT_AMT", "NUMBER(18,2)", "Commitment", "(fac * share).round(2)"),                                          # I9
             ("BRWR_ID", "NUMBER(10)", "Borrower id", "spv")]}},                                                           # I10
    ],
    "derivations": {
        "target": {},
        "source": {
            "STU_LN.RPMT_START_DT": "SELECT s.LN_NO, ADD_MONTHS(s.SEPARATION_DT, 6) AS RPMT_START_DT FROM STU_RAW s",
            "LEASE.BUYOUT_AMT": "SELECT l.LEASE_NO, l.REMAINING_BILLED + l.PURCH_OPT_FEE AS BUYOUT_AMT FROM LEASE_RAW l",
            "AUTO_LN.DLR_RSV_AMT": "SELECT a.LN_NO, a.DLR_RSV_TOTAL / a.TERM_MO AS DLR_RSV_AMT FROM AUTO_RAW a",
        },
    },
    "truth": [
        ("AUTO_LN.LN_NO", "auto_loan.loan_id", "exact", [], None),
        ("AUTO_LN.ORIG_DT", "auto_loan.origination_date", "exact", [], None),
        ("AUTO_LN.TERM_MO", "auto_loan.term_months", "exact", [], None),
        ("AUTO_LN.VEH_VAL", "auto_loan.vehicle_value", "conflict", ["methodology"], None),
        ("AUTO_LN.REPO_IND", "auto_loan.is_repossessed", "conflict", ["population"], None),
        ("AUTO_LN.DLR_RSV_AMT", "auto_loan.dealer_reserve_fee", "conflict", ["methodology"], None),
        ("STU_LN.LN_NO", "student_loan.loan_id", "exact", [], None),
        ("STU_LN.BRWR_NM", "student_loan.borrower_name", "exact", [], None),
        ("STU_LN.RPMT_START_DT", "student_loan.repayment_start_date", "conflict", ["temporal"], None),
        ("STU_LN.DISB_AMT", "student_loan.disbursement_amount", "conflict", ["inclusion"], None),
        ("STU_LN.COSGN_REL_IND", "student_loan.cosigner_release_flag", "conflict", ["population"], None),
        ("LEASE.LEASE_NO", "equipment_lease.lease_id", "exact", [], None),
        ("LEASE.START_DT", "equipment_lease.start_date", "exact", [], None),
        ("LEASE.RESID_VAL", "equipment_lease.residual_value", "conflict", ["methodology"], None),
        ("LEASE.BUYOUT_AMT", "equipment_lease.buyout_price", "conflict", ["methodology"], None),
        ("SYND_LN.DEAL_NO", "syndicated_loan.deal_id", "exact", [], None),
        ("SYND_LN.AGENT_BANK", "syndicated_loan.agent_bank", "exact", [], None),
        ("SYND_LN.CMT_AMT", "syndicated_loan.commitment_amount", "conflict", ["aggregation"], None),
        ("SYND_LN.BRWR_ID", "syndicated_loan.borrower_id", "conflict", ["identity"], None),
    ],
}

SPEC_J = {
    "loaded": ['app_session.device_id'],  # stored as loaded by the target system, not recomputed
    "names": ("cascade_redwood", "Cascade Commerce Bank", "Redwood Community Bank"),
    "dialects": ("tsql", "snowflake"),
    "entities": [
        {"name": "customer", "per_base": 1.0,
         "latent": {"nm": "name:full", "u": "uniform:0~1", "login": "date:2026-06-01..2026-10-31", "push": "bool:0.7",
                    "fail": "int:0-4", "fail_extra": "int:0-40", "susp": "code:0=0.9|3=0.04|8=0.03|20=0.03",
                    "bundle": "int:3-10"},
         "target": {"table": "customer", "key": "customer_id", "columns": [
             ("customer_id", "NUMBER(38,0)", "Customer identifier", "ID"),
             ("full_name", "VARCHAR(120)", "Customer name", "nm"),
             ("pep_flag", "BOOLEAN", "Politically exposed person: active foreign government official", "u < 0.01"),     # J2
             ("sar_count", "NUMBER(6,0)", "Distinct suspicious transactions flagged", "susp.astype(int)"),               # J3
             ("is_digital_active", "BOOLEAN", "Logged into the mobile app in the last 30 days",
              "(AS_OF - pd.to_datetime(login)).dt.days <= 30"),                                                          # J7
             ("failed_login_count", "NUMBER(4,0)", "Consecutive failed passwords since the last success", "fail")]},     # J10
         "source": {"table": "CUST", "key": "CUST_ID", "columns": [
             ("CUST_ID", "INT", "Customer id", "ID"),
             ("CUST_NM", "NVARCHAR(120)", "Customer name", "nm"),
             ("PEP_IND", "NCHAR(1)", "PEP indicator", "where(u < 0.04, 'Y', 'N')"),                                      # J2
             ("SAR_CNT", "INT", "SAR count", "np.ceil(susp.astype(int) / bundle).astype(int)"),                          # J3
             ("DIG_ACTV_IND", "NCHAR(1)", "Digital active", "where(push, 'Y', 'N')"),                                     # J7
             ("FAIL_LOGIN_CNT", "INT", "Failed logins", "fail + fail_extra")]}},                                          # J10
        {"name": "ctr", "per_base": 1.0,
         "latent": {"cust": "fk:customer", "day": "date:2026-07-01..2026-10-30,business", "base": "money:11500,sigma=0.3",
                    "extra_n": "code:0=0.7|1=0.2|2=0.1", "extra": "money:4000,sigma=0.5"},
         "target": {"table": "ctr_aggregate", "key": "ctr_id", "columns": [
             ("ctr_id", "NUMBER(38,0)", "CTR aggregation identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Person", "cust"),
             ("business_date", "DATE", "Business date", "day"),
             ("cash_total", "NUMBER(14,2)", "Daily cash deposits summed by individual conductor", "base")]},               # J1
         "source": {"table": "CTR_AGG", "key": "CTR_ID", "columns": [
             ("CTR_ID", "INT", "CTR id", "ID"),
             ("CUST_ID", "INT", "Customer id", "cust"),
             ("BUS_DT", "DATE", "Business date", "day"),
             ("CASH_TOT_AMT", "MONEY", "Cash total", "(base + extra * extra_n.astype(int)).round(2)")]}},                  # J1
        {"name": "atm", "per_base": 0.1,
         "latent": {"cass": "money:60000,sigma=0.4", "bins": "money:4000,sigma=0.6", "up": "uniform:0.97~0.999",
                    "cashout": "uniform:0~0.06", "visits": "int:3000-9000", "ops": "uniform:1.2~2.0"},
         "target": {"table": "atm", "key": "atm_id", "columns": [
             ("atm_id", "NUMBER(38,0)", "ATM identifier", "ID"),
             ("cash_balance", "NUMBER(12,2)", "Bills remaining in the dispensing cassettes", "cass"),                     # J4
             ("uptime_pct", "NUMBER(5,2)", "Percent of time powered on and connected", "(up * 100).round(2)"),            # J5
             ("txn_count", "NUMBER(8,0)", "Card insertions this month", "visits")]},                                      # J6
         "source": {"table": "ATM", "key": "ATM_ID", "columns": [
             ("ATM_ID", "INT", "ATM id", "ID"),
             ("CASH_BAL", "MONEY", "Cash balance", "(cass + bins).round(2)"),                                             # J4
             ("UPTIME_PCT", "DECIMAL(5,2)", "Uptime", "((up - cashout) * 100).round(2)"),                                 # J5
             ("TXN_CNT", "INT", "Transaction count", "(visits * ops).round().astype(int)")]}},                             # J6
        {"name": "session", "per_base": 5.0,
         "latent": {"cust": "fk:customer", "dur": "uniform:60~1800", "nologout": "bool:0.6",
                    "hw": "pattern:HW-AAAA######", "tok": "pattern:tok_############"},
         "target": {"table": "app_session", "key": "session_id", "columns": [
             ("session_id", "NUMBER(38,0)", "Session identifier", "ID"),
             ("customer_id", "NUMBER(38,0)", "Customer", "cust"),
             ("session_duration_sec", "NUMBER(8,0)", "Seconds from login to explicit logout", "dur.round().astype(int)"),  # J8
             ("device_id", "VARCHAR(20)", "Hardware-bound device identifier", "hw")]},                                      # J9
         "source": {"table": "SESSION_LOG", "key": "SESS_ID", "columns": [
             ("SESS_ID", "BIGINT", "Session id", "ID"),
             ("CUST_ID", "INT", "Customer id", "cust"),
             ("SESS_DUR_SEC", "INT", "Session duration", "(dur + where(nologout, 900, 0)).round().astype(int)"),           # J8
             ("DEVICE_ID", "NVARCHAR(20)", "Device id", "tok")]}},                                                          # J9
    ],
    "derivations": {
        "target": {"customer.is_digital_active": "SELECT s.customer_id, MAX(s.login_ts) >= DATE '2026-10-31' - INTERVAL 30 DAY AS is_digital_active FROM app_session s GROUP BY s.customer_id"},
        "source": {
            "ATM.CASH_BAL": "SELECT a.ATM_ID, a.CASSETTE_AMT + a.DEPOSIT_BIN_AMT + a.REJECT_BIN_AMT AS CASH_BAL FROM ATM_RAW a",
            "SESSION_LOG.SESS_DUR_SEC": "SELECT s.SESS_ID, DATEDIFF(second, s.LOGIN_TS, s.SESSION_END_TS) AS SESS_DUR_SEC FROM SESSION_RAW s",
            "CTR_AGG.CASH_TOT_AMT": "SELECT c.ACCT_OWNER_ID AS CUST_ID, c.BUS_DT, SUM(c.CASH_AMT) AS CASH_TOT_AMT FROM CASH_TXN c GROUP BY c.ACCT_OWNER_ID, c.BUS_DT",
        },
    },
    "truth": [
        ("CUST.CUST_ID", "customer.customer_id", "exact", [], None),
        ("CUST.CUST_NM", "customer.full_name", "exact", [], None),
        ("CUST.PEP_IND", "customer.pep_flag", "conflict", ["population"], None),
        ("CUST.SAR_CNT", "customer.sar_count", "conflict", ["aggregation"], None),
        ("CUST.DIG_ACTV_IND", "customer.is_digital_active", "conflict", ["population"], None),
        ("CUST.FAIL_LOGIN_CNT", "customer.failed_login_count", "conflict", ["aggregation"], None),
        ("CTR_AGG.CTR_ID", "ctr_aggregate.ctr_id", "exact", [], None),
        ("CTR_AGG.CUST_ID", "ctr_aggregate.customer_id", "exact", [], None),
        ("CTR_AGG.BUS_DT", "ctr_aggregate.business_date", "exact", [], None),
        ("CTR_AGG.CASH_TOT_AMT", "ctr_aggregate.cash_total", "conflict", ["aggregation"], None),
        ("ATM.ATM_ID", "atm.atm_id", "exact", [], None),
        ("ATM.CASH_BAL", "atm.cash_balance", "conflict", ["inclusion"], None),
        ("ATM.UPTIME_PCT", "atm.uptime_pct", "conflict", ["population"], None),
        ("ATM.TXN_CNT", "atm.txn_count", "conflict", ["aggregation"], None),
        ("SESSION_LOG.SESS_ID", "app_session.session_id", "exact", [], None),
        ("SESSION_LOG.CUST_ID", "app_session.customer_id", "exact", [], None),
        ("SESSION_LOG.SESS_DUR_SEC", "app_session.session_duration_sec", "conflict", ["inclusion"], None),
        ("SESSION_LOG.DEVICE_ID", "app_session.device_id", "conflict", ["identity"], None),
    ],
}

SPEC_K = {
    "loaded": ['swap_trade.notional_amount', 'repo_trade.repo_amount', 'repo_trade.maturity_date'],  # stored as loaded by the target system, not recomputed
    "names": ("beaconstreet_granitepeak", "Beacon Street Bank", "Granite Peak Capital"),
    "dialects": ("oracle", "snowflake"),
    "entities": [
        {"name": "cpty", "per_base": 0.1,
         "latent": {"nm": "bank:", "grc": "money:25000000,sigma=1.0", "net": "uniform:0.2~0.6", "coll": "uniform:0~0.5",
                    "pit": "uniform:0.002~0.06", "cycle": "uniform:0.6~1.6"},
         "target": {"table": "counterparty", "key": "cpty_id", "columns": [
             ("cpty_id", "NUMBER(38,0)", "Counterparty identifier", "ID"),
             ("cpty_name", "VARCHAR(80)", "Counterparty legal name", "nm"),
             ("exposure_amount", "NUMBER(18,2)", "Gross positive replacement cost across open trades", "grc"),           # K3
             ("pd", "NUMBER(8,6)", "Point-in-time probability of default", "pit.round(6)")]},                            # K9
         "source": {"table": "CPTY", "key": "CPTY_ID", "columns": [
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "ID"),
             ("CPTY_NM", "VARCHAR2(80)", "Counterparty", "nm"),
             ("EXPOSURE_AMT", "NUMBER(18,2)", "Exposure", "(grc * net * (1 - coll)).round(2)"),                          # K3
             ("PD", "NUMBER(8,6)", "PD", "(pit / cycle).round(6)")]}},                                                   # K9
        {"name": "swap", "per_base": 2.0,
         "latent": {"cp": "fk:cpty", "ntl": "money:50000000,sigma=0.8", "trade_dt": "date:2024-01-01..2026-10-30,business"},
         "target": {"table": "swap_trade", "key": "swap_id", "columns": [
             ("swap_id", "NUMBER(38,0)", "Swap identifier", "ID"),
             ("cpty_id", "NUMBER(38,0)", "Counterparty", "cp"),
             ("trade_date", "DATE", "Trade date", "trade_dt"),
             ("notional_amount", "NUMBER(18,2)", "Gross notional: pay leg plus receive leg", "(ntl * 2).round(2)")]},    # K1
         "source": {"table": "SWAP", "key": "SWAP_ID", "columns": [
             ("SWAP_ID", "NUMBER(12)", "Swap id", "ID"),
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "cp"),
             ("TRD_DT", "DATE", "Trade date", "trade_dt"),
             ("NTNL_AMT", "NUMBER(18,2)", "Notional", "ntl.round(2)")]}},                                                 # K1
        {"name": "bond", "per_base": 2.0,
         "latent": {"cp": "fk:cpty", "face": "money:5000000,sigma=0.7", "clean": "uniform:92~106", "accr": "uniform:0~2.8",
                    "matched": "bool:0.97", "dvp": "uniform:0~1"},
         "target": {"table": "bond_position", "key": "position_id", "columns": [
             ("position_id", "NUMBER(38,0)", "Position identifier", "ID"),
             ("cpty_id", "NUMBER(38,0)", "Counterparty", "cp"),
             ("market_value", "NUMBER(18,2)", "Clean market value, excluding accrued interest", "(face * clean / 100).round(2)"),  # K2
             ("settlement_status", "VARCHAR(8)", "SETTLED once matched at the clearinghouse, else PENDING",
              "where(matched, 'SETTLED', 'PENDING')")]},                                                                  # K10
         "source": {"table": "BOND_POSN", "key": "POSN_ID", "columns": [
             ("POSN_ID", "NUMBER(12)", "Position id", "ID"),
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "cp"),
             ("MKT_VAL", "NUMBER(18,2)", "Market value", "(face * (clean + accr) / 100).round(2)"),                       # K2
             ("STL_STAT", "CHAR(1)", "Settlement status", "where(matched & (dvp < 0.85), 'S', 'P')")]}},                  # K10
        {"name": "margin", "per_base": 0.1,
         "latent": {"cp": "fk:cpty", "settled": "money:3000000,sigma=0.8", "transit": "money:400000,sigma=1.0;null:0.5"},
         "target": {"table": "margin_account", "key": "margin_id", "columns": [
             ("margin_id", "NUMBER(38,0)", "Margin account", "ID"),
             ("cpty_id", "NUMBER(38,0)", "Counterparty", "cp"),
             ("variation_margin", "NUMBER(18,2)", "Settled cash collateral in the margin account", "settled")]},          # K4
         "source": {"table": "MRGN", "key": "MRGN_ID", "columns": [
             ("MRGN_ID", "NUMBER(10)", "Margin id", "ID"),
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "cp"),
             ("VM_BAL", "NUMBER(18,2)", "Variation margin", "(settled + transit.fillna(0)).round(2)")]}},                 # K4
        {"name": "repo", "per_base": 1.0,
         "latent": {"cp": "fk:cpty", "cash": "money:20000000,sigma=0.7", "hc": "uniform:0.01~0.05",
                    "start": "date:2026-10-01..2026-10-29,business", "open": "bool:0.3", "blank": "bool:0.5"},
         "target": {"table": "repo_trade", "key": "repo_id", "columns": [
             ("repo_id", "NUMBER(38,0)", "Repo identifier", "ID"),
             ("cpty_id", "NUMBER(38,0)", "Counterparty", "cp"),
             ("repo_amount", "NUMBER(18,2)", "Cash lent on the start date", "cash"),                                     # K5
             ("maturity_date", "DATE", "Next business day for rolling overnight repos", "bizday(start + days(1))")]},    # K6
         "source": {"table": "REPO", "key": "REPO_ID", "columns": [
             ("REPO_ID", "NUMBER(12)", "Repo id", "ID"),
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "cp"),
             ("REPO_AMT", "NUMBER(18,2)", "Repo amount", "(cash / (1 - hc)).round(2)"),                                   # K5
             ("MAT_DT", "DATE", "Maturity date",
              "bizday(start + days(1)).where(~open, pd.Timestamp('2099-12-31')).where(~(open & blank), pd.NaT)")]}},     # K6
        {"name": "line", "per_base": 1.0,
         "latent": {"cp": "fk:cpty", "undrawn": "money:2000000,sigma=0.9", "cancel": "bool:0.35",
                    "rw": "code:0.2=0.3|0.5=0.3|1.0=0.4", "irb": "uniform:0.1~1.4"},
         "target": {"table": "credit_line", "key": "line_id", "columns": [
             ("line_id", "NUMBER(38,0)", "Credit line identifier", "ID"),
             ("cpty_id", "NUMBER(38,0)", "Counterparty", "cp"),
             ("ccf", "NUMBER(4,2)", "Credit conversion factor: flat 20% on undrawn amounts", "pd.Series(0.2, index=undrawn.index)"),  # K8
             ("rwa_amount", "NUMBER(18,2)", "Risk-weighted assets, standardized risk weights",
              "(undrawn * 0.2 * rw.astype(float)).round(2)")]},                                                          # K7
         "source": {"table": "CR_LINE", "key": "LINE_ID", "columns": [
             ("LINE_ID", "NUMBER(10)", "Line id", "ID"),
             ("CPTY_ID", "NUMBER(10)", "Counterparty id", "cp"),
             ("CCF", "NUMBER(4,2)", "CCF", "where(cancel, 0.0, 0.2)"),                                                   # K8
             ("RWA_AMT", "NUMBER(18,2)", "RWA", "(undrawn * where(cancel, 0.0, 0.2) * irb).round(2)")]}},                # K7
    ],
    "derivations": {
        "target": {"credit_line.rwa_amount": "SELECT l.line_id, l.undrawn_amt * l.ccf * r.std_risk_weight AS rwa_amount FROM credit_line l JOIN rating_lookup r ON r.rating = l.rating"},
        "source": {
            "CPTY.EXPOSURE_AMT": "SELECT c.CPTY_ID, (c.GROSS_RC - c.NETTING_BENEFIT - c.CASH_COLLATERAL) AS EXPOSURE_AMT FROM CPTY_RAW c",
            "MRGN.VM_BAL": "SELECT m.MRGN_ID, m.SETTLED_CASH + m.INTRANSIT_CALLS AS VM_BAL FROM MRGN_RAW m",
            "BOND_POSN.MKT_VAL": "SELECT b.POSN_ID, b.CLEAN_MV + b.ACCRUED_INT AS MKT_VAL FROM BOND_RAW b",
            "CR_LINE.RWA_AMT": "SELECT l.LINE_ID, l.UNDRAWN_AMT * l.CCF * l.IRB_RISK_WEIGHT AS RWA_AMT FROM CR_LINE_RAW l",
        },
    },
    "truth": [
        ("CPTY.CPTY_ID", "counterparty.cpty_id", "exact", [], None),
        ("CPTY.CPTY_NM", "counterparty.cpty_name", "exact", [], None),
        ("CPTY.EXPOSURE_AMT", "counterparty.exposure_amount", "conflict", ["inclusion"], None),
        ("CPTY.PD", "counterparty.pd", "conflict", ["methodology"], None),
        ("SWAP.SWAP_ID", "swap_trade.swap_id", "exact", [], None),
        ("SWAP.CPTY_ID", "swap_trade.cpty_id", "exact", [], None),
        ("SWAP.TRD_DT", "swap_trade.trade_date", "exact", [], None),
        ("SWAP.NTNL_AMT", "swap_trade.notional_amount", "conflict", ["aggregation"], None),
        ("BOND_POSN.POSN_ID", "bond_position.position_id", "exact", [], None),
        ("BOND_POSN.CPTY_ID", "bond_position.cpty_id", "exact", [], None),
        ("BOND_POSN.MKT_VAL", "bond_position.market_value", "conflict", ["inclusion"], None),
        ("BOND_POSN.STL_STAT", "bond_position.settlement_status", "conflict", ["population"], None),
        ("MRGN.MRGN_ID", "margin_account.margin_id", "exact", [], None),
        ("MRGN.CPTY_ID", "margin_account.cpty_id", "exact", [], None),
        ("MRGN.VM_BAL", "margin_account.variation_margin", "conflict", ["inclusion"], None),
        ("REPO.REPO_ID", "repo_trade.repo_id", "exact", [], None),
        ("REPO.CPTY_ID", "repo_trade.cpty_id", "exact", [], None),
        ("REPO.REPO_AMT", "repo_trade.repo_amount", "conflict", ["inclusion"], None),
        ("REPO.MAT_DT", "repo_trade.maturity_date", "conflict", ["null_semantics"], None),
        ("CR_LINE.LINE_ID", "credit_line.line_id", "exact", [], None),
        ("CR_LINE.CPTY_ID", "credit_line.cpty_id", "exact", [], None),
        ("CR_LINE.CCF", "credit_line.ccf", "conflict", ["population"], None),
        ("CR_LINE.RWA_AMT", "credit_line.rwa_amount", "conflict", ["methodology"], None),
    ],
}

SPECS = {"G": SPEC_G, "H": SPEC_H, "I": SPEC_I, "J": SPEC_J, "K": SPEC_K}
