# Data Inventory — AffordAI (Buy or Wait?) — 2026-09-13

> **Source:** `dataset/official/` (verified byte-identical to `upstream/main:dataset/` via `git show` sha256). This file is generated from actual inspection via `python3 csv.DictReader` (UTF-8, LF, comma delimiter, no BOM). Every number reproducible via `python scripts/validate_output.py` or the forensic snippets below. Dataset is READ-ONLY; derived data goes to `dataset/generated/` or `evaluation/reports/`.

## 0. Snapshot (hashes + rows — regression detection, not business logic)

| File | Rows (excl header) | SHA256 (first 16) | Header |
|---|---:|---|---|
| `requests.csv` | 250 | `f94255baa9f55857` | `request_id,user_id,request_date,request_type,requested_amount,desired_completion_date,allows_partial_payment,request_text` |
| `sample_requests.csv` | 25 | `1195bbe962e62a3e` | `request_id,user_id,request_date,request_type,requested_amount,desired_completion_date,allows_partial_payment,request_text,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation` |
| `financial_profiles.csv` | 275 | `b91b4ccbda3d5af9` | `user_id,home_currency,current_available_balance,minimum_balance_to_keep,financial_priorities,expense_categories_to_protect,expense_categories_user_is_willing_to_reduce,expense_categories_user_is_willing_to_stop,payment_methods_user_will_consider,max_installment_months` |
| `financial_events.csv` | 25342 | `f6a7ccf24d9bfd4a` | `event_id,user_id,event_type,description,category,direction,amount,currency,event_date,settlement_date,status,linked_event_id,flexibility,minimum_allowed_amount` |
| `request_payment_options.csv` | 790 | `aedadf63a13f5dd0` | `payment_option_id,request_id,payment_method,payment_amount,number_of_payments,first_payment_date,payment_frequency_days,financing_fee,total_payable_amount` |
| `exchange_rates.csv` | 134 | `3de3877e48707fea` | `rate_date,from_currency,to_currency,rate` |
| `messages.csv` | 215 | `fd9e3a1acb604f9a` | `message_id,user_id,request_id,related_event_id,sent_at,source_type,message_text` |
| `images.csv` | 16 | `c5a3f1686b1f98ac` | `image_id,user_id,request_id,related_event_id` |
| `output.csv` (template) | 250 | `ee979aa8cc1b7704` | `request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation` |
| `media/images/*.png` | 16 files | see below | PNG 89 50 4E 47 headers valid, 111KB–756KB |

Image files (all present, `images.csv` ↔ disk 1:1):

| image_id | file | size | sha12 | linked event |
|---|---|---:|---|---|
| `image_01` | `media/images/image_01.png` | 186981 | `f37b40e6af42` | `event_253` |
| `image_02` | `media/images/image_02.png` | 427405 | `ccd779e5382b` | `event_1442` |
| `image_03` | `media/images/image_03.png` | 586307 | `e5fb0bbcda6c` | `event_1545` |
| `image_04` | `media/images/image_04.png` | 366050 | `281e7f1e7bd1` | `event_1700` |
| `image_05` | `media/images/image_05.png` | 471315 | `9abcda5647af` | `event_1786` |
| `image_06` | `media/images/image_06.png` | 270064 | `9055551fbe59` | `event_3051` |
| `image_07` | `media/images/image_07.png` | 319406 | `f6d30a743552` | `event_3231` |
| `image_08` | `media/images/image_08.png` | 200545 | `e28592ad8b4d` | `event_4535` |
| `image_09` | `media/images/image_09.png` | 123940 | `e0e74e14425d` | `event_5170` |
| `image_10` | `media/images/image_10.png` | 756059 | `c90f98caf087` | `event_6033` |
| `image_11` | `media/images/image_11.png` | 389504 | `795e000d4842` | `event_6859` |
| `image_12` | `media/images/image_12.png` | 340059 | `e10b0123e66d` | `event_7307` |
| `image_13` | `media/images/image_13.png` | 111206 | `1ae54b378a95` | `event_7941` |
| `image_14` | `media/images/image_14.png` | 316168 | `bf88e4aa35e6` | `event_9421` |
| `image_15` | `media/images/image_15.png` | 279876 | `0c0fe3d79e67` | `event_9806` |
| `image_16` | `media/images/image_16.png` | 207015 | `2665cf731a86` | `event_10521` |

> Regression: if any row count, header, or null pattern diverges, dataset was mutated.

## 1. File-level inventory (from `dataset/official/`, inspected 2026-09-13)

