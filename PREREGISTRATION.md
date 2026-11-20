# Held-out evaluation pre-registration

Recorded 2026-11-06 06:07 UTC, before MergeGuard was run on scenarios B and C.

## Frozen files (sha256)

```
ddd4a3b178cc360e4759aafc9eddd666b2bab97bad2dfd2c3e727a0bc7bd8786  mergeguard/bench/lending.py
9bcbbccbaa7085df324c8faa8fc9faf0fb7e464721852b3531b082d344e8eb3d  mergeguard/bench/cards_portfolio.py
3ce5c11ec93995b4093874ee9586c86739bb95af2f0af1b3216b01a7becab0a0  mergeguard/match.py
138b04b79358f067dba0c8eec2a452a4c728bdd729c5bede4eb1b0d081904f2c  mergeguard/cards.py
8b838cc1ee45fba38b90928127acbb9cec77d5307f24048c226e3850204855e3  mergeguard/evaluate.py
```

## Commitments

1. Scenarios B (lending) and C (cards) were written after the matcher was frozen and have not been
   run through it. Seed 101 is used for the reported run.
2. No change to match.py, cards.py or evaluate.py before the held-out numbers are reported.
   Any later fix is reported as a new version, and both numbers are kept.
3. Baselines: name-only, and Valentine's COMA, Cupid, Similarity Flooding, DistributionBased and
   JaccardDistance, each with one-to-one assignment over its similarity scores.
4. Metrics: target accuracy, conflict recall (overall and by type), harmful auto-accepts.

## Known limits of this check

The same author wrote the matcher and the held-out scenarios, so they are not fully independent.
An independently authored scenario is still needed.

## Results (v0.0.1, recorded before any change)

| Scenario | Method | Target accuracy | Harmful auto-accepts |
| --- | --- | --- | --- |
| keystone (dev) | name only | 52% | 12 |
| keystone (dev) | Valentine COMA | 70% | 12 |
| keystone (dev) | MergeGuard | 100% | 0 |
| lending (held-out) | name only | 35% | 15 |
| lending (held-out) | Valentine COMA | 50% | 13 |
| lending (held-out) | MergeGuard | 54% | 0 |
| cards (held-out) | name only | 48% | 7 |
| cards (held-out) | Valentine COMA | 72% | 9 |
| cards (held-out) | MergeGuard | 40% | 0 |

MergeGuard conflict recall: 100% dev, 64% lending, 18% cards. Baselines emit no conflict flags.
Full table including Cupid, Similarity Flooding and Jaccard: experiments/results_v0.0.1/results.md.

## Failure analysis

1. Declared types drive value evidence. COBOL PIC clauses and MONEY parse as strings, so numeric
   value profiles are never compared.
2. Identifier conventions: Key and REF are not recognized as identifiers, so keys fail.
3. Fixed abbreviation dictionary: CRD, LMT, OPN, PROD, UTIL, CHG, Prin are unknown.
4. The meaning-evidence gate then rejects correct pairs whose names and terse docs share no tokens.
5. Inclusion detection only knows fee terms; escrow and accrued interest are missed.
6. Format conflicts (phone punctuation) are not modeled.

Fixes go into v0.0.2 and must be judged on a new scenario that v0.0.2 has never seen, because
lending and cards are no longer held out once their failures are known.

## Scenario D pre-registration (for v0.0.2)

Recorded 2026-11-06 06:15 UTC, before any v0.0.2 code was written. Scenario D (insurance,
seed 202) is generated once to check its ground truth covers every column; no matcher is run on it
until v0.0.2 is frozen and hashed below.

```
99252c09f12149b979f4457a4e5065db66267511fb716586c5bf0cc145e4198a  mergeguard/bench/insurance.py
```

## v0.0.2 frozen (before its single run on scenario D)

Recorded 2026-11-06 06:32 UTC. Development scenarios: keystone, lending, cards.

```
796e74304b264507409c8d6b35216e17512eda63fc7054281fda53bf78808259  mergeguard/match.py
272f132f1c26db22ff01808e5aacfa73113cecf5a323c9e9da341d4bd944aff6  mergeguard/cards.py
7037190150f1f5405cbe873987aefea6060d4b8d02084665724814f4a8ddabbc  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
```

Changes from v0.0.1: data-driven type inference (COBOL PIC, MONEY, numbers stored as text), Key and REF
as identifiers, abbreviation matching by subsequence (crd/card), name and description cross evidence,
table alignment from column evidence before scoring context, soft logic comparison, generic inclusion
from additive terms, digit-format comparison, conflict-aware assignment, DDR for every target definition
with a 1% threshold for yes/no definitions, relative null-rate test.

Not addressed (known gaps): sign carried in a separate indicator column, many-to-one code crosswalks,
unit factors other than 100, sentinel dates, Hungarian-notation prefixes.

## v0.0.2 results on scenario D (single run)

| Method | Target accuracy | Conflict recall | Harmful auto-accepts |
| --- | --- | --- | --- |
| name only | 39% | 0% | 7 |
| Valentine COMA | 43% | 0% | 11 |
| Valentine Cupid | 26% | 0% | 4 |
| Valentine Similarity Flooding | 35% | 0% | 16 |
| Valentine Jaccard | 35% | 0% | 9 |
| MergeGuard v0.0.2 | 61% | 20% | 0 |

Development set with v0.0.2 (not evidence): keystone 100%, lending 100%, cards 100% target accuracy.

Misses on D: monthly vs annual premium (factor 12), deductible in thousands, sentinel end date vs NULL,
"Last, First" name split, ZIP integer vs zero-padded text, the LAE acronym, a policy status code mapped to
the claim status column, and reported vs loss date. Five of these were listed as known gaps before the run.
D is now a development scenario; v0.0.3 needs a new held-out scenario.

## v0.0.3 frozen (before the practitioner-authored scenario E exists)

