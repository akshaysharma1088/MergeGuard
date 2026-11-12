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
