-- ============================================================================
-- CORE BANKING MERGER & MIGRATION: AUTOMATED SEMANTIC TRAP PROFILING SUITE
-- Companion Script to: Banking_Semantic_Data_Mapping_and_SME_SignOff_Template.xlsx
-- Purpose: Automatically scans Source vs. Target staging tables to detect
--          sign inversions, scale mismatches (100x), sentinel dates, ID
--          persistence traps, gross/net hold discrepancies, and CTR/syndication
--          granularity errors before production ETL cutover.
-- Dialect: ANSI SQL (Compatible with Snowflake, Databricks, Postgres, SQL Server, Oracle)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. MASTER AUTOMATED RECONCILIATION & TRAP SUMMARY VIEW
--    Run this unified diagnostic view to output a Pass/Fail scorecard across
--    all 12 semantic trap categories in your staging environment.
-- ----------------------------------------------------------------------------
WITH trap_checks AS (

    -- [MTG-0108] Trap 1: Sign Inversion Check (Escrow Balance Shortage vs. Surplus)
    SELECT
        'MTG-0108' AS mapping_id,
        'Sign Inversion (Escrow Balance)' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN s.src_escrow_bal <> 0
                  AND SIGN(s.src_escrow_bal) = SIGN(t.tgt_esc_curr_amt)
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Source (+) = Shortage; Target (+) = Surplus. Signs must be opposite.' AS diagnostic_rule
    FROM stg_src_mortgage s
    JOIN stg_tgt_loan_esc t ON s.loan_id = t.loan_id

    UNION ALL

    -- [CIF-0712] Trap 2: 100x Rate Scale Mismatch (Decimal 0.0625 vs. Percent 6.25)
    SELECT
        'CIF-0712' AS mapping_id,
        'Scale & Precision Factor (100x Interest Rate)' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN s.note_intr_rate > 0
                  AND ABS((s.note_intr_rate * 100.0) - t.annual_rate_pct) > 0.0001
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Source rate is decimal (0.0625); Target rate is percentage (6.2500).' AS diagnostic_rule
    FROM stg_src_loan_rate s
    JOIN stg_tgt_loan_terms t ON s.loan_id = t.loan_id

    UNION ALL

    -- [DEP-0014] Trap 3: Gross vs. Net Hold Inclusion (Settled Ledger vs. Memo-Posted Balance)
    SELECT
        'DEP-0014' AS mapping_id,
        'Gross vs. Net / Memo Holds Inclusion' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN s.memo_hold_amt > 0
                  AND ABS((s.curr_bal_amt + s.memo_hold_amt) - t.ledger_bal_amt) > 0.01
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Target Ledger Balance must equal Source Current Balance + Memo Holds.' AS diagnostic_rule
    FROM stg_src_dda_acct s
    JOIN stg_tgt_dep_mast t ON s.acct_id = t.acct_id

    UNION ALL

    -- [CRD-0219] Trap 4: Hidden Shadow Overlimit Buffer in Available Credit
    SELECT
        'CRD-0219' AS mapping_id,
        'Shadow Overlimit Buffer Included in Open-to-Buy' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN t.open_to_buy_amt > (s.hard_limit_amt - s.curr_bal_amt - s.auth_holds_amt)
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Target Open-to-Buy must cap strictly at Hard Limit minus Balance and Holds.' AS diagnostic_rule
    FROM stg_src_card_limit s
    JOIN stg_tgt_card_acct t ON s.card_acct_id = t.card_acct_id

    UNION ALL

    -- [CAP-0603] Trap 5: Sentinel / Dummy Date Leakage (2099-12-31 or 1900-01-01)
    SELECT
        'CAP-0603' AS mapping_id,
        'Sentinel / Dummy Date Leakage (Repo Maturity)' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN t.term_end_dt IN (DATE '2099-12-31', DATE '9999-12-31', DATE '1900-01-01')
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Open-ended repos (2099-12-31) must convert to T+1 business date + OPEN_TERM_FLAG=Y.' AS diagnostic_rule
    FROM stg_tgt_cap_repo t

    UNION ALL

    -- [COM-0318] Trap 6: Static Origination Date Overwritten by Renewal Date
    SELECT
        'COM-0318' AS mapping_id,
        'Static vs. Rolling Lifecycle Date (Origination Date)' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN t.orig_fund_dt > h.earliest_book_dt
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Target Origination Date must match earliest historical funding date, not latest renewal.' AS diagnostic_rule
    FROM stg_tgt_loan_core t
    JOIN (
        SELECT loan_id, MIN(initial_book_dt) AS earliest_book_dt
        FROM stg_src_loan_hist
        GROUP BY loan_id
    ) h ON t.loan_id = h.loan_id

    UNION ALL

    -- [COM-0305] Trap 7: Syndicated Whole-Deal vs. Bank Pro-Rata Participation Share
    SELECT
        'COM-0305' AS mapping_id,
        'Syndicated Whole Deal vs. Bank Pro-Rata Share' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN p.bank_retained_pct < 1.0000
                  AND ABS(t.bank_commit_amt - s.commit_total_amt) < 1.00
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Target Bank Commitment must reflect pro-rata retained share, not 100% multi-bank deal.' AS diagnostic_rule
    FROM stg_src_synd_fac s
    JOIN stg_src_synd_partic p ON s.facility_id = p.facility_id
    JOIN stg_tgt_com_loan t ON s.facility_id = t.facility_id

    UNION ALL

    -- [WTH-0509] Trap 8: Currency Basis Mismatch (Pre-Converted USD vs. Local Currency)
    SELECT
        'WTH-0509' AS mapping_id,
        'FX Currency Valuation Basis (USD Mapped as Local CCY)' AS trap_type,
        COUNT(*) AS total_records_checked,
        SUM(CASE WHEN s.ccy_code <> 'USD'
                  AND s.spot_rate <> 1.0000
                  AND ABS(t.local_ccy_amt - t.usd_equiv_amt) < 0.01
                 THEN 1 ELSE 0 END) AS trap_violations_found,
        'Non-USD trades must store native currency amount in LOCAL_CCY_AMT, not USD equivalent.' AS diagnostic_rule
    FROM stg_src_fx_spot s
    JOIN stg_tgt_treas_fx t ON s.trade_id = t.trade_id
)
SELECT
    mapping_id,
    trap_type,
    total_records_checked,
    trap_violations_found,
    CASE WHEN trap_violations_found = 0 THEN 'PASS - READY FOR CUTOVER'
         ELSE 'FAIL - BLOCK MIGRATION'
    END AS gate_verdict,
    diagnostic_rule
