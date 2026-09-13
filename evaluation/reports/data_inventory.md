# Data Inventory (from `dataset/official/`, inspected 2026-09-13)

## Volumes

- `requests.csv`: 250 eval rows. `sample_requests.csv`: 25 solved examples.
- `financial_profiles.csv`: 275 users (250 eval + 25 sample-only `user_01..user_25`).
- `financial_events.csv`: 25,342 rows (~92/user).
- `request_payment_options.csv`: 790 rows → per request: 3 opts ×180, 2×65, 4×30 (275 = 250+25).
- `exchange_rates.csv`: 134 rows. `messages.csv`: 215. `images.csv`: 16 (+16 PNGs).

## Enumerations (observed, NOT assumed)

- `status`: settled 25148 / pending 71 / scheduled 70 / cancelled 22 / failed 21 / unrealized 10.
- `event_type`: expense 20525 / subscription 2488 / income 1696 / debt_payment 567 /
  investment_purchase 29 / refund 22 / investment_valuation 10 / investment_sale 5.
- `direction`: debit 23609 / credit 1723 / non_cash 10 (= unrealized valuations).
- `flexibility`: fixed 21138 / reducible 2682 / stoppable 1297 / reducible_or_stoppable 225.
- `request_type`: 8×28 + emergency 27 + other 27. `allows_partial_payment`: true 80 / false 170.
- Profile methods: full 60 / partial+install 52 / install-only 41 / full+partial 40 /
  full+install 35 / all-three 28 / partial-only 19. `max_installment_months` blank 119 (=refuse
  installments); values 2–12 otherwise.
- Payment options: installments 515 / full_payment 275 (= frequency-blank count; 1 full/req).
- Message sources: employer 126 / service_provider 31 / financial_service 23 / bank 18 / merchant 17;
  87 user-level (blank `request_id`), 39 with `related_event_id`.
- Sample outputs: with_plan 9 / not_affordable 7 / later 6 / now 3; methods cover all 5
  (partial only 1×); spending changes only 3/25 (`stop`, `reduce_to`, one combined).

## Key resolutions

1. **Blank amounts (16) ↔ images (16): exact 1:1.** Statuses vary (settled/scheduled/pending) —
   do NOT infer cash treatment from blankness; resolve image then apply status rules.
2. **`minimum_allowed_amount` filled 2907× = reducible (2682) + reducible_or_stoppable (225).**
   Stoppable-only events have no reduce target (stop only). Fixed events: no changes ever.
3. **`linked_event_id` (58×):** refund↔expense and valuation chains; link alone ≠ verdict —
   apply status rules per row (e.g. pending refund not counted until settled).
4. **FX: only 5 directed pairs** (`USD→IDR/INR/EUR`, `EUR→ZAR/USD`); foreign cash events = 139,
   pairs match exactly (no missing-pair case). Settlement days cluster on the 15th (= rate dates).
   **Assumption A1:** convert with the latest rate row on/before `settlement_date` for the exact
   directed pair (exact match when settlement falls on the 15th). No inverse-rate synthesis.
5. **Request dates** span 2023-01-20 → 2026-09-04; rate months cover 2023-10-15 → 2026-11-15
   (+2025-10-01 extra row). Pre-2023-10 settlements: check per-request; if no prior rate exists,
   fail closed (exclude foreign credit, keep foreign debit at face paranoia) and log.
6. **Currencies:** events in all 5; home split INR 67 / EUR 62 / IDR 55 / ZAR 51 / USD 40.

## Open (for Milestone 2 engine)

- Recurrence detection cadence per category (needs per-user history analysis).
- Pre-rate-window foreign events (count + handling confirmation).
- Image OCR values (16 PNGs — read during E2).