Recorded 2026-11-06 18:01 UTC. Development scenarios: keystone, lending, cards, insurance.
Scenario E will be built from traps the practitioner co-author sends after this point; v0.0.3 runs on it once.

```
71635ec9303b04d3e2a6e0ab049e614abff2f2332f20af94e9a99d98de990f66  mergeguard/match.py
f24d5831254d57ec42756127b6ea2ed65a94f951b078bc8d0559c1382d472f7b  mergeguard/cards.py
7037190150f1f5405cbe873987aefea6060d4b8d02084665724814f4a8ddabbc  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
```

Changes from v0.0.2: wider unit search (x100, x1000, x12 and inverses) with a 0.15 margin over no change,
sentinel dates excluded from date statistics and NULL-vs-sentinel flagged, Hungarian type prefixes stripped,
acronym matching against descriptions, two-value status codes compared with booleans (and in DDR),
canonical entities from aligned tables, "Last, First" splits, integer code columns compared as categories,
unsigned amounts flagged against signed ones with an indicator-column transform, many-to-one crosswalks.

Development results (not evidence): target accuracy 100 / 100 / 100 / 96%, conflict recall 100 / 100 / 91 / 80%,
zero harmful auto-accepts. Best baseline (COMA): 70 / 50 / 72 / 43%, 9 to 13 harmful auto-accepts.

Known gaps: links that need world knowledge (status A/X means in force), units across different grains,
dates whose meaning is only in documentation (claim date = reported date).

## Scenario E: practitioner-authored traps (received after the v0.0.3 freeze)

Received from co-author Akshay Sharma on 2026-11-06, verbatim:

1. Current balance is settled funds at one bank, and includes pending holds at the other.
2. Origination date is the initial loan funding date at one bank, and the latest renewal date at the other.
3. Active status means the customer made a transaction in the last 90 days at one bank, and simply that the account isn't closed at the other.
4. Branch code tracks where the account was originally opened at one bank, and where the customer currently banks at the other.
5. Delinquency days count from the missed payment due date at one bank, and from the end of the grace period at the other.
6. Loan ID stays the same after a loan modification at one bank, and changes to a brand-new ID at the other.
7. Available credit caps at the hard credit limit at one bank, and includes the hidden shadow-overlimit buffer at the other.
8. Interest rate is stored as a decimal like 0.0525 at one bank, and as a percentage number like 5.25 at the other.
9. Primary owner is the highest earner on a joint loan at one bank, and whoever happened to sign the application first at the other.
10. Transaction amount shows debits as negative numbers at one bank, and as positive numbers with a separate debit-or-credit flag at the other.

Scenario construction choices (made by the builder, not the author): which bank is acquirer, table and column names,
data distributions, data-dictionary wording, and derivation SQL for computed fields, following the same protocol as
scenarios A to D. Traps 4, 6 and 9 introduce conflict types outside the taxonomy (point-in-time attribute,
identity, role assignment); they are labeled temporal, identity and role.

Scenario E file, generated with seed 303 before the run:

```
83b86a10a97d965fd196995617cddf5c6950dcd8937cd356cffd2421ff88a7c5  mergeguard/bench/practitioner.py
```

## v0.0.3 results on scenario E (single run)

| Method | Target accuracy | Conflict recall | Harmful auto-accepts |
| --- | --- | --- | --- |
| name only | 82% | 0% | 14 |
| Valentine COMA | 89% | 0% | 14 |
| Valentine Cupid | 11% | 0% | 0 |
| Valentine Similarity Flooding | 36% | 0% | 18 |
| Valentine Jaccard | 50% | 0% | 10 |
| MergeGuard v0.0.3 | 100% | 50% | 2 |

Caught (6 of 12 labeled conflicts): T3 active status (DDR 12.0%), T2 origination date, T8 interest rate scale,
T10 transaction sign with its debit/credit flag, and two code sets.
Missed: T1 current balance with holds, T7 available credit with shadow buffer (the target rule run on source data
disagreed on 100% of credit lines, but numeric DDR is not used as a conflict signal), T4 opening vs current branch,
T5 delinquency from grace end.
Harmful auto-accepts (2): T6 loan ID that changes on modification and T9 primary owner rule. Both are identifier
columns whose values carry no visible signal of the different rule.

## v0.0.4 frozen (before the next practitioner trap list exists)

Recorded 2026-11-06 21:38 UTC. Development scenarios: A to E.

```
c2c208714efb4df32570365e36d145ea94c582d52c5d7170c67c761305c92e5f  mergeguard/match.py
f24d5831254d57ec42756127b6ea2ed65a94f951b078bc8d0559c1382d472f7b  mergeguard/cards.py
a5d6fbcba90755b430e396e33d5754a745aac2d2fd9addf8234af021f98d45d8  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
```

Changes from v0.0.3: identifier columns are never auto-accepted (a person confirms ID meaning); the target's rule
run on source data is used for amounts too (one-sided disagreement flags inclusion); a sum of components compared
with a single column flags inclusion; day counters offset by a different starting event are detected; date
conflicts from names require real derivation logic; near-match warnings on unmatched columns need a real difference.
New metric: false alarms (conflicts flagged on clean attributes).

Development results (not evidence): accuracy 100 / 100 / 100 / 96 / 100%, conflict recall 100 / 100 / 91 / 80 / 75%,
zero harmful auto-accepts, zero false alarms. COMA: 70 / 50 / 72 / 43 / 89%, 9 to 14 harmful auto-accepts.

Known gaps: links needing world knowledge, attributes that differ only by point in time (opening vs current branch),
ID semantics (stable vs reissued IDs, primary owner rules) beyond routing them to review.

## Scenario F: practitioner-authored traps (received after the v0.0.4 freeze)

Received from co-author Akshay Sharma on 2026-11-06, verbatim:

1. Card ID stays the same when a lost card is replaced at one bank, and changes to match the new 16-digit card number at the other.
2. Fee amount shows the gross fee charged at one bank, and the net fee left after customer refunds at the other.
3. Deposit maturity date is the date the original CD term ends at one bank, and the auto-renewed end date at the other.
4. Customer income is self-reported annual gross pay at one bank, and verified monthly net take-home pay at the other.
5. Charge-off amount is only the unpaid principal balance at one bank, and includes unpaid interest and late fees at the other.
6. Merchant category code comes straight from the card network at one bank, and is remapped to an internal custom category list at the other.
7. Collateral value is the original purchase appraisal at one bank, and an automated monthly house price estimate at the other.
8. Small business flag is based on the business's annual revenue at one bank, and on total loan exposure size at the other.
9. Collections status triggers the day an account goes past due at one bank, and only after it is assigned to a recovery agent at the other.
10. KYC review date is the date the last background check finished at one bank, and the deadline for the next scheduled review at the other.

Construction choices are the builder's, under the same protocol as scenario E. The card ID trap is also applied to
the card transaction foreign key, since a reissued number propagates there.

Scenario F file, generated with seed 404 before the run:

```
f899b95fd906e4a4e7610fe03eba9a24d439c4f55be4037fd9106d58473eb849  mergeguard/bench/practitioner2.py
```

## v0.0.4 results on scenario F (single run)

| Method | Target accuracy | Conflict recall | Harmful auto-accepts | Auto-accepted | False alarms |
| --- | --- | --- | --- | --- | --- |
| name only | 62% | 0% | 15 | 26 | 0/16 |
| Valentine COMA | 97% | 0% | 12 | 28 | 0/16 |
| Valentine Cupid | 17% | 0% | 4 | 5 | 0/16 |
| Valentine Similarity Flooding | 76% | 0% | 18 | 29 | 0/16 |
| Valentine Jaccard | 38% | 0% | 8 | 15 | 0/16 |
| MergeGuard v0.0.4 | 100% | 50% | 1 | 7 | 0/16 |

Caught: T8 small business flag (DDR 2.5%), T9 collections status (DDR 16.3%), T5 charge-off amount, T6 merchant
categories, T4 income unit (monthly vs annual; the gross vs net part was missed), and two code sets.
Missed: T3 renewed maturity date and T10 next KYC deadline (88% vs 39% of dates in the future, not used as a signal),
T7 collateral AVM vs appraisal, T2 fee net of refunds, T1 card ID reissue (both card ID columns were routed to
review, not auto-accepted).
Harmful auto-accept (1): T2 fee amount, accepted at score 0.90 as an exact match.

Across the two practitioner-authored scenarios: conflict recall 50% (E, v0.0.3) and 50% (F, v0.0.4); harmful
auto-accepts 2 and 1, against 12 to 18 for the baselines.

## v0.0.5 frozen (before the third practitioner trap list exists)

Recorded 2026-11-07 04:06 UTC. Development scenarios: A to F.

```
ab3fa2974fcabcf91c9f48a9efa117a5448d249521f25ab2fd230061a65c1fb5  mergeguard/match.py
676914220d98b9f308e709eab83a382031914e95cf9e68d33456147595f801b8  mergeguard/cards.py
23e79ec92f624858b7a0d2fc0be4287db5ecf2bb9587ba8a17c90b44ea9eca52  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
```

Changes from v0.0.4: date columns whose medians differ by more than 180 days with a different distribution are
flagged temporal (renewed maturity, next vs last review); amounts with values outside the other side's discrete
schedule are flagged as netting (refunds, waivers). New metric: surfaced, any warning on a risky attribute.

Tried and removed: level-shift detection (same shape, scaled by an irregular factor). Between two banks' different
customer populations, real revaluations (AVM vs appraisal) cannot be told apart from population differences;
it raised false alarms on revenue and deposit principal.

Development results (not evidence): accuracy 100 / 100 / 100 / 96 / 100 / 100%, conflict recall 100 / 100 / 91 /
80 / 75 / 71%, zero harmful auto-accepts, zero false alarms.

## Scenarios G to K: third practitioner trap list (received after the v0.0.5 freeze)

Received 2026-11-06 22:17 America/Chicago: 50 traps in five domain groups, plus a migration checklist.
Stored verbatim in experiments/practitioner_inputs/.

```
46bcc27382b2b7e280bfa9ee601a99cd57b85db999002de15d5887a2629a1efc  experiments/practitioner_inputs/traps_round3.txt
eaa27be4527fe0adc7fd842662015749fe2a0e27f45c3a7b55866d996da6e791  experiments/practitioner_inputs/migration_checklist.txt
```

Provenance to confirm with the co-author: which traps come from personal migration experience and which were
drafted with assistance. The paper reports this split.

Scenarios G to K (generator and specs), generated with seeds 571 to 575 before the run:

```
04ef29b7eb774eceafc70e3e12d845ff41b991229290863eff11c74e4d9739ee  mergeguard/bench/spec.py
edb17c349fef5b02de763fc294f4e135da1608bf91820d196d2023d73e551854  mergeguard/bench/round3.py
```

## v0.0.5 results on scenarios G to K (single run)

| Scenario | MergeGuard accuracy | Conflict recall | Surfaced | Harmful auto-accepts | COMA accuracy | COMA harmful |
| --- | --- | --- | --- | --- | --- | --- |
| G payments, mortgage, regulatory | 96% | 18% | 3/11 | 3 | 96% | 11 |
| H wealth, trade finance, fraud, GL | 100% | 30% | 4/10 | 2 | 96% | 10 |
| I auto, student, lease, syndicated | 100% | 10% | 4/10 | 0 | 100% | 10 |
| J AML, ATM, digital | 94% | 20% | 5/10 | 1 | 100% | 10 |
| K capital markets, repo, RWA | 100% | 30% | 4/10 | 2 | 96% | 9 |

Totals: 11 of 51 labeled conflicts caught with the right type (22%), 20 of 51 risky attributes surfaced to review
(39%), 8 harmful auto-accepts against 50 for COMA and 59 for name-only matching. Zero false alarms.