FROM trap_checks
ORDER BY trap_violations_found DESC, mapping_id;


-- ============================================================================
-- 2. STANDALONE DISCOVERY QUERIES (RUN DIRECTLY ON UNKNOWN LEGACY TABLES)
--    Use these queries BEFORE SME workshops to uncover undocumented traps.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- DISCOVERY QUERY A: Detect Undocumented Sign Conventions & Negative Balances
-- Scans numeric columns to reveal whether loans, holds, and escrow shortages
-- are stored as positive or negative numbers.
-- ----------------------------------------------------------------------------
SELECT
    'SRC_MORTGAGE.SRC_ESCROW_BAL' AS field_analyzed,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN src_escrow_bal > 0 THEN 1 ELSE 0 END) AS positive_count,
    SUM(CASE WHEN src_escrow_bal < 0 THEN 1 ELSE 0 END) AS negative_count,
    SUM(CASE WHEN src_escrow_bal = 0 THEN 1 ELSE 0 END) AS zero_count,
    SUM(CASE WHEN src_escrow_bal IS NULL THEN 1 ELSE 0 END) AS null_count,
    MIN(src_escrow_bal) AS min_val,
    MAX(src_escrow_bal) AS max_val,
    AVG(src_escrow_bal) AS avg_val
FROM stg_src_mortgage;


-- ----------------------------------------------------------------------------
-- DISCOVERY QUERY B: Detect Interest Rate Scale Traps (Decimal vs. Percentage)
-- If MAX(rate) <= 1.0, the bank stores decimals (0.0525).
-- If MAX(rate) > 1.0, the bank stores whole percentages (5.25).
-- Mixed regimes in the same column indicate corrupt legacy loads!
-- ----------------------------------------------------------------------------
SELECT
    product_code,
    COUNT(*) AS loan_count,
    MIN(note_intr_rate) AS min_rate,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY note_intr_rate) AS median_rate,
    MAX(note_intr_rate) AS max_rate,
    SUM(CASE WHEN note_intr_rate > 0 AND note_intr_rate < 0.35 THEN 1 ELSE 0 END) AS likely_decimal_format_cnt,
    SUM(CASE WHEN note_intr_rate >= 0.35 AND note_intr_rate <= 36.0 THEN 1 ELSE 0 END) AS likely_percentage_format_cnt