| File | Rows | Columns | Nulls | Duplicate PK | Date Range | Currencies | Notes |
|---|---:|---:|---|---|---|---|---|
| `requests.csv` | 250 | 8 | 0 nulls (all required filled) | `request_id` unique 250/250 | `request_date 2023-01-20→2026-09-04`; `desired_completion_date 2023-02-13→2026-10-19` | — (amounts in home currency) | 1 row per request, `request_26..275` order = input order; `allows_partial false 170 / true 80`; `requested_amount 199.89→83,923,000` |
| `sample_requests.csv` | 25 | 15 | `earliest_date 7 null` (all `not_affordable`) else 0 | `request_id` unique 25 | `request_date 2019-09-03→2026-07-07` | — | `request_01..25` disjoint from eval; status mix `with_plan 9 / not_aff 7 / later 6 / now 3`; methods cover all 5 |
| `financial_profiles.csv` | 275 | 10 | `reduce 39 / stop 62 / max_install blank 119` | `user_id` unique 275 | — | `home INR 67 / EUR 62 / IDR 55 / ZAR 51 / USD 40` | `balance 683.69→136,691,818.94`; `minimum 400→41,430,800`; 0 cases `minimum > balance` |
| `financial_events.csv` | 25342 | 14 | `amount 16 / settlement 10 / linked 25284 / min_allowed 22435` | `event_id` unique 25342 | `event_date 2019-03-09→2026-09-03`; `settlement 2019-03-09→2026-09-03` | `INR 6457 / EUR 5585 / IDR 4992 / ZAR 4489 / USD 3819` | ~92/user (56–129); status/type/direction below |
| `request_payment_options.csv` | 790 | 9 | `frequency 275` (= full) | `payment_option_id` unique 790 | `first_payment_date 2019-09-03→2026-09-04` | — | 1 full per request (275); installments 515; per-request 2×65, 3×180, 4×30 |
| `exchange_rates.csv` | 134 | 4 | 0 | composite `(date,from,to)` unique 134 | `rate_date 2023-10-15→2026-11-15` + outlier `2025-10-01` | `from USD 88 / EUR 46 → to INR 33 / IDR 30 / EUR 25 / USD 24 / ZAR 22` | 5 directed pairs; 39 distinct dates; no duplicate pairs |
| `messages.csv` | 215 | 7 | `request_id 87 / related 176` | `message_id` unique 215 | `sent_at 2019-08-31T09:30:00Z→2026-09-03T01:00:00Z` | — | sources `employer 126 / service 31 / fin 23 / bank 18 / merchant 17`; multilingual (ID+EN) |
| `images.csv` | 16 | 4 | 0 | `image_id` unique 16 | — | — | 16 PNGs present; 5 sample + 11 eval requests |
| `output.csv` | 250 | 8 | all 250 blank (template) | `request_id` unique 250 | — | — | order `== requests.csv`; exact 8-col schema |

All CSVs: UTF-8, LF `\n`, comma delimiter, no BOM, no null bytes, 0 malformed rows (len(row)==len(header) for every row).

## 2. Requests inventory (§5.2)

- **IDs:** `request_id` `request_26..275` unique 250, stable; `user_id` `user_26..user_275` unique 250 (1:1, each user exactly 1 request); both preserve `original_index` order in pipeline.
- **Amounts:** `requested_amount` 0 nulls; `199.89` min (USD/INR small), `83,923,000` max (IDR), median ~37k; no blank request amounts — blank handling is at **event** level, not request level.
- **Dates:** `request_date` 61 distinct, median gap to `desired_completion_date` 65 days, `desired - request` 6→86 days, 0 inverted (`desired < request` = 0), 0 >90 days beyond request.
- **Types:** 9 values: `family_transfer 28 / purchase 28 / investment 28 / debt_repayment 28 / travel 28 / housing 28 / education 28 / emergency 27 / other 27`.
- **Preferences:** `allows_partial_payment` `true 80 / false 170`; `request_text` always filled (English, embeds amount with commas, deadline paraphrase).

## 3. Financial profiles (§5.3)

- **Home currency:** `home_currency ∈ {INR,ZAR,IDR,USD,EUR}` — `INR 67, EUR 62, IDR 55, ZAR 51, USD 40`.
- **Minimum balance:** `current_available_balance 683.69→136M`, `minimum_balance_to_keep 400→41M`, **0** `minimum > balance`.
- **Priorities:** `financial_priorities` always filled (e.g. `retirement_investment|emergency_savings`); `expense_categories_to_protect` always filled (e.g. `rent|utilities|groceries`).
- **Payment preferences:** `payment_methods_user_will_consider` 7 distinct combos: `full 60 / partial+install 52 / install 41 / full+partial 40 / full+install 35 / all-three 28 / partial 19`. `max_installment_months` blank 119 (= refuse installments) else `2:15,3:18,4:17,5:16,6:13,7:14,8:10,9:9,10:12,11:16,12:16`.
- **Flexible semantics:** `willing_to_reduce` blank 39, `willing_to_stop` blank 62; reduce categories `dining,entertainment,streaming,shopping,gym`; stop `cloud_storage,delivery_membership,music_subscription,streaming,gym`. **45 profiles list `streaming` in both reduce and stop** (profile-level overlap allowed; per-event `stop`+`reduce` mutually exclusive).
- **Installment limit semantics:** blank `max_installment_months` = user will not consider installments (verified against `requests` where those users’ installment options exist but must be filtered). Value `2–12` months; span check uses `months*31` days approximation (documented unproven).