By type: temporal 4/7, inclusion 4/13, null semantics 1/1, code set 1/2, population 1/9, methodology 0/7,
aggregation 0/6, identity 0/3, currency 0/1, role 0/1, sign 0/1.

Harmful auto-accepts: wire counterparty (role), escrow sign on a symmetric distribution, HMDA action date,
FIFO vs average cost basis, LC expiry, app device ID (a text identifier not recognized as an ID), point-in-time vs
through-the-cycle PD, repo cash vs collateral value.

Reading: this round's traps are mostly methodology, aggregation and lifecycle differences whose values look
alike in distribution. Population traps were rarely caught because these scenarios carry few executable target
rules, so the disagreement-rate check could not run.

## Provenance of practitioner inputs (confirmed 2026-11-06)

Trap lists for scenarios E to K and the SME sign-off workbook template come from the co-author's own experience
in large bank integrations, organized and drafted with an LLM (Gemini) on a personal account. They describe
industry-generic behaviour, not any employer's systems. Paper wording: "traps drawn from practitioner experience,
drafted with LLM assistance and curated by the practitioner co-author."

## v0.0.6 frozen

Recorded 2026-11-07 05:54 UTC. Development scenarios: A to K.

```
67d5266e97d8510072567a914018b7c5ca7f1263a7a97a7a267c36eacb9486f3  mergeguard/match.py
dbbc93ae4127e32f8101b5fe75734ef1437bfd3fde9500efd478731b973e018d  mergeguard/cards.py
23e79ec92f624858b7a0d2fc0be4287db5ecf2bb9587ba8a17c90b44ea9eca52  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
```

Changes from v0.0.5: text identifier columns (high uniqueness plus an ID-like name) are identifiers and never
auto-accepted; yes/no definitions where one side marks at least twice as many records (and 3 points more) are
flagged as population conflicts, including two-value status codes.

Development results on G to K (not evidence): conflict recall 27 / 30 / 20 / 30 / 30% (was 18 / 30 / 10 / 20 / 30%),
harmful auto-accepts 7 (was 8), zero false alarms on all eleven scenarios. A to F unchanged except lending recall
100 to 91%.

## v0.0.7 frozen: trial-load verification

Recorded 2026-11-07 06:20 UTC. Matcher unchanged from v0.0.6; adds verify.py.

```
67d5266e97d8510072567a914018b7c5ca7f1263a7a97a7a267c36eacb9486f3  mergeguard/match.py
dbbc93ae4127e32f8101b5fe75734ef1437bfd3fde9500efd478731b973e018d  mergeguard/cards.py
23e79ec92f624858b7a0d2fc0be4287db5ecf2bb9587ba8a17c90b44ea9eca52  mergeguard/evaluate.py
1671bb06d8e4bfd0456d3d3ff7967a8ec49d8508a262f90a719e01535ba31129  mergeguard/baselines.py
fce33b53f0209926d92b34d320ebc44c9fb95cb4c8f5d9529a45ac78e5930441  mergeguard/verify.py
```

MergeBench gains a trial-migration mode (spec scenarios): the acquired accounts are also run through the acquirer's
definitions, as in a parallel run, with 0.3% benign extract noise from a separate random stream (base data unchanged).
Target fields a real target system only stores, not recomputes, are marked "loaded" per scenario and receive the
naively mapped source value. The "loaded" lists were added to round3.py after scenarios G to K were scored; they do
not change any base data.

Development results on paired G to K (not evidence; the verifier was built on these scenarios):

| Scenario | Risky | Profiling | Trial load | Combined | Computed fields caught | Loaded fields caught | False FAIL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G | 11 | 3 | 7 | 8 | 6/6 | 2/5 | 0/13 |
| H | 10 | 4 | 8 | 8 | 8/8 | 0/2 | 0/15 |
| I | 10 | 5 | 6 | 6 | 5/6 | 1/4 | 0/9 |
| J | 10 | 6 | 8 | 9 | 9/9 | 0/1 | 0/8 |
| K | 10 | 4 | 7 | 8 | 7/7 | 1/3 | 0/13 |

Combined: 39 of 51 risky attributes surfaced (76%), against 22 for profiling alone. System-computed fields: 35 of 36.
Loaded-only fields: 4 of 15; these need SME review or documentation.

## Scenario L: fourth practitioner trap list (received after the v0.0.7 freeze)

15 traps, stored verbatim (same provenance as rounds 2 and 3).

```
c0793db18e9ef1f0934f2826ecd8dd29b94cdf08fb4dfc06b877f7ff540bfc78  experiments/practitioner_inputs/traps_round4.txt
```

Scenario L spec and generator, generated with seed 612 before the run:

```
226070d868f55ea3c5a6f5d9ce1cf6dda59dc86b2febb9d264a92134d930c2e5  mergeguard/bench/round4.py
1e4e351799b8d8fb631c1c054b33ae02396d6221e05a2a2d3329356c51e68f2c  mergeguard/bench/spec.py
```

## v0.0.7 results on scenario L (single run, profiling and trial load)

| Method | Target accuracy | Traps surfaced | Wrong mappings approved |
| --- | --- | --- | --- |
| name only | 76% | 0/15 | 18 |
| Valentine COMA | 100% | 0/15 | 15 |
| Valentine Cupid / Similarity Flooding / Jaccard | 22 / 16 / 54% | 0/15 | 4 / 34 / 15 |
| MergeGuard profiling only | 100% | 4/15 | 5 |
| MergeGuard profiling + trial load | 100% | 13/15 | 1 (credit score) |

Trial load: 13 of 15 traps FAIL, including all 10 on system-computed fields and 3 of 5 on loaded fields (overdraft
limit out of range, override addresses in an unseen format, autopay 0.00 out of range). Zero false FAILs on 22 clean
columns. Type labels match ground truth for 6 of 15.
Missed: L9 credit score (origination FICO vs refreshed VantageScore on a loaded field) and L6 prepayment penalty
flag (loaded). Four of the five profiling-stage wrong approvals (address, stop payment expiry, accrued interest,
safe deposit box status) are then blocked by the trial load.
Notable diagnoses: accrued interest "target = source x 1.014" (365/360), stop payment expiry "source later by
364 days (182 to 546)", check number "target always smaller" (a changed identifier read as a count; label wrong).