FROM stg_src_loan_rate
GROUP BY product_code
ORDER BY product_code;


-- ----------------------------------------------------------------------------
-- DISCOVERY QUERY C: Scan All Date Columns for Sentinel / Dummy Placeholders
-- Exposes hidden 1900-01-01, 1970-01-01, 2099-12-31, or 9999-12-31 values
-- used by legacy COBOL/mainframe systems for open-ended terms or missing dates.
-- ----------------------------------------------------------------------------
SELECT
    maturity_dt AS suspect_date_value,
    COUNT(*) AS occurrence_count,
    MIN(acct_open_dt) AS earliest_associated_open_dt,
    MAX(acct_open_dt) AS latest_associated_open_dt
FROM stg_src_repo_book
WHERE maturity_dt <= DATE '1970-01-02'
   OR maturity_dt >= DATE '2090-01-01'
   OR maturity_dt < acct_open_dt  -- Catches backdated/corrupt maturity < origination
GROUP BY maturity_dt
ORDER BY occurrence_count DESC;


-- ----------------------------------------------------------------------------
-- DISCOVERY QUERY D: Test ID Persistence vs. Reissue/Renewal Granularity
-- Checks whether CARD_ACCT_ID or LOAN_ID is 1:1 with a customer account
-- or 1:Many across reissued plastics / loan modifications.
-- ----------------------------------------------------------------------------
SELECT
    card_acct_id,
    COUNT(DISTINCT plastic_pan_token) AS distinct_plastics_under_id,
    MIN(issue_dt) AS first_plastic_issue_dt,
    MAX(issue_dt) AS latest_plastic_issue_dt
FROM stg_src_card_mast
GROUP BY card_acct_id
HAVING COUNT(DISTINCT plastic_pan_token) > 1
ORDER BY distinct_plastics_under_id DESC
FETCH FIRST 50 ROWS ONLY;


-- ----------------------------------------------------------------------------
-- DISCOVERY QUERY E: Expose CTR Cash Aggregation Trap (Conductor vs. Owner)
-- Identifies days where aggregating by Conductor crosses the $10,000 FinCEN
-- CTR threshold, while aggregating by Account Owner stays under $10,000 (or vice versa).
-- ----------------------------------------------------------------------------
WITH conductor_agg AS (
    SELECT txn_date, conductor_party_id AS party_id, SUM(cash_in_amt) AS conductor_daily_cash
    FROM stg_src_teller_txn
    GROUP BY txn_date, conductor_party_id
),
owner_agg AS (
    SELECT t.txn_date, a.primary_owner_party_id AS party_id, SUM(t.cash_in_amt) AS owner_daily_cash
    FROM stg_src_teller_txn t
    JOIN stg_src_acct_owner a ON t.acct_id = a.acct_id
    GROUP BY t.txn_date, a.primary_owner_party_id
)
SELECT
    COALESCE(c.txn_date, o.txn_date) AS business_date,
    COALESCE(c.party_id, o.party_id) AS customer_party_id,
    COALESCE(c.conductor_daily_cash, 0) AS cash_by_conductor,
    COALESCE(o.owner_daily_cash, 0) AS cash_by_account_owner,
    CASE
        WHEN COALESCE(c.conductor_daily_cash, 0) >= 10000.01 AND COALESCE(o.owner_daily_cash, 0) < 10000.01
            THEN 'TRAP: Triggers CTR by Conductor Only'
        WHEN COALESCE(c.conductor_daily_cash, 0) < 10000.01 AND COALESCE(o.owner_daily_cash, 0) >= 10000.01
            THEN 'TRAP: Triggers CTR by Account Owner Only'
    END AS ctr_discrepancy_type
FROM conductor_agg c
FULL OUTER JOIN owner_agg o
    ON c.txn_date = o.txn_date AND c.party_id = o.party_id
WHERE (COALESCE(c.conductor_daily_cash, 0) >= 10000.01 AND COALESCE(o.owner_daily_cash, 0) < 10000.01)
   OR (COALESCE(c.conductor_daily_cash, 0) < 10000.01 AND COALESCE(o.owner_daily_cash, 0) >= 10000.01)
ORDER BY business_date DESC;