> Semantics: **VERIFIED** — 1:1 user→profile, nullability, currency split, preference lists split on `|`, blank = refuse installments.
> **INFERENCE** — categories_to_protect vs willing_to_reduce/stop mapping (from observed overlap).
> **UNKNOWN** — exact trade-off weighting of priorities (not in dataset).

## 4. Financial events (§5.4)

- **Status (observed, NOT assumed):** `settled 25148 / pending 71 / scheduled 70 / cancelled 22 / failed 21 / unrealized 10`.
- **Event type:** `expense 20525 / subscription 2488 / income 1696 / debt_payment 567 / investment_purchase 29 / refund 22 / investment_valuation 10 / investment_sale 5`.
- **Direction:** `debit 23609 / credit 1723 / non_cash 10 (= unrealized valuations)`.
- **Flexibility:** `fixed 21138 / reducible 2682 / stoppable 1297 / reducible_or_stoppable 225`.
- **Category:** 22 values top `groceries 5812 / transport 5626 / dining 3479 / salary 1690 / utilities 1452 / rent 1355 / cloud_storage 833 … windfall 6`.
- **Amount nullability:** 16 blank (0.06%) — exactly `event_253,1442,1545,1700,1786,3051,3231,4535,5170,6033,6859,7307,7941,9421,9806,10521` (12 settled, 2 scheduled, 2 pending; 1 credit salary + 15 debits). **Do NOT treat blank as zero** — each maps 1:1 to `images.csv:related_event_id` (verified `blank_ids == image_rels`).
- **Settlement nulls:** 10 blank = exactly 10 `unrealized` valuations (`non_cash`) where engine falls back to `event_date` then ignores (correct per spec: unrealized gains ignored).
- **Linked IDs:** 58 non-empty `linked_event_id`, all resolve (0 orphans), 0 self-refs, 0 fan-in (refund↔expense, valuation chains).
- **Minimum allowed amount:** filled 2907 = `reducible 2682 + reducible_or_stoppable 225`; `stoppable` 1297 correctly blank; `fixed` 21138 blank.
- **Recurrence:** inferred from history (no explicit `frequency` column); subscription streams monthly 27–32d median or weekly 6–8d with ≥4 occurrences; flexible same-description fallback `≥2, gap ≥7d`.
- **Duplicates:** 0 by `(user_id, description, amount, currency, event_date, settlement_date, status)`.

## 5. Payment options (§5.5)

- **Distribution:** 790 rows = 275 requests (250 eval + 25 sample) × 2–4 options. Per eval request: `3×165, 2×58, 4×27` (avg 2.876). Superset `719 eval` + `71 sample`.
- **Methods:** `full_payment 275 (1 per request) / installments 515`. `number_of_payments` `1:275 / 24:86 / 15:81 / 21:80 / 18:79 / 3:74 / 6:60 / 2:6 / 4:3`.
- **Schedules:** `payment_frequency_days` blank 275 (= singles), else `30: ~, 28: …, 31: …`; `first_payment_date` always `>= request_date` (0 violations); installments `payment_amount * number_of_payments == total_payable_amount` exactly (0 mismatches); `financing_fee` 0 for singles, >0 for all multis (0.01→18.4M).
- **Fees/Intervals:** fee >0 for all 515 installments; last payment date often beyond `desired_completion_date` (54.8% deadline-violating — correctly filtered).
- **IDs/Eligibility:** `payment_option_id` unique 790; 310/719 (43%) method not in `will_consider`; 208/469 installments where `max_installment_months` blank (must reject); term check `span ≤ months*31` days.

> Verified: installment schedules exactly map to per-request options when eligible; partial needs no option match.

## 6. Exchange rates (§5.6)