## v0.0.9 migrate step: development check (not pre-registered)

`mergeguard apply` (gate, rehearse, reconcile, emit SQL, audit) was built after all held-out runs. Scenarios G–L were
already development data, so this is a development result only. Protocol: generate each scenario (seed 21, 1500/1000),
fill the review workbook with the ground-truth target for every attribute, "Same" for every blank stress answer and a
sign-off name in all four columns (an analyst signing without reading), then apply with `--parallel`.
Result: computed-field traps FAIL 45/46 (miss: auto_loan.is_repossessed, 0.3% of records, reported as REVIEW);
loaded-only traps surfaced 7/20 (FAIL or REVIEW); clean columns FAIL 0/80. During development two false FAILs were fixed:
the orphan check treating a key name shared by two tables as a foreign key, and a 1-record mismatch in an 80-record
table (FAIL now also needs at least 3 records).

## v0.0.9 review baselines: post-hoc analysis (not pre-registered)

Run after external review comments, with `experiments/run_review_baselines.py` on scenarios E to L regenerated with
their original seeds (303, 404, 571 to 575, 612) at default size. All eight scenarios are development data for the
current matcher, so MergeGuard's own numbers here are optimistic (E, F and J improved since their held-out runs:
2, 1 and 1 wrong approvals then, 0 now). COMA has no tuning. Results in `experiments/results_v0.0.9_review_baselines`.

A. Abstention (203 columns). Wrong approvals / mappings auto-approved:
MergeGuard 12 / 55; COMA trusting every proposal 91 / 196; COMA with MergeGuard's send-identifiers-to-review rule
81 / 127; COMA with that rule, keeping only its top-scoring mappings at MergeGuard's coverage 24 / 55; COMA with that
rule plus MergeGuard's value detectors on its pairs 32 / 78. Largest coverage at which COMA is as safe as MergeGuard:
30 mappings against 55.
Reading: most of the headline gap (91 against 12) comes from approving fewer mappings. At equal coverage the gap is
2 to 1. 22% of what MergeGuard auto-approves is still wrong or hides a trap.

B. Plain record diff on trial-load output (G to L, columns mapped to the correct target). FAIL above 1% mismatch.
Recomputed-field traps (45): strict text diff 45, tolerant diff 44, MergeGuard verifier 44.
Stored-only traps (19): strict 0, tolerant 0, verifier 5 (conformance checks).
Clean exact columns (47): 0 false failures for all three.
Verifier diagnosis names the labeled trap type on 29 of its 49 failed trap columns.
Reading: on recomputed fields a plain diff detects as much as the verifier. Detection there comes from the trial-load
evidence, not from the verifier's logic. The verifier adds the diagnosis and the stored-field conformance checks.

## Scenario R: real public pair, Freddie Mac to Fannie Mae (frozen before the run)

First non-synthetic test. Source: Freddie Mac Single-Family Loan-Level Dataset, 2026 Q2 (origination and monthly
performance). Target: Fannie Mae Single-Family Loan Performance Data, 2026 Q2. 20,000 loans sampled per side by hash
of the loan identifier. The data cannot be redistributed; `experiments/real_pair/build_gse_pair.py` rebuilds the pair
from files a registered user downloads.

Scope: profiling stage only. The two files hold different loans, so there is no trial load and no stage three.
Neither side has derivation SQL, so the rule-rewriting check has nothing to run.

Ground truth: 47 source attributes, 24 with a stated difference, written by the builder from the two published
glossaries before any matcher ran on the pair. A conflict is labeled only where the glossaries state different
conventions (code list, placeholder for "not available", date format, counting start). Whether each stated difference
occurs in this quarter's rows was not checked. Limits: the builder wrote the labels and built the tool; column
names are the publishers' attribute names in snake case; descriptions are one-line paraphrases of the glossaries.

Frozen files (SHA-256), run once after this commit with MergeGuard, name-only and Valentine baselines:

```
e1307157eb8626052f008117d19dbb21bb2cc91fe182321cea6cf1028cbcb60e  experiments/real_pair/build_gse_pair.py
67d5266e97d8510072567a914018b7c5ca7f1263a7a97a7a267c36eacb9486f3  mergeguard/match.py
dbbc93ae4127e32f8101b5fe75734ef1437bfd3fde9500efd478731b973e018d  mergeguard/cards.py
23e79ec92f624858b7a0d2fc0be4287db5ecf2bb9587ba8a17c90b44ea9eca52  mergeguard/evaluate.py
```

## Scenario R results (single run, v0.0.9 matcher, hashes as frozen above)

| Method | Target accuracy | Type-correct recall | Surfaced | Wrong approvals / approved | False alarms |
| --- | --- | --- | --- | --- | --- |
| MergeGuard | 81% (38/47) | 24% | 8 of 24 | 4 / 10 | 1 of 14 |
| COMA | 85% | 0% | 0 of 24 | 28 / 40 | 0 of 14 |
| Name only | 72% | 0% | 0 of 24 | 24 / 36 | 0 of 14 |
| Cupid | 66% | 0% | 0 of 24 | 14 / 27 | 0 of 14 |
| Similarity Flooding | 72% | 0% | 0 of 24 | 34 / 47 | 0 of 14 |
| Jaccard distance | 49% | 0% | 0 of 24 | 25 / 31 | 0 of 14 |

Post-hoc, same pair: COMA with identifiers sent to review and limited to its 10 top-scoring mappings approved 5 wrong
(MergeGuard 4 of 10). COMA is as safe as MergeGuard at 6 approved mappings.