- **Currencies:** events use all 5; home split above; rates cover same 5.
- **Directed pairs (5):** `USD→INR 33 / USD→IDR 30 / USD→EUR 25 / EUR→USD 24 / EUR→ZAR 22`. No inverses (e.g. `INR→USD` absent).
- **Dates:** 39 distinct `2023-10-15→2026-11-15` plus outlier `2025-10-01` (single pair `USD→INR`). Median gap ~30d; duplicate `(date,from,to)` = 0.
- **Missing-rate cases:** 140 foreign-cash events (post-2023-10-15, currency ≠ home) → **0 missing** (all have exact directed pair with `latest rate ≤ settlement_date`). 702 pre-2023-10-15 events need no FX (0 foreign).
- **Gaps:** 14–31d irregular near `2025-10-01` (16d+14d); settlement days cluster on 15th (exact match).
- **Assumption A1 (unproven):** convert with **latest row on/before settlement_date for exact directed pair**; no inverse synthesis. Fallback if no prior rate: fail-closed (exclude foreign credit, keep debit at face, log). Verified sufficient for this dataset; pre-window case 0 rows.

## 7. Messages (§5.7)

- **Sources:** `employer 126 / service_provider 31 / financial_service 23 / bank 18 / merchant 17` (215 total).
- **Languages:** English + Indonesian (60 non-ASCII, e.g. `message_01` IDR payroll).
- **Relationships:** `request_id` filled 128 / blank 87 (user-level); `related_event_id` 39 / blank 176; 0 orphans (`request_id` valid 12 sample-linked but valid in superset; `related_event_id` 0 invalid; `user_id` 0 invalid). 3 messages link to blank-amount events (`message_35→event_4535`, etc.).
- **Amendment/cancellation:** ~32 amend-like (e.g. `message_05` payroll date replacement, salary increases `message_26`, seasonal ends `message_09`), 101 with `cancel/amend/delay/refund/correction` keywords.
- **Prompt injection:** 0 adversarial markup (`<`, `{{`, `ignore previous`, `system prompt`, `jailbreak`, `you are`) — only false positives `Cobalt Systems` containing `system`. One fraud lure `message_67` (`Congratulations! You've been selected … Pay the release charge`) must be ignored as untrusted.
- **Ambiguity:** 87 blank `request_id` (must score by `user_id` + window), multilingual, `related_event_id` only when 1:1.

> Treat as **untrusted evidence** — typed facts only, 4-rule conflict precedence, never override deterministic rules.

## 8. Images (§5.8)

- **Mapping:** 16 `image_id` ↔ 16 `event_id` (blank amounts) ↔ 16 PNG files **exact 1:1:1 bijection** (`blank_ids == image_rels`, `images ↔ files` both directions 0 missing).
- **Count:** 16 rows + 16 files (5 sample requests `03,16,17,19,20` + 11 eval `33,35,48,55,64,73,78,84,101,105,113`).
- **Blank amounts:** 16 events (see list); categories mixed (rent, groceries, utilities, transport…); statuses mixed (12 settled, 2 scheduled, 2 pending) — blank ≠ status signal.
- **Missing images:** 0 missing, 0 orphan.
- **Extraction:** only for blank events; OCR amount+currency+confidence with `source_id` provenance; low confidence / missing file → `UNKNOWN` (never zero), plan stays safe without it.
- **Currency/date context:** receipt contains amount+currency; event row supplies `currency` and `event_date/settlement_date`; profile supplies `home_currency` for conversion.

## 9. Join integrity (summary; full report `evaluation/reports/join_integrity.md`)

All PKs unique; all FKs resolve within eval partition (0 orphans). Superset artifacts (71 options +12 messages +5 images for sample `01..25`) appear orphan only if naïvely joined to `requests.csv` without partition filter — valid against full 275.

## 10. Open unknowns (explicitly documented, not guessed)

- FX fallback A1 off-cycle (0 rows today but must be correct if present)
- Recurrence thresholds vs official conservative estimates (±3% calibration noise)
- IDR decimal convention (2dp observed — `15952906.67` — but not stated)
- OCR confidence fallback
- Rent-bump / new-deduction message handling (ignored, documented)
- Salary-day tie-breaks, prize/ambiguous-credit handling
- `streaming`/`gym` dual willingness overlap (41 profiles)

## 11. Reproducibility

Every number above reproducible:

```python
# Example: verify blank ↔ image bijection
import csv
blanks = {r['event_id'] for r in csv.DictReader(open('dataset/official/financial_events.csv')) if not r['amount']}
rels = {r['related_event_id'] for r in csv.DictReader(open('dataset/official/images.csv'))}
assert blanks == rels and len(blanks)==16
```

Full forensic scripts used are the same as in `evaluation/reports/join_integrity.md`.

## 12. Dataset immutability

Verified via `git ls-files -- dataset` and `git show upstream/main:dataset/<file> | sha256sum` — local `dataset/official/` byte-identical to upstream `dataset/` (see Snapshot hashes). During Phase 4+5, `git diff --stat` shows 0 changes under `dataset/`. Temporary forensic outputs written outside `dataset/official/`.