Reading. On real data MergeGuard is no more accurate than COMA and only slightly safer at equal coverage.
Caught with the right type: MSA and mortgage-insurance placeholders, special-eligibility placeholder, property
valuation codes, delinquency codes, loan age. Missed and auto-approved: loan purpose (code R means "refinance, not
specified" at Freddie Mac and "no cash-out refinance" at Fannie Mae), channel, property type, zero balance code.
Missed entirely: all four date-format differences (YYYYMM against MMYYYY) and the 9, 99, 999 placeholders on
low-cardinality fields. The monthly table was mapped badly: 6 of its 17 columns went to a wrong target (period to
borrower assistance plan, current UPB to total principal current). One clean column was flagged (current UPB).
These failures are development input for the next version; scenario R is now development data.

## v0.0.9 language-model baseline: post-hoc analysis (not pre-registered)

`experiments/run_llm_baseline.py`, model qwen2.5:7b through Ollama on GitHub-hosted runners (workflow
`.github/workflows/llm-baseline.yml`), temperature 0, scenarios E to L regenerated with their original seeds.
Two prompts per source column: pick a target from all target columns (name, type, description); then judge whether
the pair has the same business meaning given both full cards (name, type, description, six sample values,
derivation SQL). No retries or prompt changes after seeing results. Raw answers in
`experiments/results_v0.0.9_llm_baseline`. 203 columns, 91 trap columns, 110 clean columns, no request errors.

| | Language model (qwen2.5:7b) | MergeGuard profiling (current version, development data) |
| --- | --- | --- |
| Correct target | 174 of 203 (86%) | 201 of 203 (99%) |
| Trap columns flagged | 78 of 91 (86%) | 45 of 91 (49%) |
| Clean columns flagged | 67 of 103 proposed (65%) | 0 of 110 |
| Approved without review / wrong | 49 / 14 (judge says same meaning) | 55 / 12 |
| Same, identifiers to review | 37 / 13 | 55 / 12 |
| Every proposal trusted | 194 / 110 | n/a |

Reading: the model says "different" for 145 of its 194 proposals. It finds far more traps than profiling, and where
derivation SQL is present its stated reason is often the true one (365 against 360 day count, non-accrual threshold).
It also flags two thirds of clean columns, often for reasons that are not differences in meaning ("different
ranges", "sample values differ"), and the mappings it does pass are no safer than MergeGuard's. One small model,
one prompt; a larger model may do better. Descriptions and derivation SQL in MergeBench were written by the builder
and may state differences more plainly than real data dictionaries do.

## v0.0.9 second review round: five post-hoc analyses (not pre-registered)

All on development data (scenarios E to L regenerated with their seeds). None of these is a held-out result.

### Simple pipeline baseline (`experiments/run_simple_pipeline.py`, scenarios G to L, 146 columns, 66 traps, 80 clean)

Question: does a pipeline built from ordinary parts match MergeGuard once a trial load exists? The simple pipeline
is COMA for the mapping, a tolerant same-record diff on the trial-load output, and standard conformance checks
(domain, range, length).

| Pipeline | Correct target | Traps flagged | Clean flagged | Approved | Wrong approvals |
| --- | --- | --- | --- | --- | --- |
| MergeGuard (matcher + verifier) | 144 | 52 of 66 | 0 of 80 | 33 | 5 |
| COMA + tolerant diff + conformance | 143 | 56 of 66 | 0 of 80 | 34 | 6 |
| Same checks on MergeGuard's mapping | 144 | 55 of 66 | 0 of 80 | 35 | 6 |

Disclosure: the first run of the simple pipeline flagged 50 of 80 clean columns because range checks fired on
identifier columns. Identifiers were then exempted from conformance, as MergeGuard does. That change was made after
seeing results. Reading: with a trial load, the simple pipeline is as good as MergeGuard at finding traps on these
scenarios. MergeGuard's detection is not better than same-record comparison plus routine checks.

### Careless reviewer on the tool's own proposals (`experiments/run_careless_e2e.py`, G to L, seed 21)

The reviewer accepts every proposed target, copies the suggested transform, answers "Same" to every stress
question and signs all four columns. All 6 runs ended FAILED, so nothing would load. The gate blocked no rows.
92 columns were in the plans: 45 wrong (all traps; none had a wrong target), 47 clean. Of the 45 wrong, 31 got a
FAIL and 33 a FAIL or REVIEW; 12 passed every check. 0 of 47 clean columns failed. The 12 silent ones are mostly
stored-only (identity, role, methodology) plus SWAP.NTNL_AMT (aggregation) and REPO.REPO_AMT (inclusion).
Limit: the matcher maps these development scenarios almost perfectly, so a wrong-target approval is not exercised.

### Rule rewriting with wrong input mappings (`experiments/run_rule_rewrite_checks.py`)

One target rule, net_pay = gross_pay - tax, on a small payroll pair; input mappings fixed by hand.

| Case | Outcome |
| --- | --- |
| Inputs mapped correctly, clean column | 0% disagreement, not flagged (correct) |
| Wrong input column (year-to-date gross) | 100% disagreement, flagged: false alarm on a clean column |
| Input in cents | 100% disagreement, flagged: false alarm on a clean column |
| Input missing | reported as not runnable (correct) |
| Real trap (source net pay also deducts a fee), inputs correct | 96% disagreement, flagged (correct) |
| Real trap, gross mapped to a source column that already deducts the fee | 0% disagreement, not flagged: trap missed |

Reading: the check is only as good as the input mappings. A wrong input gives a false alarm or hides a real trap.
In cases 2 and 3 the wrong input pair was itself flagged by the detectors (unit), so a guard that marks the rule
result "unverified" when an input pair is flagged would have caught both; it would not have caught case 6.
An earlier run of this script was invalid (tables were not aligned first, so every pair carried a grain flag and
the rule was skipped); it was fixed before these numbers.

We then tried implementing that guard (`experiments/run_guard_check.py`, post-hoc, negative result): a rewritten
rule's output is marked unverified, and no flag is raised or cleared from it, whenever one of its own input
columns is independently flagged (other than `cast`). Checked against scenarios E to L rather than the controlled
pair, the guard would fire exactly once: on `ACCT.AVAIL_CR` in scenario E, whose rule is rewritten through
`ACCT.CUR_BAL`, itself flagged `inclusion`. That one case is a real trap MergeGuard currently catches correctly
(100% disagreement, `inclusion`, true positive) and the guard would silence it, with zero false alarms fixed in
exchange. The reason is a category error: a flagged input does not mean the mapping is wrong, only that the input
differs in meaning, which is common and often the correct, expected cause of the very disagreement being measured.
The controlled payroll cases that motivated the guard used genuinely wrong correspondences (a different column, a
unit mismatch); a correctly-mapped input that is itself a trap is a different situation the guard cannot
distinguish from a wrong one. The guard was not added to the matcher. The underlying problem — a rule estimate is
only as good as the input mappings it runs through, and the tool does not know when to doubt them — is unsolved.

### Wrong approvals against coverage (`experiments/run_coverage_curves.py`, E to L, identifiers excluded)

Proposals pooled across the eight scenarios and ranked by each method's own score. This pooled cut differs from the
earlier per-scenario "COMA top 55".

| Approved | COMA by score | MergeGuard by score only | MergeGuard, unflagged first |
| --- | --- | --- | --- |
| 10 | 2 | 0 | 0 |
| 20 | 7 | 2 | 2 |
| 30 | 14 | 6 | 6 |
| 40 | 18 | 8 | 8 |
| 55 | 24 | 14 | 12 |
| 78 | 39 | 31 | 31 |
| 100 | 57 | 53 | 53 |

Operating points: MergeGuard auto-accept 55 / 12; language model with identifier rule 37 / 13; COMA with
MergeGuard's detectors 78 / 32. Reading: MergeGuard's ranking is safer than COMA's at every coverage up to about 80,
mostly because of its score and not its flags. It is still wrong on 12 of 55 (22%).

### Run time and memory (`experiments/run_scaling.py`, 2 vCPU, 7 GB)

Rows (scenario L, 37 source and 37 target columns, 7 table pairs):

| Rows per source table | Profile | Match | Verify | Stage three | Total | Peak memory |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 0.3 s | 3.2 s | 0.2 s | 0.4 s | 4.1 s | 221 MB |
| 10,000 | 1.2 s | 5.5 s | 0.4 s | 1.4 s | 8.5 s | 249 MB |
| 100,000 | 2.7 s | 5.7 s | 1.8 s | 8.6 s | 18.8 s | 443 MB |
| 1,000,000 | 17.6 s | 5.0 s | 15.8 s | 86.2 s | 124.6 s | 2.4 GB |

Columns (same scenario with every table copied k times, 2,000 rows): 74 columns 15.9 s matching, 148 columns
67.2 s, 296 columns 262.8 s. Matching is quadratic in columns, about 3 ms per column pair, and does not grow with
rows because profiles are sampled. Assignment took under 10 ms in every run. Stage three was blocked by the gate on
the 148 and 296 column copies, so its time there is not reported. Scenario L's rules cannot be rewritten, so rule
execution was timed on the payroll pair: 0.01 s, 0.02 s and 0.12 s at 10 thousand, 100 thousand and 1 million rows.
Tables are loaded into pandas for profiling, so memory grows with rows; nothing here was run beyond 1 million rows.

Code change made during this analysis: the value signal called SciPy's two-sample Kolmogorov-Smirnov test with its
default exact p-value, which the matcher never used. It now asks for the statistic only (`method="asymp"`).
Matcher output on scenarios E, G and L is identical before and after; matching time on scenario L fell from about
50 s to about 4 s. Timings above are after this change.

## Scenario M: an independent practitioner's trap list (held-out, single run)

A practitioner with experience across core banking, deposit, card, lending and mortgage servicing
migrations, independent of this tool and its author, was given only the bare definition of a semantic
trap (no taxonomy, no examples from this paper or MergeBench) and asked to write up examples from their
own experience. Their name is withheld at their request. Their write-up, frozen at
`experiments/trap_author/` with its SHA-256, is dated 2026-11-19 and states the examples were written
from memory, not looked up. It gives twelve traps across five domains (`open_dt`/`acct_open_date`,
`curr_bal`/`current_balance`, `days_past_due`/`dpd`, `cust_stat_cd`/`customer_status`,
`last_trans_dt`/`last_activity_date`, `cr_limit_amt`/`credit_limit`, `int_rate`/`interest_rate`,
`chg_off_amt`/`chargeoff_balance`, `branch_id`/`branch_code`, `last_pmt_amt`/`last_payment_amount`,
`txn_timestamp`/`trans_dt_tm`, `dob`/`birth_date`).

Before writing any code, the matcher, card and evaluator source were hashed (commit `60ff0aa`,
match.py `9a1fc34a...`, cards.py `dbbc93ae...`, evaluate.py `23e79ec9...`) and the scenario's ground
truth was hashed immediately after generation (`c1e2eecc...`), before running MergeGuard or any baseline. `mergeguard/bench/round5.py` (SPEC_M) encodes each of the twelve traps as literally as the
write-up allows, 22 clean columns alongside them, across six table pairs (customer, deposit, card, loan,
mortgage, wire). No target field has derivation SQL (the write-up describes stored behaviour, not a
target-side recomputation), so like scenario R this tests stage one only. Single run, seed 713.

| Method | Target accuracy | Traps surfaced | Auto-accepted | Harmful auto-accepts |
| --- | --- | --- | --- | --- |
| MergeGuard | 100% (34/34) | 3 of 12 | 14 | 5 |
| COMA, every proposal trusted | 100% (34/34) | 0 of 12 | 34 | 12 |
| Name only | 71% | 0 of 12 | 32 | 18 |

Every source column mapped to its correct target, including all twelve traps, so this round does not
test target-mapping accuracy under difficulty; it tests whether profiling notices something is wrong
once the mapping is already right. MergeGuard caught 3 of 12: the null-placeholder DOB trap, and the two
cases where the gap shows up as a shift in a numeric or date distribution (the days-past-due grace
period, the activity-date lag). It missed the other 9, and the misses fall into two groups.

First, a detection gap: all three inclusion traps (available balance netting holds, gross vs
principal-only charge-off, PITI vs principal-and-interest) went undetected. The inclusion detector relies
partly on derivation SQL (a `fee:` tag on the derived column's logic) that this profiling-only scenario
does not have; without it, inclusion falls back to a distributional check that these three pairs were not
different enough to trip. The code-set trap (`cust_stat_cd`/`customer_status`) was also missed for a
structural reason: both sides use the same three-letter code domain, so the crosswalk detector, which
looks for a value-set mismatch, sees full overlap and never looks at whether the two sides use those
codes in different proportions, which is exactly how this trap hides.

Second, a taxonomy gap stated plainly in the paper's taxonomy table and discussion section but worth confirming in practice:
`identity` and `methodology` traps (the origination-vs-servicing branch, the nominal-vs-APY rate, the
zeroed-vs-retained credit limit) are taxonomy types with no corresponding detector in the matcher at all;
MergeGuard cannot flag them no matter how the data looks. All three were auto-accepted.

Reading: on this practitioner's traps, auto-approved-and-wrong fell from 12 for trust-everything COMA to
5 for MergeGuard, which is in the same range as the factor of about two seen on E to L (§7.5), not the
much larger gap seen on the frozen scenarios the tool's own author wrote. An outside practitioner's traps
are harder for MergeGuard than its own author's, which is the honest and expected direction for this
check to come out.

## Reviewer study: does the diagnosis note change what a human approves

Everything above tests MergeGuard's own flagging. This round instead tests the thing the paper's
"what MergeGuard is for" discussion claims matters: whether handing a reviewer MergeGuard's diagnosis,
alongside a plain mapping they would otherwise sign off on unaided, changes what they approve.

Twenty-four source-to-target column pairs were pulled from a real MergeGuard run on scenario L
(synthetic banks "Lakeside Federal" acquired by "Oak Hollow Bank"). Twelve were picked as the obvious
traps MergeGuard flags with a diagnosis, and twelve were picked by eye as the clean, correctly-mapped
pairs. Checking against ground truth after the fact, two of those twelve "clean" picks turned out to be
real traps (`CUST.CR_SCORE`, a methodology conflict, and `LN_MSTR.PPMT_PNLTY_IND`, a population conflict):
MergeGuard's checks never flag either, with or without a note, because methodology and population are
among the taxonomy types with no detector behind them. So the true composition is fourteen traps and ten
clean pairs, not twelve and twelve; the two undercounted traps carry no note either way, since MergeGuard
never generated one for them. Each pair was placed in a spreadsheet with its two column names, their
stated definitions, and a decision field (Approve / Reject / Need more info) with a confidence rating.
Six of the fourteen traps (the six MergeGuard flags most confidently) showed a one-line system note, its
actual diagnosis text; the other eight traps and all ten clean pairs showed no note. Two forms
counterbalanced which six traps got the note (Form 1: note on set Y; Form 2: note on set X) so across the
two forms every noted trap item is judged once with a note and once without. Reviewers were told nothing
about the tool, the taxonomy, or what the notes meant; they judged each row as they would in a real
sign-off, were told not to look anything up, and gave an optional one-line, fully anonymous background
and total time. No names, emails, or employers were collected.

The sheet was sent to four reviewers (two per form) and all four returned it; this is every response
received, not a subset. Single pass, no second round.

| Respondent | Form | Background | Time | With note: caught | Harmful w/ note | Without note: caught | Harmful w/o note | False alarms on clean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | 1 | lead data engineer, 10 yrs, banking and credit systems | 24 min | 6/6 | 0 | 7/8 | 1 | 0/10 |
| P2 | 1 | data analyst, 7 yrs, deposit + lending ops | 23 min | 6/6 | 0 | 7/8 | 1 | 0/10 |
| P3 | 2 | (not given) | (not given) | 6/6 | 0 | 7/8 | 1 | 5/10 |
| P4 | 2 | systems analyst, 4 yrs, core banking migrations | 28 min | 5/6 | 1 | 7/8 | 1 | 0/10 |
| Pooled | | | | 23/24 | 1 | 28/32 | 4 | 5/40 |

With a note shown, 23 of 24 trap-judgments across all four reviewers caught the trap, versus 28 of 32
without one, a difference that held in the same direction for every reviewer individually (each caught
every trap they saw with a note except P4's one miss) rather than only in the pooled total. The one
miss-with-note (`SDB.BOX_STAT`, P4) carried a note stating a crosswalk had been found consistent across
the two sides' status codes; read as reassurance rather than a flag, it may have pointed the reviewer the
wrong way, which is itself worth knowing: a note that states a fact rather than a verdict can backfire.

One item recurred: `CHK_ITEM.CHK_NBR`, an `identity` trap, was approved outright with no note by two of
the four reviewers (P3 and P4), the only trap missed by more than one person. `identity` is one of the
four taxonomy types (identity, methodology, aggregation, role) with no corresponding automated detector
in the matcher, so this is the same taxonomy gap confirmed at the tool level in scenarios E-L and M
showing up at the human level too: exactly where MergeGuard cannot help, reviewers also tend to miss it.

False alarms on clean pairs were not evenly spread: P3 marked five of the ten clean, no-note pairs "Need
more info," far more cautious than the other three, who raised none. This looks like a reviewer-specific
hedging style rather than anything about the items, since the same ten clean pairs drew zero
hesitation from P1, P2, and P4.

n = 4 is far too small for a statistical claim, and this was not designed to produce one; no significance
test is reported. What it supports is a direction, consistent across every reviewer who saw a note and
missed nothing else material: the diagnosis changed what got approved, not just what got flagged.
